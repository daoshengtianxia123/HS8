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
lowering.write_text(text.replace(old, new, 1))

# Generated register/instruction enum names are consumed by lowering and the
# generated DAG selector. Make those enums visible in the corresponding TUs.
for rel in ("PIC14ISelLowering.cpp", "PIC14ISelDAGToDAG.cpp"):
    path = base / rel
    text = path.read_text()
    needle = '#include "PIC14ISelLowering.h"\n' if rel == "PIC14ISelLowering.cpp" else '#include "PIC14.h"\n'
    if needle not in text:
        raise SystemExit(f"include anchor not found in {rel}")
    if '#include "PIC14InstrInfo.h"\n' not in text:
        text = text.replace(needle, needle + '#include "PIC14InstrInfo.h"\n', 1)
    path.write_text(text)

print("PIC14 LLVM 23.1 SelectionDAG constructor/enums fixed")
