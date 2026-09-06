#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
llvm = root / "llvm"


def replace_once(path, old, new):
    p = Path(path)
    text = p.read_text()
    if old not in text:
        raise SystemExit(f"pattern not found in {p}: {old!r}")
    p.write_text(text.replace(old, new, 1))


# ---------------------------------------------------------------------------
# Triple registration
# ---------------------------------------------------------------------------
triple_h = llvm / "include/llvm/TargetParser/Triple.h"
replace_once(
    triple_h,
    '    avr,         // AVR: Atmel AVR microcontroller\n',
    '    avr,         // AVR: Atmel AVR microcontroller\n'
    '    pic14,       // PIC14: classic 14-bit mid-range PIC (PIC16F687)\n',
)

triple_cpp = llvm / "lib/TargetParser/Triple.cpp"
replace_once(
    triple_cpp,
    '  case avr:\n    return "avr";\n',
    '  case avr:\n    return "avr";\n'
    '  case pic14:\n    return "pic14";\n',
)
replace_once(
    triple_cpp,
    '          .Case("avr", Triple::avr)\n',
    '          .Case("avr", Triple::avr)\n'
    '          .Case("pic14", Triple::pic14)\n',
)

base = llvm / "lib/Target/PIC14"
(base / "TargetInfo").mkdir(parents=True, exist_ok=True)
(base / "MCTargetDesc").mkdir(parents=True, exist_ok=True)

files = {
"CMakeLists.txt": r'''add_llvm_component_group(PIC14)

set(LLVM_TARGET_DEFINITIONS PIC14.td)

tablegen(LLVM PIC14GenAsmWriter.inc -gen-asm-writer)
tablegen(LLVM PIC14GenCallingConv.inc -gen-callingconv)
tablegen(LLVM PIC14GenDAGISel.inc -gen-dag-isel)
tablegen(LLVM PIC14GenInstrInfo.inc -gen-instr-info)
tablegen(LLVM PIC14GenRegisterInfo.inc -gen-register-info)
tablegen(LLVM PIC14GenSubtargetInfo.inc -gen-subtarget)

add_public_tablegen_target(PIC14CommonTableGen)

add_llvm_target(PIC14CodeGen
  PIC14AsmPrinter.cpp
  PIC14FrameLowering.cpp
  PIC14ISelDAGToDAG.cpp
  PIC14ISelLowering.cpp
  PIC14InstrInfo.cpp
  PIC14RegisterInfo.cpp
  PIC14Subtarget.cpp
  PIC14TargetMachine.cpp

  LINK_COMPONENTS
  Analysis
  AsmPrinter
  CodeGen
  CodeGenTypes
  Core
  MC
  PIC14Desc
  PIC14Info
  SelectionDAG
  Support
  Target
  TargetParser
  TransformUtils

  ADD_TO_COMPONENT
  PIC14
  )

add_subdirectory(MCTargetDesc)
add_subdirectory(TargetInfo)
''',

"PIC14.td": r'''include "llvm/Target/Target.td"

class Proc<string Name, list<SubtargetFeature> Features>
    : Processor<Name, NoItineraries, Features>;

def : Proc<"generic", []>;
def : Proc<"pic16f687", []>;

include "PIC14RegisterInfo.td"
include "PIC14CallingConv.td"
include "PIC14InstrInfo.td"

defm : RemapAllTargetPseudoPointerOperands<PTRREG>;

def PIC14InstrInfo : InstrInfo;

def PIC14AsmWriter : AsmWriter {
  string AsmWriterClassName = "InstPrinter";
}

def PIC14 : Target {
  let InstructionSet = PIC14InstrInfo;
  let AssemblyWriters = [PIC14AsmWriter];
}
''',

"PIC14RegisterInfo.td": r'''class PIC14Reg<string n> : Register<n> {
  let Namespace = "PIC14";
}

// PIC16F687 classic mid-range machine state.
// RAM file registers are deliberately NOT modeled as LLVM GPRs.
def W      : PIC14Reg<"W">;
def STATUS : PIC14Reg<"STATUS">;
def FSR    : PIC14Reg<"FSR">;
def INDF   : PIC14Reg<"INDF">;
def PCL    : PIC14Reg<"PCL">;
def PCLATH : PIC14Reg<"PCLATH">;

// W is the only ordinary i8 accumulator register class.
def WREG   : RegisterClass<"PIC14", [i8], 8, (add W)>;

// Mechanical mapping required by generic LLVM pointer pseudos. FSR remains
// reserved from normal allocation; real FSR/INDF/IRP lowering is milestone M7.
def PTRREG : RegisterClass<"PIC14", [i8], 8, (add FSR)>;
''',

"PIC14CallingConv.td": r'''// No callee-saved LLVM GPRs: W is volatile accumulator state.
def CSR_PIC14_NoRegs : CalleeSavedRegs<(add)>;

// First bring-up return convention: an i8 result is carried in W.
def RetCC_PIC14 : CallingConv<[
  CCIfType<[i8], CCAssignToReg<[W]>>
]>;
''',

"PIC14InstrInfo.td": r'''def PIC14ret : SDNode<"PIC14ISD::RET_GLUE", SDTNone,
                         [SDNPHasChain, SDNPOptInGlue, SDNPVariadic]>;

class PIC14Inst<dag outs, dag ins, string asmstr, list<dag> pattern = []>
    : Instruction {
  let Namespace = "PIC14";
  let OutOperandList = outs;
  let InOperandList = ins;
  let AsmString = asmstr;
  let Pattern = pattern;
  // PIC16F687 instructions are 14-bit words; LLVM size is tracked in bytes.
  let Size = 2;
}

// M1 core instructions. W is an explicit MachineInstr def even though it is
// omitted from the textual PIC assembly syntax.
def MOVLW : PIC14Inst<
    (outs WREG:$dst), (ins i8imm:$k), "movlw\t$k",
    [(set WREG:$dst, (i8 imm:$k))]>;

// RETLW is kept as a real instruction for the later MOVLW+RETURN combine.
let isReturn = 1, isTerminator = 1, isBarrier = 1 in
def RETLW : PIC14Inst<(outs WREG:$dst), (ins i8imm:$k), "retlw\t$k", []>;

let isReturn = 1, isTerminator = 1, isBarrier = 1 in
def RETURN : PIC14Inst<(outs), (ins), "return", [(PIC14ret)]>;
''',

"PIC14.h": r'''#ifndef LLVM_LIB_TARGET_PIC14_PIC14_H
#define LLVM_LIB_TARGET_PIC14_PIC14_H

#include "llvm/CodeGen/CodeGenOptLevel.h"

namespace llvm {
class FunctionPass;
class PassRegistry;
class PIC14TargetMachine;

FunctionPass *createPIC14ISelDag(PIC14TargetMachine &TM,
                                 CodeGenOptLevel OptLevel);
void initializePIC14DAGToDAGISelLegacyPass(PassRegistry &);
void initializePIC14AsmPrinterPass(PassRegistry &);
} // namespace llvm

#endif
''',

"PIC14RegisterInfo.h": r'''#ifndef LLVM_LIB_TARGET_PIC14_PIC14REGISTERINFO_H
#define LLVM_LIB_TARGET_PIC14_PIC14REGISTERINFO_H

#include "llvm/CodeGen/TargetRegisterInfo.h"

#define GET_REGINFO_HEADER
#include "PIC14GenRegisterInfo.inc"

namespace llvm {
class PIC14RegisterInfo : public PIC14GenRegisterInfo {
public:
  PIC14RegisterInfo();

  const MCPhysReg *getCalleeSavedRegs(const MachineFunction *MF) const override;
  const uint32_t *getCallPreservedMask(const MachineFunction &MF,
                                       CallingConv::ID CC) const override;
  BitVector getReservedRegs(const MachineFunction &MF) const override;
  const TargetRegisterClass *getPointerRegClass(unsigned Kind = 0) const override;

  bool eliminateFrameIndex(MachineBasicBlock::iterator II, int SPAdj,
                           unsigned FIOperandNum,
                           RegScavenger *RS = nullptr) const override;
  Register getFrameRegister(const MachineFunction &MF) const override;
};
} // namespace llvm

#endif
''',

"PIC14RegisterInfo.cpp": r'''#include "PIC14RegisterInfo.h"
#include "PIC14.h"
#include "llvm/ADT/BitVector.h"
#include "llvm/CodeGen/MachineFunction.h"
#include "llvm/Support/ErrorHandling.h"

using namespace llvm;

#define GET_REGINFO_TARGET_DESC
#include "PIC14GenRegisterInfo.inc"

PIC14RegisterInfo::PIC14RegisterInfo() : PIC14GenRegisterInfo(0) {}

const MCPhysReg *
PIC14RegisterInfo::getCalleeSavedRegs(const MachineFunction *) const {
  return PIC14::CSR_PIC14_NoRegs_SaveList;
}

const uint32_t *PIC14RegisterInfo::getCallPreservedMask(
    const MachineFunction &, CallingConv::ID) const {
  return PIC14::CSR_PIC14_NoRegs_RegMask;
}

BitVector PIC14RegisterInfo::getReservedRegs(const MachineFunction &) const {
  BitVector Reserved(getNumRegs());
  Reserved.set(PIC14::STATUS);
  Reserved.set(PIC14::FSR);
  Reserved.set(PIC14::INDF);
  Reserved.set(PIC14::PCL);
  Reserved.set(PIC14::PCLATH);
  return Reserved;
}

const TargetRegisterClass *
PIC14RegisterInfo::getPointerRegClass(unsigned) const {
  return &PIC14::PTRREGRegClass;
}

bool PIC14RegisterInfo::eliminateFrameIndex(MachineBasicBlock::iterator,
                                            int, unsigned, RegScavenger *) const {
  report_fatal_error("PIC14 frame-index lowering is not implemented before M3");
}

Register PIC14RegisterInfo::getFrameRegister(const MachineFunction &) const {
  // FSR is the closest target address register, but it is reserved and is not
  // a C runtime stack pointer. Static frame lowering replaces this in M3.
  return PIC14::FSR;
}
''',

"PIC14InstrInfo.h": r'''#ifndef LLVM_LIB_TARGET_PIC14_PIC14INSTRINFO_H
#define LLVM_LIB_TARGET_PIC14_PIC14INSTRINFO_H

#include "PIC14RegisterInfo.h"
#include "llvm/CodeGen/TargetInstrInfo.h"

#define GET_INSTRINFO_HEADER
#include "PIC14GenInstrInfo.inc"

namespace llvm {
class PIC14Subtarget;

class PIC14InstrInfo : public PIC14GenInstrInfo {
  PIC14RegisterInfo RI;
public:
  explicit PIC14InstrInfo(const PIC14Subtarget &STI);
  const PIC14RegisterInfo &getRegisterInfo() const { return RI; }
};
} // namespace llvm

#endif
''',

"PIC14InstrInfo.cpp": r'''#include "PIC14InstrInfo.h"
#include "PIC14Subtarget.h"

using namespace llvm;

#define GET_INSTRINFO_CTOR_DTOR
#include "PIC14GenInstrInfo.inc"

PIC14InstrInfo::PIC14InstrInfo(const PIC14Subtarget &STI)
    : PIC14GenInstrInfo(STI, RI, 0, 0), RI() {}
''',

"PIC14FrameLowering.h": r'''#ifndef LLVM_LIB_TARGET_PIC14_PIC14FRAMELOWERING_H
#define LLVM_LIB_TARGET_PIC14_PIC14FRAMELOWERING_H

#include "llvm/CodeGen/TargetFrameLowering.h"

namespace llvm {
class PIC14FrameLowering : public TargetFrameLowering {
public:
  PIC14FrameLowering();

  void emitPrologue(MachineFunction &MF, MachineBasicBlock &MBB) const override;
  void emitEpilogue(MachineFunction &MF, MachineBasicBlock &MBB) const override;
  bool hasFP(const MachineFunction &MF) const override { return false; }
};
} // namespace llvm

#endif
''',

"PIC14FrameLowering.cpp": r'''#include "PIC14FrameLowering.h"
#include "llvm/CodeGen/MachineFunction.h"

using namespace llvm;

PIC14FrameLowering::PIC14FrameLowering()
    : TargetFrameLowering(TargetFrameLowering::StackGrowsDown, Align(1), 0) {}

void PIC14FrameLowering::emitPrologue(MachineFunction &,
                                      MachineBasicBlock &) const {}
void PIC14FrameLowering::emitEpilogue(MachineFunction &,
                                      MachineBasicBlock &) const {}
''',

"PIC14ISelLowering.h": r'''#ifndef LLVM_LIB_TARGET_PIC14_PIC14ISELLOWERING_H
#define LLVM_LIB_TARGET_PIC14_PIC14ISELLOWERING_H

#include "llvm/CodeGen/SelectionDAG.h"
#include "llvm/CodeGen/TargetLowering.h"

namespace llvm {
class PIC14Subtarget;

namespace PIC14ISD {
enum NodeType : unsigned {
  FIRST_NUMBER = ISD::BUILTIN_OP_END,
  RET_GLUE
};
}

class PIC14TargetLowering : public TargetLowering {
public:
  PIC14TargetLowering(const TargetMachine &TM, const PIC14Subtarget &STI);

private:
  SDValue LowerFormalArguments(
      SDValue Chain, CallingConv::ID CallConv, bool IsVarArg,
      const SmallVectorImpl<ISD::InputArg> &Ins, const SDLoc &DL,
      SelectionDAG &DAG, SmallVectorImpl<SDValue> &InVals) const override;

  SDValue LowerCall(TargetLowering::CallLoweringInfo &CLI,
                    SmallVectorImpl<SDValue> &InVals) const override;

  bool CanLowerReturn(CallingConv::ID CallConv, MachineFunction &MF,
                      bool IsVarArg,
                      const SmallVectorImpl<ISD::OutputArg> &Outs,
                      LLVMContext &Context, const Type *RetTy) const override;

  SDValue LowerReturn(SDValue Chain, CallingConv::ID CallConv, bool IsVarArg,
                      const SmallVectorImpl<ISD::OutputArg> &Outs,
                      const SmallVectorImpl<SDValue> &OutVals,
                      const SDLoc &DL, SelectionDAG &DAG) const override;
};
} // namespace llvm

#endif
''',

"PIC14ISelLowering.cpp": r'''#include "PIC14ISelLowering.h"
#include "PIC14Subtarget.h"
#include "llvm/CodeGen/MachineFunction.h"
#include "llvm/Support/ErrorHandling.h"

using namespace llvm;

PIC14TargetLowering::PIC14TargetLowering(const TargetMachine &TM,
                                         const PIC14Subtarget &STI)
    : TargetLowering(TM) {
  addRegisterClass(MVT::i8, &PIC14::WREGRegClass);
  computeRegisterProperties(STI.getRegisterInfo());
}

SDValue PIC14TargetLowering::LowerFormalArguments(
    SDValue Chain, CallingConv::ID, bool IsVarArg,
    const SmallVectorImpl<ISD::InputArg> &Ins, const SDLoc &,
    SelectionDAG &, SmallVectorImpl<SDValue> &) const {
  if (IsVarArg)
    report_fatal_error("PIC14 varargs are not supported");
  if (!Ins.empty())
    report_fatal_error("PIC14 M1 real pipeline currently accepts no arguments");
  return Chain;
}

SDValue PIC14TargetLowering::LowerCall(TargetLowering::CallLoweringInfo &,
                                       SmallVectorImpl<SDValue> &) const {
  report_fatal_error("PIC14 calls are introduced in milestone M5");
}

bool PIC14TargetLowering::CanLowerReturn(
    CallingConv::ID, MachineFunction &, bool IsVarArg,
    const SmallVectorImpl<ISD::OutputArg> &Outs, LLVMContext &,
    const Type *) const {
  if (IsVarArg || Outs.size() > 1)
    return false;
  return Outs.empty() || Outs[0].VT == MVT::i8;
}

SDValue PIC14TargetLowering::LowerReturn(
    SDValue Chain, CallingConv::ID, bool IsVarArg,
    const SmallVectorImpl<ISD::OutputArg> &Outs,
    const SmallVectorImpl<SDValue> &OutVals, const SDLoc &DL,
    SelectionDAG &DAG) const {
  if (IsVarArg || Outs.size() > 1)
    report_fatal_error("unsupported PIC14 return convention");

  SmallVector<SDValue, 4> RetOps;
  RetOps.push_back(Chain);
  SDValue Glue;

  if (!Outs.empty()) {
    if (Outs[0].VT != MVT::i8)
      report_fatal_error("PIC14 M1 only supports i8 return values");
    Chain = DAG.getCopyToReg(Chain, DL, PIC14::W, OutVals[0], Glue);
    Glue = Chain.getValue(1);
    RetOps[0] = Chain;
    RetOps.push_back(DAG.getRegister(PIC14::W, MVT::i8));
    RetOps.push_back(Glue);
  }

  return DAG.getNode(PIC14ISD::RET_GLUE, DL, MVT::Other, RetOps);
}
''',

"PIC14Subtarget.h": r'''#ifndef LLVM_LIB_TARGET_PIC14_PIC14SUBTARGET_H
#define LLVM_LIB_TARGET_PIC14_PIC14SUBTARGET_H

#include "PIC14FrameLowering.h"
#include "PIC14ISelLowering.h"
#include "PIC14InstrInfo.h"
#include "llvm/CodeGen/TargetSubtargetInfo.h"

#define GET_SUBTARGETINFO_HEADER
#include "PIC14GenSubtargetInfo.inc"

namespace llvm {
class PIC14Subtarget : public PIC14GenSubtargetInfo {
  PIC14InstrInfo InstrInfo;
  PIC14TargetLowering TLInfo;
  PIC14FrameLowering FrameLowering;

public:
  PIC14Subtarget(const Triple &TT, const std::string &CPU,
                 const std::string &FS, const TargetMachine &TM);

  PIC14Subtarget &initializeSubtargetDependencies(StringRef CPU, StringRef FS);
  void ParseSubtargetFeatures(StringRef CPU, StringRef TuneCPU, StringRef FS);

  const PIC14InstrInfo *getInstrInfo() const override { return &InstrInfo; }
  const PIC14RegisterInfo *getRegisterInfo() const override {
    return &InstrInfo.getRegisterInfo();
  }
  const PIC14TargetLowering *getTargetLowering() const override {
    return &TLInfo;
  }
  const TargetFrameLowering *getFrameLowering() const override {
    return &FrameLowering;
  }
};
} // namespace llvm

#endif
''',

"PIC14Subtarget.cpp": r'''#include "PIC14Subtarget.h"

using namespace llvm;

#define GET_SUBTARGETINFO_TARGET_DESC
#define GET_SUBTARGETINFO_CTOR
#include "PIC14GenSubtargetInfo.inc"

PIC14Subtarget &PIC14Subtarget::initializeSubtargetDependencies(StringRef CPU,
                                                                StringRef FS) {
  StringRef CPUName = CPU.empty() ? StringRef("pic16f687") : CPU;
  ParseSubtargetFeatures(CPUName, CPUName, FS);
  return *this;
}

PIC14Subtarget::PIC14Subtarget(const Triple &TT, const std::string &CPU,
                               const std::string &FS, const TargetMachine &TM)
    : PIC14GenSubtargetInfo(TT, CPU, CPU, FS),
      InstrInfo(initializeSubtargetDependencies(CPU, FS)), TLInfo(TM, *this),
      FrameLowering() {}
''',

"PIC14TargetMachine.h": r'''#ifndef LLVM_LIB_TARGET_PIC14_PIC14TARGETMACHINE_H
#define LLVM_LIB_TARGET_PIC14_PIC14TARGETMACHINE_H

#include "PIC14Subtarget.h"
#include "llvm/CodeGen/CodeGenTargetMachineImpl.h"
#include <optional>

namespace llvm {
class PIC14TargetMachine : public CodeGenTargetMachineImpl {
  std::unique_ptr<TargetLoweringObjectFile> TLOF;
  PIC14Subtarget Subtarget;

public:
  PIC14TargetMachine(const Target &T, const Triple &TT, StringRef CPU,
                     StringRef FS, const TargetOptions &Options,
                     std::optional<Reloc::Model> RM,
                     std::optional<CodeModel::Model> CM,
                     CodeGenOptLevel OL, bool JIT);
  ~PIC14TargetMachine() override;

  const PIC14Subtarget *getSubtargetImpl(const Function &) const override {
    return &Subtarget;
  }
  TargetPassConfig *createPassConfig(PassManagerBase &PM) override;
  TargetLoweringObjectFile *getObjFileLowering() const override {
    return TLOF.get();
  }
};
} // namespace llvm

#endif
''',

"PIC14TargetMachine.cpp": r'''#include "PIC14TargetMachine.h"
#include "PIC14.h"
#include "TargetInfo/PIC14TargetInfo.h"
#include "llvm/CodeGen/TargetLoweringObjectFileImpl.h"
#include "llvm/CodeGen/TargetPassConfig.h"
#include "llvm/MC/TargetRegistry.h"
#include "llvm/Support/Compiler.h"

using namespace llvm;

extern "C" LLVM_ABI LLVM_EXTERNAL_VISIBILITY void LLVMInitializePIC14Target() {
  RegisterTargetMachine<PIC14TargetMachine> X(getThePIC14Target());
  PassRegistry &PR = *PassRegistry::getPassRegistry();
  initializePIC14AsmPrinterPass(PR);
  initializePIC14DAGToDAGISelLegacyPass(PR);
}

static Reloc::Model getEffectiveRelocModel(std::optional<Reloc::Model> RM) {
  return RM.value_or(Reloc::Static);
}

PIC14TargetMachine::PIC14TargetMachine(
    const Target &T, const Triple &TT, StringRef CPU, StringRef FS,
    const TargetOptions &Options, std::optional<Reloc::Model> RM,
    std::optional<CodeModel::Model> CM, CodeGenOptLevel OL, bool)
    : CodeGenTargetMachineImpl(T, "e-p:8:8-i8:8-n8", TT, CPU, FS, Options,
                               getEffectiveRelocModel(RM),
                               getEffectiveCodeModel(CM, CodeModel::Small), OL),
      TLOF(std::make_unique<TargetLoweringObjectFileELF>()),
      Subtarget(TT, std::string(CPU), std::string(FS), *this) {
  initAsmInfo();
}

PIC14TargetMachine::~PIC14TargetMachine() = default;

namespace {
class PIC14PassConfig : public TargetPassConfig {
public:
  PIC14PassConfig(PIC14TargetMachine &TM, PassManagerBase &PM)
      : TargetPassConfig(TM, PM) {}

  PIC14TargetMachine &getPIC14TargetMachine() const {
    return getTM<PIC14TargetMachine>();
  }

  bool addInstSelector() override {
    addPass(createPIC14ISelDag(getPIC14TargetMachine(), getOptLevel()));
    return false;
  }
};
} // namespace

TargetPassConfig *PIC14TargetMachine::createPassConfig(PassManagerBase &PM) {
  return new PIC14PassConfig(*this, PM);
}
''',

"PIC14ISelDAGToDAG.cpp": r'''#include "PIC14.h"
#include "PIC14TargetMachine.h"
#include "llvm/CodeGen/SelectionDAGISel.h"
#include "llvm/InitializePasses.h"
#include "llvm/PassRegistry.h"

using namespace llvm;

#define DEBUG_TYPE "pic14-isel"
#define PASS_NAME "PIC14 DAG->DAG Pattern Instruction Selection"

namespace {
class PIC14DAGToDAGISel : public SelectionDAGISel {
public:
  PIC14DAGToDAGISel(PIC14TargetMachine &TM, CodeGenOptLevel OptLevel)
      : SelectionDAGISel(TM, OptLevel) {}

private:
#include "PIC14GenDAGISel.inc"

  void Select(SDNode *N) override {
    if (N->isMachineOpcode()) {
      N->setNodeId(-1);
      return;
    }
    SelectCode(N);
  }
};

class PIC14DAGToDAGISelLegacy : public SelectionDAGISelLegacy {
public:
  static char ID;
  PIC14DAGToDAGISelLegacy(PIC14TargetMachine &TM, CodeGenOptLevel OptLevel)
      : SelectionDAGISelLegacy(
            ID, std::make_unique<PIC14DAGToDAGISel>(TM, OptLevel)) {}
};
} // namespace

char PIC14DAGToDAGISelLegacy::ID;
INITIALIZE_PASS(PIC14DAGToDAGISelLegacy, DEBUG_TYPE, PASS_NAME, false, false)

FunctionPass *llvm::createPIC14ISelDag(PIC14TargetMachine &TM,
                                       CodeGenOptLevel OptLevel) {
  return new PIC14DAGToDAGISelLegacy(TM, OptLevel);
}
''',

"PIC14AsmPrinter.cpp": r'''#include "PIC14.h"
#include "MCTargetDesc/PIC14MCTargetDesc.h"
#include "PIC14TargetMachine.h"
#include "TargetInfo/PIC14TargetInfo.h"
#include "llvm/CodeGen/AsmPrinter.h"
#include "llvm/CodeGen/MachineInstr.h"
#include "llvm/MC/MCInst.h"
#include "llvm/MC/MCStreamer.h"
#include "llvm/MC/TargetRegistry.h"
#include "llvm/Support/Compiler.h"

using namespace llvm;

namespace {
class PIC14AsmPrinter : public AsmPrinter {
public:
  static char ID;
  PIC14AsmPrinter(TargetMachine &TM, std::unique_ptr<MCStreamer> Streamer)
      : AsmPrinter(TM, std::move(Streamer), ID) {}

  StringRef getPassName() const override { return "PIC14 Assembly Printer"; }

  void emitInstruction(const MachineInstr *MI) override {
    MCInst Out;
    Out.setOpcode(MI->getOpcode());
    for (const MachineOperand &MO : MI->operands()) {
      if (MO.isImplicit())
        continue;
      if (MO.isReg())
        Out.addOperand(MCOperand::createReg(MO.getReg()));
      else if (MO.isImm())
        Out.addOperand(MCOperand::createImm(MO.getImm()));
      else
        report_fatal_error("PIC14 M1 AsmPrinter encountered unsupported operand");
    }
    EmitToStreamer(*OutStreamer, Out);
  }
};
} // namespace

char PIC14AsmPrinter::ID = 0;
INITIALIZE_PASS(PIC14AsmPrinter, "pic14-asm-printer",
                "PIC14 Assembly Printer", false, false)

extern "C" LLVM_ABI LLVM_EXTERNAL_VISIBILITY void
LLVMInitializePIC14AsmPrinter() {
  RegisterAsmPrinter<PIC14AsmPrinter> X(getThePIC14Target());
}
''',

"MCTargetDesc/CMakeLists.txt": r'''add_llvm_component_library(LLVMPIC14Desc
  PIC14InstPrinter.cpp
  PIC14MCAsmInfo.cpp
  PIC14MCTargetDesc.cpp

  LINK_COMPONENTS
  MC
  PIC14Info
  Support
  TargetParser

  ADD_TO_COMPONENT
  PIC14
  )
''',

"MCTargetDesc/PIC14MCTargetDesc.h": r'''#ifndef LLVM_LIB_TARGET_PIC14_MCTARGETDESC_PIC14MCTARGETDESC_H
#define LLVM_LIB_TARGET_PIC14_MCTARGETDESC_PIC14MCTARGETDESC_H

namespace llvm {
class Target;
}

#define GET_REGINFO_ENUM
#include "PIC14GenRegisterInfo.inc"

#define GET_INSTRINFO_ENUM
#include "PIC14GenInstrInfo.inc"

#define GET_SUBTARGETINFO_ENUM
#include "PIC14GenSubtargetInfo.inc"

#endif
''',

"MCTargetDesc/PIC14MCAsmInfo.h": r'''#ifndef LLVM_LIB_TARGET_PIC14_MCTARGETDESC_PIC14MCASMINFO_H
#define LLVM_LIB_TARGET_PIC14_MCTARGETDESC_PIC14MCASMINFO_H

#include "llvm/MC/MCAsmInfoELF.h"

namespace llvm {
class Triple;
class PIC14MCAsmInfo : public MCAsmInfoELF {
public:
  PIC14MCAsmInfo(const Triple &TT, const MCTargetOptions &Options);
};
} // namespace llvm

#endif
''',

"MCTargetDesc/PIC14MCAsmInfo.cpp": r'''#include "PIC14MCAsmInfo.h"
#include "llvm/TargetParser/Triple.h"

using namespace llvm;

PIC14MCAsmInfo::PIC14MCAsmInfo(const Triple &, const MCTargetOptions &Options)
    : MCAsmInfoELF(Options) {
  CodePointerSize = 2;
  CalleeSaveStackSlotSize = 1;
  MinInstAlignment = Align(1);
  MaxInstLength = 2;
  CommentString = ";";
}
''',

"MCTargetDesc/PIC14InstPrinter.h": r'''#ifndef LLVM_LIB_TARGET_PIC14_MCTARGETDESC_PIC14INSTPRINTER_H
#define LLVM_LIB_TARGET_PIC14_MCTARGETDESC_PIC14INSTPRINTER_H

#include "llvm/MC/MCInstPrinter.h"

namespace llvm {
class PIC14InstPrinter : public MCInstPrinter {
public:
  PIC14InstPrinter(const MCAsmInfo &MAI, const MCInstrInfo &MII,
                   const MCRegisterInfo &MRI)
      : MCInstPrinter(MAI, MII, MRI) {}

  void printRegName(raw_ostream &O, MCRegister Reg) override;
  void printInst(const MCInst *MI, uint64_t Address, StringRef Annot,
                 const MCSubtargetInfo &STI, raw_ostream &O) override;

  std::pair<const char *, uint64_t>
  getMnemonic(const MCInst &MI) const override;
  void printInstruction(const MCInst *MI, uint64_t Address, raw_ostream &O);
  bool printAliasInstr(const MCInst *MI, uint64_t Address, raw_ostream &O);
  void printCustomAliasOperand(const MCInst *MI, uint64_t Address,
                               unsigned OpIdx, unsigned PrintMethodIdx,
                               raw_ostream &O);
  static const char *getRegisterName(MCRegister Reg);

private:
  void printOperand(const MCInst *MI, unsigned OpNo, raw_ostream &O);
};
} // namespace llvm

#endif
''',

"MCTargetDesc/PIC14InstPrinter.cpp": r'''#include "PIC14InstPrinter.h"
#include "PIC14MCTargetDesc.h"
#include "llvm/MC/MCInst.h"
#include "llvm/MC/MCSubtargetInfo.h"
#include "llvm/Support/ErrorHandling.h"

using namespace llvm;

#define PRINT_ALIAS_INSTR
#include "PIC14GenAsmWriter.inc"

void PIC14InstPrinter::printRegName(raw_ostream &O, MCRegister Reg) {
  O << getRegisterName(Reg);
}

void PIC14InstPrinter::printInst(const MCInst *MI, uint64_t Address,
                                 StringRef Annot, const MCSubtargetInfo &,
                                 raw_ostream &O) {
  if (!printAliasInstr(MI, Address, O))
    printInstruction(MI, Address, O);
  printAnnotation(O, Annot);
}

void PIC14InstPrinter::printOperand(const MCInst *MI, unsigned OpNo,
                                    raw_ostream &O) {
  const MCOperand &Op = MI->getOperand(OpNo);
  if (Op.isReg())
    O << getRegisterName(Op.getReg());
  else if (Op.isImm())
    O << Op.getImm();
  else
    llvm_unreachable("PIC14 M1 unsupported MC operand");
}
''',

"MCTargetDesc/PIC14MCTargetDesc.cpp": r'''#include "PIC14MCTargetDesc.h"
#include "PIC14InstPrinter.h"
#include "PIC14MCAsmInfo.h"
#include "TargetInfo/PIC14TargetInfo.h"
#include "llvm/MC/MCInstrInfo.h"
#include "llvm/MC/MCRegisterInfo.h"
#include "llvm/MC/MCSubtargetInfo.h"
#include "llvm/MC/TargetRegistry.h"
#include "llvm/Support/Compiler.h"

using namespace llvm;

#define GET_INSTRINFO_MC_DESC
#include "PIC14GenInstrInfo.inc"

#define GET_SUBTARGETINFO_MC_DESC
#include "PIC14GenSubtargetInfo.inc"

#define GET_REGINFO_MC_DESC
#include "PIC14GenRegisterInfo.inc"

static MCInstrInfo *createPIC14MCInstrInfo() {
  auto *X = new MCInstrInfo();
  InitPIC14MCInstrInfo(X);
  return X;
}

static MCRegisterInfo *createPIC14MCRegisterInfo(const Triple &) {
  auto *X = new MCRegisterInfo();
  InitPIC14MCRegisterInfo(X, 0);
  return X;
}

static MCAsmInfo *createPIC14MCAsmInfo(const MCRegisterInfo &, const Triple &TT,
                                       const MCTargetOptions &Options) {
  return new PIC14MCAsmInfo(TT, Options);
}

static MCSubtargetInfo *createPIC14MCSubtargetInfo(const Triple &TT,
                                                   StringRef CPU,
                                                   StringRef FS) {
  if (CPU.empty())
    CPU = "pic16f687";
  return createPIC14MCSubtargetInfoImpl(TT, CPU, CPU, FS);
}

static MCInstPrinter *createPIC14MCInstPrinter(const Triple &, unsigned Syntax,
                                               const MCAsmInfo &MAI,
                                               const MCInstrInfo &MII,
                                               const MCRegisterInfo &MRI) {
  if (Syntax == 0)
    return new PIC14InstPrinter(MAI, MII, MRI);
  return nullptr;
}

extern "C" LLVM_ABI LLVM_EXTERNAL_VISIBILITY void LLVMInitializePIC14TargetMC() {
  Target &T = getThePIC14Target();
  TargetRegistry::RegisterMCAsmInfo(T, createPIC14MCAsmInfo);
  TargetRegistry::RegisterMCInstrInfo(T, createPIC14MCInstrInfo);
  TargetRegistry::RegisterMCRegInfo(T, createPIC14MCRegisterInfo);
  TargetRegistry::RegisterMCSubtargetInfo(T, createPIC14MCSubtargetInfo);
  TargetRegistry::RegisterMCInstPrinter(T, createPIC14MCInstPrinter);
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
namespace llvm {
class Target;
Target &getThePIC14Target();
}
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
    path = base / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)

print("PIC14 real SelectionDAG M1 overlay applied")
