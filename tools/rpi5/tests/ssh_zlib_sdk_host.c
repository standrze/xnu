/* SPDX-License-Identifier: BSD-2-Clause
 * SDK-header caller against original upstream zlib, with host allocation.
 */
#include <zlib.h>
#include <stdio.h>
#include <string.h>

static unsigned char input[4096], packed[8192], output[4096];

static int roundtrip(unsigned length, int level)
{
    z_stream encoder = {0}, decoder = {0};
    int status;
    unsigned packed_length;
    if (deflateInit(&encoder, level) != Z_OK) return 1;
    encoder.next_in = input;
    encoder.avail_in = length;
    encoder.next_out = packed;
    encoder.avail_out = sizeof(packed);
    status = deflate(&encoder, Z_FINISH);
    packed_length = (unsigned)encoder.total_out;
    if (deflateEnd(&encoder) != Z_OK || status != Z_STREAM_END) return 2;
    if (inflateInit(&decoder) != Z_OK) return 3;
    decoder.next_in = packed;
    decoder.avail_in = packed_length;
    decoder.next_out = output;
    decoder.avail_out = sizeof(output);
    status = inflate(&decoder, Z_FINISH);
    if (decoder.total_out != length || memcmp(input, output, length)) return 4;
    if (inflateEnd(&decoder) != Z_OK || status != Z_STREAM_END) return 5;
    return 0;
}

int main(void)
{
    static const unsigned lengths[] = {0, 1, 257, 4096};
    unsigned i, level;
    uLongf packed_length = sizeof(packed), output_length = sizeof(output);
    z_stream decoder = {0};
    int status;
    if (strcmp(zlibVersion(), "1.3.2")) return 10;
    for (i = 0; i < sizeof(input); ++i) input[i] = (unsigned char)(i * 37U + i / 17U);
    for (level = 0; level < 2; ++level)
        for (i = 0; i < sizeof(lengths) / sizeof(lengths[0]); ++i)
            if (roundtrip(lengths[i], level ? 9 : 0)) return 11;
    if (compress2(packed, &packed_length, input, sizeof(input), 6) != Z_OK) return 12;
    packed[packed_length - 1] ^= 1;
    if (uncompress(output, &output_length, packed, packed_length) != Z_DATA_ERROR) return 13;
    packed[packed_length - 1] ^= 1;
    if (inflateInit(&decoder) != Z_OK) return 14;
    decoder.next_in = packed;
    decoder.avail_in = (unsigned)packed_length - 1;
    decoder.next_out = output;
    decoder.avail_out = sizeof(output);
    status = inflate(&decoder, Z_FINISH);
    if (inflateEnd(&decoder) != Z_OK || status != Z_BUF_ERROR) return 15;
    puts("SSH_ZLIB_SDK_ABI PASS STREAMS=8 BAD_CHECKSUM=1 TRUNCATED=1 VERSION=1.3.2");
    return 0;
}
