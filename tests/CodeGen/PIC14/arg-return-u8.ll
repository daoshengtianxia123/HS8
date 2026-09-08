; RUN: llc -enable-new-pm=0 -mtriple=pic14-unknown-none -mcpu=pic16f687 -filetype=asm < %s | FileCheck %s
;
; M2 case 02: one i8 argument arrives in W and an i8 result is returned in W.
; The identity function therefore needs no RAM-as-GPR fiction: W is the real
; classic-midrange accumulator and RETURN preserves the incoming value.
;
; This must pass through the normal PIC14 TargetMachine -> SelectionDAG ->
; MachineInstr -> AsmPrinter/MCInstPrinter path.

define i8 @identity_u8(i8 %x) {
entry:
  ret i8 %x
}

; CHECK-LABEL: identity_u8:
; CHECK: return
; CHECK-NOT: moviw
; CHECK-NOT: movwi
; CHECK-NOT: addfsr
; CHECK-NOT: FSR0
; CHECK-NOT: FSR1
; CHECK-NOT: INDF0
; CHECK-NOT: INDF1
