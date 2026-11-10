# Paper D seeded-fault study -- pilot record

Date: 2026-11-09. Harness: `D-seeded-fault-harness.py`. Seed: 20261109.

## Revisions and environment

- boys: `v5.3.1` at `2f83e40a6504368b7b2f13682e29b4f24ab2a40c` (scratch clone; the real repository was not modified).
- claimgate: `86b12caac5d3a58493da4886360d7e3efb84af69` (read-only module home), tool claimgate 0.1.0.
- harness: SHA-256 `5d65554502720e573615c756b3e6188ae1d4467bc2f7bf4e82fecbdfda87688e`.
- claimgate book: the `examples/boys-gate/book.json` transcription, `anchor_preference` set to `auto` so the anchors are read from the mutated copy; scoped to the copy with `--root`.
- gate binary: `C:\Users\myaml\dev\_d-seeded-fault\build\Release\boys-accuracy-gate.exe` built from the copy; SHA-256 `c16a9ba5b6283f94a09797ecbfa66b013d6f2d3fea6d1fe5c9fd961fa422ac2f` (clean).
- Python 3.14.7; the gate runs `--strict`.

## Detector commands

```
library gate : <build>/Release/boys-accuracy-gate.exe --strict
claimgate    : python -m claimgate run study-book/book.json --root work-boys --report <report>.json
```

Detection is the detector's own failure signal: a non-zero gate exit (2 registration check, 1 a measured row) and a claimgate exit of 1 (a failed check or judged row). A claimgate exit of 2 is a book or data error and is recorded apart.

## Controls (unmodified copy)

| control | gate exit | gate detected | claimgate exit | claimgate detected |
| --- | --- | --- | --- | --- |
| 1 | 0 | False | 0 | False |
| 2 | 0 | False | 0 | False |
| 3 | 0 | False | 0 | False |
| 4 | 0 | False | 0 | False |

## Faults

| fault | class | aspect | locus | gate exit | gate | claimgate exit | claimgate | build s | gate s | claimgate s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| D1 | documentation_drift | bound | library docs | 2 | True | 1 | True |  | 0.715 | 0.211 |
| D2 | documentation_drift | domain | library docs | 2 | True | 1 | True |  | 0.709 | 0.22 |
| D3 | documentation_drift | source anchor (line shift) | library docs | 2 | True | 1 | True |  | 0.796 | 0.219 |
| D4 | documentation_drift | bound, unregistered sentence | library docs | 0 | False | 0 | False |  | 10.907 | 0.243 |
| D5 | documentation_drift | source anchor (registration side) | registration book | 0 | False | 1 | True |  | 11.238 | 0.22 |
| C1 | code_defect | coefficient | library source | 1 | True | 0 | False | 242.38 | 10.478 | 0.291 |
| C2 | code_defect | branch | library source | 1 | True | 0 | False | 321.083 | 12.109 | 0.455 |

## Outcome matrix (measured faults)

| both detect | gate only | claimgate only | neither |
| --- | --- | --- | --- |
| 3 | 2 | 1 | 1 |

## What each detector reported

- **D1** (bound): gate 2 (registration_check) -- claim D01: the quote is not in README.md (lines 322-324, the bound's first paragraph): "For every `n <= 32` and every `x >= 0` the error of a returned value is at or below **`1e-13 · F_0(x)`** — the ladder's first rung scaled by `1e-13`, not the value the caller asked for."; claim D01: the quote is not in README.md (lines 322-324, the bound's first paragraph): "For every `n <= 32` and every `x >= 0` the error of a returned value is at or below **`1e-13 · F_0(x)`** — the ladder's first rung scaled by `1e-13`, not the value the caller asked for."; claimgate 1 (anchor) -- 2 anchor failure(s): registration reg.D01.01: the sentence is not inside README.md lines 322-324; registration reg.D01.02: the sentence is not inside README.md lines 322-324.
- **D2** (domain): gate 2 (registration_check) -- claim D02: the quote is not in docs/lane-contract.md (lines 124-126, the double lane, the batch row): "the stored fits' 1e-15 bar bounds only the arguments below that edge, where the seed is a per-order fit read at 1e-15 under a reachable gain of at most 2.171050."; EXCEEDED (the lane book, record, not judged) double single / header x<x0  n=0 x=4.9406564584124654e-324  err=2.9976e-15  bound=1e-15  ratio=2.998  ref=1 (1e0); claimgate 1 (anchor) -- 1 anchor failure(s): registration reg.D02.09: the sentence is not inside docs/lane-contract.md lines 124-126.
- **D3** (source anchor (line shift)): gate 2 (registration_check) -- claim D07: the quote spans lines 136-138 of docs/lane-contract.md, outside its anchor's 135-137; claim F02: the quote spans lines 492-497 of docs/lane-contract.md, outside its anchor's 491-496; claimgate 1 (anchor) -- 27 anchor failure(s): registration reg.D07.07: the sentence is not inside docs/lane-contract.md lines 135-137; registration reg.F02.08: the sentence is not inside docs/lane-contract.md lines 491-496.
- **D4** (bound, unregistered sentence): gate 0 (none) -- EXCEEDED (the lane book, record, not judged) double single / header x<x0  n=0 x=4.9406564584124654e-324  err=2.9976e-15  bound=1e-15  ratio=2.998  ref=1 (1e0); EXCEEDED (the lane book, record, not judged) double single / header x<x0  n=0 x=1e-300  err=2.9976e-15  bound=1e-15  ratio=2.998  ref=1 (1e0); claimgate 0 (none) -- none.
- **D5** (source anchor (registration side)): gate 0 (none) -- EXCEEDED (the lane book, record, not judged) double single / header x<x0  n=0 x=4.9406564584124654e-324  err=2.9976e-15  bound=1e-15  ratio=2.998  ref=1 (1e0); EXCEEDED (the lane book, record, not judged) double single / header x<x0  n=0 x=1e-300  err=2.9976e-15  bound=1e-15  ratio=2.998  ref=1 (1e0); claimgate 1 (anchor) -- 1 anchor failure(s): registration reg.D13.05: the sentence is not inside docs/mainpage.md lines 199-201.
- **C1** (coefficient): gate 1 (measured_row) -- NOT MET at this revision: transform.fp64.bound transform.fp64.delivered transform.tf32x3.bound transform.bf16x6.bound; FAIL (the lane book above; the books after it are still measured and printed); claimgate 0 (none) -- none.
- **C2** (branch): gate 1 (measured_row) -- NOT MET at this revision (routes): route.entries; FAIL (the route book above; the scheme book is still measured and printed); claimgate 0 (none) -- none.

## Notes on the pilot strata

- D1-D3 mutates a registered library sentence (bound, domain, anchor line shift). Both detectors read the same 37 registrations, so these are positive controls, not evidence that claimgate beats the test.
- D4 mutates a quantitative sentence that no registration covers. Neither detector is expected to see it; it measures registration coverage, not tool sensitivity.
- D5 mutates the registration's own line anchor while the library documentation is unchanged. claimgate reads the book and can see it; the library's compiled registration table cannot.
- C1 and C2 mutate the library; claimgate does not re-measure the library, so its non-detection is a property of the tool's stated boundary, not an accident of this run.

## Record

Full machine record: `pilot-record.jsonl` (JSON Lines, one object per control or fault). Logs and claimgate reports: `_scratch/out/`.

