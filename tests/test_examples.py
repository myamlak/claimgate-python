"""The three examples, measured end to end through the runner."""

import importlib.util
import json
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

    def test_relations(self):
        claim = self.report["claims"][0]
        self.assertEqual(claim["carrying_rows"], 4)
        self.assertEqual(claim["stronger_test_rows"], 0)
        self.assertEqual(claim["supporting_rows"], 0)
        self.assertEqual(claim["measuring_rows"], 0)
        self.assertEqual(claim["matching_rows"], 0)
        for row in self.report["rows"]:
            self.assertEqual(row["relation"], "carries")


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

    def test_relations(self):
        claim = self.report["claims"][0]
        self.assertEqual(claim["carrying_rows"], 4)
        self.assertEqual(claim["stronger_test_rows"], 0)
        self.assertEqual(claim["supporting_rows"], 0)
        self.assertEqual(claim["measuring_rows"], 0)
        self.assertEqual(claim["matching_rows"], 0)
        for row in self.report["rows"]:
            self.assertEqual(row["relation"], "carries")


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

    def test_relations(self):
        claims = {claim["id"]: claim for claim in self.report["claims"]}
        self.assertEqual(claims["H01"]["carrying_rows"], 0)
        self.assertEqual(claims["H01"]["stronger_test_rows"], 1)
        self.assertEqual(claims["H01"]["supporting_rows"], 0)
        self.assertEqual(claims["H01"]["measuring_rows"], 0)
        for claim_id in ("D07", "P03", "P11"):
            self.assertEqual(claims[claim_id]["carrying_rows"], 0, claim_id)
        totals = {
            key: sum(claim[key] for claim in self.report["claims"])
            for key in (
                "carrying_rows", "stronger_test_rows", "supporting_rows",
                "measuring_rows", "matching_rows",
            )
        }
        self.assertEqual(
            totals,
            {
                "carrying_rows": 29,
                "stronger_test_rows": 1,
                "supporting_rows": 6,
                "measuring_rows": 1,
                "matching_rows": 0,
            },
        )
        self.assertEqual(
            sum(totals.values()),
            sum(len(claim["rows"]) for claim in self.report["claims"]),
        )
        counts = {}
        for row in self.report["rows"]:
            counts[row["relation"]] = counts.get(row["relation"], 0) + 1
        self.assertEqual(
            counts,
            {"carries": 20, "supports": 10, "measures": 7, "strengthens": 1},
        )

    def test_extractor_relation_map_matches_the_book(self):
        # The extracted book and the extractor that regenerates it cannot drift.
        spec = importlib.util.spec_from_file_location(
            "boys_extract", EXAMPLES / "boys-gate" / "extract.py"
        )
        extract = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(extract)
        book = json.loads(
            (EXAMPLES / "boys-gate" / "book.json").read_text(encoding="utf-8")
        )
        rows_by_claim = {}
        for claim in book["claims"]:
            for row_id in claim["rows"]:
                rows_by_claim.setdefault(row_id, set()).add(claim["id"])
        for row in book["rows"]:
            expected = extract.UNREGISTERED_RELATIONS.get(row["id"])
            if expected is None:
                expected = {
                    extract.NON_CARRYING_CLAIMS.get(claim_id, "carries")
                    for claim_id in rows_by_claim[row["id"]]
                }
                self.assertEqual(len(expected), 1, row["id"])
                expected = expected.pop()
            self.assertEqual(row["relation"], expected, row["id"])

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

    def test_relations(self):
        for claim in self.report["claims"]:
            self.assertEqual(claim["carrying_rows"], 1)
            for key in ("stronger_test_rows", "supporting_rows", "measuring_rows",
                        "matching_rows"):
                self.assertEqual(claim[key], 0, key)
        for row in self.report["rows"]:
            self.assertEqual(row["relation"], "carries")


if __name__ == "__main__":
    unittest.main()
