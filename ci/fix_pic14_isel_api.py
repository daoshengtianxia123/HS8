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

print("PIC14 LLVM 23.1 SelectionDAG constructor/generated enums fixed")
