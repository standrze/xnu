/* SPDX-License-Identifier: BSD-2-Clause
 * Project ABI-name adapters, not Apple source. Classification is implemented
 * by the pinned Apple Libm __fpclassify C algorithm in the same archive.
 */
#include <math.h>
#undef isinf
#undef isnan
extern int __fpclassify(double);
int isinf(double value) { return __fpclassify(value) == FP_INFINITE; }
int isnan(double value) { return __fpclassify(value) == FP_NAN; }
