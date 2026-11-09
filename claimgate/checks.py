"""The checks that do not need to run the library: anchors, figures, bindings
and the external run record.

An anchor check reads the registration's file, takes the stated line range,
collapses whitespace in both the file region and the quoted sentence, and
requires the sentence inside the region.  When the upstream tree is not
present, a deposited line-slice made by the extractor stands in for it; the
report says which mode it used, and the slice records the digest of the
source it was cut from.

A figure check requires the number the sentence states to occur in the
sentence as a number of its own and to equal the carrying row's
``figure_bound`` to one binary64 ULP.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path

from .exact import NumberError, parse_exact, within_one_ulp

_WS = re.compile(r"\s+")
_FIGURE_CHAR = re.compile(r"[0-9A-Za-z._^]")

SLICE_DIR = "anchor-slices"
SLICE_INDEX = "index.json"


def _collapse(text: str) -> str:
    return _WS.sub(" ", text).strip()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load_source(root: Path, source_file: str, preference: str = "auto") -> dict:
    """Load a registration's source as a line map.

    Returns ``{"mode": "full-source"|"deposited-slice", "lines": {n: text},
    "path": ..., "sha256": ...}`` or ``{"mode": "missing", ...}``.  With
    ``preference='slices'`` the deposited slice is used even when a file of
    the same relative name exists in the root, which is how a consumer
    directory avoids shadowing its upstream anchors with its own files.
    """
    path = (root / source_file).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError:
        return {"mode": "missing", "reason": f"{source_file!r} escapes the root"}
    if preference != "slices" and path.is_file():
        try:
            text = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError) as exc:
            return {"mode": "missing", "reason": f"{path}: {exc}"}
        lines = {number: line for number, line in enumerate(text.splitlines(), 1)}
        return {
            "mode": "full-source",
            "lines": lines,
            "path": str(path),
            "sha256": _sha256(path),
        }
    index_path = root / SLICE_DIR / SLICE_INDEX
    if index_path.is_file():
        try:
            index = json.loads(index_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            index = {}
        entry = index.get(source_file)
        if isinstance(entry, dict) and isinstance(entry.get("file"), str):
            slice_path = root / SLICE_DIR / entry["file"]
            try:
                payload = json.loads(slice_path.read_text(encoding="utf-8"))
                lines = {int(number): text for number, text in payload["lines"].items()}
            except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
                return {"mode": "missing", "reason": f"{slice_path}: cannot be read"}
            return {
                "mode": "deposited-slice",
                "lines": lines,
                "path": str(slice_path),
                "sha256": entry.get("sha256"),
                "source": source_file,
            }
    return {"mode": "missing", "reason": f"{path}: the source and no deposited slice exist"}


def check_anchors(book, mode: str = "auto") -> dict:
    """Check every registration and supporting sentence against its source."""
    root = book.root
    cache: dict[str, dict] = {}
    failures: list[str] = []
    checked = 0
    used: dict[str, dict] = {}

    def source_for(name: str) -> dict:
        if name not in cache:
            cache[name] = load_source(root, name, getattr(book, "anchor_preference", "auto"))
            if cache[name]["mode"] != "missing":
                used[name] = {
                    "file": name,
                    "mode": cache[name]["mode"],
                    "path": cache[name].get("path"),
                    "sha256": cache[name].get("sha256"),
                }
        return cache[name]

    def check_one(where: str, source: dict, sentence: str) -> None:
        nonlocal checked
        checked += 1
        if source.get("mode") == "missing":
            failures.append(f"{where}: {source.get('reason', 'the source is missing')}")
            return
        first, last = source["lines_spec"]
        missing = [n for n in range(first, last + 1) if n not in source["lines"]]
        if missing:
            failures.append(
                f"{where}: {source['name']} lines {missing[0]}-{missing[-1]} are not in the "
                f"{source['mode']}"
            )
            return
        region = "\n".join(source["lines"][n] for n in range(first, last + 1))
        if _collapse(sentence) not in _collapse(region):
            failures.append(
                f"{where}: the sentence is not inside {source['name']} lines {first}-{last}"
            )

    for reg in book.registrations:
        def make(name, spec):
            loaded = source_for(name)
            return {
                "mode": loaded.get("mode"),
                "name": name,
                "lines_spec": (spec["lines"][0], spec["lines"][1]),
                "lines": loaded.get("lines", {}),
            }

        check_one(f"registration {reg['id']}", make(reg["source"]["file"], reg["source"]),
                  reg["sentence"])
        for j, item in enumerate(reg.get("supporting", [])):
            check_one(
                f"registration {reg['id']} supporting[{j}]",
                make(item["source"]["file"], item["source"]),
                item["sentence"],
            )

    modes = {entry["mode"] for entry in used.values()}
    if not book.registrations:
        mode_used = "skipped"
    elif not used:
        mode_used = "missing"
    elif modes == {"full-source"}:
        mode_used = "full-source"
    elif modes == {"deposited-slice"}:
        mode_used = "deposited-slice"
    else:
        mode_used = "mixed"
    if mode == "none":
        return {"mode": "skipped", "checked": 0, "failed": [], "sources": []}
    return {
        "mode": mode_used,
        "checked": checked,
        "failed": failures,
        "sources": list(used.values()),
    }


def figure_in_quote(quote: str, figure: str) -> bool:
    """True when the figure occurs in the quote as a number of its own.

    A sentence-final period is punctuation, not a decimal point: the figure
    ``2 * 10^-16`` is present in ``approximately 2 * 10^-16.`` while the
    figure ``8`` is not present in ``0.008``.
    """
    at = quote.find(figure)
    while at != -1:
        left_ok = at == 0 or not _FIGURE_CHAR.match(quote[at - 1])
        end = at + len(figure)
        if end == len(quote):
            right_ok = True
        elif not _FIGURE_CHAR.match(quote[end]):
            right_ok = True
        elif quote[end] == "." and (end + 1 == len(quote) or quote[end + 1].isspace()):
            right_ok = True
        else:
            right_ok = False
        if left_ok and right_ok:
            return True
        at = quote.find(figure, at + 1)
    return False


def parse_figure_float(text: str) -> float:
    """Read a figure as the gate does: each term to binary64, then sum."""
    total = 0.0
    for term in text.split(" + "):
        term = term.strip()
        if not term:
            raise NumberError(f"an empty summand in the figure {text!r}")
        if term.startswith("2^"):
            power = int(term[2:])
            if not -1074 <= power <= 1023:
                raise NumberError(f"a power of two outside binary64's range: {term!r}")
            value = math.ldexp(1.0, power)
        else:
            value = float(parse_exact(term))
        total += value
    return total


def check_figures(book) -> dict:
    failures: list[str] = []
    checked = 0
    absent = 0
    for reg in book.registrations:
        figure = reg.get("figure")
        if not figure:
            absent += 1
            continue
        checked += 1
        text = figure["text"]
        if not figure_in_quote(reg["sentence"], text):
            failures.append(
                f"registration {reg['id']}: the figure {text!r} is not in the quoted sentence "
                "as a number of its own"
            )
            continue
        try:
            value = parse_figure_float(text)
        except (NumberError, ValueError) as exc:
            failures.append(f"registration {reg['id']}: the figure {text!r} cannot be read: {exc}")
            continue
        for row_id in reg["rows"]:
            row = book.rows[row_id]
            figure_bound = row.get("figure_bound")
            if not figure_bound:
                failures.append(
                    f"registration {reg['id']}: states the figure {text!r}, but row {row_id} "
                    "carries no figure_bound to check it against"
                )
                continue
            if not within_one_ulp(value, float(figure_bound)):
                failures.append(
                    f"registration {reg['id']}: states the figure {text!r} ({value!r}), but "
                    f"row {row_id} is judged against {figure_bound!r}: the two differ by more "
                    "than one ULP"
                )
            bound = row.get("bound") or {}
            unit = figure.get("unit")
            if unit and bound.get("unit") and unit != bound["unit"]:
                failures.append(
                    f"registration {reg['id']}: the figure unit {unit!r} and row {row_id}'s "
                    f"bound unit {bound['unit']!r} differ"
                )
    return {"checked": checked, "absent": absent, "failed": failures}


def check_bindings(book) -> dict:
    """Every row is cited by a registration or released with a reason."""
    cited: set[str] = set()
    for reg in book.registrations:
        cited.update(reg["rows"])
    failures = []
    for row_id in book.rows:
        if row_id not in cited and row_id not in book.unregistered:
            failures.append(
                f"row {row_id}: no registration cites the row and it is not released"
            )
    for row_id in book.unregistered:
        if row_id not in book.rows:
            failures.append(
                f"book.unregistered_rows names {row_id!r}, which the book does not hold"
            )
    return {"checked": len(book.rows), "failed": failures}


def check_external_run(book) -> dict:
    """Load and check the external run record, if the book names one."""
    if not book.external_run:
        return {"file": None, "failed": []}
    path = book.resolve(book.external_run["file"])
    failures: list[str] = []
    if not path.is_file():
        return {"file": book.external_run["file"], "failed": [f"{path}: does not exist"]}
    try:
        record = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"file": book.external_run["file"], "failed": [f"{path}: {exc}"]}
    if not isinstance(record, dict):
        return {"file": book.external_run["file"], "failed": [f"{path}: not a JSON object"]}
    if record.get("schema") != "claimgate-external-run-1":
        failures.append(
            f"{path}: the schema is {record.get('schema')!r}, not 'claimgate-external-run-1'"
        )
    rows = record.get("rows")
    if not isinstance(rows, list) or not rows:
        failures.append(f"{path}: the run record has no rows")
        rows = []
    for index, row in enumerate(rows, 1):
        if not isinstance(row, dict) or not isinstance(row.get("id"), str):
            failures.append(f"{path}: row {index} has no id")
        elif row.get("verdict") not in (
            "verified",
            "met_over_domain",
            "exceeded",
            "vacuous",
            "evidence_absent",
            "not_carried",
            "not_judged",
        ):
            failures.append(f"{path}: row {index} has no known verdict")
    summary = record.get("summary")
    if isinstance(summary, dict):
        counts = {verdict: 0 for verdict in (
            "verified",
            "met_over_domain",
            "exceeded",
            "vacuous",
            "evidence_absent",
            "not_carried",
            "not_judged",
        )}
        for row in rows:
            if isinstance(row, dict) and row.get("verdict") in counts:
                counts[row["verdict"]] += 1
        for verdict, count in counts.items():
            declared = summary.get(verdict)
            if declared is not None and declared != count:
                failures.append(
                    f"{path}: summary {verdict}={declared} but the rows count {count}"
                )
        if summary.get("rows") is not None and summary["rows"] != len(rows):
            failures.append(
                f"{path}: summary rows={summary['rows']} but the record holds {len(rows)} rows"
            )
    exit_status = record.get("exit_status")
    failing = any(
        isinstance(row, dict)
        and row.get("verdict") in ("exceeded", "vacuous", "evidence_absent")
        for row in rows
    )
    if exit_status not in (0, 1, 2):
        failures.append(f"{path}: exit_status {exit_status!r} is not 0, 1 or 2")
    elif exit_status == 0 and failing:
        failures.append(
            f"{path}: exit_status 0 but the record holds a failing verdict"
        )
    elif exit_status == 1 and not failing:
        failures.append(
            f"{path}: exit_status 1 but no row carries a failing verdict"
        )
    return {
        "file": book.external_run["file"],
        "sha256": _sha256(path),
        "tool": (record.get("tool") or {}).get("name"),
        "version": (record.get("tool") or {}).get("version"),
        "exit_status": exit_status,
        "rows": rows,
        "failed": failures,
    }
