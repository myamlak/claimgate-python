"""Running a book: checks, row evaluation, report and exit status."""

from __future__ import annotations

import hashlib
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from .checks import check_anchors, check_bindings, check_external_run, check_figures
from .evaluate import evaluate_row
from .model import (
    RUN_SCHEMA,
    TOOL_NAME,
    TOOL_VERSION,
    BookError,
    load_book,
)

VERDICT_LABEL = {
    "verified": "VERIFIED",
    "met_over_domain": "MET OVER STATED DOMAIN",
    "exceeded": "EXCEEDED",
    "vacuous": "VACUOUS",
    "evidence_absent": "EVIDENCE ABSENT",
    "not_carried": "NOT CARRIED",
    "not_judged": "NOT JUDGED",
}

FAILING_VERDICTS = ("exceeded", "vacuous", "evidence_absent")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _environment() -> dict:
    return {
        "python": sys.version.split()[0],
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "executable": sys.executable,
    }


def run_book(
    book_path: Path,
    root: Path | None = None,
    anchor_mode: str = "auto",
    command: list[str] | None = None,
    portable: bool = False,
) -> tuple[dict, int, str]:
    """Run a book and return ``(report, exit_status, human_text)``.

    With ``portable=True`` the paths in the report are written relative to
    the invocation directory, so a deposited report does not carry the
    machine's absolute paths.  The SHA-256 digests are unchanged.

    Raises :class:`BookError` when the book cannot be loaded or validated.
    """
    started = time.perf_counter()
    started_utc = _now()
    book = load_book(book_path, root=root)
    book_digest = _sha256(book_path)

    inputs: dict[str, dict] = {}

    def record_input(role: str, path: Path) -> None:
        if not path.is_file():
            return
        key = str(path.resolve())
        if key in inputs:
            return
        inputs[key] = {
            "role": role,
            "path": key,
            "sha256": _sha256(path),
            "bytes": path.stat().st_size,
        }

    record_input("book", book_path)

    for row in book.rows.values():
        if row.get("data") and isinstance(row["data"].get("file"), str):
            try:
                record_input("data", book.resolve(row["data"]["file"]))
            except BookError:
                pass

    bindings = check_bindings(book)
    external = check_external_run(book)
    external_rows = external.get("rows")
    if external_rows is None and any(
        row["type"] == "external_record" for row in book.rows.values()
    ):
        external["failed"] = list(external.get("failed", [])) + [
            "the book has external_record rows but names no external_run"
        ]

    if anchor_mode == "none":
        anchors = {"mode": "skipped", "checked": 0, "failed": [], "sources": []}
    else:
        anchors = check_anchors(book, anchor_mode)
    for entry in anchors.get("sources", []):
        path = entry.get("path")
        if path:
            record_input("anchor", Path(path))
    if book.external_run:
        try:
            record_input("external-run", book.resolve(book.external_run["file"]))
        except BookError:
            pass

    figures = check_figures(book)

    row_results = []
    for row_id in book.row_order:
        row_results.append(evaluate_row(book, book.rows[row_id], external_rows))

    summary = {
        "rows": len(row_results),
        "verified": 0,
        "met_over_domain": 0,
        "exceeded": 0,
        "vacuous": 0,
        "evidence_absent": 0,
        "not_carried": 0,
        "not_judged": 0,
    }
    for result in row_results:
        summary[result["verdict"]] = summary.get(result["verdict"], 0) + 1
    summary["met"] = summary["verified"] + summary["met_over_domain"]
    summary["judged"] = (
        summary["verified"]
        + summary["met_over_domain"]
        + summary["exceeded"]
        + summary["vacuous"]
        + summary["evidence_absent"]
    )

    check_failures = (
        list(bindings["failed"])
        + list(anchors["failed"])
        + list(figures["failed"])
        + list(external.get("failed", []))
    )
    failing_rows = [result for result in row_results if result["verdict"] in book.fail_on]
    exit_status = 1 if (check_failures or failing_rows) else 0

    def registration_failed(reg_id: str, failures: list[str]) -> bool:
        prefix = f"registration {reg_id}"
        return any(
            failure.startswith(prefix + ":") or failure.startswith(prefix + " supporting[")
            for failure in failures
        )

    registration_report = []
    for reg in book.registrations:
        figure = reg.get("figure")
        entry = {
            "id": reg["id"],
            "claim_id": reg["claim_id"],
            "source": {
                "file": reg["source"]["file"],
                "lines": list(reg["source"]["lines"]),
            },
            "rows": list(reg["rows"]),
            "anchor": "failed" if registration_failed(reg["id"], anchors["failed"]) else "ok",
            "figure_check": "absent",
        }
        if figure:
            entry["figure"] = {"text": figure["text"]}
            entry["figure_check"] = (
                "failed" if registration_failed(reg["id"], figures["failed"]) else "ok"
            )
        registration_report.append(entry)

    finished = time.perf_counter()
    report = {
        "schema": RUN_SCHEMA,
        "tool": {"name": TOOL_NAME, "version": TOOL_VERSION, "writer": f"{TOOL_NAME} reference runner"},
        "book": {
            "id": book.book["id"],
            "title": book.book.get("title", ""),
            "path": str(book_path.resolve()),
            "sha256": book_digest,
        },
        "root": str(book.root.resolve()),
        "command": command or [],
        "started_utc": started_utc,
        "finished_utc": _now(),
        "duration_s": round(finished - started, 6),
        "environment": _environment(),
        "inputs": list(inputs.values()),
        "registrations": registration_report,
        "checks": {
            "anchors": {
                "mode": anchors.get("mode", "skipped"),
                "checked": anchors.get("checked", 0),
                "failed": list(anchors.get("failed", [])),
                "sources": list(anchors.get("sources", [])),
            },
            "figures": {
                "checked": figures["checked"],
                "absent": figures["absent"],
                "failed": list(figures["failed"]),
            },
            "bindings": {
                "checked": bindings["checked"],
                "failed": list(bindings["failed"]),
            },
        },
        "rows": row_results,
        "summary": summary,
        "exit_status": exit_status,
    }
    if external.get("file"):
        report["checks"]["external_run"] = {
            "file": external.get("file"),
            "sha256": external.get("sha256"),
            "tool": external.get("tool"),
            "version": external.get("version"),
            "exit_status": external.get("exit_status"),
            "failed": list(external.get("failed", [])),
        }
    report["inputs"] = list(inputs.values())
    if portable:
        base = Path.cwd()
        report["book"]["path"] = _portable(book_path, base)
        report["root"] = _portable(book.root, base)
        for entry in report["inputs"]:
            entry["path"] = _portable(Path(entry["path"]), base)
        for entry in report["checks"]["anchors"]["sources"]:
            if entry.get("path"):
                entry["path"] = _portable(Path(entry["path"]), base)
        for row in report["rows"]:
            data = row.get("data")
            if isinstance(data, dict) and data.get("path"):
                data["path"] = _portable(Path(data["path"]), base)
        if report["command"]:
            report["command"][0] = Path(report["command"][0]).name
        report["environment"]["executable"] = Path(
            report["environment"]["executable"]
        ).name
    human = format_human(report)
    return report, exit_status, human


def _portable(path: Path, base: Path) -> str:
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        return str(path)


def format_human(report: dict) -> str:
    lines: list[str] = []
    lines.append(f"{report['tool']['name']} {report['tool']['version']}")
    lines.append(f"book      : {report['book']['id']} ({report['book']['path']})")
    lines.append(f"root      : {report['root']}")
    checks = report["checks"]
    lines.append(
        "anchors   : {mode}, {checked} checked, {failed} failed".format(
            mode=checks["anchors"]["mode"],
            checked=checks["anchors"]["checked"],
            failed=len(checks["anchors"]["failed"]),
        )
    )
    lines.append(
        "figures   : {checked} checked, {absent} without a figure, {failed} failed".format(
            checked=checks["figures"]["checked"],
            absent=checks["figures"]["absent"],
            failed=len(checks["figures"]["failed"]),
        )
    )
    lines.append(
        "bindings  : {checked} rows cited or released, {failed} failed".format(
            checked=checks["bindings"]["checked"],
            failed=len(checks["bindings"]["failed"]),
        )
    )
    external = checks.get("external_run") or {}
    if external.get("file"):
        lines.append(
            "external  : {tool} {version}, exit {exit_status}, {failed} failed".format(
                tool=external.get("tool") or "unknown",
                version=external.get("version") or "",
                exit_status=external.get("exit_status"),
                failed=len(external.get("failed", [])),
            )
        )
    lines.append("")
    lines.append("rows:")
    for result in report["rows"]:
        lines.append(format_row(result))
    for failure in (
        checks["anchors"]["failed"]
        + checks["figures"]["failed"]
        + checks["bindings"]["failed"]
        + list((checks.get("external_run") or {}).get("failed", []))
    ):
        lines.append(f"  check failed: {failure}")
    summary = report["summary"]
    lines.append("")
    lines.append(
        "RESULT: {met} of {judged} judged row(s) met; {exceeded} exceeded, {vacuous} vacuous, "
        "{absent} evidence absent; {not_carried} not carried, {not_judged} not judged; "
        "exit {exit_status}".format(
            met=summary["met"],
            judged=summary["judged"],
            exceeded=summary["exceeded"],
            vacuous=summary["vacuous"],
            absent=summary["evidence_absent"],
            not_carried=summary["not_carried"],
            not_judged=summary["not_judged"],
            exit_status=report["exit_status"],
        )
    )
    return "\n".join(lines)


def format_row(result: dict) -> str:
    label = VERDICT_LABEL.get(result["verdict"], result["verdict"].upper())
    parts = [f"  [{label}] {result['id']}"]
    if result.get("cells"):
        parts.append(f"cells={result['cells']}")
    if result.get("failures"):
        parts.append(f"failures={result['failures']}")
    worst = result.get("worst") or {}
    if worst.get("text") is not None:
        unit = (result.get("metric") or {}).get("unit", "")
        parts.append(f"worst={worst['text']} {unit}".rstrip())
        bound = result.get("bound") or {}
        if bound.get("value") is not None:
            parts.append(f"bound={bound['value']}")
        cell = worst.get("cell") or {}
        at = []
        for key in ("function", "x", "input_bits", "order", "band", "label"):
            if key in cell:
                at.append(f"{key}={cell[key]}")
        if at:
            parts.append("at " + " ".join(at))
    if result.get("reason") and result["verdict"] in (
        "not_carried",
        "not_judged",
        "evidence_absent",
    ):
        parts.append(f"- {result['reason']}")
    return " ".join(parts)
