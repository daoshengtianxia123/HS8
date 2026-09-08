#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
lowering = root / "llvm" / "lib" / "Target" / "PIC14" / "PIC14ISelLowering.cpp"
text = lowering.read_text()

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
  if (Ins.size() != 1 || Ins[0].VT != MVT::i8)
    report_fatal_error("PIC14 M2 currently supports one i8 argument");

  // M2 case 02: the first byte argument arrives in W.  W remains the only
  // ordinary allocatable i8 register class; file-register RAM is memory and is
  // not modeled as a bank of argument GPRs.
  MachineFunction &MF = DAG.getMachineFunction();
  Register VReg = MF.addLiveIn(PIC14::W, &PIC14::WREGRegClass);
  SDValue Arg = DAG.getCopyFromReg(Chain, DL, VReg, MVT::i8);
  InVals.push_back(Arg);
  return Arg.getValue(1);
}
'''

if old_formal not in text:
    raise SystemExit("PIC14 M2 LowerFormalArguments anchor not found")
text = text.replace(old_formal, new_formal, 1)

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

if old_return not in text:
    raise SystemExit("PIC14 M2 non-constant return anchor not found")
text = text.replace(old_return, new_return, 1)
lowering.write_text(text)

print("PIC14 M2 case 02 single-i8 argument/return lowering enabled")
