#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
triple_cpp = root / "llvm" / "lib" / "TargetParser" / "Triple.cpp"
text = triple_cpp.read_text()

# PIC14 currently uses the AVR/ELF object-format bootstrap path.
start_marker = "static Triple::ObjectFormatType getDefaultFormat(const Triple &T) {"
end_marker = "\n}\n\nTriple::Triple"
start = text.find(start_marker)
if start < 0:
    raise SystemExit("getDefaultFormat() not found in Triple.cpp")
end = text.find(end_marker, start)
if end < 0:
    raise SystemExit("end of getDefaultFormat() not found in Triple.cpp")

section = text[start:end]
needle = "  case Triple::avr:\n"
if needle not in section:
    raise SystemExit("AVR case not found in getDefaultFormat()")
if "  case Triple::pic14:\n" not in section:
    section = section.replace(
        needle,
        "  case Triple::avr:\n  case Triple::pic14:\n",
        1,
    )
    text = text[:start] + section + text[end:]

# LLVM 23.1 implements isArch16Bit() via getArchPointerBitWidth(), so classify
# PIC14 with the <=16-bit MCU architectures there. This is only LLVM's generic
# architecture-width classification; it does not make PIC14 RAM a 16-bit GPR
# address space or change the classic mid-range W/FSR/INDF machine model.
fn_marker = "unsigned Triple::getArchPointerBitWidth(llvm::Triple::ArchType Arch) {"
fn_start = text.find(fn_marker)
if fn_start < 0:
    raise SystemExit("Triple::getArchPointerBitWidth() not found in Triple.cpp")
fn_end = text.find("\n}\n", fn_start)
if fn_end < 0:
    raise SystemExit("end of Triple::getArchPointerBitWidth() not found")
fn = text[fn_start:fn_end]
if "case llvm::Triple::pic14:" not in fn:
    avr = "  case llvm::Triple::avr:\n"
    if avr not in fn:
        raise SystemExit("AVR case not found in Triple::getArchPointerBitWidth()")
    fn = fn.replace(avr, avr + "  case llvm::Triple::pic14:\n", 1)
    text = text[:fn_start] + fn + text[fn_end:]

triple_cpp.write_text(text)
print("PIC14 Triple default object format and 16-bit architecture classification fixed")
