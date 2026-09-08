; RUN: llc -enable-new-pm=0 -mtriple=pic14-unknown-none -mcpu=pic16f687 -filetype=asm < %s | FileCheck %s
;
; M3 case 08: an address-taken/volatile i8 local lives in static file-register
; RAM.  The initial non-reentrant frame uses bank-0 GPR 0x20 for frame index 0;
; W remains the only ordinary allocatable i8 CPU register.

define i8 @local_u8(i8 %a) {
entry:
  %x = alloca i8, align 1
  store volatile i8 %a, ptr %x, align 1
  %v = load volatile i8, ptr %x, align 1
  ret i8 %v
}

; CHECK-LABEL: local_u8:
; CHECK: movwf{{[[:space:]]+}}32
; CHECK: movf{{[[:space:]]+}}32,w
; CHECK: return
; CHECK-NOT: moviw
; CHECK-NOT: movwi
; CHECK-NOT: addfsr
; CHECK-NOT: FSR0
; CHECK-NOT: FSR1
; CHECK-NOT: INDF0
; CHECK-NOT: INDF1
