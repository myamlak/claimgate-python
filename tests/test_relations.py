"""The required row relation and the counts derived from it."""

import json
import unittest
from pathlib import Path

from claimgate.model import validate_book
from claimgate.run import run_book

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "examples"
WIDER = ROOT / "wider-validation"


def load_example(name):
    return json.loads((EXAMPLES / name / "book.json").read_text(encoding="utf-8"))


class RelationValidationTest(unittest.TestCase):
    def setUp(self):
        self.data = load_example("row-types")

    def test_a_row_without_relation_is_rejected(self):
        del self.data["rows"][0]["relation"]
        errors = validate_book(self.data)
        self.assertTrue(any("relation is missing" in error for error in errors))

    def test_strengthens_is_accepted(self):
        self.data["rows"][0]["relation"] = "strengthens"
        self.assertEqual(validate_book(self.data), [])


class RelationCountTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.boost, _, _ = run_book(EXAMPLES / "boost-airy" / "book.json")
        cls.boys, _, _ = run_book(EXAMPLES / "boys-gate" / "book.json")
        cls.mpfr, _, _ = run_book(WIDER / "mpfr" / "book.json")
        cls.claims = {claim["id"]: claim for claim in cls.boys["claims"]}
        cls.rows = {row["id"]: row for row in cls.boys["rows"]}

    def test_b_strengthens_is_counted_separately(self):
        h01 = self.claims["H01"]
        self.assertEqual(h01["carrying_rows"], 0)
        self.assertEqual(h01["stronger_test_rows"], 1)
        self.assertEqual(h01["supporting_rows"], 0)
        self.assertEqual(h01["measuring_rows"], 0)
        self.assertEqual(h01["matching_rows"], 0)
        self.assertEqual(self.rows["README.half"]["relation"], "strengthens")

    def test_c_explicit_carries_count_as_before(self):
        self.assertEqual([c["carrying_rows"] for c in self.boost["claims"]], [4])
        self.assertEqual([c["stronger_test_rows"] for c in self.boost["claims"]], [0])
        self.assertEqual(sum(c["carrying_rows"] for c in self.boys["claims"]), 29)
        self.assertEqual(sum(c["stronger_test_rows"] for c in self.boys["claims"]), 1)

    def test_d_supports_and_measures_are_not_carrying(self):
        for claim_id in ("D07", "P03", "P11"):
            self.assertEqual(self.claims[claim_id]["carrying_rows"], 0, claim_id)
        self.assertEqual(self.claims["P11"]["measuring_rows"], 1)
        self.assertEqual(self.claims["D07"]["supporting_rows"], 1)
        for claim in self.mpfr["claims"]:
            self.assertEqual(claim["carrying_rows"], 0)
            self.assertEqual(claim["stronger_test_rows"], 0)
            self.assertEqual(claim["supporting_rows"], 4)
            self.assertEqual(claim["measuring_rows"], 0)
            self.assertEqual(claim["matching_rows"], 0)
        self.assertTrue(all(row["relation"] == "supports" for row in self.mpfr["rows"]))

    def test_the_five_counts_are_disjoint_and_complete(self):
        for claim in self.boys["claims"]:
            counts = (
                claim["carrying_rows"],
                claim["stronger_test_rows"],
                claim["supporting_rows"],
                claim["measuring_rows"],
                claim["matching_rows"],
            )
            self.assertEqual(sum(counts), len(claim["rows"]), claim["id"])

    def test_boys_row_relation_counts(self):
        counts = {}
        for row in self.boys["rows"]:
            counts[row["relation"]] = counts.get(row["relation"], 0) + 1
        self.assertEqual(
            counts,
            {"carries": 20, "supports": 10, "measures": 7, "strengthens": 1},
        )


if __name__ == "__main__":
    unittest.main()
