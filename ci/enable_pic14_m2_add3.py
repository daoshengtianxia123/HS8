#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
lowering = root / "llvm" / "lib" / "Target" / "PIC14" / "PIC14ISelLowering.cpp"
text = lowering.read_text()

old_limit = '  if (Ins.size() > 2)\n    report_fatal_error("PIC14 M2 currently supports at most two i8 arguments");\n'
new_limit = '  if (Ins.size() > 3)\n    report_fatal_error("PIC14 M2 currently supports at most three i8 arguments");\n'
if old_limit not in text:
    raise SystemExit("PIC14 M2 argument-count anchor not found")
text = text.replace(old_limit, new_limit, 1)

old_arg1 = '''  if (Ins.size() == 2) {
    // The second byte argument lives in COMMON RAM.  For the first static,
    // non-reentrant ABI bring-up use the first ordinary COMMON slot (0x70).
    // This is a memory location descriptor carried to instruction selection;
    // it is deliberately not a fake physical register.  M3 replaces the
    // fixed slot with the per-function static-frame allocator.
    SDValue Slot = DAG.getTargetConstant(0x70, DL, MVT::i8);
    SDValue Arg1 = DAG.getNode(PIC14ISD::RAMARG, DL, MVT::i8, Slot);
    InVals.push_back(Arg1);
  }
'''

new_args = '''  // Remaining byte arguments live in successive COMMON-RAM ABI slots.
  // These are memory operands, not fabricated GPRs.  M3 replaces the fixed
  // slots with the static non-reentrant frame allocator.
  for (unsigned I = 1; I < Ins.size(); ++I) {
    SDValue Slot = DAG.getTargetConstant(0x70 + (I - 1), DL, MVT::i8);
    SDValue Arg = DAG.getNode(PIC14ISD::RAMARG, DL, MVT::i8, Slot);
    InVals.push_back(Arg);
  }
'''
if old_arg1 not in text:
    raise SystemExit("PIC14 M2 COMMON argument anchor not found")
text = text.replace(old_arg1, new_args, 1)
lowering.write_text(text)

print("PIC14 M2 case 04 three-u8 argument ABI enabled")
