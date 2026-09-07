; RUN: llc -enable-new-pm=0 -mtriple=pic14-unknown-none -mcpu=pic16f687 -filetype=asm < %s | FileCheck %s
;
; M1 regression: this must use the normal PIC14 TargetMachine -> SelectionDAG ->
; MachineInstr -> AsmPrinter/MCInstPrinter path.  No llc.cpp IR-to-ASM shortcut.
;
; PIC16F687 is classic mid-range.  Enhanced-midrange state/instructions are
; forbidden here and in the target sources.

 define i8 @answer() {
 entry:
   ret i8 42
 }

; CHECK-LABEL: answer:
; CHECK: retlw{{[[:space:]]+}}42
; CHECK-NOT: moviw
; CHECK-NOT: movwi
; CHECK-NOT: addfsr
; CHECK-NOT: FSR0
; CHECK-NOT: FSR1
; CHECK-NOT: INDF0
; CHECK-NOT: INDF1
