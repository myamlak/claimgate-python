"""Anchors, figures, bindings and the external run record."""

import json
import math
import tempfile
import unittest
from pathlib import Path

from claimgate.checks import (
    check_anchors,
    check_bindings,
    check_external_run,
    check_figures,
    figure_in_quote,
    parse_figure_float,
)


class FakeBook:
    def __init__(self, root, registrations, rows=None, unregistered=None, external_run=None):
        self.root = Path(root)
        self.registrations = registrations
        self.rows = rows or {}
        self.unregistered = unregistered or {}
        self.external_run = external_run

    def resolve(self, relative):
        return (self.root / relative).resolve()


def write(root, name, text):
    path = Path(root) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class AnchorTest(unittest.TestCase):
    def test_inside_range(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "doc.md", "intro\nThe relative error is\nless than 100 epsilon.\nend\n")
            book = FakeBook(
                tmp,
                [{
                    "id": "r",
                    "sentence": "The relative error is less than 100 epsilon.",
                    "source": {"file": "doc.md", "lines": [2, 3]},
                }],
            )
            result = check_anchors(book)
            self.assertEqual(result["failed"], [])
            self.assertEqual(result["checked"], 1)
            self.assertEqual(result["mode"], "full-source")

    def test_outside_range(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "doc.md", "one\ntwo\nthree\n")
            book = FakeBook(
                tmp,
                [{
                    "id": "r",
                    "sentence": "three",
                    "source": {"file": "doc.md", "lines": [1, 1]},
                }],
            )
            result = check_anchors(book)
            self.assertEqual(len(result["failed"]), 1)

    def test_missing_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            book = FakeBook(
                tmp,
                [{"id": "r", "sentence": "s", "source": {"file": "no.md", "lines": [1, 1]}}],
            )
            self.assertEqual(len(check_anchors(book)["failed"]), 1)

    def test_slice_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "anchor-slices/index.json", json.dumps(
                {"doc.md": {"file": "doc.slices.json", "sha256": "0" * 64}}
            ))
            write(tmp, "anchor-slices/doc.slices.json", json.dumps(
                {"lines": {"2": "the sentence", "3": "continues here"}}
            ))
            book = FakeBook(
                tmp,
                [{
                    "id": "r",
                    "sentence": "the sentence continues here",
                    "source": {"file": "doc.md", "lines": [2, 3]},
                }],
            )
            result = check_anchors(book)
            self.assertEqual(result["failed"], [])
            self.assertEqual(result["mode"], "deposited-slice")

    def test_slice_preference_overrides_shadowing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "doc.md", "the wrong text\n")
            write(tmp, "anchor-slices/index.json", json.dumps(
                {"doc.md": {"file": "doc.slices.json", "sha256": "0" * 64}}
            ))
            write(tmp, "anchor-slices/doc.slices.json", json.dumps(
                {"lines": {"1": "the right text"}}
            ))
            book = FakeBook(
                tmp,
                [{
                    "id": "r",
                    "sentence": "the right text",
                    "source": {"file": "doc.md", "lines": [1, 1]},
                }],
            )
            book.anchor_preference = "slices"
            result = check_anchors(book)
            self.assertEqual(result["failed"], [])
            self.assertEqual(result["mode"], "deposited-slice")

    def test_supporting_sentence(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "doc.md", "a\nsupporting text\n")
            book = FakeBook(
                tmp,
                [{
                    "id": "r",
                    "sentence": "a",
                    "source": {"file": "doc.md", "lines": [1, 1]},
                    "supporting": [{
                        "sentence": "supporting text",
                        "source": {"file": "doc.md", "lines": [2, 2]},
                    }],
                }],
            )
            result = check_anchors(book)
            self.assertEqual(result["failed"], [])
            self.assertEqual(result["checked"], 2)


class FigureTest(unittest.TestCase):
    def test_in_quote(self):
        self.assertTrue(figure_in_quote("less than 100 epsilon", "100"))
        self.assertFalse(figure_in_quote("less than 100.5 epsilon", "100"))
        self.assertFalse(figure_in_quote("less than 0.008 epsilon", "8"))
        self.assertTrue(figure_in_quote("at 8 ULP", "8"))

    def test_parse(self):
        self.assertEqual(parse_figure_float("1e-13"), 1e-13)
        self.assertEqual(parse_figure_float("2^-22"), math.ldexp(1.0, -22))
        self.assertEqual(parse_figure_float("1e-15 + 2.5e-7"), 1e-15 + 2.5e-7)

    def test_check_pass(self):
        book = FakeBook(
            "/tmp",
            [{"id": "r", "sentence": "within 1e-13", "figure": {"text": "1e-13"},
              "rows": ["row"]}],
            rows={"row": {"figure_bound": 1e-13, "bound": {"unit": "relative"}}},
        )
        result = check_figures(book)
        self.assertEqual(result["failed"], [])
        self.assertEqual(result["checked"], 1)

    def test_check_mismatch(self):
        book = FakeBook(
            "/tmp",
            [{"id": "r", "sentence": "within 1e-13", "figure": {"text": "1e-13"},
              "rows": ["row"]}],
            rows={"row": {"figure_bound": 1e-12}},
        )
        self.assertEqual(len(check_figures(book)["failed"]), 1)

    def test_missing_figure_bound(self):
        book = FakeBook(
            "/tmp",
            [{"id": "r", "sentence": "within 1e-13", "figure": {"text": "1e-13"},
              "rows": ["row"]}],
            rows={"row": {}},
        )
        self.assertEqual(len(check_figures(book)["failed"]), 1)

    def test_absent(self):
        book = FakeBook(
            "/tmp",
            [{"id": "r", "sentence": "no number", "rows": ["row"]}],
            rows={"row": {}},
        )
        result = check_figures(book)
        self.assertEqual(result["checked"], 0)
        self.assertEqual(result["absent"], 1)


class BindingTest(unittest.TestCase):
    def test_all_cited(self):
        book = FakeBook(
            "/tmp",
            [{"id": "r", "rows": ["a", "b"]}],
            rows={"a": {}, "b": {}},
        )
        self.assertEqual(check_bindings(book)["failed"], [])

    def test_unreleased(self):
        book = FakeBook("/tmp", [{"id": "r", "rows": ["a"]}], rows={"a": {}, "b": {}})
        self.assertEqual(len(check_bindings(book)["failed"]), 1)

    def test_released(self):
        book = FakeBook(
            "/tmp",
            [{"id": "r", "rows": ["a"]}],
            rows={"a": {}, "b": {}},
            unregistered={"b": {"row": "b", "treatment": "retained", "reason": "own row"}},
        )
        self.assertEqual(check_bindings(book)["failed"], [])


class ExternalRunTest(unittest.TestCase):
    def record(self, tmp, **overrides):
        payload = {
            "schema": "claimgate-external-run-1",
            "tool": {"name": "gate", "version": "1"},
            "exit_status": 0,
            "summary": {
                "rows": 2,
                "verified": 2,
                "met_over_domain": 0,
                "exceeded": 0,
                "vacuous": 0,
                "evidence_absent": 0,
                "not_carried": 0,
                "not_judged": 0,
            },
            "rows": [
                {"index": 1, "id": "a", "verdict": "verified"},
                {"index": 2, "id": "b", "verdict": "verified"},
            ],
        }
        payload.update(overrides)
        write(tmp, "run.json", json.dumps(payload))
        return FakeBook(tmp, [], external_run={"file": "run.json"})

    def test_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = check_external_run(self.record(tmp))
            self.assertEqual(result["failed"], [])

    def test_summary_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload = {
                "schema": "claimgate-external-run-1",
                "exit_status": 0,
                "summary": {"rows": 2, "verified": 1},
                "rows": [
                    {"id": "a", "verdict": "verified"},
                    {"id": "b", "verdict": "verified"},
                ],
            }
            write(tmp, "run.json", json.dumps(payload))
            book = FakeBook(tmp, [], external_run={"file": "run.json"})
            self.assertTrue(check_external_run(book)["failed"])

    def test_failing_verdict_with_zero_exit(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload = {
                "schema": "claimgate-external-run-1",
                "exit_status": 0,
                "rows": [{"id": "a", "verdict": "exceeded"}],
            }
            write(tmp, "run.json", json.dumps(payload))
            book = FakeBook(tmp, [], external_run={"file": "run.json"})
            self.assertTrue(check_external_run(book)["failed"])

    def test_missing(self):
        book = FakeBook("/tmp", [], external_run={"file": "nowhere.json"})
        self.assertTrue(check_external_run(book)["failed"])


if __name__ == "__main__":
    unittest.main()
