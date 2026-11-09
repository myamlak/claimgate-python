#!/usr/bin/env python3
"""Generate the deterministic input sets for the wider validation.

Every input is written as the sixteen hexadecimal digits of a binary64 bit
pattern, one per line.  The drivers read the patterns, so the measured value
is evaluated at the exact double the set names, never at a printed decimal.

    python wider-validation/gen_inputs.py --out wider-validation/inputs
"""

from __future__ import annotations

import argparse
import math
import random
import struct
from pathlib import Path

E = math.e
PI = math.pi
DBL_MAX = float.fromhex("0x1.fffffffffffffp+1023")
TINY = float.fromhex("0x0.0000000000001p-1022")
SMALL_NORMAL = float.fromhex("0x1.0p-1022")


def bits(x: float) -> str:
    return struct.pack(">d", x).hex()


def neighbours(values, k: int = 2) -> list[float]:
    out = []
    for value in values:
        out.append(value)
        up = value
        down = value
        for _ in range(k):
            up = math.nextafter(up, math.inf)
            down = math.nextafter(down, -math.inf)
            out.extend([up, down])
    return out


def uniform(rng, lo, hi, n):
    return [rng.uniform(lo, hi) for _ in range(n)]


def loguniform(rng, lo, hi, n):
    a, b = math.log(lo), math.log(hi)
    return [math.exp(rng.uniform(a, b)) for _ in range(n)]


def random_bits(rng, n, lo_exp=-1074, hi_exp=1023):
    """Random finite binary64 patterns with an exponent in the given range."""
    out = []
    while len(out) < n:
        pattern = rng.getrandbits(64)
        value = struct.unpack(">d", pattern.to_bytes(8, "big"))[0]
        if not math.isfinite(value):
            continue
        exponent = math.frexp(value)[1] - 1 if value else -1074
        if lo_exp <= exponent <= hi_exp:
            out.append(value)
    return out


def clean(values) -> list[float]:
    seen = set()
    out = []
    for value in values:
        if not math.isfinite(value):
            continue
        key = struct.pack(">d", value)
        if key in seen:
            continue
        seen.add(key)
        out.append(value)
    return out


def write(path: Path, values) -> int:
    values = clean(values)
    path.write_text("\n".join(bits(value) for value in values) + "\n", encoding="ascii")
    return len(values)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(20261109)
    counts = {}

    # SLEEF: a sample of the u10 functions over their documented domains.
    sin_edges = neighbours([0.0, 1e-300, 1e-8, PI / 2, PI, 2 * PI, 1e8, 1e16, 1e300, DBL_MAX])
    counts["sleef_sin"] = write(
        out / "sleef_sin.txt",
        uniform(rng, -1e6, 1e6, 700) + uniform(rng, -2 * PI, 2 * PI, 300) + sin_edges,
    )
    exp_edges = neighbours(
        [-708.0, -1.0, -1e-300, 0.0, 1e-300, 1.0, 709.0]
    )
    counts["sleef_exp"] = write(
        out / "sleef_exp.txt",
        uniform(rng, -700.0, 709.0, 700) + uniform(rng, -1.0, 1.0, 200) + exp_edges,
    )
    log_edges = neighbours(
        [TINY, SMALL_NORMAL, 1e-307, 1e-300, 1e-8, 0.5, 1.0, 1.0 + 2**-52, 2.0, 10.0, 1e300, DBL_MAX]
    )
    counts["sleef_log"] = write(
        out / "sleef_log.txt",
        loguniform(rng, 1e-307, 1e307, 900) + log_edges,
    )
    erf_edges = neighbours([0.0, 1e-300, 1e-8, 0.5, 1.0, 2.0, 6.0, 27.0, -27.0])
    counts["sleef_erf"] = write(
        out / "sleef_erf.txt",
        uniform(rng, -6.0, 6.0, 700) + uniform(rng, -0.1, 0.1, 200) + erf_edges,
    )

    # MPFR: the inputs are random finite doubles, with the function's domain.
    counts["mpfr_sin"] = write(
        out / "mpfr_sin.txt",
        random_bits(rng, 900) + neighbours([0.0, PI / 2, PI, 1e300, DBL_MAX]),
    )
    counts["mpfr_exp"] = write(
        out / "mpfr_exp.txt",
        uniform(rng, -708.0, 709.0, 900) + neighbours([-708.0, -1.0, 0.0, 1.0, 709.0]),
    )
    counts["mpfr_log"] = write(
        out / "mpfr_log.txt",
        loguniform(rng, TINY, DBL_MAX, 900)
        + neighbours([TINY, SMALL_NORMAL, 1.0, DBL_MAX]),
    )
    counts["mpfr_atan"] = write(
        out / "mpfr_atan.txt",
        random_bits(rng, 900) + neighbours([0.0, 1.0, -1.0, 1e300, DBL_MAX]),
    )

    # GSL: the functions chosen from the manual's row-shaped claims.
    gsl_erf = neighbours([0.0, 1e-300, 1e-8, 0.5, 1.0, 2.0, 6.0, 27.0, -27.0])
    counts["gsl_erf"] = write(
        out / "gsl_erf.txt", uniform(rng, -6.0, 6.0, 700) + uniform(rng, -0.1, 0.1, 200) + gsl_erf
    )
    gsl_gamma = neighbours([0.5, 1.0, 1.5, 2.0, 5.0, 10.0, 50.0, 100.0, 170.0])
    counts["gsl_gamma"] = write(
        out / "gsl_gamma.txt", uniform(rng, 0.01, 170.0, 900) + gsl_gamma
    )
    gsl_bessel = neighbours([1e-8, 0.1, 1.0, 5.0, 10.0, 50.0, 100.0, 500.0])
    counts["gsl_bessel_j0"] = write(
        out / "gsl_bessel_j0.txt", uniform(rng, 0.0, 500.0, 900) + gsl_bessel
    )
    counts["gsl_bessel_j1"] = write(
        out / "gsl_bessel_j1.txt", uniform(rng, 0.0, 500.0, 900) + gsl_bessel
    )
    # The two GSL_PREC_DOUBLE functions with an MPFR reference: Airy Ai and
    # the complete elliptic integral K.  Both domains keep the value away
    # from a zero, where a relative error is not defined.
    gsl_airy = neighbours([0.0, 0.1, 1.0, 2.0, 5.0, 10.0])
    counts["gsl_airy_ai"] = write(
        out / "gsl_airy_ai.txt", uniform(rng, 0.0, 10.0, 900) + gsl_airy
    )
    gsl_ellint = [value for value in neighbours([0.0, 0.1, 0.5, 0.9]) if 0.0 <= value <= 0.9]
    counts["gsl_ellint_k"] = write(
        out / "gsl_ellint_k.txt", uniform(rng, 0.0, 0.9, 900) + gsl_ellint
    )

    for name, count in sorted(counts.items()):
        print(f"{name:20s} {count:5d} inputs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
