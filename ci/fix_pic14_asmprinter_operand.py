#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
path = root / "llvm" / "lib" / "Target" / "PIC14" / "PIC14AsmPrinter.cpp"
text = path.read_text()

old = '''    for (const MachineOperand &MO : MI->operands()) {
      if (MO.isImplicit())
        continue;
      if (MO.isReg())
        Out.addOperand(MCOperand::createReg(MO.getReg()));
      else if (MO.isImm())
        Out.addOperand(MCOperand::createImm(MO.getImm()));
      else
        report_fatal_error("PIC14 M1 AsmPrinter encountered unsupported operand");
    }
'''
new = '''    for (const MachineOperand &MO : MI->operands()) {
      // MachineOperand::isImplicit() is a register-only accessor in LLVM 23.
      // Test the operand kind first so immediates such as RETLW's literal do
      // not trip the assertion before MC lowering reaches the InstPrinter.
      if (MO.isReg()) {
        if (MO.isImplicit())
          continue;
        Out.addOperand(MCOperand::createReg(MO.getReg()));
      } else if (MO.isImm()) {
        Out.addOperand(MCOperand::createImm(MO.getImm()));
      } else {
        report_fatal_error("PIC14 M1 AsmPrinter encountered unsupported operand");
      }
    }
'''

if old not in text:
    raise SystemExit("PIC14AsmPrinter operand loop not found")
path.write_text(text.replace(old, new, 1))
print("PIC14 AsmPrinter now guards register-only implicit operand queries")
