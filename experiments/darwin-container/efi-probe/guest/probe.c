/* SPDX-License-Identifier: BSD-2-Clause
 * Original bounded UEFI execution probe. This does not load or boot XNU.
 */
#include "efi_abi.h"
#ifndef PROBE_NONCE
#error A fresh 32-character hexadecimal PROBE_NONCE is required
#endif

/* Compiler-generated aggregate initialization has no guest libc to call. */
void *memset(void *destination, int byte, size_t count)
{
    volatile uint8_t *out = destination;
    for (size_t i = 0; i < count; i++) out[i] = (uint8_t)byte;
    return destination;
}

static const guid_t loaded_image_guid = {0x5b1b31a1, 0x9562, 0x11d2,
    {0x8e, 0x3f, 0x00, 0xa0, 0xc9, 0x69, 0x72, 0x3b}};
static const guid_t filesystem_guid = {0x964e5b22, 0x6459, 0x11d2,
    {0x8e, 0x39, 0x00, 0xa0, 0xc9, 0x69, 0x72, 0x3b}};
static const guid_t acpi2_guid = {0x8868e871, 0xe4f1, 0x11d3,
    {0xbc, 0x22, 0x00, 0x80, 0xc7, 0x3c, 0x88, 0x81}};
static const guid_t fdt_guid = {0xb1b621d5, 0xf19c, 0x41a5,
    {0x83, 0x0b, 0xd9, 0x15, 0x2c, 0x69, 0xaa, 0xe0}};
static char report[4096];
static uint64_t report_length;
static uint8_t memory_map[65536] __attribute__((aligned(16)));

static void append(const char *text)
{
    while (*text && report_length < sizeof report) report[report_length++] = *text++;
}
static void hex_field(const char *key, uint64_t value)
{
    static const char digits[] = "0123456789abcdef";
    append(key);
    append("=0x");
    for (int shift = 60; shift >= 0; shift -= 4) {
        char digit[2] = {digits[(value >> shift) & 15], 0};
        append(digit);
    }
    append("\n");
}
static int same_guid(const guid_t *left, const guid_t *right)
{
    const uint8_t *a = (const uint8_t *)left, *b = (const uint8_t *)right;
    for (unsigned i = 0; i < sizeof *left; i++) if (a[i] != b[i]) return 0;
    return 1;
}
#include "diagnostics.h"

static status_t write_file(handle_t image, system_table_t *system, const char16_t *path,
                          const void *contents, uint64_t length)
{
    loaded_image_t *loaded = 0;
    filesystem_t *filesystem = 0;
    file_protocol_t *root = 0, *file = 0;
    status_t result = system->boot->handle_protocol(image, &loaded_image_guid, (void **)&loaded);
    if (result || !loaded) return result ? result : 1;
    result = system->boot->handle_protocol(loaded->device, &filesystem_guid, (void **)&filesystem);
    if (result || !filesystem) return result ? result : 2;
    result = filesystem->open_volume(filesystem, &root);
    if (result || !root) return result ? result : 3;
    result = root->open(root, &file, path, 3, 0); /* Existing file, read + write only. */
    if (!result && file) {
        result = file->set_position(file, 0);
        uint64_t size = length;
        if (!result) result = file->write(file, &size, contents);
        if (!result && size != length) result = 4;
        if (!result) result = file->flush(file);
        status_t close_result = file->close(file);
        if (!result) result = close_result;
    }
    status_t close_result = root->close(root);
    return result ? result : close_result;
}
status_t efi_main(handle_t image, system_table_t *system)
{
    if (!system || !system->boot || !system->runtime) return 1;
    for (unsigned i = 0; i < sizeof report; i++) report[i] = ' ';
    append("DARWIN_EFI_PROBE_V1\nnonce=" PROBE_NONCE "\n");
    append("scope=uefi-payload-only-not-xnu\n");
    uint64_t current_el, frequency, memory_features;
    __asm__ volatile("mrs %0, CurrentEL" : "=r"(current_el));
    __asm__ volatile("mrs %0, CNTFRQ_EL0" : "=r"(frequency));
    __asm__ volatile("mrs %0, ID_AA64MMFR0_EL1" : "=r"(memory_features));
    hex_field("current_el", current_el >> 2);
    hex_field("counter_hz", frequency);
    hex_field("memory_features", memory_features);
    hex_field("efi_revision", system->header.revision);
    hex_field("firmware_revision", system->firmware_revision);
    hex_field("configuration_tables", system->table_count);
    unsigned has_acpi = 0, has_fdt = 0;
    if (system->table_count <= 128) {
        for (uint64_t i = 0; i < system->table_count; i++) {
            has_acpi |= same_guid(&system->tables[i].guid, &acpi2_guid);
            has_fdt |= same_guid(&system->tables[i].guid, &fdt_guid);
        }
    }
    hex_field("has_acpi2", has_acpi);
    hex_field("has_fdt", has_fdt);
    map_size = sizeof memory_map;
    uint64_t map_key = 0;
    map_result = system->boot->get_memory_map(
        &map_size, memory_map, &map_key, &descriptor_size, &descriptor_version);
    hex_field("memory_map_status", map_result);
    hex_field("memory_map_bytes", map_size);
    hex_field("memory_descriptor_size", descriptor_size);
    hex_field("memory_descriptor_version", descriptor_version);
    hex_field("memory_descriptor_count", !map_result && descriptor_size ? map_size / descriptor_size : 0);
    capture_diagnostics(system);
    static const char16_t diagnostic_path[] = {'\\', 'D', 'I', 'A', 'G', '.', 'B', 'I', 'N', 0};
    status_t diagnostic_result = write_file(image, system, diagnostic_path, diagnostics, sizeof diagnostics);
    hex_field("diagnostic_write_status", diagnostic_result);
    append("report_complete=1\nEND_DARWIN_EFI_PROBE_V1\n");
    static const char16_t report_path[] = {'\\', 'R', 'E', 'S', 'U', 'L', 'T', '.', 'T', 'X', 'T', 0};
    status_t result = write_file(image, system, report_path, report, sizeof report);
    if (!result) result = diagnostic_result;
    if (system->console_out && system->console_out->output) {
        static const char16_t success[] = {'E','F','I',' ','p','r','o','b','e',' ','r','e','p','o','r','t',' ','w','r','i','t','t','e','n','\r','\n',0};
        static const char16_t failed[] = {'E','F','I',' ','p','r','o','b','e',' ','w','r','i','t','e',' ','f','a','i','l','e','d','\r','\n',0};
        system->console_out->output(system->console_out, result ? failed : success);
    }
    system->runtime->reset_system(2, result, 0, 0); /* EfiResetShutdown. */
    return result ? result : 5; /* Returning means shutdown did not take effect. */
}
