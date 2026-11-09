"""Reading a row's measured data and computing the metric exactly.

The data file is a CSV.  A value may be written as a decimal or as the
sixteen hexadecimal digits of a binary64 bit pattern; a bit pattern is read
exactly, and a decimal through :class:`decimal.Decimal`, also exactly.  The
metric is computed with :class:`fractions.Fraction`, so a comparison is not
decided by the rounding of a printed error column.

A row may name a precomputed error column as a cross-check.  When it does,
claimgate recomputes the error from the raw values and requires its own
result to agree with the deposited column; disagreement is a data error, not
a silent pass.
"""

from __future__ import annotations

import csv
import math
from fractions import Fraction
from pathlib import Path

from .exact import (
    EPS64,
    NumberError,
    binary64_ulp_at,
    bits_of,
    format_fraction,
    fraction_to_float,
    parse_decimal_value,
    parse_exact,
    parse_float_value,
    ulp_distance,
)


class DataError(Exception):
    """A data file that cannot be read as the row's specification says."""


def read_csv(path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            fieldnames = None
            for line in handle:
                if line.lstrip().startswith("#") or not line.strip():
                    continue
                reader = csv.DictReader([line], fieldnames=fieldnames, delimiter=",")
                if fieldnames is None:
                    fieldnames = reader.fieldnames
                    if fieldnames is None:
                        raise DataError(f"{path}: the CSV has no header row")
                    headers = fieldnames
                    try:
                        first = next(reader)
                    except StopIteration:
                        continue
                    if any(value and value.strip() for value in first.values()):
                        rows.append(first)
                    continue
                try:
                    row = next(reader)
                except StopIteration:
                    continue
                rows.append(row)
    except OSError as exc:
        raise DataError(f"{path}: cannot be read: {exc}") from exc
    except csv.Error as exc:
        raise DataError(f"{path}: is not a readable CSV: {exc}") from exc
    if not rows:
        raise DataError(f"{path}: the CSV has no data rows")
    return rows


def _matches(row: dict[str, str], filt: dict) -> bool:
    column = filt["column"]
    value = (row.get(column) or "").strip()
    if "equals" in filt:
        return value == filt["equals"]
    return value.startswith(filt["startswith"])


def apply_filter(rows: list[dict[str, str]], filt) -> list[dict[str, str]]:
    if not filt:
        return rows
    if "all" in filt:
        criteria = filt["all"]
        return [row for row in rows if all(_matches(row, part) for part in criteria)]
    return [row for row in rows if _matches(row, filt)]


def _column(row: dict[str, str], name: str, path: Path) -> str:
    if name not in row:
        raise DataError(f"{path}: the CSV has no column {name!r}")
    return (row.get(name) or "").strip()


def _read_value(row, columns, value_key, bits_key, path):
    """Return (value, bits, text) for the named value or bit column."""
    bits_name = columns.get(bits_key)
    if bits_name:
        text = _column(row, bits_name, path)
        try:
            value, bits = parse_float_value(text)
        except NumberError as exc:
            raise DataError(f"{path}: the column {bits_name!r}: {exc}") from exc
        return value, bits, text
    value_name = columns.get(value_key)
    if not value_name:
        raise DataError(f"{path}: the row specification names neither {value_key} nor {bits_key}")
    text = _column(row, value_name, path)
    try:
        value = parse_decimal_value(text)
    except NumberError as exc:
        raise DataError(f"{path}: the column {value_name!r}: {exc}") from exc
    return value, None, text


def _diff(got, ref):
    """Exact |got - ref|, with non-finite operands decided explicitly."""
    got_finite = isinstance(got, Fraction)
    ref_finite = isinstance(ref, Fraction)
    if got_finite and ref_finite:
        return abs(got - ref)
    if isinstance(got, float) and math.isnan(got):
        return math.inf
    if isinstance(ref, float) and math.isnan(ref):
        return math.inf
    if got == ref:
        return Fraction(0)
    return math.inf


def _relative(got, ref):
    if isinstance(got, Fraction) and isinstance(ref, Fraction):
        if ref == 0:
            return Fraction(0) if got == 0 else math.inf
        return abs(got - ref) / abs(ref)
    return _diff(got, ref)


def _bits_for(value, bits):
    if bits is not None:
        return bits
    if isinstance(value, float):
        return bits_of(value)
    return bits_of(float(value))


def metric_value(kind: str, got, ref, got_bits, ref_bits, epsilon, scale=None):
    """The exact value of one comparison in the metric's unit."""
    if kind == "absolute":
        return _diff(got, ref)
    if kind == "relative":
        return _relative(got, ref)
    if kind == "epsilon":
        return _relative(got, ref) / epsilon if isinstance(_relative(got, ref), Fraction) else _relative(got, ref)
    if kind == "scaled":
        if scale is None:
            raise DataError("a scaled metric needs a scale column")
        scale = abs(scale) if isinstance(scale, Fraction) else scale
        if isinstance(scale, Fraction) and scale == 0:
            raise DataError("a scaled metric has a zero scale")
        diff = _diff(got, ref)
        return diff / scale if isinstance(diff, Fraction) and isinstance(scale, Fraction) else diff
    if kind == "bit_identity":
        return Fraction(0) if _bits_for(got, got_bits) == _bits_for(ref, ref_bits) else Fraction(1)
    if kind == "exact":
        if isinstance(got, Fraction) and isinstance(ref, Fraction):
            return Fraction(0) if got == ref else Fraction(1)
        return Fraction(0) if got == ref else Fraction(1)
    if kind == "ulp":
        return Fraction(ulp_distance(_bits_for(got, got_bits), _bits_for(ref, ref_bits)))
    if kind == "ulp_exact":
        # The distance from a binary64 result to an exact real reference,
        # divided by the spacing of binary64 at the reference's correctly
        # rounded double.  That is the definition SLEEF's own tester uses
        # (countULPdp), with the spacing floored at the smallest subnormal.
        if isinstance(got, Fraction) and isinstance(ref, Fraction):
            try:
                nearest = float(ref)
            except OverflowError:
                nearest = math.inf
            if math.isfinite(nearest):
                denominator = binary64_ulp_at(Fraction(nearest))
            else:
                denominator = binary64_ulp_at(ref)
            return abs(got - ref) / denominator
        return math.inf
    raise DataError(f"the metric {kind!r} is not known")


def cell_context(row: dict[str, str], columns: dict[str, str], row_number: int) -> dict:
    context: dict = {"data_row": row_number}
    label = columns.get("label")
    if label and row.get(label):
        context["label"] = row[label].strip()
    for key in ("x", "input_bits", "order", "function", "band"):
        if key in row and row[key] != "":
            context[key] = row[key].strip()
    return context


class Cell:
    def __init__(self, context, metric, got_text, ref_text, got_bits=None, ref_bits=None):
        self.context = context
        self.metric = metric
        self.got_text = got_text
        self.ref_text = ref_text
        self.got_bits = got_bits
        self.ref_bits = ref_bits

    def as_dict(self) -> dict:
        out = dict(self.context)
        out["metric"] = _render(self.metric)
        out["measured"] = self.got_text
        out["reference"] = self.ref_text
        if self.got_bits is not None:
            out["measured_bits"] = f"{self.got_bits:016x}"
        if self.ref_bits is not None:
            out["reference_bits"] = f"{self.ref_bits:016x}"
        return out


def _render(value):
    if isinstance(value, Fraction):
        return format_fraction(value)
    return str(value)


def evaluate_data(book, row) -> dict:
    """Read a measured row's CSV and return its cells and statistics.

    Returns a dictionary with ``cells`` (a list of :class:`Cell`),
    ``metric_values``, ``failures``, ``vacuous_cells``, ``worst`` and
    ``bands``.  Raises :class:`DataError` when the file or the specification
    is wrong; a missing file or an empty selection is reported by the caller
    as the EvidenceAbsent verdict, not as a data error.
    """
    spec = row["data"]
    path = book.resolve(spec["file"])
    if not path.is_file():
        return {"missing": str(path)}
    raw_rows = read_csv(path)
    selected = apply_filter(raw_rows, spec.get("filter"))
    require = spec.get("require_rows")
    if require is not None and len(selected) != require:
        raise DataError(
            f"{path}: the selection has {len(selected)} rows, the book requires {require}"
        )
    if not selected:
        return {"missing": None, "empty": True, "path": str(path)}

    comparison = spec["comparison"]
    columns = spec.get("columns", {})
    metric_spec = row.get("metric", {})
    kind = metric_spec.get("kind")
    epsilon = parse_exact(metric_spec.get("epsilon", float(EPS64)))
    bound = parse_exact(row["bound"]["value"])

    cells: list[Cell] = []
    failures = 0
    vacuous = 0
    crosscheck_failures = []

    for index, raw in enumerate(selected, 1):
        got_text = ref_text = ""
        got_bits = ref_bits = None
        try:
            if comparison == "value_vs_reference":
                got, got_bits, got_text = _read_value(
                    raw, columns, "measured", "measured_bits", path
                )
                ref, ref_bits, ref_text = _read_value(
                    raw, columns, "reference", "reference_bits", path
                )
            elif comparison == "bit_identity":
                got_text = _column(raw, columns["measured_bits"], path)
                ref_text = _column(raw, columns["expected_bits"], path)
                got, got_bits = parse_float_value(got_text)
                ref, ref_bits = parse_float_value(ref_text)
            elif comparison == "exact":
                got_text = _column(raw, columns["measured"], path)
                ref_text = _column(raw, columns["expected"], path)
                got = parse_decimal_value(got_text)
                ref = parse_decimal_value(ref_text)
            elif comparison == "consistency":
                got_text = _column(raw, columns["a"], path)
                ref_text = _column(raw, columns["b"], path)
                got = parse_decimal_value(got_text)
                ref = parse_decimal_value(ref_text)
            elif comparison == "vacuous":
                ref_text = _column(raw, columns["magnitude"], path)
                ref = parse_decimal_value(ref_text)
                got, got_bits, got_text = ref, None, ref_text
            else:
                raise DataError(f"{path}: the comparison {comparison!r} is not known")
        except NumberError as exc:
            raise DataError(f"{path}: data row {index}: {exc}") from exc

        scale = None
        scale_bits_name = columns.get("scale_bits")
        scale_name = columns.get("scale")
        if scale_bits_name:
            scale_text = _column(raw, scale_bits_name, path)
            try:
                scale, _ = parse_float_value(scale_text)
            except NumberError as exc:
                raise DataError(f"{path}: the scale column {scale_bits_name!r}: {exc}") from exc
        elif scale_name:
            scale_text = _column(raw, scale_name, path)
            try:
                scale = parse_decimal_value(scale_text)
            except NumberError as exc:
                raise DataError(f"{path}: the scale column {scale_name!r}: {exc}") from exc

        value = metric_value(kind, got, ref, got_bits, ref_bits, epsilon, scale)
        context = cell_context(raw, columns, index)
        cells.append(Cell(context, value, got_text, ref_text, got_bits, ref_bits))

        if isinstance(value, Fraction) and isinstance(bound, Fraction):
            if value > bound:
                failures += 1
        elif isinstance(value, Fraction):
            if bound == math.inf:
                pass
            elif bound == -math.inf:
                failures += 1
        elif value == math.inf:
            failures += 1
        # value is nan only if a metric produced it; counted as a failure.
        elif isinstance(value, float) and math.isnan(value):
            failures += 1

        if comparison == "vacuous":
            if isinstance(ref, Fraction) and isinstance(bound, Fraction) and abs(ref) <= bound:
                vacuous += 1
        elif kind in ("absolute", "scaled") and isinstance(ref, Fraction) and isinstance(bound, Fraction):
            # An absolute bound is vacuous at a cell where the value is at
            # or below the bound: losing the value entirely still passes.
            cell_bound = bound if kind == "absolute" else bound * abs(scale)
            if abs(ref) <= cell_bound:
                vacuous += 1

        cross = spec.get("crosscheck")
        if cross:
            column = cross["column"]
            text = (raw.get(column) or "").strip()
            if text:
                try:
                    deposited = float(text)
                except ValueError as exc:
                    raise DataError(f"{path}: the crosscheck column {column!r}: {exc}") from exc
                ours = fraction_to_float(value)
                diff = abs(ours - deposited)
                scale_ref = max(abs(deposited), 1.0)
                if diff / scale_ref > cross["tolerance"]:
                    crosscheck_failures.append(
                        f"{path}: data row {index}: the computed metric {ours!r} differs from "
                        f"the deposited {column} {deposited!r}"
                    )

    if crosscheck_failures:
        raise DataError("; ".join(crosscheck_failures[:3]) + (
            f" (and {len(crosscheck_failures) - 3} more)" if len(crosscheck_failures) > 3 else ""
        ))

    worst = None
    for cell in cells:
        if worst is None or _greater(cell.metric, worst.metric):
            worst = cell

    bands = []
    band_column = columns.get("band")
    if row.get("quantifier") == "band_maximum" and band_column:
        groups: dict[str, list[Cell]] = {}
        for cell in cells:
            name = cell.context.get("band", "")
            groups.setdefault(name, []).append(cell)
        failures = 0
        for name, group in groups.items():
            group_worst = max(group, key=lambda cell: _sort_key(cell.metric))
            exceeded = _over(group_worst.metric, bound)
            if exceeded:
                failures += len(group)
            bands.append(
                {
                    "band": name,
                    "cells": len(group),
                    "worst": _render(group_worst.metric),
                    "worst_cell": group_worst.as_dict(),
                    "verdict": "exceeded" if exceeded else "verified",
                }
            )

    return {
        "path": str(path),
        "cells": cells,
        "metric_values": [cell.metric for cell in cells],
        "failures": failures,
        "vacuous_cells": vacuous,
        "worst": worst,
        "bands": bands,
        "rows": len(cells),
    }


def _greater(a, b) -> bool:
    if isinstance(a, Fraction) and isinstance(b, Fraction):
        return a > b
    if isinstance(a, float) and math.isnan(a):
        return False
    if isinstance(b, float) and math.isnan(b):
        return True
    return a > b


def _sort_key(value):
    if isinstance(value, Fraction):
        return (0, value)
    if isinstance(value, float) and math.isnan(value):
        return (2, Fraction(0))
    return (1, Fraction(0))


def _over(value, bound) -> bool:
    if isinstance(value, Fraction) and isinstance(bound, Fraction):
        return value > bound
    if isinstance(value, float) and math.isnan(value):
        return True
    if value == math.inf:
        return True
    if bound == math.inf:
        return False
    return value > bound
