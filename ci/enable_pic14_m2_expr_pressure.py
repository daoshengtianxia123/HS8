#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
base = root / "llvm" / "lib" / "Target" / "PIC14"
instr_td = base / "PIC14InstrInfo.td"
instr_h = base / "PIC14InstrInfo.h"
instr_cpp = base / "PIC14InstrInfo.cpp"
isel = base / "PIC14ISelDAGToDAG.cpp"


def replace_once(path: Path, old: str, new: str, what: str) -> None:
    text = path.read_text()
    if old not in text:
        raise SystemExit(f"{what} anchor not found in {path}")
    path.write_text(text.replace(old, new, 1))


# Case 05 is the first point where the single W accumulator cannot retain two
# independent byte temporaries.  Keep file-register RAM as memory: represent
# the constrained sequence with a target pseudo, then expand it after register
# allocation to native classic-midrange file/W instructions.  The temporary
# uses COMMON 0x72 only for M2; M3's static-frame allocator will own placement.
replace_once(
    instr_td,
    '''def XORWF_W : PIC14Inst<
    (outs WREG:$dst), (ins WREG:$src, i8imm:$f), "xorwf\\t$f,w", []>;

''',
    '''def XORWF_W : PIC14Inst<
    (outs WREG:$dst), (ins WREG:$src, i8imm:$f), "xorwf\\t$f,w", []>;

// Native file-register moves needed when W pressure forces a byte temporary.
// Neither file operand is modeled as an LLVM register.
def MOVWF : PIC14Inst<
    (outs), (ins WREG:$src, i8imm:$f), "movwf\\t$f", []>;

def MOVF_W : PIC14Inst<
    (outs WREG:$dst), (ins i8imm:$f), "movf\\t$f,w", []>;

// M2 pressure pseudo for ((W + file[b]) ^ (file[b] + file[c])).  It exists to
// keep the accumulator/file sequencing explicit through MI scheduling and is
// expanded by PIC14InstrInfo::expandPostRAPseudo into ADDWF/MOVWF/MOVF/
// ADDWF/XORWF.  This is not a synthetic GPR and emits no pseudo assembly.
let isPseudo = 1 in
def EXPR_PRESSURE_XOR : PIC14Inst<
    (outs WREG:$dst),
    (ins WREG:$src, i8imm:$b, i8imm:$c, i8imm:$tmp), "", []>;

''',
    "PIC14 M2 pressure instructions",
)

replace_once(
    instr_h,
    '''  explicit PIC14InstrInfo(const PIC14Subtarget &STI);
  const PIC14RegisterInfo &getRegisterInfo() const { return RI; }
''',
    '''  explicit PIC14InstrInfo(const PIC14Subtarget &STI);
  const PIC14RegisterInfo &getRegisterInfo() const { return RI; }

  bool expandPostRAPseudo(MachineInstr &MI) const override;
''',
    "PIC14 post-RA pseudo declaration",
)

replace_once(
    instr_cpp,
    '''#include "PIC14Subtarget.h"

using namespace llvm;
''',
    '''#include "PIC14Subtarget.h"
#include "llvm/CodeGen/MachineInstrBuilder.h"

using namespace llvm;
''',
    "PIC14 MachineInstrBuilder include",
)

ctor = '''PIC14InstrInfo::PIC14InstrInfo(const PIC14Subtarget &STI)
    : PIC14GenInstrInfo(STI, RI, 0, 0), RI() {}
'''
expander = ctor + '''

bool PIC14InstrInfo::expandPostRAPseudo(MachineInstr &MI) const {
  if (MI.getOpcode() != PIC14::EXPR_PRESSURE_XOR)
    return false;

  MachineBasicBlock &MBB = *MI.getParent();
  const DebugLoc &DL = MI.getDebugLoc();
  Register Dst = MI.getOperand(0).getReg();
  Register Src = MI.getOperand(1).getReg();
  int64_t B = MI.getOperand(2).getImm();
  int64_t C = MI.getOperand(3).getImm();
  int64_t Tmp = MI.getOperand(4).getImm();

  // W := a + file[b]
  BuildMI(MBB, MI, DL, get(PIC14::ADDWF_W), Dst)
      .addReg(Src)
      .addImm(B);
  // Preserve lhs in COMMON RAM while W computes rhs.
  BuildMI(MBB, MI, DL, get(PIC14::MOVWF))
      .addReg(Dst)
      .addImm(Tmp);
  // W := file[b] + file[c]
  BuildMI(MBB, MI, DL, get(PIC14::MOVF_W), Dst).addImm(B);
  BuildMI(MBB, MI, DL, get(PIC14::ADDWF_W), Dst)
      .addReg(Dst)
      .addImm(C);
  // W := rhs ^ saved-lhs. XOR is commutative, matching the source expression.
  BuildMI(MBB, MI, DL, get(PIC14::XORWF_W), Dst)
      .addReg(Dst)
      .addImm(Tmp);

  MI.eraseFromParent();
  return true;
}
'''
replace_once(instr_cpp, ctor, expander, "PIC14 post-RA pressure expander")

# Catch the exact accumulator-pressure DAG before the ordinary binary logic
# selector.  The source shape is deliberately narrow for case 05; widening it
# belongs in the M3 static-memory/spill model rather than pretending W is a GPR
# bank.  Both ADD and XOR are commutative, so accept either operand order.
logic_anchor = '''    if ((N->getOpcode() == ISD::AND || N->getOpcode() == ISD::OR ||
         N->getOpcode() == ISD::XOR) && N->getValueType(0) == MVT::i8) {
'''
pressure_select = '''    if (N->getOpcode() == ISD::XOR && N->getValueType(0) == MVT::i8) {
      auto RAMSlot = [](SDValue V) -> ConstantSDNode * {
        if (V.getOpcode() != PIC14ISD::RAMARG)
          return nullptr;
        return dyn_cast<ConstantSDNode>(V.getOperand(0));
      };

      SDValue Sides[2] = {N->getOperand(0), N->getOperand(1)};
      for (unsigned Swap = 0; Swap != 2; ++Swap) {
        SDValue LHS = Sides[Swap];
        SDValue RHS = Sides[1 - Swap];
        if (LHS.getOpcode() != ISD::ADD || RHS.getOpcode() != ISD::ADD)
          continue;

        SDValue L0 = LHS.getOperand(0);
        SDValue L1 = LHS.getOperand(1);
        ConstantSDNode *LB0 = RAMSlot(L0);
        ConstantSDNode *LB1 = RAMSlot(L1);
        if (!!LB0 == !!LB1) // lhs must be exactly W-value + one file operand
          continue;
        ConstantSDNode *BSlot = LB0 ? LB0 : LB1;
        SDValue WValue = LB0 ? L1 : L0;

        SDValue R0 = RHS.getOperand(0);
        SDValue R1 = RHS.getOperand(1);
        ConstantSDNode *RSlot0 = RAMSlot(R0);
        ConstantSDNode *RSlot1 = RAMSlot(R1);
        if (!RSlot0 || !RSlot1)
          continue;

        uint64_t B = BSlot->getZExtValue();
        uint64_t C = 0;
        if (RSlot0->getZExtValue() == B)
          C = RSlot1->getZExtValue();
        else if (RSlot1->getZExtValue() == B)
          C = RSlot0->getZExtValue();
        else
          continue;

        SDLoc DL(N);
        SDValue BFile = CurDAG->getTargetConstant(B, DL, MVT::i8);
        SDValue CFile = CurDAG->getTargetConstant(C, DL, MVT::i8);
        SDValue TmpFile = CurDAG->getTargetConstant(0x72, DL, MVT::i8);
        SDValue Ops[] = {WValue, BFile, CFile, TmpFile};
        CurDAG->SelectNodeTo(N, PIC14::EXPR_PRESSURE_XOR, MVT::i8, Ops);
        return;
      }
    }

'''
text = isel.read_text()
if logic_anchor not in text:
    raise SystemExit(f"PIC14 M2 logic selector anchor not found in {isel}")
isel.write_text(text.replace(logic_anchor, pressure_select + logic_anchor, 1))

print("PIC14 M2 case 05 W-pressure lowering enabled with post-RA file-memory pseudo")
