"""The claimgate command line.

    python -m claimgate run BOOK [--root DIR] [--report FILE] [--json] [--no-anchors]
    python -m claimgate validate BOOK [--root DIR]
    python -m claimgate summary REPORT
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .data import DataError
from .model import (
    TOOL_NAME,
    TOOL_VERSION,
    BookError,
    load_book,
)
from .run import run_book


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def _error_report(book_path: Path, message: str) -> dict:
    return {
        "schema": "claimgate-error-1",
        "tool": {"name": TOOL_NAME, "version": TOOL_VERSION},
        "book": {"path": str(book_path.resolve())},
        "error": message,
        "exit_status": 2,
    }


def command_run(args) -> int:
    book_path = Path(args.book)
    report_path = Path(args.report) if args.report else None
    try:
        report, exit_status, human = run_book(
            book_path,
            root=Path(args.root) if args.root else None,
            anchor_mode="none" if args.no_anchors else "auto",
            command=[sys.executable, "-m", "claimgate", *sys.argv[1:]],
            portable=args.portable,
        )
    except (BookError, DataError) as exc:
        message = str(exc)
        print(f"error: {message}", file=sys.stderr)
        if report_path:
            _write_json(report_path, _error_report(book_path, message))
        return 2
    if report_path:
        _write_json(report_path, report)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(human)
        if report_path:
            print(f"report: {report_path}")
    return exit_status


def command_validate(args) -> int:
    book_path = Path(args.book)
    try:
        book = load_book(book_path, root=Path(args.root) if args.root else None)
    except BookError as exc:
        print(f"{book_path}: INVALID", file=sys.stderr)
        for error in exc.errors:
            print(f"  {error}", file=sys.stderr)
        return 2
    print(
        f"{book_path}: OK ({len(book.claims)} claim(s), {len(book.registrations)} registration(s), "
        f"{len(book.rows)} row(s))"
    )
    return 0


def command_summary(args) -> int:
    path = Path(args.report)
    try:
        report = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: {path}: {exc}", file=sys.stderr)
        return 2
    if not isinstance(report, dict) or "summary" not in report:
        print(f"error: {path}: not a claimgate run report", file=sys.stderr)
        return 2
    summary = report["summary"]
    print(f"book      : {report.get('book', {}).get('id')}")
    print(f"tool      : {report.get('tool', {}).get('name')} {report.get('tool', {}).get('version')}")
    print(f"rows      : {summary.get('rows')}")
    print(f"met       : {summary.get('met')} of {summary.get('judged')} judged")
    for verdict in (
        "exceeded",
        "vacuous",
        "evidence_absent",
        "not_carried",
        "not_judged",
    ):
        print(f"{verdict:10s}: {summary.get(verdict, 0)}")
    print(f"exit      : {report.get('exit_status')}")
    return 0 if report.get("exit_status") in (0, 1) else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="claimgate",
        description="Check documented numerical accuracy claims against their evidence.",
    )
    parser.add_argument("--version", action="version", version=f"{TOOL_NAME} {TOOL_VERSION}")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run a claims book")
    run.add_argument("book", help="the book JSON file")
    run.add_argument("--root", help="the root the book's relative paths resolve against")
    run.add_argument("--report", help="write the machine-readable report to this file")
    run.add_argument("--json", action="store_true", help="print the report as JSON")
    run.add_argument(
        "--no-anchors",
        action="store_true",
        help="skip the anchor check (the report says the check was skipped)",
    )
    run.add_argument(
        "--portable",
        action="store_true",
        help="write the report's paths relative to the invocation directory",
    )
    run.set_defaults(func=command_run)

    validate = sub.add_parser("validate", help="validate a book without running it")
    validate.add_argument("book")
    validate.add_argument("--root")
    validate.set_defaults(func=command_validate)

    summary = sub.add_parser("summary", help="summarise a run report")
    summary.add_argument("report")
    summary.set_defaults(func=command_summary)
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
