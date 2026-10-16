/* SPDX-License-Identifier: BSD-2-Clause */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int apple_sscanf_under_test(const char *, const char *, ...);

/* A string-backed FILE has no more bytes once its initial buffer is spent. */
int
fixture_srefill(FILE *stream)
{
	(void)stream;
	return EOF;
}

static void
require(int condition, const char *message)
{
	if (!condition) {
		fprintf(stderr, "FAIL %s\n", message);
		exit(2);
	}
}

int
main(int argc, char **argv)
{
	int major = -1, minor = -1, count = -1;
	unsigned display = 0, byte = 0;
	char software[64] = {0};
	char proto[32] = {0};
	char data[32] = {0};
	char scanset[16] = {0};

	if (argc > 1)
		return 37;

	require(apple_sscanf_under_test("SSH-2.0-OpenSSH_9.9\n",
	    "SSH-%d.%d-%63[^\n]\n", &major, &minor, software) == 3,
	    "SSH version assignment count");
	require(major == 2 && minor == 0 && strcmp(software, "OpenSSH_9.9") == 0,
	    "SSH version values");

	require(apple_sscanf_under_test("10", "%u", &display) == 1 && display == 10,
	    "X11 display number");
	require(apple_sscanf_under_test("Aftrail", "%2x%n", &byte, &count) == 1 &&
	    byte == 0xaf && count == 2, "X11 hex byte and consumed count");

	require(apple_sscanf_under_test("ignored MIT-MAGIC cookie",
	    "%*s %31s %31s", proto, data) == 2,
	    "X11 token assignment count");
	require(strcmp(proto, "MIT-MAGIC") == 0 && strcmp(data, "cookie") == 0,
	    "X11 token values");

	require(apple_sscanf_under_test("abc123", "%15[a-z]", scanset) == 1 &&
	    strcmp(scanset, "abc") == 0, "character class");
	require(apple_sscanf_under_test("", "%u", &display) == EOF,
	    "empty input failure");

	puts("APPLE_LIBC167_SSCANF PASS SSH=1 X11=1 HEX=1 TOKEN=1 SCANSET=1 EOF=1");
	return 0;
}
