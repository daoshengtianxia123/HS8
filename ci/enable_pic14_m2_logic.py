#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
base = root / "llvm" / "lib" / "Target" / "PIC14"
instr_td = base / "PIC14InstrInfo.td"
isel = base / "PIC14ISelDAGToDAG.cpp"


def replace_once(path: Path, old: str, new: str, what: str) -> None:
    text = path.read_text()
    if old not in text:
        raise SystemExit(f"{what} anchor not found in {path}")
    path.write_text(text.replace(old, new, 1))


# PIC16F687 classic-midrange byte logic is accumulator/file-register based.
# Model the native W := W op file forms directly; the file operand remains RAM,
# never a fabricated GPR.  Z flag dependencies are introduced when M4 starts
# consuming STATUS in control flow, rather than incorrectly clobbering C/DC now.
replace_once(
    instr_td,
    '''let Defs = [STATUS] in
def ADDWF_W : PIC14Inst<
    (outs WREG:$dst), (ins WREG:$src, i8imm:$f), "addwf\\t$f,w", []>;

''',
    '''let Defs = [STATUS] in
def ADDWF_W : PIC14Inst<
    (outs WREG:$dst), (ins WREG:$src, i8imm:$f), "addwf\\t$f,w", []>;

def ANDWF_W : PIC14Inst<
    (outs WREG:$dst), (ins WREG:$src, i8imm:$f), "andwf\\t$f,w", []>;

def IORWF_W : PIC14Inst<
    (outs WREG:$dst), (ins WREG:$src, i8imm:$f), "iorwf\\t$f,w", []>;

def XORWF_W : PIC14Inst<
    (outs WREG:$dst), (ins WREG:$src, i8imm:$f), "xorwf\\t$f,w", []>;

''',
    "PIC14 M2 byte logic instructions",
)

# Reuse the same native file,W fold as ADDWF for AND/IOR/XOR.  RAMARG is a
# file-register location descriptor, so the selected machine instruction takes
# the W-resident value plus an immediate file address.
anchor = '''    if (N->getOpcode() == ISD::ADD && N->getValueType(0) == MVT::i8) {
'''
insert = '''    if ((N->getOpcode() == ISD::AND || N->getOpcode() == ISD::OR ||
         N->getOpcode() == ISD::XOR) && N->getValueType(0) == MVT::i8) {
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
        unsigned Opc = N->getOpcode() == ISD::AND ? PIC14::ANDWF_W
                       : N->getOpcode() == ISD::OR ? PIC14::IORWF_W
                                                  : PIC14::XORWF_W;
        CurDAG->SelectNodeTo(N, Opc, MVT::i8, WValue, File);
        return;
      }
    }

'''
text = isel.read_text()
if anchor not in text:
    raise SystemExit(f"PIC14 ADD selector anchor not found in {isel}")
isel.write_text(text.replace(anchor, insert + anchor, 1))

print("PIC14 M2 case 06 native ANDWF/IORWF/XORWF lowering enabled")
