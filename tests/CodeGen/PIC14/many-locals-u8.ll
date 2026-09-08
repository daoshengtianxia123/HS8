; RUN: llc -enable-new-pm=0 -mtriple=pic14-unknown-none -mcpu=pic16f687 -filetype=asm < %s | FileCheck %s
;
; M3 case 09: multiple volatile i8 locals occupy distinct static file-register
; RAM slots.  The first non-reentrant frame stays in bank-0 GPR RAM and W
; remains the only ordinary allocatable i8 CPU register.

define i8 @many_locals_u8(i8 %a, i8 %b, i8 %c) {
entry:
  %x0 = alloca i8, align 1
  %x1 = alloca i8, align 1
  %x2 = alloca i8, align 1
  %x3 = alloca i8, align 1
  store volatile i8 %a, ptr %x0, align 1
  store volatile i8 %b, ptr %x1, align 1
  store volatile i8 %c, ptr %x2, align 1
  %ab = add i8 %a, %b
  store volatile i8 %ab, ptr %x3, align 1
  %v0 = load volatile i8, ptr %x0, align 1
  %v1 = load volatile i8, ptr %x1, align 1
  %v2 = load volatile i8, ptr %x2, align 1
  %v3 = load volatile i8, ptr %x3, align 1
  %s01 = add i8 %v0, %v1
  %s23 = add i8 %v2, %v3
  %sum = add i8 %s01, %s23
  ret i8 %sum
}

; CHECK-LABEL: many_locals_u8:
; CHECK: movwf{{[[:space:]]+}}32
; CHECK: movwf{{[[:space:]]+}}33
; CHECK: movwf{{[[:space:]]+}}34
; CHECK: movwf{{[[:space:]]+}}35
; CHECK: movf{{[[:space:]]+}}32,w
; CHECK: movf{{[[:space:]]+}}33,w
; CHECK: movf{{[[:space:]]+}}34,w
; CHECK: movf{{[[:space:]]+}}35,w
; CHECK: return
; CHECK-NOT: moviw
; CHECK-NOT: movwi
; CHECK-NOT: addfsr
; CHECK-NOT: FSR0
; CHECK-NOT: FSR1
; CHECK-NOT: INDF0
; CHECK-NOT: INDF1
