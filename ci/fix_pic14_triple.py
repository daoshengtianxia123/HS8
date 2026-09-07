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

# LLVM generic code asks Triple::isArch16Bit() before entering the target
# pipeline. PIC14 program addresses/instructions are 14-bit-word based, but
# LLVM's architecture-width classification has no 14-bit category; classify
# the target with the other <=16-bit MCU architectures so generic TLI does not
# hit llvm_unreachable(). This does not make RAM a 16-bit GPR address space.
fn_marker = "bool Triple::isArch16Bit() const {"
fn_start = text.find(fn_marker)
if fn_start < 0:
    raise SystemExit("Triple::isArch16Bit() not found in Triple.cpp")
fn_end = text.find("\n}\n", fn_start)
if fn_end < 0:
    raise SystemExit("end of Triple::isArch16Bit() not found")
fn = text[fn_start:fn_end]
if "case Triple::pic14:" not in fn:
    avr = "  case Triple::avr:\n"
    if avr not in fn:
        raise SystemExit("AVR case not found in Triple::isArch16Bit()")
    fn = fn.replace(avr, avr + "  case Triple::pic14:\n", 1)
    text = text[:fn_start] + fn + text[fn_end:]

triple_cpp.write_text(text)
print("PIC14 Triple default object format and 16-bit architecture classification fixed")
