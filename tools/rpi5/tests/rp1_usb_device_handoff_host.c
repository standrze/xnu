/* SPDX-License-Identifier: BSD-2-Clause */
#define main prior_device_handoff_test_main
#include "pcie_device_handoff_host.c"
#undef main

#include "rp1_usb_device_handoff.h"

static void
reject_usb(const void *fdt, size_t bytes, const struct rpi5_memory_types *input)
{
    struct rpi5_memory_types out, before;
    memset(&out, 0xa5, sizeof out);
    before = out;
    assert(rpi5_rp1_usb_device_handoff(fdt, bytes, input, &out));
    assert(!memcmp(&out, &before, sizeof out));
}

int
main(int argc, char **argv)
{
    assert(argc == 3);
    FILE *file = fopen(argv[1], "rb");
    assert(file && !fseek(file, 0, SEEK_END));
    long length = ftell(file);
    assert(length > 0 && length < 256 * 1024);
    rewind(file);
    unsigned char *allocation = malloc((size_t)length + 8);
    assert(allocation);
    void *fdt = allocation + 4;
    assert(fread(fdt, 1, (size_t)length, file) == (size_t)length);
    assert(!fclose(file));

    struct rpi5_memory_types input = initial(), host, out;
    if (!strcmp(argv[2], "reject")) {
        reject_usb(fdt, (size_t)length, &input);
        free(allocation);
        puts("RP1_USB_DEVICE_REJECT");
        return 0;
    }

    assert(!strcmp(argv[2], "accept"));
    assert(!rpi5_pcie_device_handoff(fdt, (size_t)length, &input, &host));
    assert(!rpi5_rp1_usb_device_handoff(fdt, (size_t)length, &host, &out));
    assert(out.device.count == host.device.count + 3);
    assert(!memcmp(&host.normal, &out.normal, sizeof host.normal));
    const struct rpi5_range usb = {0x1f00200000, 0x1f00300000};
    assert(rpi5_memory_type_for(&out, usb) == RPI5_MEMORY_DEVICE);
    assert(rpi5_memory_type_for(&out,
        (struct rpi5_range){usb.start - 1, usb.start}) == RPI5_MEMORY_UNKNOWN);
    assert(rpi5_memory_type_for(&out,
        (struct rpi5_range){usb.end, usb.end + 1}) == RPI5_MEMORY_UNKNOWN);

    unsigned char encoded[RPI5_MEMORY_MAP_MAX_BYTES];
    size_t written = 0;
    assert(!rpi5_memory_types_encode(&out, encoded, sizeof encoded, &written));
    struct rpi5_kernel_memory_map kernel = {0};
    assert(!rpi5_map_decode(encoded, written, &kernel));
    assert(rpi5_map_type(&kernel, usb.start, usb.end) == RPI5_MEMORY_DEVICE);
    assert(!rpi5_map_type(&kernel, 0x1f00300000, 0x1f00400000));

    reject_usb(fdt, (size_t)length, &out);
    reject_usb(fdt, (size_t)length - 1, &host);
    assert(rpi5_rp1_usb_device_handoff(fdt, (size_t)length, &host, &host));
    struct rpi5_memory_types bad = host;
    bad.normal.extent[bad.normal.count++] = usb;
    reject_usb(fdt, (size_t)length, &bad);
    bad = host;
    bad.device.extent[bad.device.count++] = usb;
    reject_usb(fdt, (size_t)length, &bad);

    struct rpi5_memory_types full = initial();
    full.device.count = 29;
    for (unsigned i = 0; i < 30; i++) {
        full.device.extent[i] = (struct rpi5_range){
            0x1100000000 + i * 0x8000ull,
            0x1100004000 + i * 0x8000ull,
        };
    }
    assert(!rpi5_rp1_usb_device_handoff(fdt, (size_t)length, &full, &out));
    assert(out.device.count == 32);
    full.device.count = 30;
    reject_usb(fdt, (size_t)length, &full);

    free(allocation);
    puts("RP1_USB_DEVICE_PASS EXACT_USB0_PAGES=64 TOTAL_NEW_PAGES=70 KERNEL_DECODE=1 NO_MMIO=1");
    return 0;
}
