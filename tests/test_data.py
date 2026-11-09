"""Reading data and computing the metric exactly."""

import math
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path

from claimgate.data import DataError, apply_filter, evaluate_data, metric_value, read_csv
from claimgate.exact import parse_float_value


class DummyBook:
    def __init__(self, root):
        self.root = Path(root)

    def resolve(self, relative):
        return (self.root / relative).resolve()


def write(root, name, text):
    path = Path(root) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def row(spec, **overrides):
    base = {
        "id": "r",
        "type": "reference_comparison",
        "statement": "s",
        "subject": "s",
        "domain": {"description": "d"},
        "metric": {"kind": "relative", "unit": "relative"},
        "bound": {"value": "1e-6", "unit": "relative"},
        "quantifier": "pointwise",
        "evidence_class": "measured_error",
        "data": {
            "file": "data.csv",
            "format": "csv",
            "comparison": "value_vs_reference",
            "columns": {"measured": "measured", "reference": "reference"},
        },
    }
    base.update(spec)
    base.update(overrides)
    return base


class MetricTest(unittest.TestCase):
    def test_absolute(self):
        self.assertEqual(metric_value("absolute", Fraction(3), Fraction(1), None, None, None),
                         Fraction(2))

    def test_relative(self):
        self.assertEqual(metric_value("relative", Fraction(3), Fraction(2), None, None, None),
                         Fraction(1, 2))

    def test_relative_zero_reference(self):
        self.assertEqual(metric_value("relative", Fraction(0), Fraction(0), None, None, None),
                         Fraction(0))
        self.assertEqual(metric_value("relative", Fraction(1), Fraction(0), None, None, None),
                         math.inf)

    def test_epsilon(self):
        eps = Fraction(1, 2**52)
        value = metric_value("epsilon", Fraction(1) + eps, Fraction(1), None, None, eps)
        self.assertEqual(value, Fraction(1))

    def test_ulp(self):
        one, _ = parse_float_value("3ff0000000000000")
        above, _ = parse_float_value("3ff0000000000001")
        self.assertEqual(
            metric_value("ulp", one, above, 0x3FF0000000000000, 0x3FF0000000000001, None),
            Fraction(1),
        )

    def test_bit_identity(self):
        self.assertEqual(
            metric_value("bit_identity", Fraction(1), Fraction(1), 1, 1, None), Fraction(0)
        )
        self.assertEqual(
            metric_value("bit_identity", Fraction(1), Fraction(1), 1, 2, None), Fraction(1)
        )

    def test_exact(self):
        self.assertEqual(metric_value("exact", Fraction(1), Fraction(1), None, None, None),
                         Fraction(0))
        self.assertEqual(metric_value("exact", Fraction(1), Fraction(2), None, None, None),
                         Fraction(1))

    def test_scaled(self):
        self.assertEqual(
            metric_value("scaled", Fraction(3), Fraction(1), None, None, None, Fraction(2)),
            Fraction(1),
        )


class CsvTest(unittest.TestCase):
    def test_comments_and_blanks(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, "data.csv", "# comment\n\nx,y\n0,1\n1,2\n")
            rows = read_csv(path)
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[1]["y"], "2")

    def test_filter_all(self):
        rows = [
            {"function": "ai", "label": "grid i=0"},
            {"function": "ai", "label": "other"},
            {"function": "bi", "label": "grid i=0"},
        ]
        selected = apply_filter(
            rows,
            {"all": [
                {"column": "function", "equals": "ai"},
                {"column": "label", "startswith": "grid"},
            ]},
        )
        self.assertEqual(selected, [rows[0]])


class EvaluateDataTest(unittest.TestCase):
    def test_value_vs_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "data.csv", "x,measured,reference\n0,1.0,1.0\n1,1.000002,1.0\n")
            data = evaluate_data(DummyBook(tmp), row({}))
            self.assertEqual(data["rows"], 2)
            self.assertEqual(data["failures"], 1)
            self.assertEqual(data["worst"].metric, Fraction(2, 10**6))
            self.assertEqual(data["vacuous_cells"], 0)

    def test_value_column_is_not_read_as_bits(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "data.csv", "measured,reference\n0000000000000001,1\n")
            spec = row({
                "metric": {"kind": "absolute", "unit": "absolute"},
                "bound": {"value": 0, "unit": "absolute"},
                "data": {
                    "file": "data.csv",
                    "format": "csv",
                    "comparison": "value_vs_reference",
                    "columns": {"measured": "measured", "reference": "reference"},
                },
            })
            data = evaluate_data(DummyBook(tmp), spec)
            self.assertEqual(data["failures"], 0)

    def test_filter(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "data.csv",
                  "function,measured,reference\nai,1.0,1.0\nbi,2.0,1.0\n")
            spec = row({
                "data": {
                    "file": "data.csv",
                    "format": "csv",
                    "comparison": "value_vs_reference",
                    "columns": {"measured": "measured", "reference": "reference"},
                    "filter": {"column": "function", "equals": "bi"},
                }
            })
            data = evaluate_data(DummyBook(tmp), spec)
            self.assertEqual(data["rows"], 1)
            self.assertEqual(data["failures"], 1)

    def test_bit_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "data.csv",
                  "got,expected\n3ff0000000000000,3ff0000000000000\n3ff0000000000001,3ff0000000000000\n")
            spec = row({
                "metric": {"kind": "bit_identity", "unit": "bit"},
                "bound": {"value": 0, "unit": "bit"},
                "data": {
                    "file": "data.csv",
                    "format": "csv",
                    "comparison": "bit_identity",
                    "columns": {"measured_bits": "got", "expected_bits": "expected"},
                },
            })
            data = evaluate_data(DummyBook(tmp), spec)
            self.assertEqual(data["failures"], 1)

    def test_consistency(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "data.csv", "a,b\n1.0,1.0000000000001\n")
            spec = row({
                "metric": {"kind": "absolute", "unit": "absolute"},
                "bound": {"value": "1e-12", "unit": "absolute"},
                "data": {
                    "file": "data.csv",
                    "format": "csv",
                    "comparison": "consistency",
                    "columns": {"a": "a", "b": "b"},
                },
            })
            data = evaluate_data(DummyBook(tmp), spec)
            self.assertEqual(data["failures"], 0)

    def test_vacuous(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "data.csv", "m\n0.001\n0.002\n")
            spec = row({
                "type": "vacuity",
                "metric": {"kind": "absolute", "unit": "absolute"},
                "bound": {"value": "1e-2", "unit": "absolute"},
                "evidence_class": "vacuous",
                "data": {
                    "file": "data.csv",
                    "format": "csv",
                    "comparison": "vacuous",
                    "columns": {"magnitude": "m"},
                },
            })
            data = evaluate_data(DummyBook(tmp), spec)
            self.assertEqual(data["vacuous_cells"], 2)

    def test_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = evaluate_data(DummyBook(tmp), row({}))
            self.assertIn("missing", data)
            self.assertTrue(data["missing"].endswith("data.csv"))

    def test_empty_filter(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "data.csv", "function,measured,reference\nai,1.0,1.0\n")
            spec = row({
                "data": {
                    "file": "data.csv",
                    "format": "csv",
                    "comparison": "value_vs_reference",
                    "columns": {"measured": "measured", "reference": "reference"},
                    "filter": {"column": "function", "equals": "bi"},
                }
            })
            data = evaluate_data(DummyBook(tmp), spec)
            self.assertTrue(data.get("empty"))

    def test_require_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "data.csv", "measured,reference\n1.0,1.0\n")
            spec = row({
                "data": {
                    "file": "data.csv",
                    "format": "csv",
                    "comparison": "value_vs_reference",
                    "columns": {"measured": "measured", "reference": "reference"},
                    "require_rows": 2,
                }
            })
            with self.assertRaises(DataError):
                evaluate_data(DummyBook(tmp), spec)

    def test_crosscheck(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "data.csv", "measured,reference,error\n1.000002,1.0,999\n")
            spec = row({
                "data": {
                    "file": "data.csv",
                    "format": "csv",
                    "comparison": "value_vs_reference",
                    "columns": {"measured": "measured", "reference": "reference"},
                    "crosscheck": {"column": "error", "tolerance": 1e-9},
                }
            })
            with self.assertRaises(DataError):
                evaluate_data(DummyBook(tmp), spec)

    def test_band_maximum(self):
        with tempfile.TemporaryDirectory() as tmp:
            write(tmp, "data.csv",
                  "band,measured,reference\nA,1.000001,1.0\nB,2.000003,2.0\n")
            spec = row({
                "quantifier": "band_maximum",
                "data": {
                    "file": "data.csv",
                    "format": "csv",
                    "comparison": "value_vs_reference",
                    "columns": {"measured": "measured", "reference": "reference", "band": "band"},
                },
            })
            data = evaluate_data(DummyBook(tmp), spec)
            self.assertEqual(data["failures"], 1)
            verdicts = {band["band"]: band["verdict"] for band in data["bands"]}
            self.assertEqual(verdicts, {"A": "verified", "B": "exceeded"})


if __name__ == "__main__":
    unittest.main()
