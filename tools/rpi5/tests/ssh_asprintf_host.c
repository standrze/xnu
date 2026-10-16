/* SPDX-License-Identifier: BSD-2-Clause */
/* Native oracle for the exact Apple-distributed OpenSSH compatibility body. */
#include <assert.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int
call_vasprintf(char **result, const char *format, ...)
{
	va_list args;
	int rc;

	va_start(args, format);
	rc = vasprintf(result, format, args);
	va_end(args);
	return rc;
}

int
main(int argc, char **argv)
{
	char long_input[4097];
	char *value = NULL;
	int rc;

	if (argc != 1)
		return 37;
	rc = asprintf(&value, "%s:%d", "apple-openssh", 1000);
	assert(rc == 18);
	assert(strcmp(value, "apple-openssh:1000") == 0);
	free(value);

	memset(long_input, 'x', sizeof(long_input) - 1);
	long_input[sizeof(long_input) - 1] = '\0';
	value = NULL;
	rc = call_vasprintf(&value, "[%s]", long_input);
	assert(rc == 4098);
	assert(value[0] == '[' && value[4097] == ']' && value[4098] == '\0');
	free(value);

	value = NULL;
	rc = asprintf(&value, "%s", "");
	assert(rc == 0);
	assert(value != NULL && value[0] == '\0');
	free(value);

	puts("APPLE_OPENSSH_ASPRINTF PASS APIS=2 REALLOC_PATH=1 TARGET_NOT_RUN");
	return 0;
}
