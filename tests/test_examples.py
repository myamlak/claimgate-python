"""The three examples, measured end to end through the runner."""

import unittest
from pathlib import Path

from claimgate.run import run_book

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "examples"


def run(name):
    return run_book(EXAMPLES / name / "book.json")


class BoostAiryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report, cls.status, cls.human = run("boost-airy")
        cls.rows = {row["id"]: row for row in cls.report["rows"]}

    def test_exit_status(self):
        self.assertEqual(self.status, 1)

    def test_four_rows_exceeded(self):
        self.assertEqual(self.report["summary"]["exceeded"], 4)

    def test_paper_witness_bi(self):
        worst = self.rows["boost.airy.bi.a2_grid"]["worst"]
        self.assertAlmostEqual(worst["value"], 414.11089562284541, places=9)
        self.assertEqual(worst["cell"]["x"], "78.12521875")

    def test_paper_witness_ai(self):
        worst = self.rows["boost.airy.ai.named"]["worst"]
        self.assertAlmostEqual(worst["value"], 121.39533957606637, places=9)
        self.assertEqual(worst["cell"]["x"], "35.9")

    def test_ai_grid_extends_past_a1(self):
        worst = self.rows["boost.airy.ai.a2_grid"]["worst"]
        self.assertAlmostEqual(worst["value"], 414.87895725321977, places=9)

    def test_checks(self):
        self.assertEqual(self.report["checks"]["anchors"]["failed"], [])
        self.assertEqual(self.report["checks"]["anchors"]["checked"], 1)
        self.assertEqual(self.report["checks"]["figures"]["failed"], [])
        self.assertEqual(self.report["checks"]["figures"]["checked"], 1)

    def test_limitation_is_reported(self):
        limitations = self.rows["boost.airy.ai.a2_grid"]["limitations"]
        self.assertTrue(any("cannot establish a uniform bound" in line for line in limitations))


class CrlibmTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report, cls.status, cls.human = run("crlibm-sinh")
        cls.rows = {row["id"]: row for row in cls.report["rows"]}

    def test_exit_status(self):
        self.assertEqual(self.status, 1)

    def test_rn_verified(self):
        row = self.rows["crlibm.sinh.rn"]
        self.assertEqual(row["verdict"], "verified")
        self.assertEqual(row["failures"], 0)
        self.assertEqual(row["cells"], 422)

    def test_ru_one_mismatch(self):
        row = self.rows["crlibm.sinh.ru"]
        self.assertEqual(row["verdict"], "exceeded")
        self.assertEqual(row["failures"], 1)
        self.assertEqual(row["worst"]["cell"]["input_bits"], "c08633ce8fb9f87e")

    def test_rd_one_mismatch(self):
        row = self.rows["crlibm.sinh.rd"]
        self.assertEqual(row["verdict"], "exceeded")
        self.assertEqual(row["failures"], 1)
        self.assertEqual(row["worst"]["cell"]["input_bits"], "408633ce8fb9f87e")

    def test_rz_two_mismatches(self):
        row = self.rows["crlibm.sinh.rz"]
        self.assertEqual(row["verdict"], "exceeded")
        self.assertEqual(row["failures"], 2)

    def test_anchors(self):
        self.assertEqual(self.report["checks"]["anchors"]["checked"], 2)
        self.assertEqual(self.report["checks"]["anchors"]["failed"], [])

    def test_figure_absent(self):
        self.assertEqual(self.report["checks"]["figures"]["checked"], 0)
        self.assertEqual(self.report["checks"]["figures"]["absent"], 1)


class BoysGateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report, cls.status, cls.human = run("boys-gate")

    def test_exit_status(self):
        self.assertEqual(self.status, 0)

    def test_counts(self):
        summary = self.report["summary"]
        self.assertEqual(summary["rows"], 38)
        self.assertEqual(summary["verified"], 29)
        self.assertEqual(summary["met_over_domain"], 9)
        self.assertEqual(summary["exceeded"], 0)
        self.assertEqual(summary["met"], 38)

    def test_registration_checks(self):
        checks = self.report["checks"]
        self.assertEqual(checks["anchors"]["mode"], "deposited-slice")
        self.assertEqual(checks["anchors"]["checked"], 37)
        self.assertEqual(checks["anchors"]["failed"], [])
        self.assertEqual(checks["figures"]["checked"], 13)
        self.assertEqual(checks["figures"]["absent"], 24)
        self.assertEqual(checks["figures"]["failed"], [])

    def test_external_run(self):
        external = self.report["checks"]["external_run"]
        self.assertEqual(external["exit_status"], 0)
        self.assertEqual(external["version"], "5.3.1")
        self.assertEqual(external["failed"], [])

    def test_the_consistency_row_is_released(self):
        # The gate marks code.half_simd_budget as carrying no enumerated claim.
        from claimgate.model import load_book

        book = load_book(EXAMPLES / "boys-gate" / "book.json")
        self.assertIn("code.half_simd_budget", book.unregistered)
        self.assertEqual(book.unregistered["code.half_simd_budget"]["treatment"], "retained")
        ids = {row["id"] for row in self.report["rows"]}
        self.assertIn("code.half_simd_budget", ids)


class RowTypesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report, cls.status, cls.human = run("row-types")
        cls.rows = {row["id"]: row for row in cls.report["rows"]}

    def test_exit_status(self):
        self.assertEqual(self.status, 1)

    def test_every_verdict(self):
        expected = {
            "reference.whole": "exceeded",
            "reference.stated": "met_over_domain",
            "consistency.paths": "verified",
            "exact.zero": "verified",
            "vacuity.bound": "vacuous",
            "absent.sweep": "evidence_absent",
            "notcarried.seam": "not_carried",
            "reference.notjudged": "not_judged",
        }
        for row_id, verdict in expected.items():
            with self.subTest(row=row_id):
                self.assertEqual(self.rows[row_id]["verdict"], verdict)

    def test_summary(self):
        summary = self.report["summary"]
        self.assertEqual(summary["judged"], 6)
        self.assertEqual(summary["met"], 3)
        self.assertEqual(summary["not_carried"], 1)
        self.assertEqual(summary["not_judged"], 1)


if __name__ == "__main__":
    unittest.main()
