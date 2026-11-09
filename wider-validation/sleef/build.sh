#!/bin/sh
# Build the SLEEF measurement driver against the pinned SLEEF and MPFR builds.
# Run from any directory; the paths are absolute.
set -eu
ROOT="$HOME/wider-validation"
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
OUT="$ROOT/bin"
mkdir -p "$OUT"
gcc -O2 -std=c11 -Wall -Wextra \
    -I"$ROOT/build/sleef/include" \
    -I"$ROOT/prefix/mpfr-4.2.2/include" \
    "$HERE/driver.c" \
    -o "$OUT/sleef_driver" \
    "$ROOT/build/sleef/lib/libsleef.a" \
    "$ROOT/prefix/mpfr-4.2.2/lib/libmpfr.a" \
    -lgmp -lm
echo "built $OUT/sleef_driver"
