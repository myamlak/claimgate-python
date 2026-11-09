"""The book model: loading, structural validation and referential integrity.

The JSON Schema in ``schema/`` is the language-neutral specification.  This
module is the reference implementation of it: it checks the same required
fields, the same enumerations, the row-type requirements, the evidence-class
compatibility rule and the references between claims, registrations and rows.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from .exact import NumberError, parse_exact

TOOL_NAME = "claimgate"
TOOL_VERSION = "0.1.0"
BOOK_SCHEMA = 1
RUN_SCHEMA = "claimgate-run-1"
EXTERNAL_RUN_SCHEMA = "claimgate-external-run-1"

VERDICTS = (
    "verified",
    "met_over_domain",
    "exceeded",
    "vacuous",
    "evidence_absent",
    "not_carried",
    "not_judged",
)

EVIDENCE_CLASSES = (
    "proof",
    "certified_bound",
    "conditional_bound",
    "measured_error",
    "finite_grid_conformance",
    "empirical_allowance",
    "proxy",
    "vacuous",
    "evidence_absent",
    "not_carried",
)

METRIC_KINDS = ("absolute", "relative", "epsilon", "ulp", "bit_identity", "scaled", "exact", "external")

QUANTIFIERS = ("pointwise", "uniform", "observed_maximum", "band_maximum")

ROW_TYPES = (
    "reference_comparison",
    "consistency",
    "exactness",
    "vacuity",
    "evidence_absent",
    "not_carried",
    "external_record",
)

#: Evidence classes a row of each type may carry.  A measured data file can
#: refute a bound and establish conformance on its own cells; it cannot be a
#: proof or a certified bound.  The two classes that establish a claim
#: unconditionally are claim-level classes, never measured-row classes.
ROW_ALLOWED_EVIDENCE = {
    "reference_comparison": {
        "measured_error",
        "finite_grid_conformance",
        "empirical_allowance",
        "proxy",
        "conditional_bound",
    },
    "consistency": {
        "measured_error",
        "finite_grid_conformance",
        "empirical_allowance",
        "proxy",
        "conditional_bound",
    },
    "exactness": {"measured_error", "finite_grid_conformance"},
    "vacuity": {"vacuous"},
    "evidence_absent": {"evidence_absent"},
    "not_carried": {"not_carried"},
    # A transcription of another tool's run record.  claimgate carries the
    # verdict; it does not re-judge it and does not upgrade its evidence.
    "external_record": set(EVIDENCE_CLASSES),
}

#: What each class establishes, printed beside a verdict in the report.
ESTABLISHES = {
    "proof": "the claim, unconditionally",
    "certified_bound": "the claim, by a certified enclosure",
    "conditional_bound": "the claim, conditionally on its stated hypotheses",
    "measured_error": "the observed error on the measured cells; a breach refutes, a pass does not establish a uniform bound",
    "finite_grid_conformance": "conformance on the measured cells only",
    "empirical_allowance": "an allowance observed over a design; not a bound",
    "proxy": "evidence related to the claim, not the claim itself",
    "vacuous": "nothing: the bound cannot discriminate on these cells",
    "evidence_absent": "nothing: the evidence the row names was not produced",
    "not_carried": "nothing: this build does not carry the claim's subject",
}

FAIL_ON_DEFAULT = ("exceeded", "vacuous", "evidence_absent")

FAMILY = {
    "verified": "judged_and_met",
    "met_over_domain": "judged_and_met",
    "exceeded": "judged_and_unmet",
    "vacuous": "judged_and_unmet",
    "evidence_absent": "judged_and_unmet",
    "not_carried": "not_judged",
    "not_judged": "not_judged",
}


class BookError(Exception):
    """A book that cannot be loaded or validated."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("\n".join(errors))


class Book:
    """A validated claims book."""

    def __init__(self, data: dict[str, Any], path: Path, root: Path):
        self.data = data
        self.path = path
        self.root = root
        self.book = data["book"]
        self.claims = {claim["id"]: claim for claim in data.get("claims", [])}
        self.registrations = list(data.get("registrations", []))
        self.rows = {row["id"]: row for row in data["rows"]}
        self.row_order = [row["id"] for row in data["rows"]]
        self.unregistered = {
            entry["row"]: entry for entry in self.book.get("unregistered_rows", [])
        }
        defaults = data.get("defaults", {})
        self.fail_on = tuple(defaults.get("fail_on", FAIL_ON_DEFAULT))
        self.anchor_preference = defaults.get("anchor_preference", "auto")
        self.external_run = data.get("external_run")

    def resolve(self, relative: str) -> Path:
        """Resolve a book-relative path, refusing one that escapes the root."""
        return resolve_relative(self.root, relative)


def resolve_relative(root: Path, relative: str) -> Path:
    raw = Path(relative)
    if raw.is_absolute() or raw.drive or raw.root:
        raise BookError([f"{relative!r}: a book path must be relative to the root"])
    resolved = (root / raw).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise BookError([f"{relative!r}: the path escapes the root {str(root)!r}"]) from exc
    return resolved


def load_book(path: Path, root: Path | None = None) -> Book:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise BookError([f"{path}: cannot be read: {exc}"]) from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise BookError([f"{path}: is not JSON: {exc}"]) from exc
    if not isinstance(data, dict):
        raise BookError([f"{path}: the book must be a JSON object"])
    base = root if root is not None else path.parent
    errors = validate_book(data)
    if errors:
        raise BookError(errors)
    return Book(data, path, base)


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _check_source(errors: list[str], where: str, source, required: bool = True) -> None:
    if source is None:
        if required:
            errors.append(f"{where}: the source is missing")
        return
    if not isinstance(source, dict):
        errors.append(f"{where}: the source must be an object")
        return
    name = source.get("file")
    if not isinstance(name, str) or not name:
        errors.append(f"{where}: the source has no file")
    lines = source.get("lines")
    if (
        not isinstance(lines, list)
        or len(lines) != 2
        or not all(isinstance(n, int) and n >= 1 for n in lines)
        or lines[0] > lines[1]
    ):
        errors.append(f"{where}: the source lines must be two increasing positive integers")


def _check_bound(errors: list[str], where: str, bound, required: bool = True) -> None:
    if bound is None:
        if required:
            errors.append(f"{where}: the bound is missing")
        return
    if not isinstance(bound, dict):
        errors.append(f"{where}: the bound must be an object")
        return
    value = bound.get("value")
    if not (_is_number(value) or isinstance(value, str)):
        errors.append(f"{where}: the bound value must be a number or a numeric string")
    else:
        try:
            parsed = parse_exact(value)
        except NumberError as exc:
            errors.append(f"{where}: the bound cannot be read: {exc}")
        else:
            if isinstance(parsed, float) and math.isnan(parsed):
                errors.append(f"{where}: the bound is NaN")
    if not isinstance(bound.get("unit"), str) or not bound["unit"]:
        errors.append(f"{where}: the bound has no unit")


def _check_metric(errors: list[str], where: str, metric, required: bool = True) -> None:
    if metric is None:
        if required:
            errors.append(f"{where}: the metric is missing")
        return
    if not isinstance(metric, dict):
        errors.append(f"{where}: the metric must be an object")
        return
    kind = metric.get("kind")
    if kind not in METRIC_KINDS:
        errors.append(f"{where}: the metric kind {kind!r} is not one of {', '.join(METRIC_KINDS)}")
    eps = metric.get("epsilon")
    if eps is not None and not (_is_number(eps) and eps > 0):
        errors.append(f"{where}: the metric epsilon must be a positive number")


def _check_domain(errors: list[str], where: str, domain, required: bool = True) -> None:
    if domain is None:
        if required:
            errors.append(f"{where}: the domain is missing")
        return
    if not isinstance(domain, dict):
        errors.append(f"{where}: the domain must be an object")
        return
    if not isinstance(domain.get("description"), str) or not domain["description"]:
        errors.append(f"{where}: the domain has no description")
    scope = domain.get("scope", "whole")
    if scope not in ("whole", "stated"):
        errors.append(f"{where}: the domain scope {scope!r} is not whole or stated")
    interval = domain.get("interval")
    if interval is not None:
        if not isinstance(interval, dict):
            errors.append(f"{where}: the domain interval must be an object")
        else:
            for key in ("lo", "hi"):
                if key not in interval:
                    errors.append(f"{where}: the domain interval has no {key}")
                else:
                    try:
                        parse_exact(interval[key])
                    except NumberError as exc:
                        errors.append(f"{where}: the interval {key} cannot be read: {exc}")


def _check_single_filter(errors: list[str], where: str, filt) -> None:
    if not isinstance(filt, dict):
        errors.append(f"{where}: a filter criterion must be an object")
        return
    if not isinstance(filt.get("column"), str) or not filt["column"]:
        errors.append(f"{where}: the data filter has no column")
        return
    if not any(key in filt for key in ("equals", "startswith")):
        errors.append(f"{where}: the data filter has neither equals nor startswith")
    elif "equals" in filt and not isinstance(filt["equals"], str):
        errors.append(f"{where}: the data filter equals must be a string")
    elif "startswith" in filt and not isinstance(filt["startswith"], str):
        errors.append(f"{where}: the data filter startswith must be a string")


def _check_data(errors: list[str], where: str, data) -> None:
    if not isinstance(data, dict):
        errors.append(f"{where}: the data specification must be an object")
        return
    if not isinstance(data.get("file"), str) or not data["file"]:
        errors.append(f"{where}: the data file is missing")
    if data.get("format") != "csv":
        errors.append(f"{where}: the data format must be csv")
    comparison = data.get("comparison")
    required_columns = {
        "value_vs_reference": ("measured", "reference"),
        "consistency": ("a", "b"),
        "bit_identity": ("measured_bits", "expected_bits"),
        "exact": ("measured", "expected"),
        "vacuous": ("magnitude",),
    }
    if comparison not in required_columns:
        errors.append(f"{where}: the comparison {comparison!r} is not known")
        return
    columns = data.get("columns", {})
    if not isinstance(columns, dict):
        errors.append(f"{where}: the data columns must be an object")
        return
    for column in required_columns[comparison]:
        if not isinstance(columns.get(column), str) or not columns[column]:
            errors.append(f"{where}: comparison {comparison!r} needs the column {column!r}")
    if data.get("filter") is not None:
        filt = data["filter"]
        if not isinstance(filt, dict):
            errors.append(f"{where}: the data filter must be an object")
        elif "all" in filt:
            if not isinstance(filt["all"], list) or not filt["all"]:
                errors.append(f"{where}: the data filter 'all' must be a non-empty array")
            else:
                for j, part in enumerate(filt["all"]):
                    _check_single_filter(errors, f"{where} filter.all[{j}]", part)
        else:
            _check_single_filter(errors, where, filt)
    require = data.get("require_rows")
    if require is not None and not (isinstance(require, int) and require >= 1):
        errors.append(f"{where}: require_rows must be a positive integer")
    cross = data.get("crosscheck")
    if cross is not None:
        if not isinstance(cross, dict) or not isinstance(cross.get("column"), str):
            errors.append(f"{where}: the crosscheck has no column")
        elif not (_is_number(cross.get("tolerance")) and cross["tolerance"] > 0):
            errors.append(f"{where}: the crosscheck tolerance must be positive")


def validate_book(data: dict[str, Any]) -> list[str]:
    """Return every structural and referential error in a book."""
    errors: list[str] = []

    if data.get("claimgate_book") != BOOK_SCHEMA:
        errors.append(f"the top-level claimgate_book must be {BOOK_SCHEMA}")
    book = data.get("book")
    if not isinstance(book, dict):
        errors.append("the book metadata is missing")
    else:
        if not isinstance(book.get("id"), str) or not book["id"]:
            errors.append("the book has no id")
        if not isinstance(book.get("title"), str) or not book["title"]:
            errors.append("the book has no title")
        unregistered = book.get("unregistered_rows", [])
        if not isinstance(unregistered, list):
            errors.append("book.unregistered_rows must be an array")
        else:
            for entry in unregistered:
                if not isinstance(entry, dict):
                    errors.append("book.unregistered_rows has a non-object entry")
                    continue
                if not all(isinstance(entry.get(key), str) and entry.get(key) for key in
                           ("row", "treatment", "reason")):
                    errors.append(
                        f"book.unregistered_rows entry {entry.get('row')!r} needs row, treatment and reason"
                    )

    defaults = data.get("defaults", {})
    if not isinstance(defaults, dict):
        errors.append("defaults must be an object")
    elif defaults.get("anchor_preference", "auto") not in ("auto", "slices"):
        errors.append(
            "defaults.anchor_preference must be 'auto' or 'slices', "
            f"not {defaults.get('anchor_preference')!r}"
        )

    claims_list = data.get("claims", [])
    if not isinstance(claims_list, list):
        errors.append("claims must be an array")
        claims_list = []
    claims: dict[str, dict] = {}
    for index, claim in enumerate(claims_list):
        where = f"claim[{index}]"
        if not isinstance(claim, dict):
            errors.append(f"{where}: must be an object")
            continue
        cid = claim.get("id")
        if not isinstance(cid, str) or not cid:
            errors.append(f"{where}: has no id")
            continue
        where = f"claim {cid}"
        if cid in claims:
            errors.append(f"{where}: the id is used twice")
        claims[cid] = claim
        for field in ("object", "route", "subject"):
            if not isinstance(claim.get(field), str) or not claim[field]:
                errors.append(f"{where}: the {field} is missing")
        if claim.get("evidence_class") not in EVIDENCE_CLASSES:
            errors.append(f"{where}: the evidence class {claim.get('evidence_class')!r} is not known")
        _check_domain(errors, where, claim.get("domain"))
        _check_metric(errors, where, claim.get("metric"))
        _check_bound(errors, where, claim.get("bound"))
        bound = claim.get("bound")
        if isinstance(bound, dict) and bound.get("quantifier") not in QUANTIFIERS:
            errors.append(f"{where}: the quantifier {bound.get('quantifier')!r} is not known")
        output = claim.get("output")
        if not isinstance(output, dict) or not isinstance(output.get("representation"), str):
            errors.append(f"{where}: the output representation is missing")
        implementation = claim.get("implementation")
        if not isinstance(implementation, dict) or not all(
            isinstance(implementation.get(key), str) and implementation[key]
            for key in ("name", "version")
        ):
            errors.append(f"{where}: the implementation name and version are required")
        _check_source(errors, where, claim.get("source"))
        rows = claim.get("rows")
        if not isinstance(rows, list) or not rows or not all(isinstance(r, str) for r in rows):
            errors.append(f"{where}: rows must be a non-empty array of row ids")

    registrations = data.get("registrations", [])
    if not isinstance(registrations, list):
        errors.append("registrations must be an array")
        registrations = []
    registration_ids: set[str] = set()
    registered_claims: set[str] = set()
    cited_rows: dict[str, set[str]] = {}
    for index, reg in enumerate(registrations):
        where = f"registration[{index}]"
        if not isinstance(reg, dict):
            errors.append(f"{where}: must be an object")
            continue
        rid = reg.get("id")
        if not isinstance(rid, str) or not rid:
            errors.append(f"{where}: has no id")
            continue
        where = f"registration {rid}"
        if rid in registration_ids:
            errors.append(f"{where}: the id is used twice")
        registration_ids.add(rid)
        cid = reg.get("claim_id")
        if not isinstance(cid, str) or not cid:
            errors.append(f"{where}: has no claim_id")
        else:
            registered_claims.add(cid)
            if cid not in claims:
                errors.append(f"{where}: names claim {cid!r}, which the book does not hold")
            else:
                for row in reg.get("rows", []) if isinstance(reg.get("rows"), list) else []:
                    if isinstance(row, str):
                        cited_rows.setdefault(cid, set()).add(row)
        if not isinstance(reg.get("sentence"), str) or not reg["sentence"]:
            errors.append(f"{where}: the sentence is missing")
        _check_source(errors, where, reg.get("source"))
        rows = reg.get("rows")
        if not isinstance(rows, list) or not rows or not all(isinstance(r, str) for r in rows):
            errors.append(f"{where}: rows must be a non-empty array of row ids")
        figure = reg.get("figure")
        if figure is not None:
            if not isinstance(figure, dict) or not isinstance(figure.get("text"), str):
                errors.append(f"{where}: the figure must be an object with a text")
            else:
                try:
                    parse_exact(figure["text"])
                except NumberError as exc:
                    errors.append(f"{where}: the figure cannot be read: {exc}")
        supporting = reg.get("supporting", [])
        if not isinstance(supporting, list):
            errors.append(f"{where}: supporting must be an array")
        else:
            for j, item in enumerate(supporting):
                swhere = f"{where} supporting[{j}]"
                if not isinstance(item, dict):
                    errors.append(f"{swhere}: must be an object")
                    continue
                if not isinstance(item.get("sentence"), str) or not item["sentence"]:
                    errors.append(f"{swhere}: the sentence is missing")
                _check_source(errors, swhere, item.get("source"))

    rows_data = data.get("rows")
    if not isinstance(rows_data, list):
        errors.append("rows must be an array")
        rows_data = []
    rows: dict[str, dict] = {}
    for index, row in enumerate(rows_data):
        where = f"row[{index}]"
        if not isinstance(row, dict):
            errors.append(f"{where}: must be an object")
            continue
        row_id = row.get("id")
        if not isinstance(row_id, str) or not row_id:
            errors.append(f"{where}: has no id")
            continue
        where = f"row {row_id}"
        if row_id in rows:
            errors.append(f"{where}: the id is used twice")
        rows[row_id] = row
        row_type = row.get("type")
        if row_type not in ROW_TYPES:
            errors.append(f"{where}: the row type {row_type!r} is not known")
            continue
        for field in ("statement", "subject"):
            if not isinstance(row.get(field), str) or not row[field]:
                errors.append(f"{where}: the {field} is missing")
        evidence = row.get("evidence_class")
        if evidence not in EVIDENCE_CLASSES:
            errors.append(f"{where}: the evidence class {evidence!r} is not known")
        elif evidence not in ROW_ALLOWED_EVIDENCE[row_type]:
            errors.append(
                f"{where}: a {row_type} row cannot carry evidence class {evidence!r}; "
                f"the class establishes {ESTABLISHES.get(evidence, 'nothing')}"
            )
        relation = row.get("relation")
        if relation is not None and relation not in ("carries", "measures", "matches", "supports"):
            errors.append(f"{where}: the relation {relation!r} is not known")
        _check_domain(errors, where, row.get("domain"))
        if row.get("claim_id") is not None:
            if not isinstance(row["claim_id"], str):
                errors.append(f"{where}: claim_id must be a string")
            elif row["claim_id"] not in claims:
                errors.append(f"{where}: names claim {row['claim_id']!r}, which the book does not hold")
        figure_bound = row.get("figure_bound")
        if figure_bound is not None and not (_is_number(figure_bound) and figure_bound > 0):
            errors.append(f"{where}: figure_bound must be a positive number or absent")
        if row_type in ("reference_comparison", "consistency", "exactness", "vacuity"):
            _check_metric(errors, where, row.get("metric"))
            _check_bound(errors, where, row.get("bound"))
            _check_data(errors, where, row.get("data"))
        if row_type in ("reference_comparison", "consistency", "vacuity"):
            if row.get("quantifier") not in QUANTIFIERS:
                errors.append(f"{where}: the quantifier {row.get('quantifier')!r} is not known")
        if row_type == "exactness":
            if row.get("quantifier") not in QUANTIFIERS:
                errors.append(f"{where}: the quantifier {row.get('quantifier')!r} is not known")
        if row_type == "external_record":
            record = row.get("record")
            if not isinstance(record, dict):
                errors.append(f"{where}: an external_record row needs a record object")
            else:
                if not isinstance(record.get("file"), str) or not record["file"]:
                    errors.append(f"{where}: the record file is missing")
                if not isinstance(record.get("row_index"), int) or record["row_index"] < 1:
                    errors.append(f"{where}: the record row_index must be a positive integer")
                if record.get("verdict") is not None and record["verdict"] not in VERDICTS:
                    errors.append(f"{where}: the record verdict {record['verdict']!r} is not known")
        if row_type in ("not_carried", "evidence_absent"):
            if not isinstance(row.get("reason"), str) or not row["reason"]:
                errors.append(f"{where}: a {row_type} row needs a reason")
        state = row.get("state")
        if state is not None:
            if state not in ("not_carried", "not_judged", "evidence_absent"):
                errors.append(f"{where}: the state {state!r} is not known")
            elif not isinstance(row.get("reason"), str) or not row["reason"]:
                errors.append(f"{where}: a row with state {state} needs a reason")

    # Referential integrity.
    for cid, claim in claims.items():
        for row_id in claim.get("rows", []) if isinstance(claim.get("rows"), list) else []:
            if row_id not in rows:
                errors.append(f"claim {cid}: names row {row_id!r}, which the book does not hold")
            elif row_id not in cited_rows.get(cid, set()):
                errors.append(
                    f"claim {cid}: names row {row_id!r}, but no registration of the claim cites it"
                )
        if claim.get("evidence_class") in ("proof", "certified_bound"):
            row_classes = {
                rows[row_id].get("evidence_class")
                for row_id in claim.get("rows", []) if isinstance(claim.get("rows"), list)
                if row_id in rows
            }
            if claim["evidence_class"] not in row_classes:
                errors.append(
                    f"claim {cid}: is registered as {claim['evidence_class']!r}, but no carrying "
                    f"row carries that class (the rows carry {sorted(c for c in row_classes if c)})"
                )
    for reg in registrations:
        if not isinstance(reg, dict):
            continue
        for row_id in reg.get("rows", []) if isinstance(reg.get("rows"), list) else []:
            if row_id not in rows:
                errors.append(
                    f"registration {reg.get('id')}: names row {row_id!r}, which the book does not hold"
                )
    for row_id, row in rows.items():
        if row.get("claim_id") and row_id not in cited_rows.get(row["claim_id"], set()):
            errors.append(
                f"row {row_id}: names claim {row['claim_id']!r}, but no registration of the claim cites the row"
            )
    released = set()
    if isinstance(book, dict):
        for entry in book.get("unregistered_rows", []):
            if isinstance(entry, dict) and isinstance(entry.get("row"), str):
                released.add(entry["row"])
    for row_id in rows:
        cited = any(row_id in found for found in cited_rows.values())
        if not cited and row_id not in released:
            errors.append(
                f"row {row_id}: no registration cites the row and it is not listed in "
                "book.unregistered_rows with a treatment and reason"
            )
    return errors


def external_run_path(book: Book):
    if not book.external_run:
        return None
    relative = book.external_run.get("file")
    if not isinstance(relative, str):
        raise BookError(["external_run.file must be a string"])
    return book.resolve(relative)
