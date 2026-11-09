# Captured runs

The reports in this directory are the machine-readable output of the
documented commands, made with claimgate 0.1.0 on 2026-11-09.

| report | command | exit | result |
| --- | --- | --- | --- |
| `boost-airy.run.json` | `python -m claimgate run examples/boost-airy/book.json --portable --report records/boost-airy.run.json` | 1 | 0 of 4 judged rows met; 4 exceeded |
| `crlibm-sinh.run.json` | `python -m claimgate run examples/crlibm-sinh/book.json --portable --report records/crlibm-sinh.run.json` | 1 | 1 of 4 judged rows met; 3 exceeded |
| `boys-gate.run.json` | `python -m claimgate run examples/boys-gate/book.json --portable --report records/boys-gate.run.json` | 0 | 38 of 38 judged rows met |
| `row-types.run.json` | `python -m claimgate run examples/row-types/book.json --portable --report records/row-types.run.json` | 1 | 3 of 6 judged rows met; 1 exceeded, 1 vacuous, 1 evidence absent |
| `sleef.run.json` | `python -m claimgate run wider-validation/sleef/book.json --portable --report records/sleef.run.json` | 0 | 4 of 4 judged rows met; worst 0.691 ULP |
| `gsl.run.json` | `python -m claimgate run wider-validation/gsl/book.json --portable --report records/gsl.run.json` | 1 | 3 of 6 judged rows met; 3 exceeded |
| `mpfr.run.json` | `python -m claimgate run wider-validation/mpfr/book.json --portable --report records/mpfr.run.json` | 0 | 16 of 16 judged rows met; 0 mismatches |

Each report carries the book digest, the root, the command, the environment,
the SHA-256 of every input, the per-row results and the summary.  The reports
are outputs, not inputs: regenerating them may change the timestamps and the
environment block, and nothing in the check reads them.

The two pilots reproduce the paper's witnesses:

* Boost.Math `airy_bi` at x = 78.12521875: 414.110896 epsilon (the paper's
  414.111), and `airy_ai` at x = 35.9: 121.395340 epsilon (the paper's
  121.395).
* crlibm `sinh_rn` 0 mismatches, `sinh_ru` 1, `sinh_rd` 1, `sinh_rz` 2 over
  422 sampled inputs.
