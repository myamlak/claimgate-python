#!/bin/sh
# Build the GSL measurement driver against the pinned GSL and MPFR builds.
set -eu
ROOT="$HOME/wider-validation"
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
OUT="$ROOT/bin"
mkdir -p "$OUT"
gcc -O2 -std=c11 -Wall -Wextra \
    -I"$ROOT/prefix/gsl-2.8/include" \
    -I"$ROOT/prefix/mpfr-4.2.2/include" \
    "$HERE/driver.c" \
    -o "$OUT/gsl_driver" \
    "$ROOT/prefix/gsl-2.8/lib/libgsl.a" \
    "$ROOT/prefix/gsl-2.8/lib/libgslcblas.a" \
    "$ROOT/prefix/mpfr-4.2.2/lib/libmpfr.a" \
    -lgmp -lm
echo "built $OUT/gsl_driver"
