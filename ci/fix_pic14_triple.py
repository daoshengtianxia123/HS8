#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
triple_cpp = root / "llvm" / "lib" / "TargetParser" / "Triple.cpp"
text = triple_cpp.read_text()

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
section = section.replace(
    needle,
    "  case Triple::avr:\n  case Triple::pic14:\n",
    1,
)
text = text[:start] + section + text[end:]
triple_cpp.write_text(text)

print("PIC14 Triple default object format mapped with AVR/ELF bootstrap path")
