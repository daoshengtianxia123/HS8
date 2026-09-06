#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
path = root / "llvm" / "lib" / "Target" / "PIC14" / "MCTargetDesc" / "PIC14MCAsmInfo.cpp"
text = path.read_text()
needle = '#include "PIC14MCAsmInfo.h"\n'
replacement = needle + '#include "llvm/Support/Alignment.h"\n'
if replacement in text:
    print("PIC14 MCAsmInfo Alignment include already present")
    raise SystemExit(0)
if needle not in text:
    raise SystemExit("PIC14MCAsmInfo include anchor not found")
path.write_text(text.replace(needle, replacement, 1))
print("PIC14 MCAsmInfo Alignment include added")
