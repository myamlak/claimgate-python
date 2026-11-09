# claimgate

A reference runner for documented numerical accuracy claims.

A library states an accuracy claim in prose.  claimgate carries that sentence as
a **registration** (the verbatim text, its file and line anchor, the figure it
states), binds it to one or more **rows** (the statement, domain, metric, bound
and measured data), runs the rows, and reports one **verdict** per row.  The
book, the row types, the evidence classes and the run record are specified in
`schema/`.

The tool exists so that the chain

```
documented sentence -> registration -> row -> evidence -> verdict
```

is checked by a machine wherever the machine can check it, and by a human
everywhere else.  The boundary is stated below and in `schema/README.md`.

## Requirements

Python 3.10 or newer.  The runner uses only the standard library.  The two
pilot data sets shipped in `examples/` are plain CSV.

## Quick start

From the repository root:

```sh
python -m claimgate validate examples/boost-airy/book.json
python -m claimgate run examples/boost-airy/book.json
python -m claimgate run examples/crlibm-sinh/book.json --report records/crlibm-sinh.run.json
python -m claimgate run examples/boys-gate/book.json
python -m claimgate run examples/row-types/book.json
```

The exit status is `0` when every judged row is met and every check passes,
`1` when the book ran and something failed (a row verdict, an anchor, a figure,
a binding or the external run record), and `2` when the book or its data
cannot be read or validated.  `--json` prints the run report; `--report FILE`
writes it; `--portable` writes the report's paths relative to the invocation
directory, which is what the deposited records use.  `--no-anchors` skips the
anchor check and says so in the report.

An ordinary test invocation is the same command.  The suite that ships with
the tool is:

```sh
python -m unittest discover -s tests
```

## The book

A book is one JSON file.  Its top level holds metadata, claims, registrations,
rows and optionally an external run record:

```json
{
  "claimgate_book": 1,
  "book": {"id": "...", "title": "...", "library": {...}},
  "claims": [ ... ],
  "registrations": [ ... ],
  "rows": [ ... ],
  "external_run": {"file": "run-record.json"}
}
```

A **claim** carries the object, the input domain, the output representation,
the metric, the bound and its quantifier, the implementation version, the
route, the assumptions, the source location, the evidence class, the subject
and the carrying rows.

A **registration** carries the verbatim sentence, its file and inclusive line
range, its scope, the figure the sentence states, and the rows it binds.

A **row** carries its type, statement, subject, domain, metric, bound,
quantifier, evidence class, and either a data specification or an external
record.  `figure_bound` is the numeric bound the registration's stated figure
is compared with, to one binary64 ULP.

The **verdicts** are the seven of the boys accuracy gate, reused as one
implementation of the evidence taxonomy:

| verdict | family | fails the run |
| --- | --- | --- |
| `verified` | judged and met | no |
| `met_over_domain` | judged and met | no |
| `exceeded` | judged and unmet | yes |
| `vacuous` | judged and unmet | yes |
| `evidence_absent` | judged and unmet | yes |
| `not_carried` | not judged | no |
| `not_judged` | not judged | no |

The failed verdict set is `defaults.fail_on`, defaulting to the three
judged-and-unmet verdicts.

## Row types

| type | what it computes |
| --- | --- |
| `reference_comparison` | a metric between a measured value and a reference, over the selected cells |
| `consistency` | a metric between two paths, over the selected cells |
| `exactness` | exact or bit-identity equality of a measured value with an expected value |
| `vacuity` | whether the bound is at least the value's own magnitude at every cell |
| `evidence_absent` | a declared verdict: the named evidence was not produced |
| `not_carried` | a declared verdict: the build does not carry the claim's subject |
| `external_record` | a verdict read from another tool's run record, checked against the record |

A row may also carry `state: "not_judged"`; its data are measured and printed
and the verdict is withheld.  This is how a measured row whose figure belongs
to another build is recorded without being judged.

## Metrics and exactness

A finite quantity is read exactly.  A decimal in the data file goes through
`decimal.Decimal`; a sixteen-hex-digit pattern is the bits of a binary64; both
become `fractions.Fraction`.  The metric is computed with exact rational
arithmetic and compared with an exactly parsed bound.  The float conversion is
only for presentation.  The metrics are `absolute`, `relative`, `epsilon`
(relative divided by a stated epsilon, binary64 `2^-52` by default), `ulp`
(the number of representable binary64 values between the two patterns),
`bit_identity`, `scaled` and `exact`.

A row may name a `crosscheck` column, generally an error column the depositor
computed.  claimgate recomputes the error from the raw values and fails the
run as a data error if its result disagrees with the deposited column beyond
the stated tolerance.  The pilot books use this to show that the tool
reproduces the deposited computation rather than trusting it.

## Evidence classes

| class | what a verdict can be read as |
| --- | --- |
| `proof` | the claim, unconditionally |
| `certified_bound` | the claim, by a certified enclosure |
| `conditional_bound` | the claim, conditionally on its stated hypotheses |
| `measured_error` | the observed error on the measured cells; a breach refutes, a pass does not establish a uniform bound |
| `finite_grid_conformance` | conformance on the measured cells only |
| `empirical_allowance` | an allowance observed over a design; not a bound |
| `proxy` | evidence related to the claim, not the claim itself |
| `vacuous` | nothing: the bound cannot discriminate on these cells |
| `evidence_absent` | nothing: the evidence was not produced |
| `not_carried` | nothing: the build does not carry the subject |

A measured data file cannot be registered as a `proof` or a `certified_bound`.
The validator refuses that combination; the reason is printed with the error.
Where a measured row's quantifier is `uniform`, the report adds the limitation
that a finite set cannot establish a uniform bound.

## Checks at every invocation

* **Anchor**: the registration's sentence, with whitespace runs collapsed, is
  inside the stated line range of the stated file.  If the upstream tree is
  absent, a deposited line-slice stands in for it; the report records
  `full-source` or `deposited-slice` and the source's SHA-256.
* **Figure**: the number the sentence states occurs in the sentence as a
  number of its own, parses exactly as the document writes it (a decimal,
  `2^p`, or a sum), and equals the carrying row's `figure_bound` to one ULP.
  A registration with no figure is counted apart, not silently passed.
* **Binding**: every registration names rows the book holds; every row is
  cited by a registration or listed in `book.unregistered_rows` with a
  treatment and a reason.
* **External run record**: the record's schema, row count, per-verdict counts
  and exit status are internally consistent, and each `external_record` row's
  declared verdict agrees with the record's row.

The report records the tool version, the book digest, the root, the command,
the environment, the SHA-256 of every input it read, the registration chain
(each registration's claim, source, rows, anchor and figure result), the
checks, the rows, the summary and the exit status.

## Examples

### Boost.Math 1.92.0: the Airy sentence (a pilot)

`examples/boost-airy/` carries the sentence "In general though, the relative
error is low (less than 100 [epsilon]) for /x > 0/ ..." as one registration
with figure `100`, and four measured rows over the deposited witness data.
The reference is mpmath 1.4.1 at 60 significant digits; the measured values
are MSVC binary64 evaluations.  The runner recomputes every error from the raw
measured bits and the reference decimal, exactly.

The run reproduces the paper's two witnesses:

| row | cells | worst (epsilon) | at | verdict |
| --- | --- | --- | --- | --- |
| A2 grid, `airy_bi` | 65 | 414.110896 | x = 78.12521875 | `exceeded` |
| named witness, `airy_ai` | 3 | 121.395340 | x = 35.9 | `exceeded` |
| A2 grid, `airy_ai` | 65 | 414.878957 | x = 78.12521875 | `exceeded` |
| literal 78.1252, `airy_bi` | 3 | 157.818977 | x = 78.1252 - 1 ulp | `exceeded` |

The A2 grid on `airy_ai` is a finding beyond the audit's A1 row: the audit
stopped A1 at x = 30 because its double reference underflowed, and the
deposited 60-digit reference does not.  The audit's A1 grid itself is not in
the deposit.  The book says so in its provenance.

### crlibm 1.0beta5: the `sinh` correct-rounding claim (a pilot)

`examples/crlibm-sinh/` carries Table 1's `sinh` entry, marked `complete`, and
the manual's definition of `complete` as correct rounding over the whole
floating-point input range.  Four rows, one per rounding mode, compare the
measured bits with the expected bits over the 422-argument witness set:

| row | cells | mismatches | verdict |
| --- | --- | --- | --- |
| `sinh_rn` | 422 | 0 | `verified` |
| `sinh_ru` | 422 | 1 | `exceeded` |
| `sinh_rd` | 422 | 1 | `exceeded` |
| `sinh_rz` | 422 | 2 | `exceeded` |

The mismatches are the witnesses the paper reports: `+inf` where `+DBL_MAX`
is required at `0x408633ce8fb9f87e`, and the mirrored case at the negated
input.  The rows are finite-grid conformance: a mismatch refutes the claim; a
pass on 422 arguments does not establish it over the whole range, and the
report says so.

### The boys accuracy gate at v5.3.1 (a consumer)

`examples/boys-gate/` expresses the gate's 37 registration entries over 36
claims and its 38 claims-book rows, with the verdicts of the captured
`04b-gate-run.log` transcript.  The 37 anchor quotes are checked against
deposited line-slices cut from the tagged source; the 13 stated figures are
checked against the rows' `figure_bound`; the 10 released rows keep the gate's
own treatments; and the run record's 38 verdicts, its 29 verified / 9 met over
a stated domain split and its exit status 0 are checked against one another.
The run reproduces the gate's own RESULT: 38 of 38 judged rows met.

The gate stays in the boys repository.  `examples/boys-gate/extract.py`
regenerates this book from the tagged source and the transcript; it requires
the boys checkout and is not needed to run the example.

### The row-type testbed (a construction)

`examples/row-types/` is a constructed book, not a measurement.  It drives
every row type and every verdict family, including a vacuous row, an absent
row, a not-carried row and a not-judged row.  Its exit status is 1.

## What the tool does not do

* It does not understand prose.  A human authors every registration.
* It does not prove that an enumeration of a library's claims is complete.
  The book is a lower bound on the claims that were carried.
* It does not certify beyond the evidence class.  A measured row is a
  measurement, not a proof.
* It does not re-measure an `external_record` row.  It checks the record's
  structure, digests and internal consistency and carries the external tool's
  verdict.
* It does not decide what a sentence means.  The domain, metric, quantifier
  and bound are the author's reading and are visible in the book.
* The JSON Schema files are the language-neutral specification.  The runner's
  validator is the reference implementation; the tests check the examples
  through the runner, not through a generic JSON Schema validator.

## Layout

| path | what it is |
| --- | --- |
| `schema/claimgate-book.schema.json` | the book schema |
| `schema/claimgate-run.schema.json` | the run report schema |
| `schema/README.md` | the entity and field guide |
| `claimgate/` | the reference runner |
| `examples/boost-airy/` | the Boost.Math Airy pilot |
| `examples/crlibm-sinh/` | the crlibm sinh pilot |
| `examples/boys-gate/` | the boys gate consumer, its extractor and anchor slices |
| `examples/row-types/` | the constructed row-type testbed |
| `tests/` | the unit and example tests |
| `tools/outsider_check.py` | the fresh-clone check |
| `records/` | the captured run reports |

## Data provenance

The two pilot data files and the documentation excerpts are copied unchanged
from the `accuracy-claim-audit` deposit (`witness-rerun/`); each book records
the SHA-256 and the upstream tag.  The boys consumer is extracted from the
`v5.3.1` tag of the boys repository and the captured gate transcript; the
extractor records both digests.  No measurement was invented for this
artifact.

## Licence

BSD 3-Clause.  See `LICENSE`.
