; RUN: llc -enable-new-pm=0 -mtriple=pic14-unknown-none -mcpu=pic16f687 -filetype=asm < %s | FileCheck %s
;
; M2 case 06: classic-midrange byte logic keeps arg0 in W and arg1 in COMMON
; RAM.  File-register RAM is a memory operand, not a symmetric GPR.

define i8 @and_u8(i8 %a, i8 %b) {
entry:
  %v = and i8 %a, %b
  ret i8 %v
}

; CHECK-LABEL: and_u8:
; CHECK: andwf{{[[:space:]]+}}112,w
; CHECK: return

define i8 @or_u8(i8 %a, i8 %b) {
entry:
  %v = or i8 %a, %b
  ret i8 %v
}

; CHECK-LABEL: or_u8:
; CHECK: iorwf{{[[:space:]]+}}112,w
; CHECK: return

define i8 @xor_u8(i8 %a, i8 %b) {
entry:
  %v = xor i8 %a, %b
  ret i8 %v
}

; CHECK-LABEL: xor_u8:
; CHECK: xorwf{{[[:space:]]+}}112,w
; CHECK: return

; CHECK-NOT: moviw
; CHECK-NOT: movwi
; CHECK-NOT: addfsr
; CHECK-NOT: FSR0
; CHECK-NOT: FSR1
; CHECK-NOT: INDF0
; CHECK-NOT: INDF1
