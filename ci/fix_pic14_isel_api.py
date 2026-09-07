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

# Use the generated return calling convention when constructing CopyToReg.
# This follows LLVM 23.1's normal SelectionDAG return-lowering contract instead
# of hard-coding a physical register directly in LowerReturn.  In particular,
# CCValAssign supplies both the physical register and LocVT used by the DAG.
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
    SDValue Chain, CallingConv::ID CallConv, bool IsVarArg,
    const SmallVectorImpl<ISD::OutputArg> &Outs,
    const SmallVectorImpl<SDValue> &OutVals, const SDLoc &DL,
    SelectionDAG &DAG) const {
  if (IsVarArg || Outs.size() > 1)
    report_fatal_error("unsupported PIC14 return convention");

  SmallVector<CCValAssign, 4> RVLocs;
  CCState CCInfo(CallConv, IsVarArg, DAG.getMachineFunction(), RVLocs,
                 *DAG.getContext());
  CCInfo.AnalyzeReturn(Outs, RetCC_PIC14);

  SDValue Glue;
  SmallVector<SDValue, 4> RetOps(1, Chain);
  for (unsigned I = 0, E = RVLocs.size(); I != E; ++I) {
    CCValAssign &VA = RVLocs[I];
    if (!VA.isRegLoc())
      report_fatal_error("PIC14 M1 return must be assigned to W");
    Chain = DAG.getCopyToReg(Chain, DL, VA.getLocReg(), OutVals[I], Glue);
    Glue = Chain.getValue(1);
    RetOps.push_back(DAG.getRegister(VA.getLocReg(), VA.getLocVT()));
  }

  RetOps[0] = Chain;
  if (Glue.getNode())
    RetOps.push_back(Glue);
  return DAG.getNode(PIC14ISD::RET_GLUE, DL, MVT::Other, RetOps);
}
'''
if old_return not in text:
    raise SystemExit("PIC14 LowerReturn LLVM 23.1 CCState fix pattern not found")
text = text.replace(old_return, new_return, 1)
lowering.write_text(text)

# LLVM 23.1 emits the physical-register and instruction opcode enums through
# the GET_*_ENUM sections consumed by PIC14MCTargetDesc.h.  The normal
# GET_REGINFO_HEADER / GET_INSTRINFO_HEADER sections declare the target helper
# classes, but they do not make PIC14::W / PIC14::MOVLW / PIC14::RETURN visible
# to these translation units.  Include the target-desc enum header where the
# lowering and generated DAG selector consume those names.
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

print("PIC14 LLVM 23.1 SelectionDAG constructor/generated enums/return CC fixed")
