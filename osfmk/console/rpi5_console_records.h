/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_CONSOLE_RECORDS_H
#define RPI5_CONSOLE_RECORDS_H
#include <stdarg.h>
#include <stddef.h>
/* 1 means accepted by the ordinary console path, not physically displayed.
 * 0 leaves the original early/IRQ/panic/raw caller responsible for output. */
int rpi5_console_kprintf_record(const char *, va_list);
int rpi5_console_write_record(const char *, size_t);
#endif
