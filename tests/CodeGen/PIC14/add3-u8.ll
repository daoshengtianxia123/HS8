; RUN: llc -enable-new-pm=0 -mtriple=pic14-unknown-none -mcpu=pic16f687 -filetype=asm < %s | FileCheck %s
;
; M2 case 04: arg0 is W, arg1/arg2 are successive COMMON-RAM byte slots.
; The two additions must stay in the classic-midrange accumulator model:
; W := W + file[0x70], then W := W + file[0x71].

define i8 @add3_u8(i8 %a, i8 %b, i8 %c) {
entry:
  %ab = add i8 %a, %b
  %sum = add i8 %ab, %c
  ret i8 %sum
}

; CHECK-LABEL: add3_u8:
; CHECK: addwf{{[[:space:]]+}}112,w
; CHECK: addwf{{[[:space:]]+}}113,w
; CHECK: return
; CHECK-NOT: moviw
; CHECK-NOT: movwi
; CHECK-NOT: addfsr
; CHECK-NOT: FSR0
; CHECK-NOT: FSR1
; CHECK-NOT: INDF0
; CHECK-NOT: INDF1
