/* SPDX-License-Identifier: BSD-2-Clause */
/*
 * Link-only target contract for Apple's current FILE/__sFILEX pairing.
 *
 * This object is never substituted into the accepted Libc-167 runtime.  It
 * deliberately consumes the current Libc checkout's public FILE definition
 * and private __sFILEX definition together, then calls the unchanged current
 * fwide(3) and flockfile implementation through the genuine Apple pthread
 * mutex implementation.  Runtime qualification still requires execution on
 * the Raspberry Pi target.
 */

#include <errno.h>
#include <stddef.h>
#include <pthread.h>
#include <stdio.h>

#include "local.h"

extern void _flockfile(FILE *);
extern int _ftrylockfile(FILE *);
extern void _funlockfile(FILE *);

volatile unsigned int apple_filex_candidate_result;
const unsigned long apple_filex_file_size = sizeof(FILE);
const unsigned long apple_filex_extra_size = sizeof(struct __sFILEX);
const unsigned long apple_filex_extra_offset = offsetof(FILE, _extra);
const unsigned long apple_filex_mutex_offset =
    offsetof(struct __sFILEX, fl_mutex);
static FILE apple_filex_stream;
static struct __sFILEX apple_filex_extra;

__attribute__((noreturn))
void
apple_filex_candidate_start(void)
{
	FILE *stream = &apple_filex_stream;

	stream->_extra = &apple_filex_extra;
	apple_filex_extra.fl_mutex =
	    (pthread_mutex_t)PTHREAD_RECURSIVE_MUTEX_INITIALIZER;
	apple_filex_extra.orientation = 0;
	errno = EBUSY;

	if (fwide(stream, 1) != 1 || fwide(stream, -1) != 1 || errno != EBUSY)
		apple_filex_candidate_result |= 1u;

	_flockfile(stream);
	_flockfile(stream);
	if (_ftrylockfile(stream) != 0)
		apple_filex_candidate_result |= 2u;
	_funlockfile(stream);
	_funlockfile(stream);
	_funlockfile(stream);
	if (errno != EBUSY)
		apple_filex_candidate_result |= 4u;

	apple_filex_candidate_result |= 0x80000000u;
	for (;;)
		__asm__ volatile("wfe");
}
