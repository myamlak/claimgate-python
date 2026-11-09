"""Exact reading of bounds, measured values and references.

A claimgate comparison must not inherit the rounding of the values it
compares.  Every finite quantity is carried as :class:`fractions.Fraction`:
a decimal in a data file is read through :class:`decimal.Decimal`, which is
exact, and a binary64 is read from its hexadecimal bit pattern, which is
exact.  Only the presentation to the report converts to float.

Non-finite values are carried as the corresponding Python float (``inf``,
``-inf``, ``nan``); a comparison with one is decided explicitly.
"""

from __future__ import annotations

import math
import struct
from decimal import Decimal, InvalidOperation
from fractions import Fraction

#: binary64 epsilon, 2**-52, the unit Boost.Math's accuracy tables use.
EPS64 = Fraction(1, 2**52)


class NumberError(ValueError):
    """A number in a book or a data file cannot be read exactly."""


def is_finite(value) -> bool:
    return isinstance(value, Fraction)


def parse_exact(value):
    """Read a book number exactly.

    Accepts an int, a float, or a string holding a decimal, a hexadecimal
    float, ``2^p``, or terms of those separated by ``' + '``.  The string
    ``1e-15 + 2.5e-7`` is read as the exact sum.
    """
    if isinstance(value, bool):
        raise NumberError(f"a boolean is not a number: {value!r}")
    if isinstance(value, int):
        return Fraction(value)
    if isinstance(value, float):
        if math.isfinite(value):
            return Fraction(value)
        return value
    if not isinstance(value, str):
        raise NumberError(f"cannot read {value!r} as a number")

    text = value.strip()
    if not text:
        raise NumberError("an empty string is not a number")
    if text.lower() in ("inf", "+inf", "infinity", "+infinity"):
        return math.inf
    if text.lower() in ("-inf", "-infinity"):
        return -math.inf
    if text.lower() == "nan":
        return math.nan

    terms = text.split(" + ")
    total = Fraction(0)
    for term in terms:
        total += _parse_term(term.strip())
    return total


def _parse_term(text: str) -> Fraction:
    if not text:
        raise NumberError("an empty summand in a bound")
    lowered = text.lower()
    if lowered.startswith("2^"):
        try:
            power = int(text[2:])
        except ValueError as exc:
            raise NumberError(f"cannot read the power of two {text!r}") from exc
        if not -1074 <= power <= 1023:
            raise NumberError(f"a power of two outside binary64's range: {text!r}")
        return Fraction(1, 2**-power) if power < 0 else Fraction(2**power)
    if lowered.startswith(("0x", "+0x", "-0x")):
        try:
            value = float.fromhex(text)
        except ValueError as exc:
            raise NumberError(f"cannot read the hexadecimal float {text!r}") from exc
        return Fraction(value)
    try:
        decimal = Decimal(text)
    except InvalidOperation as exc:
        raise NumberError(f"cannot read {text!r} as a decimal") from exc
    if not decimal.is_finite():
        raise NumberError(f"a non-finite term in a bound: {text!r}")
    return Fraction(decimal)


def parse_float_value(text: str):
    """Read a data-file value exactly.

    A 16-character hex string is read as the bits of a binary64; anything
    else is read as an exact decimal.  Returns ``(Fraction_or_float, bits)``
    where ``bits`` is the 64-bit integer pattern when the text was a bit
    pattern, else ``None``.
    """
    text = text.strip()
    if not text:
        raise NumberError("an empty data cell")
    if len(text) == 16 and all(ch in "0123456789abcdefABCDEF" for ch in text):
        bits = int(text, 16)
        value = struct.unpack(">d", bits.to_bytes(8, "big"))[0]
        if math.isfinite(value):
            return Fraction(value), bits
        return value, bits
    if text.lower() in ("nan", "inf", "+inf", "-inf", "infinity", "-infinity"):
        value = float(text.replace("infinity", "inf"))
        return value, None
    try:
        decimal = Decimal(text)
    except InvalidOperation as exc:
        raise NumberError(f"cannot read the data value {text!r}") from exc
    if not decimal.is_finite():
        return float(decimal), None
    return Fraction(decimal), None


def bits_of(value: float) -> int:
    return struct.unpack(">Q", struct.pack(">d", value))[0]


def value_of_bits(bits: int) -> float:
    return struct.unpack(">d", struct.pack(">Q", bits))[0]


def ordered_index(bits: int) -> int:
    """Map a binary64 bit pattern to a monotone integer."""
    if bits & (1 << 63):
        return -(bits & ((1 << 63) - 1))
    return bits


def ulp_distance(a_bits: int, b_bits: int) -> int:
    """The number of representable binary64 values between two patterns."""
    if a_bits == b_bits:
        return 0
    if math.isnan(value_of_bits(a_bits)) or math.isnan(value_of_bits(b_bits)):
        return 1 << 62
    return abs(ordered_index(a_bits) - ordered_index(b_bits))


def within_one_ulp(a: float, b: float) -> bool:
    """True when two binary64 values are equal or adjacent."""
    if a == b:
        return True
    lo, hi = (a, b) if a < b else (b, a)
    return math.nextafter(lo, math.inf) >= hi


def finite_fraction(value) -> Fraction:
    if not isinstance(value, Fraction):
        raise NumberError(f"the value is not finite: {value!r}")
    return value


def format_fraction(value) -> str:
    """A compact decimal rendering of an exact value, for the report."""
    if isinstance(value, Fraction):
        if value.denominator == 1:
            return str(value.numerator)
        decimal = Decimal(value.numerator) / Decimal(value.denominator)
        return format(decimal, ".17g")
    return str(value)


def fraction_to_float(value) -> float:
    if isinstance(value, Fraction):
        try:
            return float(value)
        except OverflowError:
            return math.inf if value > 0 else -math.inf
    return float(value)
