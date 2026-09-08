# HS8 PIC14/PIC16F687 Work Context V2

Updated: 2026-09-09

## Repository state

- repo: `daoshengtianxia123/HS8`
- working branch: `pic14-cloud-test`
- draft PR: #1 -> `main` (keep Draft; do not merge/close)
- cloud reference LLVM: `llvmorg-23.1.0`
- architecture target: classic mid-range PIC16F687 / PIC14

## Milestone status

### M1 — complete

The direct `llc.cpp` IR-to-assembly bootstrap has been replaced by the real path:

```text
LLVM IR -> PIC14 TargetMachine -> SelectionDAG -> MachineInstr
        -> PIC14 AsmPrinter / MCInstPrinter -> assembly
```

`ret i8 42` lowers to native `retlw 42` and is covered by lit/FileCheck and CI.

### M2 — complete at CI #56 / head d5b730d5c306b989ea17b633d7b7ceb4d055d3c0

XC8-oracle cases covered:

- 02_arg_return_u8
- 03_add_u8
- 04_add3_u8
- 05_expr_pressure_u8
- 06_logic_u8

M2 preserves the classic mid-range model:

- W is the only ordinary allocatable i8 CPU register.
- extra byte arguments/temporaries are file-register RAM memory locations, not fake GPRs.
- arithmetic/logical file/W instructions are used natively.
- STATUS is represented as an implicit machine dependency where the instruction changes flags.
- enhanced-midrange FSR0/FSR1/INDF0/INDF1/MOVIW/MOVWI/ADDFSR are rejected by CI.

### M3 — in progress

Mapped oracle cases:

- 08_local_u8
- 09_many_locals_u8
- 25_static_local
- 28_global_rmw

First M3 slice introduces one-byte address-taken/volatile local storage using the initial static/non-reentrant frame model. File-register RAM remains memory. Ordinary frame slots start in bank-0 GPR RAM at 0x20; there is no fabricated software SP/GPR bank. Calls/live-across-call remain M5 and whole-program overlay remains later.

## Architecture rules that must not drift

Priority: PIC16F687 datasheet > XC8 V7 P1/ASM/LST/MAP/SYM oracle > historical LLVM PIC16/kpzip architecture references.

- W is the true accumulator and the ordinary allocatable i8 register class is W-only.
- file-register RAM is memory, never a symmetric LLVM GPR bank.
- STATUS C/DC/Z become real MachineIR/SelectionDAG dependencies as relevant.
- indirect addressing is single FSR + INDF + STATUS.IRP.
- never introduce FSR0/FSR1, INDF0/INDF1, MOVIW/MOVWI, or ADDFSR.
- i16 uses byte memory pairs + W + carry, never invented AVR-style register pairs.
- initial C frames are static/non-reentrant; overlay is a later whole-program optimization.
- SelectionDAG first; do not develop GlobalISel in parallel.
- bank/page/skip/carry complexities prefer pseudos plus late expansion.
- PIC16F687 datasheet is final encoding authority.

## Next progression

Fix only the first real CI error from the M3 `08_local_u8` slice. Once green, proceed to `09_many_locals_u8`, then static local and global RMW. Do not jump to calls, pointers, i16, or frontend work before their mapped milestones.
