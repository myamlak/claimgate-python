"""The run report against the shipped run schema's structural rules."""

import unittest
from pathlib import Path

from claimgate.run import run_book

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "examples"

TOP_LEVEL = {
    "schema", "tool", "book", "root", "command", "started_utc", "finished_utc",
    "duration_s", "environment", "inputs", "registrations", "checks", "rows",
    "summary", "exit_status",
}
CHECKS = {"anchors", "figures", "bindings", "external_run"}
ROW_KEYS = {
    "id", "type", "claim_id", "statement", "subject", "verdict", "family", "met",
    "evidence_class", "relation", "metric", "bound", "quantifier", "domain", "cells",
    "judged_cells", "failures", "vacuous_cells", "discriminating_cells", "worst",
    "establishes", "limitations", "reason", "data", "external",
}
SUMMARY = {
    "rows", "verified", "met_over_domain", "exceeded", "vacuous", "evidence_absent",
    "not_carried", "not_judged", "met", "judged",
}


class ReportShapeTest(unittest.TestCase):
    def test_reports(self):
        for name in ("boost-airy", "crlibm-sinh", "boys-gate", "row-types"):
            with self.subTest(example=name):
                report, _, _ = run_book(EXAMPLES / name / "book.json")
                self.assertEqual(report["schema"], "claimgate-run-1")
                self.assertLessEqual(set(report), TOP_LEVEL)
                self.assertLessEqual(set(report["checks"]), CHECKS)
                self.assertLessEqual(set(report["summary"]), SUMMARY)
                self.assertEqual(
                    report["summary"]["met"],
                    report["summary"]["verified"] + report["summary"]["met_over_domain"],
                )
                self.assertIn(report["exit_status"], (0, 1, 2))
                for row in report["rows"]:
                    self.assertLessEqual(set(row), ROW_KEYS)
                    self.assertIn(
                        row["verdict"],
                        ("verified", "met_over_domain", "exceeded", "vacuous",
                         "evidence_absent", "not_carried", "not_judged"),
                    )
                    self.assertIn(
                        row["family"], ("judged_and_met", "judged_and_unmet", "not_judged")
                    )
                for entry in report["inputs"]:
                    self.assertRegex(entry["sha256"], r"^[0-9a-f]{64}$")
                for entry in report["registrations"]:
                    self.assertIn(entry["anchor"], ("ok", "failed"))
                    self.assertIn(entry["figure_check"], ("ok", "failed", "absent"))
                    self.assertTrue(entry["rows"])


if __name__ == "__main__":
    unittest.main()
