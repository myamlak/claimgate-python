/*
 * Measure GSL special functions against an MPFR reference.
 *
 * Usage: gsl_driver <erf|gamma|bessel_j0|bessel_j1|airy_ai|ellint_k> <inputs.txt>
 *
 * The first four are the _e routines, whose gsl_sf_result carries the
 * library's own absolute error estimate.  airy_ai and ellint_k take a
 * gsl_mode_t and are measured at GSL_PREC_DOUBLE, the mode whose manual
 * entry states a relative accuracy of approximately 2e-16.
 *
 * Output:
 *   input_bits,x,result_bits,result,gsl_err,gsl_err_bits,reference_60d,
 *   true_error,relative_error,error_over_err,status
 *
 * true_error and relative_error are |result - reference| and that divided by
 * |reference|.  error_over_err is true_error / gsl_err, the test of the
 * library's own error estimate.  status is "ok" only when the value is a
 * finite non-zero result with a finite non-zero reference and, for the _e
 * rows, a positive gsl_err.
 */

#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <gsl/gsl_sf.h>
#include <gsl/gsl_sf_airy.h>
#include <gsl/gsl_sf_bessel.h>
#include <gsl/gsl_sf_ellint.h>
#include <gsl/gsl_sf_erf.h>
#include <gsl/gsl_sf_gamma.h>
#include <mpfr.h>

#define REFERENCE_BITS 256

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

int main(int argc, char **argv)
{
    if (argc != 3) {
        fprintf(stderr, "usage: %s <function> <inputs.txt>\n", argv[0]);
        return 2;
    }
    const char *name = argv[1];
    const int is_mode = strcmp(name, "airy_ai") == 0 || strcmp(name, "ellint_k") == 0;
    const int is_error_estimate = !is_mode;
    if (!is_mode && strcmp(name, "erf") != 0 && strcmp(name, "gamma") != 0
        && strcmp(name, "bessel_j0") != 0 && strcmp(name, "bessel_j1") != 0) {
        fprintf(stderr, "unknown function %s\n", name);
        return 2;
    }

    FILE *input = fopen(argv[2], "r");
    if (input == NULL) {
        perror(argv[2]);
        return 2;
    }

    mpfr_set_default_prec(REFERENCE_BITS);
    mpfr_t x, reference, error, absolute_error, relative_error, temp, one, m, root, agm, pi;
    mpfr_inits(x, reference, error, absolute_error, relative_error, temp, one, m, root,
               agm, pi, (mpfr_ptr)0);
    mpfr_set_ui(one, 1, MPFR_RNDN);

    printf("input_bits,x,result_bits,result,gsl_err,gsl_err_bits,reference_60d,"
           "true_error,relative_error,error_over_err,status\n");
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

        gsl_sf_result result;
        int status = 0;
        if (strcmp(name, "erf") == 0) {
            status = gsl_sf_erf_e(argument, &result);
            mpfr_set_d(x, argument, MPFR_RNDN);
            mpfr_erf(reference, x, MPFR_RNDN);
        } else if (strcmp(name, "gamma") == 0) {
            status = gsl_sf_gamma_e(argument, &result);
            mpfr_set_d(x, argument, MPFR_RNDN);
            mpfr_gamma(reference, x, MPFR_RNDN);
        } else if (strcmp(name, "bessel_j0") == 0) {
            status = gsl_sf_bessel_J0_e(argument, &result);
            mpfr_set_d(x, argument, MPFR_RNDN);
            mpfr_j0(reference, x, MPFR_RNDN);
        } else if (strcmp(name, "bessel_j1") == 0) {
            status = gsl_sf_bessel_J1_e(argument, &result);
            mpfr_set_d(x, argument, MPFR_RNDN);
            mpfr_j1(reference, x, MPFR_RNDN);
        } else if (strcmp(name, "airy_ai") == 0) {
            status = gsl_sf_airy_Ai_e(argument, GSL_PREC_DOUBLE, &result);
            mpfr_set_d(x, argument, MPFR_RNDN);
            mpfr_ai(reference, x, MPFR_RNDN);
        } else { /* ellint_k: K(k) = pi / (2 agm(1, sqrt(1-k^2))) */
            status = gsl_sf_ellint_Kcomp_e(argument, GSL_PREC_DOUBLE, &result);
            mpfr_set_d(x, argument, MPFR_RNDN);
            mpfr_mul(m, x, x, MPFR_RNDN);
            mpfr_ui_sub(m, 1, m, MPFR_RNDN);
            mpfr_sqrt(root, m, MPFR_RNDN);
            mpfr_agm(agm, one, root, MPFR_RNDN);
            mpfr_const_pi(pi, MPFR_RNDN);
            mpfr_div(reference, pi, agm, MPFR_RNDN);
            mpfr_div_ui(reference, reference, 2, MPFR_RNDN);
        }

        const double got = result.val;
        const double gsl_err = result.err;
        uint64_t result_bits = 0;
        uint64_t gsl_err_bits = 0;
        memcpy(&result_bits, &got, sizeof result_bits);
        memcpy(&gsl_err_bits, &gsl_err, sizeof gsl_err_bits);
        const double nearest = mpfr_get_d(reference, MPFR_RNDN);

        char reference_text[256];
        mpfr_snprintf(reference_text, sizeof reference_text, "%.60Re", reference);

        const int finite = status == 0 && isfinite(got) && isfinite(nearest) && nearest != 0.0;
        const int errorest_ok = !is_error_estimate || (isfinite(gsl_err) && gsl_err > 0.0);
        double true_error = NAN;
        double relative = NAN;
        double over = NAN;
        const char *state = "nonfinite";
        if (finite && errorest_ok) {
            mpfr_set_d(error, got, MPFR_RNDN);
            mpfr_sub(error, error, reference, MPFR_RNDN);
            mpfr_abs(absolute_error, error, MPFR_RNDN);
            mpfr_abs(temp, reference, MPFR_RNDN);
            mpfr_div(relative_error, absolute_error, temp, MPFR_RNDN);
            true_error = mpfr_get_d(absolute_error, MPFR_RNDN);
            relative = mpfr_get_d(relative_error, MPFR_RNDN);
            if (is_error_estimate) {
                mpfr_set_d(temp, gsl_err, MPFR_RNDN);
                mpfr_div(error, absolute_error, temp, MPFR_RNDN);
                over = mpfr_get_d(error, MPFR_RNDN);
            }
            state = "ok";
        } else if (finite) {
            state = "zero_error";
        }
        printf("%s,%.17g,%016llx,%.17g,%.17g,%016llx,%s,%.17g,%.17g,%.17g,%s\n",
               line,
               argument,
               (unsigned long long)result_bits,
               got,
               gsl_err,
               (unsigned long long)gsl_err_bits,
               reference_text,
               true_error,
               relative,
               over,
               state);
    }
    fclose(input);
    mpfr_clears(x, reference, error, absolute_error, relative_error, temp, one, m, root,
                agm, pi, (mpfr_ptr)0);
    return 0;
}
