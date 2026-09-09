#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
base = root / "llvm" / "lib" / "Target" / "PIC14"
instr_td = base / "PIC14InstrInfo.td"
instr_cpp = base / "PIC14InstrInfo.cpp"
isel = base / "PIC14ISelDAGToDAG.cpp"


def replace_once(path: Path, old: str, new: str, what: str) -> None:
    text = path.read_text()
    if old not in text:
        raise SystemExit(f"{what} anchor not found in {path}")
    path.write_text(text.replace(old, new, 1))


# M3 case 09 is the first local-expression shape where four volatile file-RAM
# values feed an add tree.  Two W-valued subexpressions cannot coexist on a
# classic mid-range core because W is the only ordinary i8 register.  Keep the
# pressure sequence explicit as a pseudo and expand it after RA using W plus
# COMMON-RAM byte temporaries.  No file register becomes a synthetic GPR.
frame_movf = '''let mayLoad = 1, Defs = [STATUS] in
def MOVF_W : PIC14Inst<
    (outs WREG:$dst), (ins i8imm:$f), "movf\\t$f,w", []>;
'''
frame_pseudo = frame_movf + '''
// Compute (file[f0] + file[f1]) + (file[f2] + file[f3]) with the real W
// accumulator.  COMMON 0x72/0x73 are temporary file-memory bytes for this M3
// slice; later frame allocation owns pressure-slot placement globally.
let isPseudo = 1, mayLoad = 1, mayStore = 1, hasSideEffects = 1,
    Defs = [STATUS] in
def ADD4_FRAME_W : PIC14Inst<
    (outs WREG:$dst),
    (ins i8imm:$f0, i8imm:$f1, i8imm:$f2, i8imm:$f3), "", []>;
'''
replace_once(instr_td, frame_movf, frame_pseudo,
             "PIC14 M3 four-frame add pseudo")

expander_anchor = '''bool PIC14InstrInfo::expandPostRAPseudo(MachineInstr &MI) const {
  if (MI.getOpcode() != PIC14::EXPR_PRESSURE_XOR)
    return false;
'''
expander_code = '''bool PIC14InstrInfo::expandPostRAPseudo(MachineInstr &MI) const {
  if (MI.getOpcode() == PIC14::ADD4_FRAME_W) {
    MachineBasicBlock &MBB = *MI.getParent();
    const DebugLoc &DL = MI.getDebugLoc();
    Register Dst = MI.getOperand(0).getReg();
    int64_t F0 = MI.getOperand(1).getImm();
    int64_t F1 = MI.getOperand(2).getImm();
    int64_t F2 = MI.getOperand(3).getImm();
    int64_t F3 = MI.getOperand(4).getImm();
    constexpr int64_t Tmp01 = 0x72;
    constexpr int64_t Tmp23 = 0x73;

    // W := file[f0]; save lhs byte in real file-register RAM.
    BuildMI(MBB, MI, DL, get(PIC14::MOVF_W), Dst).addImm(F0);
    BuildMI(MBB, MI, DL, get(PIC14::MOVWF)).addReg(Dst).addImm(Tmp01);
    // W := file[f1] + saved f0; preserve the first subexpression.
    BuildMI(MBB, MI, DL, get(PIC14::MOVF_W), Dst).addImm(F1);
    BuildMI(MBB, MI, DL, get(PIC14::ADDWF_W), Dst)
        .addReg(Dst)
        .addImm(Tmp01);
    BuildMI(MBB, MI, DL, get(PIC14::MOVWF)).addReg(Dst).addImm(Tmp01);

    // W := file[f2]; save it, then form the second subexpression with f3.
    BuildMI(MBB, MI, DL, get(PIC14::MOVF_W), Dst).addImm(F2);
    BuildMI(MBB, MI, DL, get(PIC14::MOVWF)).addReg(Dst).addImm(Tmp23);
    BuildMI(MBB, MI, DL, get(PIC14::MOVF_W), Dst).addImm(F3);
    BuildMI(MBB, MI, DL, get(PIC14::ADDWF_W), Dst)
        .addReg(Dst)
        .addImm(Tmp23);
    // Addition is modulo i8: W := rhs + saved lhs.
    BuildMI(MBB, MI, DL, get(PIC14::ADDWF_W), Dst)
        .addReg(Dst)
        .addImm(Tmp01);

    MI.eraseFromParent();
    return true;
  }

  if (MI.getOpcode() != PIC14::EXPR_PRESSURE_XOR)
    return false;
'''
replace_once(instr_cpp, expander_anchor, expander_code,
             "PIC14 M3 four-frame post-RA expansion")

select_anchor = '''  void Select(SDNode *N) override {
    if (N->getOpcode() == ISD::STORE) {
'''
select_code = '''  void Select(SDNode *N) override {
    // Fold the exact M3 case-09 add tree before its four volatile frame loads
    // are individually selected to W.  The pseudo carries a chain from the
    // first load predecessor to the final load successor, so the four volatile
    // memory operations remain ordered with surrounding stores/loads.
    if (N->getOpcode() == ISD::ADD && N->getValueType(0) == MVT::i8) {
      SDValue L = N->getOperand(0);
      SDValue R = N->getOperand(1);
      if (L.getOpcode() == ISD::ADD && R.getOpcode() == ISD::ADD) {
        SDValue Leaves[4] = {L.getOperand(0), L.getOperand(1),
                             R.getOperand(0), R.getOperand(1)};
        LoadSDNode *Loads[4] = {};
        FrameIndexSDNode *Frames[4] = {};
        bool Match = true;
        for (unsigned I = 0; I != 4; ++I) {
          Loads[I] = dyn_cast<LoadSDNode>(Leaves[I]);
          if (!Loads[I] || !Loads[I]->isVolatile() ||
              Loads[I]->getMemoryVT() != MVT::i8 ||
              Loads[I]->getValueType(0) != MVT::i8) {
            Match = false;
            break;
          }
          Frames[I] = dyn_cast<FrameIndexSDNode>(Loads[I]->getBasePtr());
          if (!Frames[I] || Frames[I]->getIndex() < 0 ||
              Frames[I]->getIndex() >= 0x50) {
            Match = false;
            break;
          }
        }
        if (Match) {
          for (unsigned I = 1; I != 4; ++I)
            if (Loads[I]->getChain() != SDValue(Loads[I - 1], 1))
              Match = false;
        }
        if (Match) {
          SDLoc DL(N);
          SDValue Ops[5];
          for (unsigned I = 0; I != 4; ++I)
            Ops[I] = CurDAG->getTargetConstant(
                0x20 + Frames[I]->getIndex(), DL, MVT::i8);
          Ops[4] = Loads[0]->getChain();
          SDNode *Res = CurDAG->getMachineNode(PIC14::ADD4_FRAME_W, DL,
                                               MVT::i8, MVT::Other, Ops);
          ReplaceUses(SDValue(N, 0), SDValue(Res, 0));
          ReplaceUses(SDValue(Loads[3], 1), SDValue(Res, 1));
          CurDAG->RemoveDeadNode(N);
          return;
        }
      }
    }

    if (N->getOpcode() == ISD::STORE) {
'''
replace_once(isel, select_anchor, select_code,
             "PIC14 M3 four-frame add selector")

print("PIC14 M3 case 09 multi-local W-pressure lowering enabled")
