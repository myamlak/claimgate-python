# Wider validation: SLEEF, GSL and MPFR

The independent validation of the claimgate method on three libraries the
author did not write, with three different documentation cultures:

| Library | Version | Documentation style | Error control | Claim sampled |
| --- | --- | --- | --- | --- |
| SLEEF | 3.9.0 | per-function ULP bounds | vectorised special functions | the scalar `u10` 1.0 ULP bounds |
| GSL | 2.8 | accuracy modes and error estimates | C library, `_e` routines | `GSL_PREC_DOUBLE`'s 2e-16 and the `_e` err field |
| MPFR | 4.2.2 | a proof-backed correct-rounding guarantee | reference-grade arithmetic | correct rounding at precision 53 |

The sources are pinned by URL and SHA-256 in `sources.lock.json`; the
archives are not redistributed. The measurements, the claimgate books, the
reports and the drivers are deposited here. Every number below is from the
reported run, not from memory.

## Results

### SLEEF 3.9.0: four `u10` claims

The documented sentence is "The error bound of the returned value is 1.0
ULP." for the scalar `Sleef_sin_u10`, `Sleef_exp_u10`, `Sleef_log_u10` and
`Sleef_erf_u10`. The ULP error is measured with SLEEF's own tester
definition (`countULPdp`): the denominator is the binary64 spacing at the
correctly rounded reference, floored at the smallest subnormal.

| Row | cells | worst (ULP) | at | verdict |
| --- | --- | --- | --- | --- |
| sin | 1048 | 0.612908 | x = 247332.919 | verified |
| exp | 935 | 0.690651 | x = -0.430775 | verified |
| log | 952 | 0.500000 | x = 0.99999999999999978 | verified |
| erf | 945 | 0.612159 | x = 1e-8 | verified |

No defect was found in the sample. All four rows are within the 1.0 ULP
bound; the worst is 0.691.

### GSL 2.8: an accuracy mode and an error estimate

| Row | cells | measure | worst | verdict |
| --- | --- | --- | --- | --- |
| Airy Ai at `GSL_PREC_DOUBLE` | 930 | relative error | 3.338971e-15 | exceeded (570 cells over 2e-16) |
| Elliptic K at `GSL_PREC_DOUBLE` | 916 | relative error | 4.329956e-16 | exceeded (177 cells over 2e-16) |
| `gsl_sf_erf_e` error estimate | 944 | true error / reported err | 1.343685 | exceeded (8 cells over 1.0) |
| `gsl_sf_gamma_e` error estimate | 945 | true error / reported err | 0.711392 | verified |
| `gsl_sf_bessel_J0_e` error estimate | 940 | true error / reported err | 0.849874 | verified |
| `gsl_sf_bessel_J1_e` error estimate | 935 | true error / reported err | 0.602726 | verified |

The manual's `GSL_PREC_DOUBLE` entry says "a relative accuracy of
approximately 2 * 10^-16". The word "approximately" makes it an allowance,
not a bound; the observed relative errors exceed it by up to 17 times on
Airy Ai. The `_e` entry says the `err` field "contains an estimate of the
absolute error in the value"; the estimate is below the true error at 8 of
944 `erf` cells, worst 1.344 times the reported error at x = 0.902963. That
is an optimistic estimate at those cells, not a false sentence.

### MPFR 4.2.2: the correct-rounding guarantee

The manual states that the value stored in the destination variable is
correctly rounded. The claim is registered with the `certified_bound`
evidence class; the rows are finite-grid conformance and relate to the claim
as `supports`, not `carries`.

| Function | cells | mismatches, RN / RU / RD / RZ | verdict |
| --- | --- | --- | --- |
| `mpfr_sin` | 919 | 0 / 0 / 0 / 0 | 4 rows verified |
| `mpfr_exp` | 925 | 0 / 0 / 0 / 0 | 4 rows verified |
| `mpfr_log` | 913 | 0 / 0 / 0 / 0 | 4 rows verified |
| `mpfr_atan` | 919 | 0 / 0 / 0 / 0 | 4 rows verified |

14,704 bit comparisons, no mismatch. The expected value is an independent
evaluation at 53+64 to 53+16384 bits, certified by `mpfr_can_round`. This
confirms the guarantee on the sample; it does not verify the library's proof.

## Claim enumeration

The enumeration is a lower bound on each library's row-shaped claims, built
by hand from the pinned documentation. The sample registered and measured is
a subset.

| Library | Enumerated | Registered | Record |
| --- | --- | --- | --- |
| SLEEF | 27 scalar double-precision `u10` entries in `docs/purec.xhtml`, each with its documented bound | 4 (sin, exp, log, erf) | `sleef/enumeration.tsv` |
| GSL | 4 numeric accuracy statements in the special-functions chapter (`GSL_PREC_DOUBLE`, `GSL_PREC_SINGLE`, `GSL_PREC_APPROX`, the `err` estimate) | 2 (the `GSL_PREC_DOUBLE` allowance and the `err` estimate) | `gsl/enumeration.tsv` |
| MPFR | 1 correct-rounding guarantee, scoped over every function and rounding mode | 4 functions × 4 modes at precision 53 | `mpfr/enumeration.tsv` |

The SLEEF census excludes the `u35` and `u05` families and the vector entries;
the GSL census is the special-functions chapter, not the whole manual; the
MPFR guarantee is one claim, so its "sample" is a set of function-and-mode
instances rather than a set of sentences. No enumeration is claimed complete.

## Undetermined claims

* GSL's two sentences are not strict, row-shaped claims. "Approximately" and
  "estimate" cannot be judged as bounds. The tool records the author's
  reading and its evidence class (`empirical_allowance`), and the verdicts
  are findings against that reading, not refutations of the sentences.
  The GSL mode claim also does not say which functions or arguments it
  covers; a relative error at a zero of a function is undefined. The sample
  avoids zeros (Airy Ai and K have none in the chosen ranges).
* SLEEF's sentence says "the returned value" without a stated domain. The
  tool's row chooses the finite-result domain and a sample; whether
  subnormal, overflow and NaN results are inside the sentence is the
  author's reading, not the tool's decision.
* MPFR's guarantee is proof-backed and covers every precision. The book
  measures precision 53 in the binary64 normal range; the tool cannot check
  the proof, and the binary64 bit comparison is a proxy for MPFR's
  precision-53 result in that range.

## What the tool cannot handle

* The metric is part of the claim. SLEEF's "1.0 ULP" needed a new
  `ulp_exact` metric and the library's own floor definition; a tool that
  assumed a single ULP definition would have measured the wrong quantity.
* The hedge. "Approximately" and "estimate" have no machine form. The
  evidence-class compatibility check can refuse a measured row as a proof,
  but it cannot decide whether a sentence is a bound or an allowance; that
  is the author's registration.
* The proof. MPFR's guarantee is certified by the library, not by the row.
  The book can mark the claim `certified_bound` and the row `supports`; the
  tool reports both, and cannot verify the certificate.
* The documentation format. The anchors are deposited excerpts quoted by
  hand from HTML, reStructuredText and Texinfo. The tool checks the quote
  and its line; it does not parse those formats, strip markup, or reconcile
  a variable rendered as `<i>a</i>` with the plain `a`.
* The domain. The tool records the domain the author registers; it cannot
  infer from a sentence that a relative error is undefined at a zero, or
  that a correct-rounding claim is about an unbounded-exponent format.
* The measurement. The tool reads a CSV; it does not build a library,
  generate inputs or run a driver. The three drivers here are part of the
  validation record, not part of the reference runner.

## Effort

One lane session. Observable work: three pinned archives (12 MB), three
library builds (SLEEF 24 MB build tree, GSL 30 MB prefix, MPFR 11 MB
prefix), three C drivers, ten measured functions, 3,880 SLEEF cells, 5,610
GSL cells and 14,704 MPFR bit comparisons, three claimgate books, three
reports. No wall clock was instrumented for the builds; the claimgate runs
themselves are sub-second (see each report's `duration_s`).

## Reproduce

The commands are for the WSL Ubuntu host used here. The drivers' build
scripts expect the build root at `$HOME/wider-validation` and take the
driver source from their own directory; set `ROOT` in each script for
another host.

```sh
# 1. Fetch and verify. The archives are untrusted data; extract each into
#    its own empty directory and check the hash first.
mkdir -p ~/wider-validation/{src,build,prefix,bin}
curl -L -o downloads/sleef-3.9.0.tar.gz https://github.com/shibatch/sleef/archive/refs/tags/3.9.0.tar.gz
curl -L -o downloads/gsl-2.8.tar.gz https://mirrors.kernel.org/gnu/gsl/gsl-2.8.tar.gz
curl -L -o downloads/mpfr-4.2.2.tar.xz https://www.mpfr.org/mpfr-4.2.2/mpfr-4.2.2.tar.xz
sha256sum -c ../sources.sha256

# 2. Build MPFR (the reference), GSL and SLEEF; see sources.lock.json.
#    MPFR needs GMP 6.3.0; the Ubuntu libgmp-dev provides it.

# 3. Generate the inputs and build and run the drivers.
python wider-validation/gen_inputs.py --out wider-validation/inputs
sh wider-validation/mpfr/build.sh
sh wider-validation/gsl/build.sh
sh wider-validation/sleef/build.sh
# then the per-function driver commands in sources.lock.json

# 4. Run the books.
python -m claimgate run wider-validation/sleef/book.json --portable --report wider-validation/sleef/report.json
python -m claimgate run wider-validation/gsl/book.json  --portable --report wider-validation/gsl/report.json
python -m claimgate run wider-validation/mpfr/book.json --portable --report wider-validation/mpfr/report.json
```

Exit statuses: SLEEF 0 (4 of 4 met), GSL 1 (3 of 6 met), MPFR 0 (16 of 16
met). The reports carry the input digests and the checks.
