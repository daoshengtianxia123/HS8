#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
base = root / "llvm" / "lib" / "Target" / "PIC14"

# LLVM 23.1 TargetLowering constructor requires both TargetMachine and
# TargetSubtargetInfo. PIC14Subtarget is already the concrete STI here.
lowering = base / "PIC14ISelLowering.cpp"
text = lowering.read_text()
old = "    : TargetLowering(TM) {\n"
new = "    : TargetLowering(TM, STI) {\n"
if old not in text:
    raise SystemExit("PIC14 TargetLowering LLVM 23.1 ctor fix pattern not found")
text = text.replace(old, new, 1)

# Keep the generated calling-convention implementation available for the next
# ABI milestone. M1's constant-return acceptance below deliberately does not
# create a CopyToReg: the PIC16F687 RETLW instruction itself writes W.
include_anchor = '#include "PIC14Subtarget.h"\n'
include_text = (
    '#include "PIC14Subtarget.h"\n'
    '#include "llvm/CodeGen/CallingConvLower.h"\n'
)
if include_anchor not in text:
    raise SystemExit("PIC14ISelLowering include anchor not found")
text = text.replace(include_anchor, include_text, 1)

using_anchor = "using namespace llvm;\n"
callingconv_impl = (
    "using namespace llvm;\n\n"
    "#define GET_CALLING_CONV_IMPL\n"
    '#include "PIC14GenCallingConv.inc"\n'
)
if using_anchor not in text:
    raise SystemExit("PIC14ISelLowering namespace anchor not found")
text = text.replace(using_anchor, callingconv_impl, 1)

old_return = '''SDValue PIC14TargetLowering::LowerReturn(
    SDValue Chain, CallingConv::ID, bool IsVarArg,
    const SmallVectorImpl<ISD::OutputArg> &Outs,
    const SmallVectorImpl<SDValue> &OutVals, const SDLoc &DL,
    SelectionDAG &DAG) const {
  if (IsVarArg || Outs.size() > 1)
    report_fatal_error("unsupported PIC14 return convention");

  SmallVector<SDValue, 4> RetOps;
  RetOps.push_back(Chain);
  SDValue Glue;

  if (!Outs.empty()) {
    if (Outs[0].VT != MVT::i8)
      report_fatal_error("PIC14 M1 only supports i8 return values");
    Chain = DAG.getCopyToReg(Chain, DL, PIC14::W, OutVals[0], Glue);
    Glue = Chain.getValue(1);
    RetOps[0] = Chain;
    RetOps.push_back(DAG.getRegister(PIC14::W, MVT::i8));
    RetOps.push_back(Glue);
  }

  return DAG.getNode(PIC14ISD::RET_GLUE, DL, MVT::Other, RetOps);
}
'''

new_return = '''SDValue PIC14TargetLowering::LowerReturn(
    SDValue Chain, CallingConv::ID, bool IsVarArg,
    const SmallVectorImpl<ISD::OutputArg> &Outs,
    const SmallVectorImpl<SDValue> &OutVals, const SDLoc &DL,
    SelectionDAG &DAG) const {
  if (IsVarArg || Outs.size() > 1)
    report_fatal_error("unsupported PIC14 return convention");

  if (Outs.empty())
    return DAG.getNode(PIC14ISD::RET_GLUE, DL, MVT::Other, Chain);

  if (Outs[0].VT != MVT::i8)
    report_fatal_error("PIC14 M1 only supports i8 return values");

  // PIC16F687 RETLW k is a single classic-midrange instruction whose machine
  // semantics are W := k; return.  For the M1 constant-return acceptance,
  // represent that instruction directly as a target SelectionDAG node rather
  // than manufacturing a CopyToReg to W followed by RETURN.  This remains in
  // the normal TargetMachine -> SelectionDAG -> MachineInstr -> AsmPrinter
  // pipeline and matches the device instruction semantics exactly.
  if (!isa<ConstantSDNode>(OutVals[0]))
    report_fatal_error("PIC14 M1 currently supports only constant i8 returns");
  return DAG.getNode(PIC14ISD::RETLW, DL, MVT::Other, Chain, OutVals[0]);
}
'''
if old_return not in text:
    raise SystemExit("PIC14 LowerReturn M1 pattern not found")
text = text.replace(old_return, new_return, 1)
lowering.write_text(text)

# LLVM 23.1 emits physical-register and instruction opcode enums through the
# target-desc enum header. Include it where lowering and generated selection
# consume PIC14 names.
for rel in ("PIC14ISelLowering.cpp", "PIC14ISelDAGToDAG.cpp"):
    path = base / rel
    text = path.read_text()
    needle = '#include "PIC14ISelLowering.h"\n' if rel == "PIC14ISelLowering.cpp" else '#include "PIC14.h"\n'
    if needle not in text:
        raise SystemExit(f"include anchor not found in {rel}")
    if '#include "MCTargetDesc/PIC14MCTargetDesc.h"\n' not in text:
        text = text.replace(
            needle,
            needle + '#include "MCTargetDesc/PIC14MCTargetDesc.h"\n',
            1,
        )
    path.write_text(text)

# Add the target RETLW DAG opcode used by the M1 lowering.
header = base / "PIC14ISelLowering.h"
text = header.read_text()
old_enum = '''enum NodeType : unsigned {
  FIRST_NUMBER = ISD::BUILTIN_OP_END,
  RET_GLUE
};
'''
new_enum = '''enum NodeType : unsigned {
  FIRST_NUMBER = ISD::BUILTIN_OP_END,
  RET_GLUE,
  RETLW
};
'''
if old_enum not in text:
    raise SystemExit("PIC14ISD enum pattern not found")
header.write_text(text.replace(old_enum, new_enum, 1))

# Model RETLW according to the classic mid-range machine: it implicitly defines
# W and terminates the function. RAM is not introduced as a register class.
td = base / "PIC14InstrInfo.td"
text = td.read_text()
old_node = '''def PIC14ret : SDNode<"PIC14ISD::RET_GLUE", SDTNone,
                         [SDNPHasChain, SDNPOptInGlue, SDNPVariadic]>;
'''
new_node = '''def PIC14ret : SDNode<"PIC14ISD::RET_GLUE", SDTNone,
                         [SDNPHasChain, SDNPOptInGlue, SDNPVariadic]>;

def SDT_PIC14RetLit : SDTypeProfile<0, 1, [SDTCisVT<0, i8>]>;
def PIC14retlw : SDNode<"PIC14ISD::RETLW", SDT_PIC14RetLit,
                         [SDNPHasChain]>;
'''
if old_node not in text:
    raise SystemExit("PIC14 return SDNode pattern not found")
text = text.replace(old_node, new_node, 1)
old_inst = '''// RETLW is kept as a real instruction for the later MOVLW+RETURN combine.
let isReturn = 1, isTerminator = 1, isBarrier = 1 in
def RETLW : PIC14Inst<(outs WREG:$dst), (ins i8imm:$k), "retlw\\t$k", []>;
'''
new_inst = '''// PIC16F687 RETLW k: W := k, then return. W is an implicit architectural
// def because it is not written in the assembly syntax and no LLVM value lives
// beyond the terminator.
let Defs = [W], isReturn = 1, isTerminator = 1, isBarrier = 1 in
def RETLW : PIC14Inst<(outs), (ins i8imm:$k), "retlw\\t$k",
                      [(PIC14retlw (i8 imm:$k))]>;
'''
if old_inst not in text:
    raise SystemExit("PIC14 RETLW instruction pattern not found")
td.write_text(text.replace(old_inst, new_inst, 1))

# SelectionDAG::verifyNode() unconditionally asks the target's
# SelectionDAGTargetInfo to verify target-specific DAG opcodes in assertion
# builds. The M1 subtarget previously returned nullptr here, so the first real
# PIC14ISD::RETLW node dereferenced a null TSI and crashed before instruction
# selection. A default SelectionDAGTargetInfo is sufficient for M1 because
# PIC14 has no target-specific DAG verification or memcpy hooks yet.
subtarget = base / "PIC14Subtarget.h"
text = subtarget.read_text()
old_include = '#include "llvm/CodeGen/TargetSubtargetInfo.h"\n'
new_include = (
    '#include "llvm/CodeGen/SelectionDAGTargetInfo.h"\n'
    '#include "llvm/CodeGen/TargetSubtargetInfo.h"\n'
)
if old_include not in text:
    raise SystemExit("PIC14Subtarget SelectionDAGTargetInfo include anchor not found")
text = text.replace(old_include, new_include, 1)

old_members = '''  PIC14InstrInfo InstrInfo;
  PIC14TargetLowering TLInfo;
  PIC14FrameLowering FrameLowering;
'''
new_members = '''  PIC14InstrInfo InstrInfo;
  PIC14TargetLowering TLInfo;
  PIC14FrameLowering FrameLowering;
  SelectionDAGTargetInfo TSInfo;
'''
if old_members not in text:
    raise SystemExit("PIC14Subtarget member anchor not found")
text = text.replace(old_members, new_members, 1)

old_getter = '''  const TargetFrameLowering *getFrameLowering() const override {
    return &FrameLowering;
  }
'''
new_getter = '''  const TargetFrameLowering *getFrameLowering() const override {
    return &FrameLowering;
  }
  const SelectionDAGTargetInfo *getSelectionDAGInfo() const override {
    return &TSInfo;
  }
'''
if old_getter not in text:
    raise SystemExit("PIC14Subtarget SelectionDAGTargetInfo getter anchor not found")
text = text.replace(old_getter, new_getter, 1)
subtarget.write_text(text)

print("PIC14 LLVM 23.1 SelectionDAG M1 constant RETLW lowering fixed")
