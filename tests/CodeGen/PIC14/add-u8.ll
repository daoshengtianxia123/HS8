; RUN: llc -enable-new-pm=0 -mtriple=pic14-unknown-none -mcpu=pic16f687 -filetype=asm < %s | FileCheck %s
;
; M2 case 03: arg0 is W and arg1 is the first COMMON-RAM byte argument slot.
; Classic mid-range PIC16F687 has an accumulator architecture, so the byte
; addition must consume the file-register operand directly with W as source
; and destination; file-register RAM must not be modeled as a symmetric GPR.

define i8 @add_u8(i8 %a, i8 %b) {
entry:
  %sum = add i8 %a, %b
  ret i8 %sum
}

; CHECK-LABEL: add_u8:
; CHECK: addwf{{[[:space:]]+}}112,w
; CHECK: return
; CHECK-NOT: moviw
; CHECK-NOT: movwi
; CHECK-NOT: addfsr
; CHECK-NOT: FSR0
; CHECK-NOT: FSR1
; CHECK-NOT: INDF0
; CHECK-NOT: INDF1
