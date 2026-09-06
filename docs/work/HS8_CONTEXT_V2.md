# HS8 PIC14/PIC16F687 Work Context V2

Updated: 2026-09-06

This file is the durable handoff for ChatGPT Work/Codex and other coding agents working on the HS8 PIC14 LLVM backend.

## Repository state

- repo: `daoshengtianxia123/HS8`
- working branch: `pic14-cloud-test`
- draft PR: #1 -> `main`
- cloud reference LLVM: `llvmorg-23.1.0`
- LLVM commit: `ea7d852a70e8bdfaf601d6626a760f9771b2c4b4`
- do not merge to main unless explicitly requested

Latest observed CI before this handoff was run #15 (`34039441066`) at head `4f07719aca9289bde95e26c7c2c0a0478f569d21`.

## Current progress

The real M1 cloud build has already passed:

- PIC14 Triple/TargetParser registration path
- CMake configuration as an experimental target
- PIC14 TableGen generation
- `LLVMPIC14Info`
- substantial `LLVMPIC14Desc`
- entry into real `LLVMPIC14CodeGen`

Run #15 reached approximately `[1847/1873]` before the first PIC14 C++ compile failure.

## Current first real blocker

```text
llvm/lib/Target/PIC14/PIC14.h:4:10: fatal error:
llvm/CodeGen/CodeGenOptLevel.h: No such file or directory
```

Classify this as LLVM 23.1 API/header compatibility, not an ISA/ABI design failure.

## Single next task

1. Inspect LLVM 23.1 in-tree targets for the correct optimization-level type/header/API.
2. Update the minimum PIC14 declaration/implementation surface.
3. Rebuild `LLVMPIC14CodeGen` / `llc`.
4. Inspect the next first real error.
5. Repeat without expanding beyond M1.

## Strict M1 acceptance

Golden IR:

```llvm
define i8 @f() {
entry:
  ret i8 42
}
```

Preferred output:

```asm
retlw 42
```

Temporary plumbing fallback may be:

```asm
movlw 42
return
```

M1 is not complete until the real LLVM target pipeline is used:

```text
LLVM IR
 -> PIC14 TargetMachine
 -> SelectionDAG
 -> MachineInstr
 -> PIC14 AsmPrinter / MCInst printer
 -> assembly
```

Do not keep a direct IR-to-assembly string bootstrap shortcut as the final M1 solution.

## Architecture decisions that must not drift

- W is the true accumulator.
- Conceptual allocatable 8-bit CPU register class is W-only.
- File-register RAM is memory, never a symmetric GPR bank.
- Do not model 0x20/0x70-style RAM locations as physical registers.
- STATUS C/DC/Z become real dependencies at the arithmetic/compare milestone; do not fake them in M1.
- FSR/INDF pointer semantics are later, not M1.
- i16 must not be represented as invented AVR-like register pairs.
- initial C frame model is static/non-reentrant; overlay is a later whole-program optimization.
- use SelectionDAG first; do not develop GlobalISel in parallel.
- awkward carry/skip/bank/page sequences should prefer pseudos and late expansion.
- bank/page decisions must remain late.
- XC8 is a semantic/codegen-strategy oracle; PIC16F687 datasheet is the final encoding authority.
- do not invent instruction-size or CodeEmitter encoding details during asm-only M1.
- AsmParser is optional in M1 unless compilation actually requires it.

## M1 forbidden scope

Do not implement or claim:

- i16 ABI/arithmetic
- direct RAM/static-frame allocator beyond what M1 mechanically needs
- STATUS compare/branch
- FSR/INDF data-pointer ABI
- bank allocator
- frame overlay
- native `__bit`
- interrupts
- MUL/DIV runtime
- ROM const/switch tables
- Clang target extensions

## CI debugging rule

Always fix the first real PIC14 error, not the last Ninja symptom.

Failure categories:

```text
I.   infrastructure/CMake
II.  TableGen
III. Triple/TargetParser API
IV.  MC API
V.   TargetMachine/CodeGen API
VI.  SelectionDAG semantics
VII. MachineInstr/AsmPrinter semantics
VIII.M1 regression
```

Use minimal patches and rerun CI after each first-blocker fix.

## Version strategy

Keep cloud CI pinned to LLVM 23.1.0 until M1 is green. Only after that, forward-port the same architecture to the exact local macOS LLVM SHA.

Prior local macOS setup used `/Users/ds/Desktop/llvm-project`, build directory `/Users/ds/Desktop/llvm-build-pic14`, LLVM 24.0.0git on Apple M5, with `pic16f687-agent/` as the local agent harness.

This two-track approach separates backend architecture correctness from LLVM-version API churn.

## Work/Codex continuation instruction

Use this as the starting task:

```text
Continue the HS8 PIC14/PIC16F687 backend on branch pic14-cloud-test.
Read docs/work/HS8_CONTEXT_V2.md first.
Stay strictly within M0/M1.
Inspect the latest GitHub Actions run and fix only the first real error.
Use LLVM 23.1 in-tree targets as API references while preserving the architecture decisions above.
Trigger/run cloud CI after each minimal fix.
Do not merge to main.
Do not start M2 until LLVMPIC14CodeGen + llc + ret i8 42 -> retlw 42 + lit/FileCheck are green.
```
