; RUN: llc -enable-new-pm=0 -mtriple=pic14-unknown-none -mcpu=pic16f687 -filetype=asm < %s | FileCheck %s
;
; M2 case 05: force one byte temporary while W is the only allocatable i8
; register.  The implementation must spill the first partial result to
; file-register RAM; it must not invent a symmetric GPR or enhanced-midrange
; addressing state.
;
; ABI for this milestone: arg0 arrives in W, arg1 is COMMON 0x70, arg2 is
; COMMON 0x71.  A temporary may use the next COMMON byte (0x72) until the M3
; static-frame allocator owns placement.

define i8 @expr_pressure_u8(i8 %a, i8 %b, i8 %c) {
entry:
  %lhs = add i8 %a, %b
  %rhs = add i8 %b, %c
  %v = xor i8 %lhs, %rhs
  ret i8 %v
}

; CHECK-LABEL: expr_pressure_u8:
; The exact instruction order is intentionally only constrained enough to
; prove accumulator pressure is resolved with real file-register storage.
; CHECK: addwf{{[[:space:]]+}}112,w
; CHECK: movwf{{[[:space:]]+}}114
; CHECK: movf{{[[:space:]]+}}112,w
; CHECK: addwf{{[[:space:]]+}}113,w
; CHECK: xorwf{{[[:space:]]+}}114,w
; CHECK: return
; CHECK-NOT: moviw
; CHECK-NOT: movwi
; CHECK-NOT: addfsr
; CHECK-NOT: FSR0
; CHECK-NOT: FSR1
; CHECK-NOT: INDF0
; CHECK-NOT: INDF1
