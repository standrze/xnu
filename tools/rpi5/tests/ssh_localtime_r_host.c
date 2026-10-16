/* SPDX-License-Identifier: BSD-2-Clause */
/* Native oracle for Apple OpenSSH's public localtime_r fallback. */
#include <assert.h>
#include <stdlib.h>
#include <time.h>
#include <stdio.h>

int
main(int argc, char **argv)
{
	time_t epoch = 0;
	struct tm result;
	struct tm *returned;

	if (argc != 1)
		return 37;
	assert(setenv("TZ", "UTC0", 1) == 0);
	tzset();
	returned = localtime_r(&epoch, &result);
	assert(returned == &result);
	assert(epoch == 0);
	assert(result.tm_year == 70 && result.tm_mon == 0 && result.tm_mday == 1);
	assert(result.tm_hour == 0 && result.tm_min == 0 && result.tm_sec == 0);
	puts("APPLE_OPENSSH_LOCALTIME_R PASS API=1 UTC_EPOCH=1 TARGET_NOT_RUN");
	return 0;
}
