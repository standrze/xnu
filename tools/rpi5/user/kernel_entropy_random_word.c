/* SPDX-License-Identifier: BSD-2-Clause
 * Project API adapter over the existing fail-stop kernel entropy adapter.
 * The original LibreSSL rejection sampler supplies arc4random_uniform.
 * No user-space generator or retained random state is introduced here.
 */
#include <stdint.h>
#include <stdlib.h>

uint32_t arc4random(void)
{
    uint32_t value;
    arc4random_buf(&value, sizeof(value));
    return value;
}
