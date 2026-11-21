# The claimgate schema

Two JSON Schema documents (draft 2020-12) are the language-neutral
specification:

* `claimgate-book.schema.json` defines a book: its metadata, claims,
  registrations, rows and the optional external run record.
* `claimgate-run.schema.json` defines a run report, and the shape of an
  external run record (`claimgate-external-run-1`).

The Python runner in `claimgate/` implements the same rules.  It is the
reference implementation; a consumer in another language can read the schema
and produce or consume the same JSON.

## The chain

```
documented sentence
      |
      v  registration: verbatim sentence, file, line anchor, figure, scope
      |
      v  row: statement, domain, metric, bound, quantifier, data or external record
      |
      v  evidence: a CSV measured against a reference; a run record; a declared absence
      |
      v  verdict: one of the seven, with the evidence class that says what it establishes
```

A row **carries** a claim when its statement restates the sentence's domain,
bound and quantifier.  It **strengthens** the claim when it tests a stronger
condition, so a pass implies the sentence but a failure does not refute it.
It **measures** the same object under another subject.  It **matches** when it
measures the same object without carrying the sentence.  It **supports** when
it is related evidence.  Every row states its relation and the validator
refuses a row that does not; there is no default.  The schema records the
sentence and the row; the relationship is the author's reading, and the book
shows it.

## Entities

### book

| field | meaning |
| --- | --- |
| `id` | a stable name |
| `title` | one line |
| `description` | what the book is and is not |
| `library` | name, version, tag, revision, source |
| `created` | a date |
| `provenance` | free-form record of where the data and anchors came from |
| `unregistered_rows` | rows that carry no registered claim, each with `treatment` (`retained`, `supporting`, `external`, `withdrawn`) and `reason` |

`defaults.root` is the directory the book's relative paths resolve against
(the book's own directory when absent).  A path must be relative and must not
escape the root.  `defaults.fail_on` names the verdicts that fail the run; the
default is `exceeded`, `vacuous`, `evidence_absent`.

### claim

The formal record of one documented claim.  Fields, after the D brief's list:

| field | meaning |
| --- | --- |
| `id` | a stable name |
| `object` | the function, routine, entry or composed call |
| `domain` | the input domain: a description, `scope` (`whole` or `stated`), an optional interval, and a source |
| `output` | the output representation and precision, e.g. binary64 and 53 bits |
| `metric` | the kind and unit, with an optional epsilon |
| `bound` | the value, unit and quantifier (`pointwise`, `uniform`, `observed_maximum`, `band_maximum`) |
| `implementation` | name, version, tag, revision |
| `route` | the route or configuration the claim is about |
| `assumptions` | the arithmetic, compiler, lane or storage assumptions |
| `source` | the document, file and line range |
| `evidence_class` | what the evidence is |
| `subject` | what the claim is about |
| `rows` | the row or rows registered for it |

A claim whose evidence is an external record may mark its metric `external`
and its bound as the row's own figure; the runner does not recompute it.

### registration

| field | meaning |
| --- | --- |
| `id` | a stable name |
| `claim_id` | the claim it binds |
| `sentence` | the documented sentence, verbatim |
| `source` | file and inclusive line range |
| `scope` | the scope the sentence states |
| `figure` | the number the sentence states, as the document writes it |
| `rows` | the rows it binds |
| `version`, `route`, `assumptions` | optional context |
| `supporting` | further quoted sentences with their own sources |

Whitespace runs are collapsed by the anchor check, not by the author.

### row

| field | meaning |
| --- | --- |
| `id` | a stable name |
| `type` | `reference_comparison`, `consistency`, `exactness`, `vacuity`, `evidence_absent`, `not_carried` or `external_record` |
| `claim_id` | the claim this row is evidence for, if any |
| `statement` | the row's statement of its claim |
| `subject` | what the row measures |
| `domain` | the row's domain and whether it is a restriction the document states |
| `metric` | the metric kind and unit |
| `bound` | the bound the row is judged against |
| `quantifier` | how the bound is read over the domain |
| `evidence_class` | what the row's evidence is |
| `figure_bound` | the numeric bound the registration's figure is checked against |
| `relation` | required: `carries`, `measures`, `matches`, `supports` or `strengthens`; a row without one is refused |
| `data` | the CSV specification: file, comparison, columns, filter, `require_rows`, `crosscheck` |
| `record` | for `external_record`: the run record file and the row index |
| `state` | `not_judged`, `not_carried` or `evidence_absent`, with a `reason` |
| `assumptions`, `notes` | optional |

The `data.comparison` values are `value_vs_reference`, `consistency`,
`bit_identity`, `exact` and `vacuous`.  A value column may be a decimal or a
hexadecimal float, and is never read as a bit pattern; a bit column is always
sixteen hexadecimal digits.  The ULP metric is exact when both operands are
bit patterns; a decimal value is converted to the nearest binary64 first.  A
filter is one criterion (`column` plus `equals` or `startswith`) or an
`{"all": [...]}` of criteria.

### external run record

An external record is a JSON object with

* `schema`: the string `claimgate-external-run-1`;
* `tool`: name and version (and optional binary digest);
* `exit_status`: 0, 1 or 2;
* `summary`: the row count and one count per verdict;
* `rows`: an ordered array of `{index, id, verdict, ...}`.

The runner checks the counts against the rows, checks that the exit status
agrees with the verdicts, and checks every `external_record` row's declared
verdict against the record.

### run report

The top level holds `schema` (`claimgate-run-1`), `tool`, `book` (id, title,
path, SHA-256), `root`, `command`, timestamps, `environment`, `inputs` (each
with a SHA-256), `registrations` (the chain: each registration's id, claim,
source, rows and its anchor and figure results), `checks` (anchors, figures,
bindings, external run), `rows`, `summary` and `exit_status`.

Each row result carries the verdict, its family, `met`, the evidence class,
the relation, the metric and bound, the cell and failure counts, the worst
cell, what the verdict establishes and its limitations.  Each claim result
carries `carrying_rows` (explicit `carries` only), `stronger_test_rows`
(explicit `strengthens` only) and `supporting_rows` (every row that is not a
carry, the stronger tests included).

## Exit status

* `0`: the book ran; every judged row is met; every check passed.
* `1`: the book ran; at least one row carries a failed verdict or a check
  failed.
* `2`: the book or its data could not be read or validated.  The error report
  uses the schema `claimgate-error-1` and carries the message.

## What the schema cannot express

The schema records what the author asserts about a sentence: its reading of
the domain, the metric, the quantifier and the evidence class.  It does not
contain the sentence's meaning, and it cannot show that an enumeration is
complete.  A machine checks the anchor, the figure, the binding, the
measurement and the verdict; a human decides what the sentence claims and
whether the evidence class is the right one.
