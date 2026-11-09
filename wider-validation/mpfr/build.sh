#!/bin/sh
# Build the MPFR correct-rounding driver against the pinned MPFR build.
set -eu
ROOT="$HOME/wider-validation"
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
OUT="$ROOT/bin"
mkdir -p "$OUT"
gcc -O2 -std=c11 -Wall -Wextra \
    -I"$ROOT/prefix/mpfr-4.2.2/include" \
    "$HERE/driver.c" \
    -o "$OUT/mpfr_driver" \
    "$ROOT/prefix/mpfr-4.2.2/lib/libmpfr.a" \
    -lgmp -lm
echo "built $OUT/mpfr_driver"
