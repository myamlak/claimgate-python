"""Turning a row and its data into one verdict.

The verdict is one of the seven operational verdicts.  The evidence class
decides what the verdict can be read as; the row type decides what is
computed.
"""

from __future__ import annotations

import math

from .data import DataError, evaluate_data
from .exact import format_fraction, fraction_to_float
from .model import ESTABLISHES, FAMILY, VERDICTS


def _render(value) -> str:
    if isinstance(value, float):
        return str(value)
    return format_fraction(value)


def _as_float(value) -> float:
    return fraction_to_float(value)


def _limitations(row, cells: int) -> list[str]:
    evidence = row["evidence_class"]
    limitations: list[str] = []
    if evidence in (
        "measured_error",
        "finite_grid_conformance",
        "empirical_allowance",
        "proxy",
        "conditional_bound",
    ):
        limitations.append(
            f"the verdict covers {cells} measured cell(s) and makes no statement between them"
        )
    if evidence == "measured_error" and row.get("quantifier") == "uniform":
        limitations.append(
            "a finite measured set cannot establish a uniform bound; a breach refutes it, a pass "
            "establishes conformance on the measured cells only"
        )
    if evidence == "proxy":
        limitations.append("the row is proxy evidence, not the claim itself")
    if evidence == "conditional_bound":
        limitations.append("the verdict is conditional on the row's stated assumptions")
    if evidence == "empirical_allowance":
        limitations.append("an observed allowance is not a bound")
    return limitations


def _base_result(row) -> dict:
    relation = row.get("relation")
    if relation is None and row.get("claim_id"):
        relation = "carries"
    result = {
        "id": row["id"],
        "type": row["type"],
        "claim_id": row.get("claim_id"),
        "statement": row["statement"],
        "subject": row["subject"],
        "verdict": "not_judged",
        "family": "not_judged",
        "met": None,
        "evidence_class": row["evidence_class"],
        "metric": row.get("metric"),
        "bound": row.get("bound"),
        "quantifier": row.get("quantifier"),
        "domain": row.get("domain"),
        "cells": 0,
        "judged_cells": 0,
        "failures": 0,
        "vacuous_cells": 0,
        "discriminating_cells": 0,
        "worst": {},
        "establishes": ESTABLISHES.get(row["evidence_class"], ""),
        "limitations": [],
    }
    if relation:
        result["relation"] = relation
    return result


def _judged(result: dict, verdict: str, met: bool) -> dict:
    if verdict not in VERDICTS:
        raise ValueError(f"the verdict {verdict!r} is not known")
    result["verdict"] = verdict
    result["family"] = FAMILY[verdict]
    result["met"] = met
    return result


def evaluate_external(row, record_rows: list[dict]) -> dict:
    result = _base_result(row)
    record = row["record"]
    index = record["row_index"]
    if not 1 <= index <= len(record_rows):
        raise DataError(
            f"row {row['id']}: the external record has {len(record_rows)} rows, "
            f"the book names row {index}"
        )
    external = record_rows[index - 1]
    verdict = external.get("verdict")
    if verdict not in VERDICTS:
        raise DataError(f"row {row['id']}: the external record's row {index} has no known verdict")
    if record.get("row_id") and external.get("id") and external["id"] != record["row_id"]:
        raise DataError(
            f"row {row['id']}: the external record's row {index} is {external['id']!r}, "
            f"not {record['row_id']!r}"
        )
    if record.get("verdict") and record["verdict"] != verdict:
        raise DataError(
            f"row {row['id']}: the book declares {record['verdict']!r} but the external "
            f"record holds {verdict!r}"
        )
    result["verdict"] = verdict
    result["family"] = FAMILY[verdict]
    result["met"] = verdict in ("verified", "met_over_domain")
    result["establishes"] = external.get("establishes", ESTABLISHES.get(row["evidence_class"], ""))
    result["limitations"] = list(external.get("limitations", []))
    result["limitations"].append(
        "the verdict is the external tool's run record; claimgate checks the record's "
        "structure and digest and does not re-measure the row"
    )
    result["external"] = {
        "row_index": index,
        "id": external.get("id"),
        "verdict": verdict,
        "tool": "the row's external run record",
    }
    if external.get("worst") is not None:
        result["worst"] = external["worst"]
    for key in ("cells", "failures", "vacuous_cells"):
        if isinstance(external.get(key), int):
            result[key] = external[key]
    result["judged_cells"] = result["cells"]
    if external.get("reason"):
        result["reason"] = external["reason"]
    return result


def evaluate_row(book, row, record_rows) -> dict:
    row_type = row["type"]

    if row_type == "not_carried":
        result = _base_result(row)
        result["verdict"] = "not_carried"
        result["family"] = "not_judged"
        result["met"] = False
        result["reason"] = row.get("reason", "")
        result["establishes"] = ESTABLISHES["not_carried"]
        return result

    if row_type == "evidence_absent":
        result = _base_result(row)
        result["verdict"] = "evidence_absent"
        result["family"] = "judged_and_unmet"
        result["met"] = False
        result["reason"] = row.get("reason", "")
        result["establishes"] = ESTABLISHES["evidence_absent"]
        result["limitations"] = [f"the evidence named is absent: {row.get('reason', '')}"]
        return result

    if row_type == "external_record":
        if record_rows is None:
            raise DataError(
                f"row {row['id']}: the book has no external_run, so an external_record row "
                "cannot be read"
            )
        return evaluate_external(row, record_rows)

    if row.get("state") == "not_carried":
        result = _base_result(row)
        result["verdict"] = "not_carried"
        result["family"] = "not_judged"
        result["met"] = False
        result["reason"] = row.get("reason", "")
        result["establishes"] = ESTABLISHES["not_carried"]
        return result

    if row.get("state") == "evidence_absent":
        result = _base_result(row)
        result["verdict"] = "evidence_absent"
        result["family"] = "judged_and_unmet"
        result["met"] = False
        result["reason"] = row.get("reason", "")
        result["establishes"] = ESTABLISHES["evidence_absent"]
        result["limitations"] = [f"the evidence named is absent: {row.get('reason', '')}"]
        return result

    measurement = evaluate_data(book, row)
    result = _base_result(row)

    if measurement.get("missing") is not None or measurement.get("empty"):
        result["verdict"] = "evidence_absent"
        result["family"] = "judged_and_unmet"
        result["met"] = False
        if measurement.get("missing"):
            result["reason"] = f"the data file {measurement['missing']} does not exist"
        else:
            result["reason"] = f"the data selection in {measurement.get('path')} has no rows"
        result["establishes"] = ESTABLISHES["evidence_absent"]
        result["limitations"] = [result["reason"]]
        return result

    cells = measurement["cells"]
    failures = measurement["failures"]
    vacuous = measurement["vacuous_cells"]
    count = len(cells)
    worst = measurement["worst"]

    result["cells"] = count
    result["judged_cells"] = count
    result["failures"] = failures
    result["vacuous_cells"] = vacuous
    result["discriminating_cells"] = max(0, count - vacuous)
    result["data"] = {
        "file": row["data"]["file"],
        "path": measurement["path"],
        "comparison": row["data"]["comparison"],
        "rows": measurement["rows"],
    }
    if row.get("quantifier") == "band_maximum":
        result["data"]["bands"] = measurement["bands"]
    if worst is not None:
        result["worst"] = {
            "value": _as_float(worst.metric),
            "text": _render(worst.metric),
            "cell": worst.as_dict(),
        }
    result["limitations"] = _limitations(row, count)

    if row.get("state") == "not_judged":
        result["verdict"] = "not_judged"
        result["family"] = "not_judged"
        result["met"] = None
        result["reason"] = row.get("reason", "")
        result["limitations"].append("the row's measurement is recorded but withheld from the verdict")
        return result

    if row_type == "vacuity":
        if count == 0:
            result["verdict"] = "evidence_absent"
            result["family"] = "judged_and_unmet"
            result["met"] = False
            result["reason"] = "the row measured no cell"
            return result
        if vacuous == count:
            result["verdict"] = "vacuous"
            result["family"] = "judged_and_unmet"
            result["met"] = False
            result["establishes"] = ESTABLISHES["vacuous"]
            result["limitations"].append(
                "the bound is at least the value's own magnitude at every measured cell, "
                "so losing the value would still pass"
            )
        else:
            _judged(result, "verified", True)
        return result

    if failures > 0:
        _judged(result, "exceeded", False)
        return result

    if vacuous == count and count > 0:
        result["verdict"] = "vacuous"
        result["family"] = "judged_and_unmet"
        result["met"] = False
        result["establishes"] = ESTABLISHES["vacuous"]
        result["limitations"].append(
            "the bound is at least the value's own magnitude at every measured cell"
        )
        return result

    stated = (row.get("domain") or {}).get("scope") == "stated"
    _judged(result, "met_over_domain" if stated else "verified", True)
    if stated:
        result["establishes"] = "on the stated domain, " + result["establishes"]
        result["limitations"].append(
            "the claim is met over the domain the document states, not over the whole input domain"
        )
    return result
