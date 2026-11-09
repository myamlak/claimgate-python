"""The exact numeric layer."""

import math
import unittest
from fractions import Fraction

from claimgate.exact import (
    EPS64,
    NumberError,
    binary64_ulp_at,
    format_fraction,
    parse_decimal_value,
    parse_exact,
    parse_float_value,
    ulp_distance,
    value_of_bits,
    within_one_ulp,
)


class ParseExactTest(unittest.TestCase):
    def test_decimal(self):
        self.assertEqual(parse_exact("1e-13"), Fraction(1, 10**13))
        self.assertEqual(parse_exact("0.5"), Fraction(1, 2))

    def test_power_of_two(self):
        self.assertEqual(parse_exact("2^-22"), Fraction(1, 2**22))
        self.assertEqual(parse_exact("2^10"), Fraction(1024))

    def test_sum(self):
        self.assertEqual(
            parse_exact("1e-15 + 2.5e-7"),
            Fraction(1, 10**15) + Fraction(25, 10**8),
        )

    def test_product(self):
        self.assertEqual(parse_exact("2 * 10^-16"), Fraction(2, 10**16))
        self.assertEqual(parse_exact("1.5 * 2^-10"), Fraction(3, 2) * Fraction(1, 2**10))

    def test_hex_float(self):
        self.assertEqual(parse_exact("0x1.8p+3"), Fraction(12))

    def test_float_is_exact_binary(self):
        self.assertEqual(parse_exact(0.1), Fraction(0.1))

    def test_int(self):
        self.assertEqual(parse_exact(8), Fraction(8))

    def test_errors(self):
        for text in ("", "abc", "2^2000", "1e-15 + ", "1e-15 + abc"):
            with self.assertRaises(NumberError, msg=text):
                parse_exact(text)

    def test_nan(self):
        self.assertTrue(math.isnan(parse_exact("nan")))


class ParseFloatValueTest(unittest.TestCase):
    def test_bits(self):
        value, bits = parse_float_value("3ff0000000000000")
        self.assertEqual(value, Fraction(1))
        self.assertEqual(bits, 0x3FF0000000000000)

    def test_decimal(self):
        value, bits = parse_float_value("0.5")
        self.assertEqual(value, Fraction(1, 2))
        self.assertIsNone(bits)

    def test_infinity(self):
        value, bits = parse_float_value("7ff0000000000000")
        self.assertEqual(value, math.inf)
        self.assertEqual(bits, 0x7FF0000000000000)

    def test_bad(self):
        with self.assertRaises(NumberError):
            parse_float_value("not-a-number")


class ParseDecimalValueTest(unittest.TestCase):
    def test_sixteen_digits_are_a_decimal(self):
        self.assertEqual(parse_decimal_value("0000000000000001"), Fraction(1))

    def test_short_hex_digits_are_a_decimal(self):
        self.assertEqual(parse_decimal_value("1234567890123456"), Fraction(1234567890123456))

    def test_hex_float(self):
        self.assertEqual(parse_decimal_value("0x1.8p+3"), Fraction(12))


class Binary64UlpTest(unittest.TestCase):
    def test_normal(self):
        self.assertEqual(binary64_ulp_at(Fraction(1)), Fraction(1, 2**52))
        self.assertEqual(binary64_ulp_at(Fraction(2)), Fraction(1, 2**51))
        self.assertEqual(binary64_ulp_at(Fraction(3, 4)), Fraction(1, 2**53))
        self.assertEqual(binary64_ulp_at(Fraction(1, 3)), Fraction(1, 2**54))

    def test_subnormal_and_zero(self):
        self.assertEqual(binary64_ulp_at(Fraction(1, 2**1022)), Fraction(1, 2**1074))
        self.assertEqual(binary64_ulp_at(Fraction(0)), Fraction(1, 2**1074))

    def test_negative(self):
        self.assertEqual(binary64_ulp_at(Fraction(-1)), Fraction(1, 2**52))


class UlpTest(unittest.TestCase):
    def test_distance(self):
        one = 0x3FF0000000000000
        above = one + 1
        below = one - 1
        self.assertEqual(ulp_distance(one, one), 0)
        self.assertEqual(ulp_distance(one, above), 1)
        self.assertEqual(ulp_distance(below, above), 2)
        # +0 and -0 are the same value; the ULP metric follows the value.
        self.assertEqual(ulp_distance(0x8000000000000000, 0x0000000000000000), 0)
        self.assertEqual(ulp_distance(0x8000000000000001, 0x0000000000000001), 2)
        # The bit-identity metric, not the ULP metric, separates the two zeros.
        self.assertNotEqual(0x8000000000000000, 0x0000000000000000)

    def test_within_one_ulp(self):
        one = value_of_bits(0x3FF0000000000000)
        above = value_of_bits(0x3FF0000000000001)
        above2 = value_of_bits(0x3FF0000000000002)
        self.assertTrue(within_one_ulp(one, one))
        self.assertTrue(within_one_ulp(one, above))
        self.assertFalse(within_one_ulp(one, above2))

    def test_epsilon(self):
        self.assertEqual(EPS64, Fraction(1, 2**52))


class FormatTest(unittest.TestCase):
    def test_fraction(self):
        self.assertEqual(format_fraction(Fraction(1, 4)), "0.25")
        self.assertEqual(format_fraction(Fraction(3)), "3")


if __name__ == "__main__":
    unittest.main()
