#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
base = root / "llvm" / "lib" / "Target" / "PIC14"
lowering_h = base / "PIC14ISelLowering.h"
lowering = base / "PIC14ISelLowering.cpp"
instr_td = base / "PIC14InstrInfo.td"
isel = base / "PIC14ISelDAGToDAG.cpp"


def replace_once(path: Path, old: str, new: str, what: str) -> None:
    text = path.read_text()
    if old not in text:
        raise SystemExit(f"{what} anchor not found in {path}")
    path.write_text(text.replace(old, new, 1))


# M2 needs an explicit target value for a byte argument that is resident in
# COMMON RAM.  This is an ABI location descriptor, not a fabricated GPR.
replace_once(
    lowering_h,
    '''  FIRST_NUMBER = ISD::BUILTIN_OP_END,\n  RET_GLUE\n''',
    '''  FIRST_NUMBER = ISD::BUILTIN_OP_END,\n  RET_GLUE,\n  RAMARG\n''',
    "PIC14ISD RAMARG",
)

old_formal = '''SDValue PIC14TargetLowering::LowerFormalArguments(
    SDValue Chain, CallingConv::ID, bool IsVarArg,
    const SmallVectorImpl<ISD::InputArg> &Ins, const SDLoc &,
    SelectionDAG &, SmallVectorImpl<SDValue> &) const {
  if (IsVarArg)
    report_fatal_error("PIC14 varargs are not supported");
  if (!Ins.empty())
    report_fatal_error("PIC14 M1 real pipeline currently accepts no arguments");
  return Chain;
}
'''

new_formal = '''SDValue PIC14TargetLowering::LowerFormalArguments(
    SDValue Chain, CallingConv::ID, bool IsVarArg,
    const SmallVectorImpl<ISD::InputArg> &Ins, const SDLoc &DL,
    SelectionDAG &DAG, SmallVectorImpl<SDValue> &InVals) const {
  if (IsVarArg)
    report_fatal_error("PIC14 varargs are not supported");
  if (Ins.empty())
    return Chain;
  if (Ins.size() > 2)
    report_fatal_error("PIC14 M2 currently supports at most two i8 arguments");
  for (const ISD::InputArg &In : Ins)
    if (In.VT != MVT::i8)
      report_fatal_error("PIC14 M2 currently supports only i8 arguments");

  // XC8 oracle / initial PIC14 ABI: arg0 arrives in W.  W remains the only
  // ordinary allocatable i8 register; file-register RAM is never modeled as a
  // symmetric register bank.
  MachineFunction &MF = DAG.getMachineFunction();
  Register VReg = MF.addLiveIn(PIC14::W, &PIC14::WREGRegClass);
  SDValue Arg0 = DAG.getCopyFromReg(Chain, DL, VReg, MVT::i8);
  InVals.push_back(Arg0);
  Chain = Arg0.getValue(1);

  if (Ins.size() == 2) {
    // The second byte argument lives in COMMON RAM.  For the first static,
    // non-reentrant ABI bring-up use the first ordinary COMMON slot (0x70).
    // This is a memory location descriptor carried to instruction selection;
    // it is deliberately not a fake physical register.  M3 replaces the
    // fixed slot with the per-function static-frame allocator.
    SDValue Slot = DAG.getTargetConstant(0x70, DL, MVT::i8);
    SDValue Arg1 = DAG.getNode(PIC14ISD::RAMARG, DL, MVT::i8, Slot);
    InVals.push_back(Arg1);
  }

  return Chain;
}
'''
replace_once(lowering, old_formal, new_formal, "PIC14 M2 LowerFormalArguments")

old_return = '''  // PIC16F687 RETLW k is a single classic-midrange instruction whose machine
  // semantics are W := k; return.  For the M1 constant-return acceptance,
  // represent that instruction directly as a target SelectionDAG node rather
  // than manufacturing a CopyToReg to W followed by RETURN.  This remains in
  // the normal TargetMachine -> SelectionDAG -> MachineInstr -> AsmPrinter
  // pipeline and matches the device instruction semantics exactly.
  if (!isa<ConstantSDNode>(OutVals[0]))
    report_fatal_error("PIC14 M1 currently supports only constant i8 returns");
  return DAG.getNode(PIC14ISD::RETLW, DL, MVT::Other, Chain, OutVals[0]);
'''

new_return = '''  // Keep the M1 constant-return optimization exact: PIC16F687 RETLW k is a
  // single classic-midrange instruction whose semantics are W := k; return.
  if (isa<ConstantSDNode>(OutVals[0]))
    return DAG.getNode(PIC14ISD::RETLW, DL, MVT::Other, Chain, OutVals[0]);

  // M2 non-constant i8 returns use the ABI result register W and the ordinary
  // RETURN instruction.  This is still normal SelectionDAG lowering; no
  // llc.cpp or IR-to-text shortcut is involved.
  SDValue Glue;
  Chain = DAG.getCopyToReg(Chain, DL, PIC14::W, OutVals[0], Glue);
  Glue = Chain.getValue(1);
  SmallVector<SDValue, 4> RetOps;
  RetOps.push_back(Chain);
  RetOps.push_back(DAG.getRegister(PIC14::W, MVT::i8));
  RetOps.push_back(Glue);
  return DAG.getNode(PIC14ISD::RET_GLUE, DL, MVT::Other, RetOps);
'''
replace_once(lowering, old_return, new_return, "PIC14 M2 non-constant return")

# ADDWF f,W is the native classic-midrange operation for W := W + file[f].
# STATUS is an implicit def so arithmetic already carries a real machine-state
# dependency instead of pretending flags do not exist.
replace_once(
    instr_td,
    '''def MOVLW : PIC14Inst<
    (outs WREG:$dst), (ins i8imm:$k), "movlw\\t$k",
    [(set WREG:$dst, (i8 imm:$k))]>;

''',
    '''def MOVLW : PIC14Inst<
    (outs WREG:$dst), (ins i8imm:$k), "movlw\\t$k",
    [(set WREG:$dst, (i8 imm:$k))]>;

let Defs = [STATUS] in
def ADDWF_W : PIC14Inst<
    (outs WREG:$dst), (ins WREG:$src, i8imm:$f), "addwf\\t$f,w", []>;

''',
    "PIC14 ADDWF_W instruction",
)

# Fold an i8 add of the W-resident arg and a RAMARG directly to ADDWF f,W.
# RAMARG itself is intentionally not selected into a fake load/GPR; it denotes
# the file-register operand consumed by the native arithmetic instruction.
replace_once(
    isel,
    '''#include "PIC14.h"\n#include "PIC14TargetMachine.h"\n''',
    '''#include "PIC14.h"\n#include "PIC14ISelLowering.h"\n#include "PIC14TargetMachine.h"\n''',
    "PIC14 ISel lowering include",
)
replace_once(
    isel,
    '''  void Select(SDNode *N) override {
    if (N->isMachineOpcode()) {
      N->setNodeId(-1);
      return;
    }
    SelectCode(N);
  }
''',
    '''  void Select(SDNode *N) override {
    if (N->isMachineOpcode()) {
      N->setNodeId(-1);
      return;
    }

    if (N->getOpcode() == ISD::ADD && N->getValueType(0) == MVT::i8) {
      SDValue LHS = N->getOperand(0);
      SDValue RHS = N->getOperand(1);
      SDValue WValue;
      SDValue RAMValue;
      if (RHS.getOpcode() == PIC14ISD::RAMARG) {
        WValue = LHS;
        RAMValue = RHS;
      } else if (LHS.getOpcode() == PIC14ISD::RAMARG) {
        WValue = RHS;
        RAMValue = LHS;
      }

      if (RAMValue.getNode()) {
        auto *Slot = dyn_cast<ConstantSDNode>(RAMValue.getOperand(0));
        if (!Slot)
          report_fatal_error("PIC14 RAMARG requires a constant COMMON slot");
        SDLoc DL(N);
        SDValue File = CurDAG->getTargetConstant(Slot->getZExtValue(), DL,
                                                 MVT::i8);
        CurDAG->SelectNodeTo(N, PIC14::ADDWF_W, MVT::i8, WValue, File);
        return;
      }
    }

    // A RAMARG must be folded by an operation that understands file-register
    // memory.  Leaving it unselected is safe only while it still has a folding
    // user; unsupported standalone uses will be rejected by selection.
    if (N->getOpcode() == PIC14ISD::RAMARG) {
      N->setNodeId(-1);
      return;
    }

    SelectCode(N);
  }
''',
    "PIC14 M2 ADD custom selector",
)

# Install the next M2 oracle as a real LLVM lit/FileCheck regression.  The
# exact COMMON address is intentionally not part of the textual contract yet;
# M3 owns static-frame allocation.  The required machine semantic is ADDWF
# file,W followed by return, with no enhanced-midrange state/instructions.
test_dir = root / "llvm" / "test" / "CodeGen" / "PIC14"
test_dir.mkdir(parents=True, exist_ok=True)
(test_dir / "add-u8.ll").write_text('''; RUN: llc -enable-new-pm=0 -mtriple=pic14-unknown-none -mcpu=pic16f687 -filetype=asm < %s | FileCheck %s
;
; M2 case 03: arg0 is W, arg1 is COMMON RAM, result is W.  ADDWF f,W is the
; native classic-midrange operation and STATUS is an implicit machine def.

define i8 @add_u8(i8 %a, i8 %b) {
entry:
  %sum = add i8 %a, %b
  ret i8 %sum
}

; CHECK-LABEL: add_u8:
; CHECK: addwf{{[[:space:]]+}}112,w
; CHECK: return
; CHECK-NOT: moviw
; CHECK-NOT: movwi
; CHECK-NOT: addfsr
; CHECK-NOT: FSR0
; CHECK-NOT: FSR1
; CHECK-NOT: INDF0
; CHECK-NOT: INDF1
''')

print("PIC14 M2 cases 02/03 single-u8 ABI and native ADDWF lowering enabled")
