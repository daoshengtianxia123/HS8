# HS8 / PIC14 LLVM cloud experiment

This repository is being used as an isolated cloud comparison harness for a minimal LLVM PIC14/PIC16F687 backend experiment.

Current scope: **M0/M1 only**

- register a `pic14` LLVM target/triple
- model W as the only ordinary i8 accumulator register class
- define minimal `RETLW`, `RETURN`, and fallback `MOVLW`
- build `llc` and `FileCheck`
- compile a minimal `ret i8 42` testcase and check for `retlw 42` (or temporary `movlw 42` + `return` while bringing up the backend)

The full upstream LLVM source is not vendored here. CI checks out the official `llvm-project` source and applies the overlay/patch from this repository.
