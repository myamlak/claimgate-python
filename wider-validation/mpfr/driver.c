/*
 * Check MPFR's correct-rounding guarantee at binary64 precision.
 *
 * Usage: mpfr_driver <sin|exp|log|atan> <inputs.txt>
 *
 * For each input and each of the four rounding modes, the driver evaluates
 * the MPFR function at precision 53, then independently evaluates it at
 * increasing precision until mpfr_can_round certifies the rounding, and
 * compares the two bit patterns.
 *
 * Output (one row per input):
 *   input_bits,x,got_rn_bits,expected_rn_bits,match_rn, ... for ru, rd, rz,
 *   status
 *
 * status is "ok" when every mode was certified and both results are finite
 * normal binary64 values, "undetermined" when the Ziv loop did not certify
 * a mode, and "nonfinite" when a result is not a finite normal binary64.
 */

#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <mpfr.h>

#define PRECISION 53
#define START_EXTRA 64
#define MAX_EXTRA 16384

static int parse_bits(const char *text, double *value, uint64_t *bits)
{
    char *end = NULL;
    if (strlen(text) != 16) {
        return 0;
    }
    unsigned long long pattern = strtoull(text, &end, 16);
    if (end == NULL || *end != '\0') {
        return 0;
    }
    *bits = (uint64_t)pattern;
    memcpy(value, bits, sizeof *value);
    return 1;
}

static void evaluate(mpfr_t out, const char *name, const mpfr_t x, mpfr_rnd_t rnd)
{
    if (strcmp(name, "sin") == 0) {
        mpfr_sin(out, x, rnd);
    } else if (strcmp(name, "exp") == 0) {
        mpfr_exp(out, x, rnd);
    } else if (strcmp(name, "log") == 0) {
        mpfr_log(out, x, rnd);
    } else if (strcmp(name, "atan") == 0) {
        mpfr_atan(out, x, rnd);
    } else {
        fprintf(stderr, "unknown function %s\n", name);
        exit(2);
    }
}

static uint64_t bits_of(mpfr_t value)
{
    const double d = mpfr_get_d(value, MPFR_RNDN);
    uint64_t bits = 0;
    memcpy(&bits, &d, sizeof bits);
    return bits;
}

static int representable(mpfr_t value)
{
    if (!mpfr_number_p(value)) {
        return 0;
    }
    if (mpfr_zero_p(value)) {
        return 1; /* an exact zero is a valid correctly rounded result */
    }
    const double d = mpfr_get_d(value, MPFR_RNDN);
    if (!isfinite(d) || d == 0.0) {
        return 0;
    }
    /* Binary64 normals have MPFR exponents in [-1021, 1024]. */
    const mpfr_exp_t exponent = mpfr_get_exp(value);
    return exponent >= -1021 && exponent <= 1024;
}

int main(int argc, char **argv)
{
    if (argc != 3) {
        fprintf(stderr, "usage: %s <sin|exp|log|atan> <inputs.txt>\n", argv[0]);
        return 2;
    }
    const char *name = argv[1];
    FILE *input = fopen(argv[2], "r");
    if (input == NULL) {
        perror(argv[2]);
        return 2;
    }

    mpfr_set_default_prec(PRECISION);
    mpfr_t x, got, high;
    mpfr_inits2(PRECISION, x, got, (mpfr_ptr)0);
    mpfr_init2(high, PRECISION + START_EXTRA);

    printf("input_bits,x,got_rn_bits,expected_rn_bits,match_rn,"
           "got_ru_bits,expected_ru_bits,match_ru,"
           "got_rd_bits,expected_rd_bits,match_rd,"
           "got_rz_bits,expected_rz_bits,match_rz,status\n");
    char line[256];
    while (fgets(line, sizeof line, input) != NULL) {
        char *newline = strpbrk(line, "\r\n");
        if (newline != NULL) {
            *newline = '\0';
        }
        if (line[0] == '\0') {
            continue;
        }
        double argument = 0.0;
        uint64_t argument_bits = 0;
        if (!parse_bits(line, &argument, &argument_bits)) {
            continue;
        }
        mpfr_set_d(x, argument, MPFR_RNDN);

        uint64_t got_bits[4] = {0, 0, 0, 0};
        uint64_t expected_bits[4] = {0, 0, 0, 0};
        int match[4] = {0, 0, 0, 0};
        mpfr_rnd_t modes[4] = {MPFR_RNDN, MPFR_RNDU, MPFR_RNDD, MPFR_RNDZ};
        int ok = 1;
        int undetermined = 0;
        for (int i = 0; i < 4; ++i) {
            mpfr_set_prec(got, PRECISION);
            evaluate(got, name, x, modes[i]);
            if (!mpfr_number_p(got)) {
                ok = 0;
                continue;
            }
            mpfr_prec_t extra = START_EXTRA;
            int certified = 0;
            while (extra <= MAX_EXTRA) {
                mpfr_set_prec(high, PRECISION + extra);
                evaluate(high, name, x, MPFR_RNDN);
                if (mpfr_can_round(high, PRECISION + extra - PRECISION - 8,
                                   MPFR_RNDN, modes[i], PRECISION)) {
                    mpfr_prec_round(high, PRECISION, modes[i]);
                    certified = 1;
                    break;
                }
                extra *= 2;
            }
            if (!certified) {
                /* An exact result at PRECISION bits (zero, one, ...) is its
                   own correct rounding; the certification test declines it. */
                if (mpfr_equal_p(got, high)) {
                    certified = 1;
                } else {
                    undetermined = 1;
                    continue;
                }
            }
            if (!representable(got) || !representable(high)) {
                ok = 0;
                continue;
            }
            got_bits[i] = bits_of(got);
            expected_bits[i] = bits_of(high);
            match[i] = got_bits[i] == expected_bits[i];
        }
        const char *status = undetermined ? "undetermined" : (ok ? "ok" : "nonfinite");
        printf("%s,%.17g,%016llx,%016llx,%d,%016llx,%016llx,%d,%016llx,%016llx,%d,"
               "%016llx,%016llx,%d,%s\n",
               line, argument,
               (unsigned long long)got_bits[0], (unsigned long long)expected_bits[0], match[0],
               (unsigned long long)got_bits[1], (unsigned long long)expected_bits[1], match[1],
               (unsigned long long)got_bits[2], (unsigned long long)expected_bits[2], match[2],
               (unsigned long long)got_bits[3], (unsigned long long)expected_bits[3], match[3],
               status);
    }
    fclose(input);
    mpfr_clears(x, got, high, (mpfr_ptr)0);
    return 0;
}
