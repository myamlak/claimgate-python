/*
 * Measure a scalar SLEEF u10 function against an MPFR reference.
 *
 * Usage: sleef_driver <sin|exp|log|erf> <inputs.txt>
 *
 * Each input line is sixteen hexadecimal digits of a binary64 bit pattern.
 * The output is CSV:
 *
 *   input_bits,x,result_bits,result,reference_60d,error_ulp,status
 *
 * error_ulp is |result - reference| divided by the binary64 spacing at the
 * correctly rounded reference, floored at the smallest subnormal.  That is
 * the definition SLEEF's own tester uses (countULPdp in
 * src/common/testerutil.c).  The reference is MPFR at 256 bits; the printed
 * 60 significant digits are more than enough for a binary64 comparison.
 */

#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <mpfr.h>
#include <sleef.h>

#define REFERENCE_BITS 256
#define SMALLEST_SUBNORMAL 4.9406564584124654e-324

typedef double (*scalar_function)(double);

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

static void reference_value(mpfr_t out, const char *name, const mpfr_t x)
{
    if (strcmp(name, "sin") == 0) {
        mpfr_sin(out, x, MPFR_RNDN);
    } else if (strcmp(name, "exp") == 0) {
        mpfr_exp(out, x, MPFR_RNDN);
    } else if (strcmp(name, "log") == 0) {
        mpfr_log(out, x, MPFR_RNDN);
    } else if (strcmp(name, "erf") == 0) {
        mpfr_erf(out, x, MPFR_RNDN);
    } else {
        fprintf(stderr, "unknown function %s\n", name);
        exit(2);
    }
}

int main(int argc, char **argv)
{
    if (argc != 3) {
        fprintf(stderr, "usage: %s <sin|exp|log|erf> <inputs.txt>\n", argv[0]);
        return 2;
    }
    const char *name = argv[1];
    scalar_function function = NULL;
    if (strcmp(name, "sin") == 0) {
        function = Sleef_sin_u10;
    } else if (strcmp(name, "exp") == 0) {
        function = Sleef_exp_u10;
    } else if (strcmp(name, "log") == 0) {
        function = Sleef_log_u10;
    } else if (strcmp(name, "erf") == 0) {
        function = Sleef_erf_u10;
    } else {
        fprintf(stderr, "unknown function %s\n", name);
        return 2;
    }

    FILE *input = fopen(argv[2], "r");
    if (input == NULL) {
        perror(argv[2]);
        return 2;
    }

    mpfr_set_default_prec(REFERENCE_BITS);
    mpfr_t x, reference, error, spacing;
    mpfr_inits(x, reference, error, spacing, (mpfr_ptr)0);

    printf("input_bits,x,result_bits,result,reference_60d,error_ulp,status\n");
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
        reference_value(reference, name, x);
        const double result = function(argument);
        uint64_t result_bits = 0;
        memcpy(&result_bits, &result, sizeof result_bits);

        char reference_text[256];
        mpfr_snprintf(reference_text, sizeof reference_text, "%.60Re", reference);

        const double nearest = mpfr_get_d(reference, MPFR_RNDN);
        const int finite = isfinite(result) && isfinite(nearest);
        double error_ulp = NAN;
        const char *status = "nonfinite";
        if (finite) {
            int exponent = 0;
            frexp(nearest, &exponent);
            const double ulp = fmax(ldexp(1.0, exponent - 53), SMALLEST_SUBNORMAL);
            mpfr_set_d(error, result, MPFR_RNDN);
            mpfr_sub(error, error, reference, MPFR_RNDN);
            mpfr_abs(error, error, MPFR_RNDN);
            mpfr_set_d(spacing, ulp, MPFR_RNDN);
            mpfr_div(error, error, spacing, MPFR_RNDN);
            error_ulp = mpfr_get_d(error, MPFR_RNDN);
            status = "ok";
        }
        printf("%s,%.17g,%016llx,%.17g,%s,%.17g,%s\n",
               line,
               argument,
               (unsigned long long)result_bits,
               result,
               reference_text,
               error_ulp,
               status);
    }
    fclose(input);
    mpfr_clears(x, reference, error, spacing, (mpfr_ptr)0);
    return 0;
}
