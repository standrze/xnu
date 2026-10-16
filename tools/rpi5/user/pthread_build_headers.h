/* SPDX-License-Identifier: BSD-2-Clause */
/* Compile-only compatibility for independently published Apple source sets.
 * No types/layouts, runtime definitions, security options or bodies changed. */
#include <Availability.h>
#include <stdbool.h>

/* Current libpthread still spells two availability annotations xros. Apple's
 * current AvailabilityVersions DSL calls that platform visionos and records
 * cmd_aliases=xros. Preserve the actual availability attribute, not an empty
 * annotation or a change to the advertised macOS availability. */
#ifndef __API_AVAILABLE_PLATFORM_xros
#define __API_AVAILABLE_PLATFORM_xros(x) __API_AVAILABLE_PLATFORM_visionos(x)
#endif

/* Declaration matches the genuine definition in XNU's
 * libsyscall/wrappers/_libkernel_init.c. It remains an unresolved import until
 * that real initialization provider is integrated; no value is supplied here. */
extern bool _os_xbs_chrooted;
