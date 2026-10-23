/* Shared finite-aware comparison: NaN must never look like zero error. */
#ifndef JEV_TEST_COMMON_H
#define JEV_TEST_COMMON_H
#include <math.h>
static float finite_diff(float actual, float expected) {
    if (!isfinite(actual) || !isfinite(expected)) return INFINITY;
    return fabsf(actual - expected);
}
#endif
