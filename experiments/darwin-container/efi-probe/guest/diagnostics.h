/* SPDX-License-Identifier: BSD-2-Clause
 * Original bounded snapshot of public UEFI/ACPI data, not a hardware driver.
 * Included after probe.c's report helpers and memory-map storage.
 */
#define DIAGNOSTIC_BYTES (256 * 1024)
static uint8_t diagnostics[DIAGNOSTIC_BYTES];
static uint32_t diagnostic_used = 64, diagnostic_count, diagnostic_errors;
static uint64_t map_size, descriptor_size;
static uint32_t descriptor_version;
static status_t map_result;
static const guid_t serial_guid = {0xbb25cf6f, 0xf1d4, 0x11d2,
    {0x9a, 0x0c, 0x00, 0x90, 0x27, 0x3f, 0xc1, 0xfd}};
static const guid_t device_path_guid = {0x09576e91, 0x6d3f, 0x11d2,
    {0x8e, 0x39, 0x00, 0xa0, 0xc9, 0x69, 0x72, 0x3b}};
static const guid_t pci_guid = {0x4cf5b200, 0x68b8, 0x4ca5,
    {0x9e, 0xec, 0xb2, 0x3e, 0x3f, 0x50, 0x02, 0x9a}};

static uint64_t little(const uint8_t *bytes, unsigned count)
{
    uint64_t value = 0;
    for (unsigned i = 0; i < count; i++) value |= (uint64_t)bytes[i] << (8 * i);
    return value;
}
static void store_little(uint8_t *bytes, uint64_t value, unsigned count)
{
    for (unsigned i = 0; i < count; i++) bytes[i] = (uint8_t)(value >> (8 * i));
}
static void copy_bytes(void *destination, const void *source, uint64_t length)
{
    uint8_t *out = destination;
    const uint8_t *in = source;
    for (uint64_t i = 0; i < length; i++) out[i] = in[i];
}
static void record(uint32_t kind, uint32_t index, const void *bytes, uint32_t count)
{
    if (count > DIAGNOSTIC_BYTES - 16 || diagnostic_used > DIAGNOSTIC_BYTES - 16 - count) {
        diagnostic_errors++;
        return;
    }
    store_little(diagnostics + diagnostic_used, kind, 4);
    store_little(diagnostics + diagnostic_used + 4, index, 4);
    store_little(diagnostics + diagnostic_used + 8, count, 4);
    copy_bytes(diagnostics + diagnostic_used + 16, bytes, count);
    diagnostic_used += 16 + count;
    diagnostic_count++;
}
/* ACPI pointers must fit wholly in one EFI RAM descriptor. Never read MMIO. */
static int readable(const void *pointer, uint64_t length)
{
    uint64_t address = (uint64_t)(uintptr_t)pointer;
    if (map_result || descriptor_size < 40 || !length || address + length < address) return 0;
    for (uint64_t offset = 0; offset + descriptor_size <= map_size; offset += descriptor_size) {
        uint8_t *descriptor = memory_map + offset;
        uint32_t type = (uint32_t)little(descriptor, 4);
        uint64_t base = little(descriptor + 8, 8), pages = little(descriptor + 24, 8);
        if (type > 10 || type == 8 || pages > UINT64_MAX / 4096) continue;
        uint64_t bytes = pages * 4096;
        if (base + bytes < base) continue;
        if (address >= base && address + length <= base + bytes) return 1;
    }
    return 0;
}
static int signature(const uint8_t *table, const char *expected, unsigned length)
{
    for (unsigned i = 0; i < length; i++) if (table[i] != (uint8_t)expected[i]) return 0;
    return 1;
}
static int checksum(const uint8_t *bytes, unsigned length)
{
    uint8_t sum = 0;
    for (unsigned i = 0; i < length; i++) sum += bytes[i];
    return sum == 0;
}
static uint32_t capture_table(const uint8_t *table, uint32_t index)
{
    if (!readable(table, 36)) { diagnostic_errors++; return 0; }
    uint32_t length = (uint32_t)little(table + 4, 4);
    if (length < 36 || length > 65536 || !readable(table, length) || !checksum(table, length)) {
        diagnostic_errors++;
        return 0;
    }
    record(2, index, table, length);
    return length;
}
static void capture_acpi(const uint8_t *rsdp)
{
    if (!readable(rsdp, 36) || !signature(rsdp, "RSD PTR ", 8) || rsdp[15] < 2 ||
        little(rsdp + 20, 4) != 36 || !checksum(rsdp, 20) || !checksum(rsdp, 36)) {
        diagnostic_errors++;
        return;
    }
    record(1, 0, rsdp, 36);
    const uint8_t *xsdt = (const uint8_t *)(uintptr_t)little(rsdp + 24, 8);
    uint32_t length = capture_table(xsdt, 0);
    if (!length || !signature(xsdt, "XSDT", 4) || (length - 36) % 8) {
        diagnostic_errors++;
        return;
    }
    uint32_t entries = (length - 36) / 8;
    if (entries > 64) { diagnostic_errors++; return; }
    for (uint32_t i = 0; i < entries; i++) {
        const uint8_t *table = (const uint8_t *)(uintptr_t)little(xsdt + 36 + i * 8, 8);
        uint32_t table_length = capture_table(table, i + 1);
        if (table_length >= 44 && signature(table, "FACP", 4)) {
            uint64_t dsdt = table_length >= 148 ? little(table + 140, 8) : 0;
            if (!dsdt) dsdt = little(table + 40, 4);
            if (dsdt) capture_table((const uint8_t *)(uintptr_t)dsdt, 0x10000 + i);
        }
    }
}
static void indexed_field(const char *prefix, unsigned index, const char *name, uint64_t value)
{
    char key[80];
    unsigned length = 0;
    while (*prefix && length < 60) key[length++] = *prefix++;
    key[length++] = '0' + (index / 10) % 10;
    key[length++] = '0' + index % 10;
    key[length++] = '_';
    while (*name && length < sizeof key - 1) key[length++] = *name++;
    key[length] = 0;
    hex_field(key, value);
}
static void capture_serial(system_table_t *system)
{
    handle_t handles[16];
    uint64_t bytes = sizeof handles;
    status_t status = system->boot->locate_handle(2, &serial_guid, 0, &bytes, handles);
    hex_field("serial_locate_status", status);
    hex_field("serial_handle_count", !status ? bytes / sizeof(handle_t) : 0);
    if (status || bytes > sizeof handles || bytes % sizeof(handle_t)) return;
    for (unsigned i = 0; i < bytes / sizeof(handle_t); i++) {
        serial_io_t *serial = 0;
        status = system->boot->handle_protocol(handles[i], &serial_guid, (void **)&serial);
        indexed_field("serial", i, "protocol_status", status);
        if (status || !serial) continue;
        uint8_t *path = 0;
        status = system->boot->handle_protocol(handles[i], &device_path_guid, (void **)&path);
        indexed_field("serial", i, "path_status", status);
        if (!status && path) {
            uint32_t length = 0;
            while (length + 4 <= 1024 && readable(path + length, 4)) {
                uint32_t node_length = (uint32_t)little(path + length + 2, 2);
                if (node_length < 4 || length + node_length > 1024 || !readable(path + length, node_length)) break;
                uint8_t end = path[length] == 0x7F && path[length + 1] == 0xFF;
                length += node_length;
                if (end) { record(4, i, path, length); break; }
            }
        }
        static const char marker[] = "EFI_SERIAL_PROBE nonce=" PROBE_NONCE "\r\n";
        uint64_t count = sizeof marker - 1;
        status = serial->write(serial, &count, marker);
        indexed_field("serial", i, "write_status", status);
        indexed_field("serial", i, "written_bytes", count);
    }
}
static void capture_pci(system_table_t *system)
{
    handle_t handles[32];
    uint64_t bytes = sizeof handles;
    status_t status = system->boot->locate_handle(2, &pci_guid, 0, &bytes, handles);
    hex_field("pci_locate_status", status);
    hex_field("pci_handle_count", !status ? bytes / sizeof(handle_t) : 0);
    if (status || bytes > sizeof handles || bytes % sizeof(handle_t)) return;
    for (unsigned i = 0; i < bytes / sizeof(handle_t); i++) {
        pci_io_t *pci = 0;
        status = system->boot->handle_protocol(handles[i], &pci_guid, (void **)&pci);
        if (status || !pci) { diagnostic_errors++; continue; }
        uint64_t location[4] = {0};
        uint8_t configuration[288] __attribute__((aligned(8))) = {0};
        status = pci->get_location(pci, &location[0], &location[1], &location[2], &location[3]);
        if (!status) status = pci->pci_read(pci, 2, 0, 64, configuration + 32);
        if (status) { diagnostic_errors++; continue; }
        for (unsigned n = 0; n < 4; n++) store_little(configuration + n * 8, location[n], 8);
        record(5, i, configuration, sizeof configuration);
    }
}
static void capture_diagnostics(system_table_t *system)
{
    copy_bytes(diagnostics, "EFIDIAG2", 8);
    store_little(diagnostics + 8, 2, 4);
    copy_bytes(diagnostics + 16, PROBE_NONCE, 32);
    if (!map_result && map_size <= sizeof memory_map) record(3, 0, memory_map, (uint32_t)map_size);
    if (system->table_count <= 128) {
        for (uint64_t i = 0; i < system->table_count; i++) {
            if (same_guid(&system->tables[i].guid, &acpi2_guid)) capture_acpi(system->tables[i].table);
        }
    }
    capture_serial(system);
    capture_pci(system);
    store_little(diagnostics + 12, diagnostic_used, 4);
    store_little(diagnostics + 48, diagnostic_count, 4);
    store_little(diagnostics + 52, diagnostic_errors == 0, 4);
    hex_field("diagnostic_bytes_used", diagnostic_used);
    hex_field("diagnostic_records", diagnostic_count);
    hex_field("diagnostic_errors", diagnostic_errors);
}
