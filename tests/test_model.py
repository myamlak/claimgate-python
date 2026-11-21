"""Book validation and referential integrity."""

import copy
import json
import unittest
from pathlib import Path

from claimgate.model import BookError, load_book, resolve_relative, validate_book

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "examples"


def load_example(name):
    return json.loads((EXAMPLES / name / "book.json").read_text(encoding="utf-8"))


class ExampleValidityTest(unittest.TestCase):
    def test_all_examples_validate(self):
        for name in ("boost-airy", "crlibm-sinh", "boys-gate", "row-types"):
            with self.subTest(example=name):
                book = load_book(EXAMPLES / name / "book.json")
                self.assertGreater(len(book.rows), 0)

    def test_schema_is_json(self):
        for name in ("claimgate-book.schema.json", "claimgate-run.schema.json"):
            payload = json.loads((ROOT / "schema" / name).read_text(encoding="utf-8"))
            self.assertEqual(payload["$schema"], "https://json-schema.org/draft/2020-12/schema")

    def test_book_schema_defs(self):
        payload = json.loads(
            (ROOT / "schema" / "claimgate-book.schema.json").read_text(encoding="utf-8")
        )
        for entity in ("claim", "registration", "row", "book", "externalRun", "verdict"):
            self.assertIn(entity, payload["$defs"])


class ValidationErrorTest(unittest.TestCase):
    def setUp(self):
        self.data = load_example("row-types")

    def errors(self, data):
        return validate_book(data)

    def test_clean(self):
        self.assertEqual(self.errors(self.data), [])

    def test_bad_row_type(self):
        self.data["rows"][0]["type"] = "not_a_type"
        self.assertTrue(any("row type" in error for error in self.errors(self.data)))

    def test_evidence_class_not_allowed(self):
        self.data["rows"][0]["evidence_class"] = "proof"
        errors = self.errors(self.data)
        self.assertTrue(any("cannot carry evidence class 'proof'" in error for error in errors))

    def test_duplicate_row_id(self):
        self.data["rows"].append(copy.deepcopy(self.data["rows"][0]))
        self.assertTrue(any("used twice" in error for error in self.errors(self.data)))

    def test_registration_names_missing_row(self):
        self.data["registrations"][0]["rows"] = ["missing.row"]
        errors = self.errors(self.data)
        self.assertTrue(any("missing.row" in error for error in errors))

    def test_unreleased_row(self):
        self.data["registrations"] = [
            reg for reg in self.data["registrations"] if "reference.whole" not in reg["rows"]
        ]
        self.data["claims"] = [
            claim for claim in self.data["claims"] if claim["id"] != "demo.reference"
        ]
        errors = self.errors(self.data)
        self.assertTrue(any("reference.whole" in error for error in errors))

    def test_claim_row_not_cited(self):
        self.data["claims"][0]["rows"].append("reference.stated")
        errors = self.errors(self.data)
        self.assertTrue(any("no registration of the claim cites it" in error for error in errors))

    def test_figure_not_numeric(self):
        self.data["registrations"][0]["figure"]["text"] = "lots"
        errors = self.errors(self.data)
        self.assertTrue(any("figure cannot be read" in error for error in errors))

    def test_data_columns(self):
        self.data["rows"][0]["data"]["columns"] = {"measured": "m"}
        errors = self.errors(self.data)
        self.assertTrue(any("needs one of the columns reference" in error for error in errors))

    def test_external_record_needs_record(self):
        self.data["rows"][0] = {
            "id": "ext",
            "type": "external_record",
            "statement": "s",
            "subject": "s",
            "domain": {"description": "d"},
            "evidence_class": "measured_error",
        }
        self.data["registrations"][0]["rows"] = ["ext"]
        self.data["claims"][0]["rows"] = ["ext"]
        errors = self.errors(self.data)
        self.assertTrue(any("needs a record object" in error for error in errors))

    def test_not_carried_needs_reason(self):
        for row in self.data["rows"]:
            if row["type"] == "not_carried":
                del row["reason"]
        errors = self.errors(self.data)
        self.assertTrue(any("needs a reason" in error for error in errors))

    def test_claim_evidence_class(self):
        self.data["claims"][0]["evidence_class"] = "proof"
        errors = self.errors(self.data)
        self.assertTrue(any("no carrying row carries that class" in error for error in errors))

    def test_book_metadata(self):
        del self.data["book"]["title"]
        self.assertTrue(any("no title" in error for error in self.errors(self.data)))

    def test_missing_relation_rejected(self):
        del self.data["rows"][0]["relation"]
        errors = self.errors(self.data)
        self.assertTrue(any("relation is missing" in error for error in errors))

    def test_unknown_relation_rejected(self):
        self.data["rows"][0]["relation"] = "restates"
        errors = self.errors(self.data)
        self.assertTrue(any("relation 'restates' is not one of" in error for error in errors))

    def test_strengthens_is_known(self):
        self.data["rows"][0]["relation"] = "strengthens"
        self.assertEqual(self.errors(self.data), [])


class ResolveTest(unittest.TestCase):
    def test_relative(self):
        root = Path.cwd()
        self.assertEqual(resolve_relative(root, "a/b.csv"), (root / "a" / "b.csv").resolve())

    def test_absolute_refused(self):
        with self.assertRaises(BookError):
            resolve_relative(Path.cwd(), str(Path.cwd() / "x"))

    def test_escape_refused(self):
        with self.assertRaises(BookError):
            resolve_relative(Path.cwd(), "../outside.csv")


if __name__ == "__main__":
    unittest.main()
