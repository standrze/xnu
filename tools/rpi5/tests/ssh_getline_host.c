/* SPDX-License-Identifier: BSD-2-Clause */
/* Native oracle for Apple OpenSSH's public bsd-getline.c provider. */
#define _WITH_GETLINE
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int
main(int argc, char **argv)
{
	FILE *stream;
	char *line = NULL;
	size_t capacity = 0;
	ssize_t length;
	int i;

	if (argc != 1)
		return 37;
	stream = tmpfile();
	assert(stream != NULL);
	assert(fputs("first line\n\n", stream) >= 0);
	for (i = 0; i < 9000; i++)
		assert(fputc('x', stream) == 'x');
	assert(fflush(stream) == 0);
	rewind(stream);

	length = getline(&line, &capacity, stream);
	assert(length == 11 && strcmp(line, "first line\n") == 0);
	length = getline(&line, &capacity, stream);
	assert(length == 1 && strcmp(line, "\n") == 0);
	length = getline(&line, &capacity, stream);
	assert(length == 9000 && capacity > 9000);
	assert(line[0] == 'x' && line[8999] == 'x' && line[9000] == '\0');
	length = getline(&line, &capacity, stream);
	assert(length == -1 && feof(stream));

	free(line);
	assert(fclose(stream) == 0);
	puts("APPLE_OPENSSH_GETLINE PASS API=1 LONG=9000 EOF=1 TARGET_NOT_RUN");
	return 0;
}
