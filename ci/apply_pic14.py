#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
llvm = root / "llvm"


def replace_once(path, old, new):
    p = Path(path)
    s = p.read_text()
    if old not in s:
        raise SystemExit(f"pattern not found in {p}: {old!r}")
    p.write_text(s.replace(old, new, 1))

# Register the architecture in Triple.  Keep the change intentionally small.
triple_h = llvm / "include/llvm/TargetParser/Triple.h"
replace_once(triple_h,
             '    avr,         // AVR: Atmel AVR microcontroller\n',
             '    avr,         // AVR: Atmel AVR microcontroller\n    pic14,       // PIC14: Microchip baseline/mid-range PIC14 core\n')

triple_cpp = llvm / "lib/TargetParser/Triple.cpp"
replace_once(triple_cpp,
             '  case avr:\n    return "avr";\n',
             '  case avr:\n    return "avr";\n  case pic14:\n    return "pic14";\n')

# parseArch is deliberately patched by a stable nearby entry used by LLVM 23.1.
replace_once(triple_cpp,
             '          .Case("avr", Triple::avr)\n',
             '          .Case("avr", Triple::avr)\n          .Case("pic14", Triple::pic14)\n')

base = llvm / "lib/Target/PIC14"
(base / "TargetInfo").mkdir(parents=True, exist_ok=True)

files = {
"CMakeLists.txt": r'''add_llvm_component_group(PIC14)

set(LLVM_TARGET_DEFINITIONS PIC14.td)

tablegen(LLVM PIC14GenInstrInfo.inc -gen-instr-info)
tablegen(LLVM PIC14GenRegisterInfo.inc -gen-register-info)
tablegen(LLVM PIC14GenSubtargetInfo.inc -gen-subtarget)
tablegen(LLVM PIC14GenAsmWriter.inc -gen-asm-writer)

add_public_tablegen_target(PIC14CommonTableGen)

add_subdirectory(TargetInfo)
''',
"PIC14.td": r'''include "llvm/Target/Target.td"
include "PIC14RegisterInfo.td"
include "PIC14InstrInfo.td"

def PIC14InstrInfo : InstrInfo;
def PIC14AsmParser : AsmParser;
def PIC14AsmWriter : AsmWriter;
def PIC14 : Target {
  let InstructionSet = PIC14InstrInfo;
  let AssemblyParsers = [PIC14AsmParser];
  let AssemblyWriters = [PIC14AsmWriter];
}
''',
"PIC14RegisterInfo.td": r'''class PIC14Reg<string n> : Register<n> {
  let Namespace = "PIC14";
}

def W      : PIC14Reg<"W">;
def STATUS : PIC14Reg<"STATUS">;
def FSR    : PIC14Reg<"FSR">;
def INDF   : PIC14Reg<"INDF">;
def PCL    : PIC14Reg<"PCL">;
def PCLATH : PIC14Reg<"PCLATH">;

def WREG : RegisterClass<"PIC14", [i8], 8, (add W)>;
''',
"PIC14InstrInfo.td": r'''class PIC14Inst<dag outs, dag ins, string asmstr, list<dag> pattern = []>
    : Instruction {
  let Namespace = "PIC14";
  let OutOperandList = outs;
  let InOperandList = ins;
  let AsmString = asmstr;
  let Pattern = pattern;
  let Size = 2;
}

let Defs = [W] in
def MOVLW : PIC14Inst<(outs), (ins i8imm:$k), "movlw\t$k">;

let Defs = [W], isReturn = 1, isTerminator = 1 in
def RETLW : PIC14Inst<(outs), (ins i8imm:$k), "retlw\t$k">;

let isReturn = 1, isTerminator = 1 in
def RETURN : PIC14Inst<(outs), (ins), "return">;
''',
"TargetInfo/CMakeLists.txt": r'''add_llvm_component_library(LLVMPIC14Info
  PIC14TargetInfo.cpp
  LINK_COMPONENTS
  MC
  Support
  TargetParser
  ADD_TO_COMPONENT
  PIC14
  )
''',
"TargetInfo/PIC14TargetInfo.h": r'''#ifndef LLVM_LIB_TARGET_PIC14_TARGETINFO_PIC14TARGETINFO_H
#define LLVM_LIB_TARGET_PIC14_TARGETINFO_PIC14TARGETINFO_H
namespace llvm { class Target; Target &getThePIC14Target(); }
#endif
''',
"TargetInfo/PIC14TargetInfo.cpp": r'''#include "PIC14TargetInfo.h"
#include "llvm/MC/TargetRegistry.h"
#include "llvm/Support/Compiler.h"
using namespace llvm;

Target &llvm::getThePIC14Target() {
  static Target ThePIC14Target;
  return ThePIC14Target;
}

extern "C" LLVM_ABI LLVM_EXTERNAL_VISIBILITY void LLVMInitializePIC14TargetInfo() {
  RegisterTarget<Triple::pic14> X(getThePIC14Target(), "pic14",
                                  "PIC14/PIC16F687 [experimental]", "PIC14");
}
''',
}

for rel, content in files.items():
    p = base / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)

print("PIC14 M0/M1 TableGen overlay applied")
