# The boys accuracy gate as a claimgate consumer

This directory is a faithful transcription of the boys accuracy gate's
registration table and its captured v5.3.1 run.  The gate stays in the boys
repository; this is one consumer of the tool.

## What is here

| file | what it is |
| --- | --- |
| `book.json` | 36 claims, 37 registrations, 38 rows, 10 released rows |
| `run-record.json` | the gate's captured run: 38 verdicts, the RESULT summary, exit 0 |
| `anchor-slices/index.json` | maps each source file to its deposited line-slice and full-source SHA-256 |
| `anchor-slices/*.slices.json` | the cited line ranges, cut from the `v5.3.1` tag |
| `extract.py` | regenerates the three files above from the tagged source and the transcript |

## The extraction

The gate source and the anchor sources are read at tag `v5.3.1`
(peeled commit `2f83e40a6504368b7b2f13682e29b4f24ab2a40c`) with
`git show`; the transcript is the paper's captured
`04b-gate-run.log`.  The extractor:

* preprocesses the source with `BOYS_GATE_FP16` defined and
  `BOYS_GATE_EXTERNAL_BOOST` undefined, the configuration the published
  numbering was made in;
* reads the 38 `add()` calls of the claims book and the 37 entries of
  `kRegistrations[]`, and evaluates each `figureBound` expression against the
  gate's own constants;
* reads the 38 verdict entries of the documented-claims block and the
  RESULT line, and refuses to write a book if the counts disagree;
* cuts the anchor slices and checks every registration quote against its
  source before writing.

Regenerate with:

```sh
python examples/boys-gate/extract.py \
    --repo <boys-checkout> --tag v5.3.1 \
    --transcript <04b-gate-run.log> --out examples/boys-gate
```

The extractor needs the boys repository and the paper's transcript.  Running
the example needs neither: the slices and the run record are deposited here.

## What claimgate checks

* every registration's verbatim sentence lies inside its stated lines of the
  deposited slice;
* the 13 stated figures occur in their sentences and equal the bound rows'
  `figure_bound` to one ULP; the other 24 registrations are counted apart;
* every registration names rows the book holds, and every row is cited or is
  in the gate's own released list with its treatment and reason;
* the run record's row count, its per-verdict counts and its exit status are
  internally consistent, and every row's declared verdict agrees with the
  record.

## The row relations

Every row states its relation explicitly: 20 carry, 1 strengthens (H01), 10
support and 7 measure.  The assignments follow the evidence partition in the
accompanying paper: the deposited H04, P02 and P04 rows carry; the model-only
X03-X06 and the proxy D07 and P03 support; H01's stronger test is
`strengthens`; P11 is measured without restating its sentence.  The
supporting rows the gate releases beside its claims, and the retained rows
that measure objects no enumerated claim states at this tag, are marked
`supports` and `measures` respectively.

## What claimgate does not check

It does not re-measure the library and does not re-judge the gate.  Each row
is an `external_record`: its verdict is the gate's.  The claim model fields
are transcribed from the gate's registrations and rows; where the gate states
no figure the claim bound is 0 and the metric is marked `external`, so the
placeholder is visible rather than passed off as a measurement.  The book's
provenance names the transcription and the placeholders.
