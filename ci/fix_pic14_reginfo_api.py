#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
base = root / "llvm" / "lib" / "Target" / "PIC14"

# LLVM 23.1 splits register enums/MC descriptors from the generated target
# register-info class.  Make those generated declarations visible before
# GET_REGINFO_TARGET_DESC is instantiated.
path = base / "PIC14RegisterInfo.cpp"
text = path.read_text()
needle = '#include "PIC14.h"\n'
insert = '#include "MCTargetDesc/PIC14MCTargetDesc.h"\n#include "llvm/CodeGen/TargetSubtargetInfo.h"\n'
if needle not in text:
    raise SystemExit("PIC14RegisterInfo.cpp include anchor not found")
if 'MCTargetDesc/PIC14MCTargetDesc.h' not in text:
    text = text.replace(needle, needle + insert, 1)

# Callee-saved arrays emitted by LLVM 23.1 are in namespace llvm, not PIC14.
text = text.replace('PIC14::CSR_PIC14_NoRegs_SaveList',
                    'CSR_PIC14_NoRegs_SaveList')
text = text.replace('PIC14::CSR_PIC14_NoRegs_RegMask',
                    'CSR_PIC14_NoRegs_RegMask')
path.write_text(text)

# Generated subtarget parsing uses LLVM_DEBUG and therefore needs DEBUG_TYPE
# defined before GET_SUBTARGETINFO_TARGET_DESC/CTOR is expanded.
path = base / "PIC14Subtarget.cpp"
text = path.read_text()
anchor = 'using namespace llvm;\n\n'
if anchor not in text:
    raise SystemExit("PIC14Subtarget.cpp DEBUG_TYPE anchor not found")
if '#define DEBUG_TYPE "pic14-subtarget"' not in text:
    text = text.replace(anchor,
                        anchor + '#define DEBUG_TYPE "pic14-subtarget"\n\n', 1)
path.write_text(text)

print("PIC14 LLVM 23.1 RegisterInfo generated declarations and DEBUG_TYPE fixed")
