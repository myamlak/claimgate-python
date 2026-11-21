"""The command line: exit statuses, the report file, and the error path."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def cli(*args):
    return subprocess.run(
        [sys.executable, "-m", "claimgate", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


class CliTest(unittest.TestCase):
    def test_version(self):
        result = cli("--version")
        self.assertEqual(result.returncode, 0)
        self.assertIn("claimgate", result.stdout)
        self.assertIn("0.2.0", result.stdout)

    def test_validate(self):
        result = cli("validate", "examples/row-types/book.json")
        self.assertEqual(result.returncode, 0)
        self.assertIn("OK", result.stdout)

    def test_validate_bad(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            path.write_text('{"claimgate_book": 1}', encoding="utf-8")
            result = cli("validate", str(path))
            self.assertEqual(result.returncode, 2)

    def test_run_json(self):
        result = cli("run", "examples/boost-airy/book.json", "--json")
        self.assertEqual(result.returncode, 1)
        report = json.loads(result.stdout)
        self.assertEqual(report["schema"], "claimgate-run-1")
        self.assertEqual(report["summary"]["exceeded"], 4)

    def test_run_report_and_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            report_path = Path(tmp) / "report.json"
            result = cli(
                "run", "examples/row-types/book.json", "--report", str(report_path)
            )
            self.assertEqual(result.returncode, 1)
            self.assertTrue(report_path.is_file())
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["exit_status"], 1)
            summary = cli("summary", str(report_path))
            self.assertEqual(summary.returncode, 0)
            self.assertIn("met       : 3 of 6 judged", summary.stdout)

    def test_run_error_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            path.write_text('{"claimgate_book": 1}', encoding="utf-8")
            report_path = Path(tmp) / "report.json"
            result = cli("run", str(path), "--report", str(report_path))
            self.assertEqual(result.returncode, 2)
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["schema"], "claimgate-error-1")
            self.assertEqual(report["exit_status"], 2)

    def test_no_anchors(self):
        result = cli("run", "examples/boost-airy/book.json", "--no-anchors", "--json")
        report = json.loads(result.stdout)
        self.assertEqual(report["checks"]["anchors"]["mode"], "skipped")


if __name__ == "__main__":
    unittest.main()
