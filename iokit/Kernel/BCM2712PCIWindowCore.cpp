/* SPDX-License-Identifier: BSD-2-Clause */
/* Reuse the unchanged freestanding C core under the real IOKit C++ compile
 * template, preserving its C API linkage. No alternate register implementation. */
extern "C" {
#include "../../loader/rpi5/pcie_windows.c"
}
