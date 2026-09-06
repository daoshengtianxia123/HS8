#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
header = root / "llvm" / "lib" / "Target" / "PIC14" / "PIC14.h"
text = header.read_text()
old = '#include "llvm/CodeGen/CodeGenOptLevel.h"\n'
new = '#include "llvm/Support/CodeGen.h"\n'
if old not in text:
    raise SystemExit("obsolete CodeGenOptLevel.h include not found in PIC14.h")
header.write_text(text.replace(old, new, 1))
print("PIC14 CodeGenOptLevel include fixed for LLVM 23.1")
