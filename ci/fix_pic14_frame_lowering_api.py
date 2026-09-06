#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
header = root / "llvm" / "lib" / "Target" / "PIC14" / "PIC14FrameLowering.h"
text = header.read_text()
old = "  bool hasFP(const MachineFunction &MF) const override { return false; }\n"
new = "  bool hasFPImpl(const MachineFunction &MF) const override { return false; }\n"
if old not in text:
    raise SystemExit("PIC14FrameLowering LLVM 23.1 hasFP fix pattern not found")
header.write_text(text.replace(old, new, 1))
print("PIC14 TargetFrameLowering hasFPImpl API fixed for LLVM 23.1")
