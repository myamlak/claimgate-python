#!/usr/bin/env python3
"""Express the boys accuracy gate's registration table and run record as a
claimgate book.

The consumer demonstration.  The gate source and the run transcript are read
at the tag the transcript was made at; the extracted book carries

* the gate's 37 registration entries as claimgate registrations, with their
  verbatim sentences, file anchors and stated figures;
* the gate's 38 claims-book rows as ``external_record`` rows, each bound to
  its verdict in the ``04b-gate-run.log`` transcript;
* the gate's ``kUnregisteredRows`` as released rows with their treatments;
* deposited anchor slices cut from the tagged source, so the anchor check
  runs without the upstream tree;
* a ``claimgate-external-run-1`` run record holding the transcript's 38
  verdicts and its RESULT summary.

The extractor fails loudly when the tagged source, the transcript and the
known counts disagree.

    python examples/boys-gate/extract.py \
        --repo <boys-checkout> --tag v5.3.1 \
        --transcript <04b-gate-run.log> \
        --out examples/boys-gate
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
import sys
from pathlib import Path

DEFINES = {
    "BOYS_GATE_FP16": True,
    "BOYS_GATE_EXTERNAL_BOOST": False,
    "__x86_64__": True,
    "_M_X64": True,
}

CONDITIONAL = re.compile(r"^\s*#\s*(ifdef|ifndef|if|elif|else|endif)\b(.*)$")
DEFINED_ATOM = re.compile(r"defined\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)$")
CONSTANT = re.compile(
    r"^\s*(?:static\s+)?constexpr\s+double\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*([^;]+);"
)

ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "0": "\0", "\\": "\\", '"': '"', "'": "'"}


class ExtractError(Exception):
    pass


def read_tag_file(repo: Path, tag: str | None, relative: str) -> str:
    if tag:
        result = subprocess.run(
            ["git", "-C", str(repo), "show", f"{tag}:{relative}"],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if result.returncode != 0:
            raise ExtractError(f"git show {tag}:{relative}: {result.stderr.strip()}")
        return result.stdout
    path = repo / relative
    if not path.is_file():
        raise ExtractError(f"{path}: does not exist")
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# A small preprocessor: the published numbering was made with BOYS_GATE_FP16
# defined and BOYS_GATE_EXTERNAL_BOOST not defined.


def _atom(text: str) -> bool:
    text = text.strip()
    match = DEFINED_ATOM.match(text)
    if match:
        return bool(DEFINES.get(match.group(1), False))
    if text in ("1", "true"):
        return True
    if text in ("0", "false"):
        return False
    return bool(DEFINES.get(text, False))


def _condition(kind: str, expression: str) -> bool:
    expression = expression.strip()
    if kind == "ifdef":
        name = expression.split()[0] if expression else ""
        return bool(DEFINES.get(name, False))
    if kind == "ifndef":
        name = expression.split()[0] if expression else ""
        return not bool(DEFINES.get(name, False))
    if kind == "if":
        if "||" in expression:
            return any(_atom(part) for part in expression.split("||"))
        if "&&" in expression:
            return all(_atom(part) for part in expression.split("&&"))
        return _atom(expression)
    raise ExtractError(f"unknown conditional directive: {kind}")


def active_lines(lines: list[str]):
    stack: list[list[bool]] = []
    active = True
    for number, line in enumerate(lines, 1):
        match = CONDITIONAL.match(line)
        if match:
            kind, expression = match.group(1), match.group(2)
            if kind in ("ifdef", "ifndef", "if"):
                condition = _condition(kind, expression)
                stack.append([active, condition])
                active = active and condition
            elif kind == "elif":
                if not stack:
                    raise ExtractError("an #elif has no opening directive")
                parent, taken = stack[-1]
                condition = (not taken) and _condition("if", expression)
                stack[-1][1] = taken or condition
                active = parent and condition
            elif kind == "else":
                if not stack:
                    raise ExtractError("an #else has no opening directive")
                parent, taken = stack[-1]
                stack[-1][1] = True
                active = parent and (not taken)
            else:
                if not stack:
                    raise ExtractError("an #endif has no opening directive")
                parent, _ = stack.pop()
                active = parent
            continue
        if active:
            yield number, line
    if stack:
        raise ExtractError("a conditional is not closed")


# ---------------------------------------------------------------------------
# C++ string literals and argument splitting.


def skip_string(text: str, index: int) -> int:
    """Return the index just past the string literal starting at ``index``."""
    cursor = index + 1
    while cursor < len(text):
        if text[cursor] == "\\":
            cursor += 2
            continue
        if text[cursor] == '"':
            return cursor + 1
        cursor += 1
    raise ExtractError("an unterminated string literal")


def string_literals(text: str) -> list[tuple[int, int, str]]:
    out = []
    index = 0
    while index < len(text):
        if text[index] != '"':
            index += 1
            continue
        end = skip_string(text, index)
        raw = text[index + 1 : end - 1]
        chars = []
        cursor = 0
        while cursor < len(raw):
            if raw[cursor] == "\\" and cursor + 1 < len(raw):
                chars.append(ESCAPES.get(raw[cursor + 1], raw[cursor + 1]))
                cursor += 2
                continue
            chars.append(raw[cursor])
            cursor += 1
        out.append((index, end, "".join(chars)))
        index = end
    return out


def join_literals(argument: str) -> str | None:
    pieces = [value for _, _, value in string_literals(argument)]
    return "".join(pieces) if pieces else None


def split_args(text: str) -> list[str]:
    args = []
    depth = 0
    start = 0
    index = 0
    while index < len(text):
        char = text[index]
        if char == '"':
            index = skip_string(text, index)
            continue
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
        elif char == "," and depth == 0:
            args.append(text[start:index])
            start = index + 1
        index += 1
    args.append(text[start:])
    return args


def balanced_region(text: str, start: int, open_char: str, close_char: str) -> tuple[int, int]:
    """Return the (start, end) indices of the region inside the first pair."""
    open_at = text.find(open_char, start)
    if open_at < 0:
        raise ExtractError(f"no {open_char!r} after index {start}")
    depth = 0
    index = open_at
    while index < len(text):
        char = text[index]
        if char == '"':
            index = skip_string(text, index)
            continue
        if char == open_char:
            depth += 1
        elif char == close_char:
            depth -= 1
            if depth == 0:
                return open_at + 1, index
        index += 1
    raise ExtractError(f"no matching {close_char!r}")


# ---------------------------------------------------------------------------
# The gate source.


def parse_constants(texts: list[str]) -> dict[str, float]:
    constants: dict[str, float] = {}
    for text in texts:
        for line in text.splitlines():
            match = CONSTANT.match(line)
            if not match:
                continue
            name, expression = match.group(1), match.group(2).strip()
            expression = expression.split("//")[0].strip()
            expression = expression.replace("std::ldexp", "ldexp")
            try:
                value = eval(  # noqa: S307 - the tagged source is the input
                    expression,
                    {"__builtins__": {}},
                    {**constants, "ldexp": math.ldexp},
                )
            except Exception as exc:  # noqa: BLE001
                raise ExtractError(f"constant {name} = {expression}: {exc}") from exc
            constants[name] = float(value)
    return constants


def eval_figure_bound(expression: str, constants: dict[str, float]) -> float:
    expression = expression.strip()
    expression = expression.replace("std::ldexp", "ldexp")
    try:
        return float(
            eval(  # noqa: S307
                expression,
                {"__builtins__": {}},
                {**constants, "ldexp": math.ldexp},
            )
        )
    except Exception as exc:  # noqa: BLE001
        raise ExtractError(f"figureBound expression {expression!r}: {exc}") from exc


def parse_add_calls(source: str) -> list[dict]:
    lines = source.splitlines()
    active_numbers = {number for number, _ in active_lines(lines)}
    in_book = False
    rows: list[dict] = []
    index = 0
    while index < len(lines):
        number = index + 1
        line = lines[index]
        stripped = line.strip()
        if not in_book:
            if "std::vector<DocClaim> book;" in line:
                in_book = True
            index += 1
            continue
        if stripped.startswith("struct Registration"):
            break
        if number in active_numbers and (
            stripped.startswith("add(") or stripped.startswith("add (")
        ):
            call = line
            cursor = index
            while True:
                try:
                    open_at, close_at = balanced_region(call, call.find("add"), "(", ")")
                    break
                except ExtractError:
                    cursor += 1
                    if cursor >= len(lines):
                        raise ExtractError(f"the add() call at line {number} is not closed")
                    call += "\n" + lines[cursor]
            while ";" not in call[close_at + 1 :]:
                cursor += 1
                if cursor >= len(lines):
                    raise ExtractError(f"the add() call at line {number} has no semicolon")
                call += "\n" + lines[cursor]
            args = split_args(call[open_at:close_at])
            row_id = join_literals(args[0]) if args else None
            if row_id:
                statement = join_literals(args[1]) if len(args) > 1 else None
                evidence = join_literals(args[4]) if len(args) > 4 else None
                rows.append(
                    {
                        "id": row_id.strip(),
                        "statement": (statement or "").strip(),
                        "evidence": (evidence or "").strip(),
                        "figure_bound": 0.0,
                        "call": call,
                    }
                )
            index = cursor + 1
            continue
        index += 1
    constants = parse_constants(CONSTANTS_SOURCES)
    for row in rows:
        call = row.pop("call")
        match = re.search(r"\.figureBound\s*=\s*([^;]+);", call)
        if match:
            row["figure_bound"] = eval_figure_bound(match.group(1), constants)
    return rows


def parse_registration_array(source: str, array_name: str, fields: int) -> list[list[str | None]]:
    start_match = re.search(
        rf"\b{array_name}\s*\[\s*\]\s*=\s*\{{", source
    )
    if not start_match:
        raise ExtractError(f"{array_name}[] is not in the source")
    region_start = start_match.end() - 1
    open_at, close_at = balanced_region(source, region_start, "{", "}")
    region = source[open_at:close_at]
    entries: list[list[str | None]] = []
    depth = 0
    entry_start = None
    index = 0
    while index < len(region):
        char = region[index]
        if char == '"':
            index = skip_string(region, index)
            continue
        if char == "{":
            if depth == 0:
                entry_start = index + 1
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0 and entry_start is not None:
                entry = region[entry_start:index]
                args = split_args(entry)
                if len(args) != fields:
                    raise ExtractError(
                        f"{array_name} entry has {len(args)} fields, expected {fields}: "
                        f"{entry[:80]!r}"
                    )
                values: list[str | None] = []
                for argument in args:
                    if argument.strip() == "nullptr":
                        values.append(None)
                    else:
                        values.append(join_literals(argument))
                entries.append(values)
                entry_start = None
        index += 1
    return entries


def parse_anchor_lines(anchor: str) -> tuple[int, int]:
    match = re.search(r"lines\s+(\d+)(?:\s*-\s*(\d+))?", anchor or "")
    if not match:
        raise ExtractError(f"the anchor {anchor!r} states no line range")
    first = int(match.group(1))
    last = int(match.group(2)) if match.group(2) else first
    return first, last


def parse_transcript(path: Path) -> tuple[list[dict], dict, dict, int]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    try:
        start = next(
            i for i, line in enumerate(lines)
            if line.strip() == "documented claims, each with one verdict:"
        )
    except StopIteration as exc:
        raise ExtractError(f"{path}: no 'documented claims' block") from exc
    end = None
    for i in range(start + 1, len(lines)):
        if lines[i].strip().startswith("RESULT (the claim book)"):
            end = i
            break
    if end is None:
        raise ExtractError(f"{path}: no claim-book RESULT line")
    entries: list[dict] = []
    for line in lines[start + 1 : end]:
        match = re.match(r"^  \[([^\]]+)\] (.*)$", line)
        if not match:
            continue
        token, detail = match.group(1), match.group(2)
        if token.startswith("verified at this revision"):
            verdict = "verified"
        elif token.startswith("met over the stated domain"):
            verdict = "met_over_domain"
        elif token.startswith("EXCEEDED"):
            verdict = "exceeded"
        elif token.startswith("vacuous"):
            verdict = "vacuous"
        elif token.startswith("evidence absent"):
            verdict = "evidence_absent"
        elif token.startswith("not carried"):
            verdict = "not_carried"
        elif token.startswith("recorded, not judged"):
            verdict = "not_judged"
        else:
            raise ExtractError(f"{path}: unknown verdict token {token!r}")
        entries.append({"verdict": verdict, "token": token, "detail": detail.strip()})
    full_text = "\n".join(lines[end : end + 4])
    result = re.search(
        r"RESULT \(the claim book\): (\d+) of (\d+) claims met at this revision "
        r"\((\d+) verified outright, (\d+) met over a stated domain, (\d+) exceeded, "
        r"(\d+) vacuous only, (\d+) evidence absent, (\d+) not carried by this build, "
        r"(\d+) recorded and not judged",
        full_text,
    )
    if not result:
        raise ExtractError(f"{path}: cannot read the RESULT line")
    summary = {
        "rows": int(result.group(2)),
        "verified": int(result.group(3)),
        "met_over_domain": int(result.group(4)),
        "exceeded": int(result.group(5)),
        "vacuous": int(result.group(6)),
        "evidence_absent": int(result.group(7)),
        "not_carried": int(result.group(8)),
        "not_judged": int(result.group(9)),
    }
    summary["met"] = summary["verified"] + summary["met_over_domain"]
    summary["judged"] = summary["met"] + summary["exceeded"] + summary["vacuous"] + summary["evidence_absent"]
    registration = re.search(
        r"registration: (\d+) documented claims in (\d+) entries; "
        r"(\d+) with a checked figure, (\d+) without",
        text,
    )
    if not registration:
        raise ExtractError(f"{path}: cannot read the registration summary line")
    registration_summary = {
        "claims": int(registration.group(1)),
        "entries": int(registration.group(2)),
        "figure_checked": int(registration.group(3)),
        "figure_absent": int(registration.group(4)),
    }
    exit_path = path.with_suffix(".exit")
    exit_status = int(exit_path.read_text().strip()) if exit_path.is_file() else 0
    return entries, summary, registration_summary, exit_status


# ---------------------------------------------------------------------------
# Building the book.


CONSTANTS_SOURCES: list[str] = []


def sanitize(name: str) -> str:
    return name.replace("/", "__").replace("\\", "__")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, type=Path, help="the boys git checkout")
    parser.add_argument("--tag", default=None, help="the tag to read (default: the working tree)")
    parser.add_argument("--transcript", required=True, type=Path, help="04b-gate-run.log")
    parser.add_argument("--out", required=True, type=Path, help="the example directory")
    parser.add_argument("--tag-object", default=None)
    parser.add_argument("--source-revision", default=None)
    parser.add_argument("--captured", default=None)
    args = parser.parse_args(argv)

    gate_path = "tests/boys_accuracy_gate.cpp"
    reference_path = "tests/boys_gate_reference.hpp"
    gate_text = read_tag_file(args.repo, args.tag, gate_path)
    reference_text = read_tag_file(args.repo, args.tag, reference_path)
    CONSTANTS_SOURCES.extend([gate_text, reference_text])

    rows = parse_add_calls(gate_text)
    registrations = parse_registration_array(gate_text, "kRegistrations", 6)
    unregistered = parse_registration_array(gate_text, "kUnregisteredRows", 3)
    entries, summary, registration_summary, exit_status = parse_transcript(args.transcript)

    if len(rows) != summary["rows"]:
        raise ExtractError(
            f"the gate yields {len(rows)} active book rows; the transcript reports {summary['rows']}"
        )
    if len(entries) != summary["rows"]:
        raise ExtractError(
            f"the transcript yields {len(entries)} verdict entries for {summary['rows']} rows"
        )
    if len(registrations) != registration_summary["entries"]:
        raise ExtractError(
            f"the gate has {len(registrations)} registrations; the transcript reports "
            f"{registration_summary['entries']}"
        )
    if len({reg[0] for reg in registrations}) != registration_summary["claims"]:
        raise ExtractError("the registration claim count disagrees with the transcript")
    figure_count = sum(1 for reg in registrations if reg[5] is not None)
    if figure_count != registration_summary["figure_checked"]:
        raise ExtractError(
            f"{figure_count} registrations carry a figure; the transcript reports "
            f"{registration_summary['figure_checked']}"
        )
    row_ids = {row["id"] for row in rows}
    for reg in registrations:
        if reg[1] not in row_ids:
            raise ExtractError(f"registration {reg[0]} names row {reg[1]!r}, which is not in the book")
    released = {entry[0] for entry in unregistered if entry[0] in row_ids}
    cited = {reg[1] for reg in registrations}
    uncovered = sorted(row_ids - cited - released)
    if uncovered:
        raise ExtractError(f"rows cited by no registration and released by none: {uncovered}")

    # The verdicts, in the book's order.
    verdict_by_row = {}
    for row, entry in zip(rows, entries):
        verdict_by_row[row["id"]] = entry["verdict"]
        if entry["verdict"] not in (
            "verified", "met_over_domain", "exceeded", "vacuous",
            "evidence_absent", "not_carried", "not_judged",
        ):
            raise ExtractError(f"row {row['id']}: unknown verdict {entry['verdict']!r}")

    out: Path = args.out
    (out / "anchor-slices").mkdir(parents=True, exist_ok=True)

    # Anchor slices and their index.
    source_cache: dict[str, list[str]] = {}
    ranges: dict[str, list[tuple[int, int]]] = {}
    for reg in registrations:
        source_file, anchor = reg[2], reg[3]
        if not source_file or not anchor:
            raise ExtractError(f"registration {reg[0]} has no source or anchor")
        first, last = parse_anchor_lines(anchor)
        ranges.setdefault(source_file, []).append((first, last))
    slice_index = {}
    for source_file, spans in sorted(ranges.items()):
        text = read_tag_file(args.repo, args.tag, source_file)
        lines = text.splitlines()
        source_cache[source_file] = lines
        wanted = sorted({n for first, last in spans for n in range(first, last + 1)})
        missing = [n for n in wanted if n > len(lines)]
        if missing:
            raise ExtractError(f"{source_file}: the anchor names line {missing[0]} of {len(lines)}")
        payload = {
            "source": source_file,
            "tag": args.tag,
            "sha256": hashlib.sha256(text.encode()).hexdigest(),
            "lines": {str(n): lines[n - 1] for n in wanted},
        }
        slice_name = sanitize(source_file) + ".slices.json"
        (out / "anchor-slices" / slice_name).write_text(
            json.dumps(payload, indent=1) + "\n", encoding="utf-8"
        )
        slice_index[source_file] = {
            "file": slice_name,
            "sha256": payload["sha256"],
            "tag": args.tag,
        }
    (out / "anchor-slices" / "index.json").write_text(
        json.dumps(slice_index, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    # The registrations and their claims.
    claims_order: list[str] = []
    rows_by_claim: dict[str, list[str]] = {}
    reg_rows: list[dict] = []
    for index, reg in enumerate(registrations, 1):
        claim_id, row_id, source_file, anchor, quote, figure = reg
        if claim_id not in rows_by_claim:
            claims_order.append(claim_id)
            rows_by_claim[claim_id] = []
        if row_id not in rows_by_claim[claim_id]:
            rows_by_claim[claim_id].append(row_id)
        first, last = parse_anchor_lines(anchor)
        item = {
            "id": f"reg.{claim_id}.{index:02d}",
            "claim_id": claim_id,
            "sentence": quote,
            "source": {"file": source_file, "lines": [first, last]},
            "scope": anchor,
            "rows": [row_id],
        }
        if figure is not None:
            item["figure"] = {"text": figure}
        reg_rows.append(item)

    # Verify every quote against its source now, so a bad extraction fails here.
    for item in reg_rows:
        source_file = item["source"]["file"]
        first, last = item["source"]["lines"]
        lines = source_cache[source_file]
        region = " ".join(" ".join(lines[first - 1 : last]).split())
        sentence = " ".join(item["sentence"].split())
        if sentence not in region:
            raise ExtractError(
                f"registration {item['id']}: the quote is not in {source_file} "
                f"lines {first}-{last}"
            )

    # The rows, as external records bound to the transcript's verdicts.
    book_rows = []
    for index, row in enumerate(rows, 1):
        verdict = verdict_by_row[row["id"]]
        item = {
            "id": row["id"],
            "type": "external_record",
            "statement": row["statement"] or f"gate row {row['id']}",
            "subject": f"gate row {row['id']}",
            "domain": {
                "description": "the domain the gate's row measures, as the gate's own run records it",
                "scope": "stated" if verdict == "met_over_domain" else "whole",
            },
            "evidence_class": "measured_error",
            "record": {
                "file": "run-record.json",
                "row_index": index,
                "row_id": row["id"],
                "verdict": verdict,
            },
        }
        if row["figure_bound"] > 0:
            item["figure_bound"] = row["figure_bound"]
        if row["evidence"]:
            item["notes"] = "the gate's evidence: " + row["evidence"]
        book_rows.append(item)

    # The claims, transcribed from the gate's own bindings.
    rows_by_id = {row["id"]: row for row in rows}
    claims = []
    for claim_id in claims_order:
        first_row = rows_by_claim[claim_id][0]
        source = next(item["source"] for item in reg_rows if item["claim_id"] == claim_id)
        stated = any(
            verdict_by_row[row_id] == "met_over_domain"
            for row_id in rows_by_claim[claim_id]
        )
        figure_bound = rows_by_id[first_row]["figure_bound"]
        claims.append(
            {
                "id": claim_id,
                "object": ", ".join(rows_by_claim[claim_id]),
                "domain": {
                    "description": "the domains of the gate's rows for this claim",
                    "scope": "stated" if stated else "whole",
                },
                "output": {"representation": "the gate's declared output representation"},
                "metric": {"kind": "external", "unit": "the row's own figure"},
                "bound": {
                    "value": figure_bound,
                    "unit": "the row's own figure",
                    "quantifier": "uniform",
                },
                "implementation": {
                    "name": "boys",
                    "version": "5.3.1",
                    "tag": "v5.3.1",
                    "revision": args.source_revision or "",
                },
                "route": ", ".join(rows_by_claim[claim_id]),
                "assumptions": [
                    "transcribed from the boys accuracy gate at v5.3.1",
                    "claimgate checks the registration, the anchor, the figure and the run record; it does not re-measure the rows",
                ],
                "source": source,
                "evidence_class": "measured_error",
                "subject": next(
                    row["statement"] for row in rows if row["id"] == first_row
                ),
                "rows": rows_by_claim[claim_id],
            }
        )

    # The run record.
    run_rows = []
    for index, row in enumerate(rows, 1):
        run_rows.append(
            {
                "index": index,
                "id": row["id"],
                "verdict": verdict_by_row[row["id"]],
                "detail": entries[index - 1]["detail"][:400],
            }
        )
    run_record = {
        "schema": "claimgate-external-run-1",
        "tool": {
            "name": "boys-accuracy-gate",
            "version": "5.3.1",
            "binary_sha256": "172be307e680d1d765570ecc2a80dc857b45d8736943fdce5e8864ab45c21370",
            "binary_bytes": 8134144,
        },
        "command": "build\\Release\\boys-accuracy-gate.exe",
        "tag": "v5.3.1",
        "tag_object": args.tag_object or "d1e63f71c6f2501aecc6340e31216a42c2a390b9",
        "source_revision": args.source_revision or "2f83e40a6504368b7b2f13682e29b4f24ab2a40c",
        "captured": args.captured or "2026-11-08",
        "host": "Windows 11 Pro, x86-64",
        "compiler": "MSVC, Visual Studio 18 2026, Release",
        "registration": registration_summary,
        "summary": summary,
        "exit_status": exit_status,
        "rows": run_rows,
        "inputs": {
            "src": "7e5c43b4919f7f4e",
            "include": "a5115e4cc203c6df",
            "gate": "629d88caa4273bb1",
            "grid": "970db44ddb6a7da5",
            "cmake": "02a9ac36190a748e",
        },
    }
    (out / "run-record.json").write_text(
        json.dumps(run_record, indent=2) + "\n", encoding="utf-8"
    )

    book = {
        "claimgate_book": 1,
        "book": {
            "id": "boys-gate-5.3.1",
            "title": "The boys accuracy gate at v5.3.1: registration table and run record",
            "description": (
                "A faithful transcription of the boys accuracy gate's registration table and "
                "its captured v5.3.1 run, expressed as a claimgate book. The claims, rows and "
                "verdicts are the gate's; claimgate checks the registration anchors, the stated "
                "figures, the row bindings and the run record's structure. It does not re-measure "
                "the library."
            ),
            "library": {
                "name": "boys",
                "version": "5.3.1",
                "tag": "v5.3.1",
                "revision": args.source_revision or "2f83e40a6504368b7b2f13682e29b4f24ab2a40c",
            },
            "created": "2026-11-09",
            "provenance": {
                "gate": f"{gate_path} at {args.tag}; SHA-256 "
                        f"{hashlib.sha256(gate_text.encode()).hexdigest()}",
                "transcript": f"{args.transcript.name}; SHA-256 "
                              f"{hashlib.sha256(args.transcript.read_bytes()).hexdigest()}",
                "run": "papers-b-v5/papers/claims-as-rows/program-demo/gate-v5.3.1/",
                "extraction": "python examples/boys-gate/extract.py --repo <boys> --tag v5.3.1 "
                              "--transcript <04b-gate-run.log> --out examples/boys-gate",
                "transcribed": "claim id, object, domain scope, route, rows, source and bound from the gate's registrations and rows",
                "placeholder": "the claim metric is marked 'external'; the claim bound is the first carrying row's figure_bound, or 0 where the gate states no figure; the claim output representation is the gate's own",
                "verdicts": "the seven verdicts are the transcript's, one per row, in book order",
                "anchor_slices": "cut from the tagged source; the index records each full source's SHA-256",
            },
            "unregistered_rows": [
                {"row": entry[0], "treatment": entry[1], "reason": entry[2]}
                for entry in unregistered
                if entry[0] in row_ids
            ],
        },
        "defaults": {"root": ".", "anchor_preference": "slices"},
        "claims": claims,
        "registrations": reg_rows,
        "rows": book_rows,
        "external_run": {
            "file": "run-record.json",
            "schema": "claimgate-external-run-1",
            "note": "the boys accuracy gate's captured run; claimgate checks its structure and digests",
        },
    }
    (out / "book.json").write_text(json.dumps(book, indent=2) + "\n", encoding="utf-8")

    print(f"book        : {out / 'book.json'}")
    print(f"rows        : {len(book_rows)}")
    print(f"claims      : {len(claims)}")
    print(f"registr.    : {len(reg_rows)} ({registration_summary['figure_checked']} with a figure)")
    print(f"released    : {len(book['book']['unregistered_rows'])}")
    print(f"transcript  : {len(entries)} verdicts "
          f"({summary['verified']} verified, {summary['met_over_domain']} met over a domain)")
    print(f"exit status : {exit_status}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ExtractError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)
