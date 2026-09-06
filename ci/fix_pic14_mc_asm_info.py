#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
path = root / "llvm" / "lib" / "Target" / "PIC14" / "MCTargetDesc" / "PIC14MCAsmInfo.cpp"
text = path.read_text()

# LLVM 23.1 MCAsmInfo::MinInstAlignment is an unsigned byte count, not Align.
# Keep this compatibility fix isolated in CI until the real overlay is folded
# into a normal source patch.
old = "  MinInstAlignment = Align(1);\n"
new = "  MinInstAlignment = 1;\n"
if new in text:
    print("PIC14 MCAsmInfo MinInstAlignment already uses LLVM 23.1 unsigned API")
    raise SystemExit(0)
if old not in text:
    raise SystemExit("PIC14 MCAsmInfo MinInstAlignment anchor not found")
path.write_text(text.replace(old, new, 1))
print("PIC14 MCAsmInfo MinInstAlignment fixed for LLVM 23.1")
