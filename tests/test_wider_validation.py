"""The wider validation books: SLEEF, GSL and MPFR."""

import unittest
from pathlib import Path

from claimgate.run import run_book

ROOT = Path(__file__).resolve().parent.parent
WIDER = ROOT / "wider-validation"


def run(name):
    return run_book(WIDER / name / "book.json")


class SleefTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report, cls.status, cls.human = run("sleef")
        cls.rows = {row["id"]: row for row in cls.report["rows"]}

    def test_exit_and_counts(self):
        self.assertEqual(self.status, 0)
        self.assertEqual(self.report["summary"]["verified"], 4)
        self.assertEqual(self.report["summary"]["judged"], 4)

    def test_worst_values(self):
        expected = {
            "sleef.sin.u10.row": (0.61290757112923522, 1048),
            "sleef.exp.u10.row": (0.69065126951601842, 935),
            "sleef.log.u10.row": (0.50000000000000007, 952),
            "sleef.erf.u10.row": (0.61215882006155699, 945),
        }
        for row_id, (worst, cells) in expected.items():
            with self.subTest(row=row_id):
                self.assertEqual(self.rows[row_id]["cells"], cells)
                self.assertAlmostEqual(self.rows[row_id]["worst"]["value"], worst, places=12)

    def test_anchors_and_figures(self):
        checks = self.report["checks"]
        self.assertEqual(checks["anchors"]["checked"], 4)
        self.assertEqual(checks["anchors"]["failed"], [])
        self.assertEqual(checks["figures"]["checked"], 4)
        self.assertEqual(checks["figures"]["failed"], [])

    def test_relations(self):
        self.assertEqual(sum(c["carrying_rows"] for c in self.report["claims"]), 4)
        self.assertEqual(sum(c["stronger_test_rows"] for c in self.report["claims"]), 0)
        for row in self.report["rows"]:
            self.assertEqual(row["relation"], "carries")


class GslTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report, cls.status, cls.human = run("gsl")
        cls.rows = {row["id"]: row for row in cls.report["rows"]}

    def test_exit_and_counts(self):
        self.assertEqual(self.status, 1)
        summary = self.report["summary"]
        self.assertEqual(summary["exceeded"], 3)
        self.assertEqual(summary["verified"], 3)

    def test_precision_mode_rows(self):
        airy = self.rows["gsl.airy_ai.prec_double"]
        self.assertEqual(airy["verdict"], "exceeded")
        self.assertEqual(airy["failures"], 570)
        self.assertAlmostEqual(airy["worst"]["value"], 3.3389708504182248e-15, places=24)
        ellint = self.rows["gsl.ellint_k.prec_double"]
        self.assertEqual(ellint["verdict"], "exceeded")
        self.assertEqual(ellint["failures"], 177)
        self.assertAlmostEqual(ellint["worst"]["value"], 4.3299560707178672e-16, places=25)

    def test_error_estimate_rows(self):
        erf = self.rows["gsl.erf.err"]
        self.assertEqual(erf["verdict"], "exceeded")
        self.assertEqual(erf["failures"], 8)
        self.assertAlmostEqual(erf["worst"]["value"], 1.3436852052247729, places=12)
        for row_id, worst in (
            ("gsl.gamma.err", 0.71139216754923351),
            ("gsl.bessel_j0.err", 0.84987390470966261),
            ("gsl.bessel_j1.err", 0.60272632811895081),
        ):
            with self.subTest(row=row_id):
                self.assertEqual(self.rows[row_id]["verdict"], "verified")
                self.assertAlmostEqual(self.rows[row_id]["worst"]["value"], worst, places=12)

    def test_evidence_class_is_an_allowance(self):
        for row in self.report["rows"]:
            self.assertEqual(row["evidence_class"], "empirical_allowance")
            self.assertTrue(any("not a bound" in line for line in row["limitations"]))

    def test_relations(self):
        claims = {claim["id"]: claim for claim in self.report["claims"]}
        self.assertEqual(claims["gsl.specfunc.prec_double"]["carrying_rows"], 2)
        self.assertEqual(claims["gsl.specfunc.error_estimate"]["carrying_rows"], 4)
        self.assertEqual(sum(c["stronger_test_rows"] for c in self.report["claims"]), 0)
        for row in self.report["rows"]:
            self.assertEqual(row["relation"], "carries")


class MpfrTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report, cls.status, cls.human = run("mpfr")

    def test_exit_and_counts(self):
        self.assertEqual(self.status, 0)
        self.assertEqual(self.report["summary"]["judged"], 16)
        self.assertEqual(self.report["summary"]["verified"], 16)
        self.assertEqual(self.report["summary"]["exceeded"], 0)

    def test_no_mismatch(self):
        # Four rounding modes against the same inputs: 14704 bit comparisons.
        self.assertEqual(sum(row["cells"] for row in self.report["rows"]), 14704)
        for row in self.report["rows"]:
            self.assertEqual(row["verdict"], "verified", row["id"])
            self.assertEqual(row["failures"], 0)

    def test_claims_are_supported_not_carried(self):
        for claim in self.report["claims"]:
            self.assertEqual(claim["evidence_class"], "certified_bound")
            self.assertEqual(claim["carrying_rows"], 0)
            self.assertEqual(claim["stronger_test_rows"], 0)
            self.assertEqual(claim["supporting_rows"], 4)
        for row in self.report["rows"]:
            self.assertEqual(row["relation"], "supports")


if __name__ == "__main__":
    unittest.main()
