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


# M3 starts the static/non-reentrant C frame.  File-register RAM stays memory:
# the native MOVWF/MOVF instructions get real memory side-effect flags and
# MOVF records its STATUS write (Z is affected by classic mid-range MOVF).
replace_once(
    instr_td,
    '''def MOVWF : PIC14Inst<
    (outs), (ins WREG:$src, i8imm:$f), "movwf\\t$f", []>;

def MOVF_W : PIC14Inst<
    (outs WREG:$dst), (ins i8imm:$f), "movf\\t$f,w", []>;
''',
    '''let mayStore = 1 in
def MOVWF : PIC14Inst<
    (outs), (ins WREG:$src, i8imm:$f), "movwf\\t$f", []>;

let mayLoad = 1, Defs = [STATUS] in
def MOVF_W : PIC14Inst<
    (outs WREG:$dst), (ins i8imm:$f), "movf\\t$f,w", []>;
''',
    "PIC14 M3 native file-memory flags",
)

# Select i8 stack objects directly as classic-midrange file-register memory.
# This first M3 slice intentionally maps ordinary one-byte frame indices to
# bank-0 GPR RAM starting at 0x20.  There is no software stack pointer and no
# fabricated RAM register class.  Calls/live-across-call are still M5, so this
# per-function static-frame mapping is sufficient for case 08 and is widened
# by the later frame-allocation milestones.
select_anchor = '''  void Select(SDNode *N) override {
    if (N->isMachineOpcode()) {
'''
select_code = '''  void Select(SDNode *N) override {
    if (N->getOpcode() == ISD::STORE) {
      auto *ST = cast<StoreSDNode>(N);
      auto *FI = dyn_cast<FrameIndexSDNode>(ST->getBasePtr());
      if (FI) {
        if (ST->getMemoryVT() != MVT::i8)
          report_fatal_error("PIC14 M3 static frame currently supports only i8 stores");
        int Index = FI->getIndex();
        if (Index < 0 || Index >= 0x50)
          report_fatal_error("PIC14 M3 static frame index is outside bank-0 GPR RAM");
        SDLoc DL(N);
        SDValue File = CurDAG->getTargetConstant(0x20 + Index, DL, MVT::i8);
        SDValue Ops[] = {ST->getValue(), File, ST->getChain()};
        SDNode *Res = CurDAG->getMachineNode(PIC14::MOVWF, DL, MVT::Other, Ops);
        CurDAG->setNodeMemRefs(cast<MachineSDNode>(Res), {ST->getMemOperand()});
        ReplaceUses(SDValue(N, 0), SDValue(Res, 0));
        CurDAG->RemoveDeadNode(N);
        return;
      }
    }

    if (N->getOpcode() == ISD::LOAD) {
      auto *LD = cast<LoadSDNode>(N);
      auto *FI = dyn_cast<FrameIndexSDNode>(LD->getBasePtr());
      if (FI) {
        if (LD->getMemoryVT() != MVT::i8 || LD->getValueType(0) != MVT::i8)
          report_fatal_error("PIC14 M3 static frame currently supports only i8 loads");
        int Index = FI->getIndex();
        if (Index < 0 || Index >= 0x50)
          report_fatal_error("PIC14 M3 static frame index is outside bank-0 GPR RAM");
        SDLoc DL(N);
        SDValue File = CurDAG->getTargetConstant(0x20 + Index, DL, MVT::i8);
        SDValue Ops[] = {File, LD->getChain()};
        SDNode *Res = CurDAG->getMachineNode(PIC14::MOVF_W, DL,
                                             MVT::i8, MVT::Other, Ops);
        CurDAG->setNodeMemRefs(cast<MachineSDNode>(Res), {LD->getMemOperand()});
        ReplaceUses(SDValue(N, 0), SDValue(Res, 0));
        ReplaceUses(SDValue(N, 1), SDValue(Res, 1));
        CurDAG->RemoveDeadNode(N);
        return;
      }
    }

    if (N->isMachineOpcode()) {
'''
replace_once(isel, select_anchor, select_code, "PIC14 M3 frame load/store selector")

print("PIC14 M3 case 08 one-byte static local frame lowering enabled")
