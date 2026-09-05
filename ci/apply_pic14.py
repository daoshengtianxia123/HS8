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

# Register the architecture in Triple. Keep the change intentionally small.
triple_h = llvm / "include/llvm/TargetParser/Triple.h"
replace_once(triple_h,
             '    avr,         // AVR: Atmel AVR microcontroller\n',
             '    avr,         // AVR: Atmel AVR microcontroller\n    pic14,       // PIC14: Microchip baseline/mid-range PIC14 core\n')

triple_cpp = llvm / "lib/TargetParser/Triple.cpp"
replace_once(triple_cpp,
             '  case avr:\n    return "avr";\n',
             '  case avr:\n    return "avr";\n  case pic14:\n    return "pic14";\n')
replace_once(triple_cpp,
             '          .Case("avr", Triple::avr)\n',
             '          .Case("avr", Triple::avr)\n          .Case("pic14", Triple::pic14)\n')

base = llvm / "lib/Target/PIC14"
(base / "TargetInfo").mkdir(parents=True, exist_ok=True)
(base / "MCTargetDesc").mkdir(parents=True, exist_ok=True)

files = {
"CMakeLists.txt": r'''add_llvm_component_group(PIC14)

set(LLVM_TARGET_DEFINITIONS PIC14.td)

tablegen(LLVM PIC14GenInstrInfo.inc -gen-instr-info)
tablegen(LLVM PIC14GenRegisterInfo.inc -gen-register-info)
tablegen(LLVM PIC14GenSubtargetInfo.inc -gen-subtarget)
tablegen(LLVM PIC14GenAsmWriter.inc -gen-asm-writer)

add_public_tablegen_target(PIC14CommonTableGen)

add_llvm_target(PIC14CodeGen
  PIC14TargetMachine.cpp

  LINK_COMPONENTS
  CodeGen
  Core
  MC
  PIC14Desc
  PIC14Info
  Support
  Target
  TargetParser

  ADD_TO_COMPONENT
  PIC14
  )

add_subdirectory(MCTargetDesc)
add_subdirectory(TargetInfo)
''',
"PIC14.td": r'''include "llvm/Target/Target.td"
include "PIC14RegisterInfo.td"
include "PIC14InstrInfo.td"

// LLVM 23 standard pseudos use PointerLikeRegClass operands. Every target
// must map those generic pointer operands to a concrete target register class.
defm : RemapAllTargetPseudoPointerOperands<PTRREG>;

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

def WREG   : RegisterClass<"PIC14", [i8], 8, (add W)>;
def PTRREG : RegisterClass<"PIC14", [i8], 8, (add FSR)>;
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
"PIC14TargetMachine.cpp": r'''//===-- PIC14TargetMachine.cpp - staged PIC14 bootstrap -------------------===//
#include "llvm/IR/Constants.h"
#include "llvm/IR/Function.h"
#include "llvm/IR/Instructions.h"
#include "llvm/IR/Module.h"
#include "llvm/Support/Compiler.h"
#include "llvm/Support/raw_ostream.h"

using namespace llvm;

// Stage-M1 bootstrap emitter.  This is intentionally narrow: it proves the
// target is selectable by the real llc driver and that an i8 constant return
// reaches the PIC14-specific emission path.  Subsequent milestones replace
// this with the normal TargetMachine/SelectionDAG pipeline.
bool llvm::emitPIC14BootstrapAssembly(const Module &M, raw_ostream &OS,
                                      std::string &Error) {
  bool EmittedAny = false;
  for (const Function &F : M) {
    if (F.isDeclaration())
      continue;
    if (!F.arg_empty() || !F.getReturnType()->isIntegerTy(8) || F.size() != 1) {
      Error = "PIC14 M1 bootstrap accepts only no-argument single-block i8 functions";
      return false;
    }

    const BasicBlock &BB = F.getEntryBlock();
    const auto *RI = dyn_cast<ReturnInst>(BB.getTerminator());
    const auto *CI = RI ? dyn_cast_or_null<ConstantInt>(RI->getReturnValue()) : nullptr;
    if (!CI || CI->getBitWidth() != 8) {
      Error = "PIC14 M1 bootstrap requires 'ret i8 <constant>'";
      return false;
    }

    OS << "\t.text\n";
    OS << "\t.globl\t" << F.getName() << "\n";
    OS << F.getName() << ":\n";
    OS << "\tretlw\t" << CI->getZExtValue() << "\n";
    EmittedAny = true;
  }

  if (!EmittedAny) {
    Error = "PIC14 M1 bootstrap found no function body to emit";
    return false;
  }
  return true;
}

extern "C" LLVM_ABI LLVM_EXTERNAL_VISIBILITY void LLVMInitializePIC14Target() {
  // Full TargetMachine registration follows in the next backend milestone.
}
''',
"MCTargetDesc/CMakeLists.txt": r'''add_llvm_component_library(LLVMPIC14Desc
  PIC14MCTargetDesc.cpp

  LINK_COMPONENTS
  MC
  PIC14Info
  Support

  ADD_TO_COMPONENT
  PIC14
  )
''',
"MCTargetDesc/PIC14MCTargetDesc.cpp": r'''#include "llvm/Support/Compiler.h"

extern "C" LLVM_ABI LLVM_EXTERNAL_VISIBILITY void LLVMInitializePIC14TargetMC() {
  // M1 only needs the symbol expected by InitializeAllTargetMCs().
}
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

# Route the first M1 acceptance through llc itself.  We bypass generic
# TargetMachine creation only for PIC14 while the full CodeGen pipeline is
# still under construction; all parsing, target selection flags and output
# handling remain in the production llc driver.
llc_cpp = llvm / "tools/llc/llc.cpp"
replace_once(
    llc_cpp,
    'using namespace llvm;\n\nstatic codegen::RegisterCodeGenFlags CGF;\n',
    'using namespace llvm;\n\nnamespace llvm {\n'
    'bool emitPIC14BootstrapAssembly(const Module &, raw_ostream &, std::string &);\n'
    '}\n\n'
    'static codegen::RegisterCodeGenFlags CGF;\n')

replace_once(
    llc_cpp,
    '    TheTriple = Triple(IRTargetTriple);\n    if (TheTriple.getTriple().empty())\n      TheTriple.setTriple(sys::getDefaultTargetTriple());\n\n    std::string Error;\n',
    '    if (codegen::getMArch() == "pic14" && TargetTriple.empty())\n'
    '      IRTargetTriple = "pic14-unknown-none";\n'
    '    TheTriple = Triple(IRTargetTriple);\n'
    '    if (TheTriple.getTriple().empty())\n'
    '      TheTriple.setTriple(sys::getDefaultTargetTriple());\n\n'
    '    if (TheTriple.getArch() == Triple::pic14)\n'
    '      return std::string("e-p:8:8-i8:8-n8");\n\n'
    '    std::string Error;\n')

replace_once(
    llc_cpp,
    '  if (!TargetTriple.empty())\n    M->setTargetTriple(Triple(Triple::normalize(TargetTriple)));\n\n  std::optional<CodeModel::Model> CM_IR = M->getCodeModel();\n',
    '  if (!TargetTriple.empty())\n'
    '    M->setTargetTriple(Triple(Triple::normalize(TargetTriple)));\n\n'
    '  if (TheTriple.getArch() == Triple::pic14) {\n'
    '    if (codegen::getFileType() != CodeGenFileType::AssemblyFile) {\n'
    '      WithColor::error(errs(), argv[0])\n'
    '          << "PIC14 M1 bootstrap currently supports assembly output only\\n";\n'
    '      return 1;\n'
    '    }\n'
    '    std::unique_ptr<ToolOutputFile> Out = GetOutputStream(TheTriple.getOS());\n'
    '    if (!Out)\n'
    '      return 1;\n'
    '    std::string PIC14Error;\n'
    '    if (!emitPIC14BootstrapAssembly(*M, Out->os(), PIC14Error)) {\n'
    '      WithColor::error(errs(), argv[0]) << PIC14Error << "\\n";\n'
    '      return 1;\n'
    '    }\n'
    '    OutputFilename = Out->outputFilename();\n'
    '    Out->keep();\n'
    '    return 0;\n'
    '  }\n\n'
    '  std::optional<CodeModel::Model> CM_IR = M->getCodeModel();\n')

print("PIC14 M0/M1 bootstrap overlay applied")
