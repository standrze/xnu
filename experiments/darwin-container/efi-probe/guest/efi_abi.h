/* SPDX-License-Identifier: BSD-2-Clause
 * Original minimal declarations of the public UEFI 2.10 AArch64 ABI.
 * Names/layouts follow UEFI specification chapters 4, 7, 8, 9 and 13.
 * No Apple or EDK II implementation source is copied here.
 */
#ifndef PROBE_EFI_ABI_H
#define PROBE_EFI_ABI_H
#include <stddef.h>
#include <stdint.h>

typedef uint64_t status_t;
typedef void *handle_t;
typedef uint16_t char16_t;
typedef struct { uint32_t a; uint16_t b, c; uint8_t d[8]; } guid_t;
typedef struct { uint64_t signature; uint32_t revision, size, crc, reserved; } table_header_t;
typedef struct { guid_t guid; void *table; } config_table_t;
typedef struct { void *reset; status_t (*output)(void *, const char16_t *); } text_output_t;
typedef struct {
    table_header_t header;
    void *before_reset[10];
    void (*reset_system)(uint32_t, status_t, uint64_t, void *);
} runtime_services_t;
typedef struct {
    table_header_t header;
    void *before_map[4];
    status_t (*get_memory_map)(uint64_t *, void *, uint64_t *, uint64_t *, uint32_t *);
    void *before_handle_protocol[11];
    status_t (*handle_protocol)(handle_t, const guid_t *, void **);
    void *reserved;
    void *register_protocol_notify;
    status_t (*locate_handle)(uint32_t, const guid_t *, void *, uint64_t *, handle_t *);
} boot_services_t;
typedef struct {
    table_header_t header;
    char16_t *firmware_vendor;
    uint32_t firmware_revision;
    uint32_t padding;
    handle_t console_in_handle;
    void *console_in;
    handle_t console_out_handle;
    text_output_t *console_out;
    handle_t stderr_handle;
    text_output_t *stderr_output;
    runtime_services_t *runtime;
    boot_services_t *boot;
    uint64_t table_count;
    config_table_t *tables;
} system_table_t;
typedef struct {
    uint32_t revision;
    uint32_t padding;
    handle_t parent;
    system_table_t *system;
    handle_t device;
} loaded_image_t;
typedef struct file_protocol file_protocol_t;
struct file_protocol {
    uint64_t revision;
    status_t (*open)(file_protocol_t *, file_protocol_t **, const char16_t *, uint64_t, uint64_t);
    status_t (*close)(file_protocol_t *);
    void *delete_file;
    void *read;
    status_t (*write)(file_protocol_t *, uint64_t *, const void *);
    void *get_position;
    status_t (*set_position)(file_protocol_t *, uint64_t);
    void *get_info;
    void *set_info;
    status_t (*flush)(file_protocol_t *);
};
typedef struct {
    uint64_t revision;
    status_t (*open_volume)(void *, file_protocol_t **);
} filesystem_t;
typedef struct serial_io serial_io_t;
struct serial_io {
    uint32_t revision, padding;
    void *reset;
    void *set_attributes;
    void *set_control;
    void *get_control;
    status_t (*write)(serial_io_t *, uint64_t *, const void *);
    void *read;
    void *mode;
};
typedef struct pci_io pci_io_t;
struct pci_io {
    void *before_pci_read[6];
    status_t (*pci_read)(pci_io_t *, uint32_t, uint32_t, uint64_t, void *);
    void *before_location[7];
    status_t (*get_location)(pci_io_t *, uint64_t *, uint64_t *, uint64_t *, uint64_t *);
};

_Static_assert(offsetof(system_table_t, boot) == 96, "UEFI system table ABI");
_Static_assert(offsetof(boot_services_t, handle_protocol) == 152, "UEFI boot services ABI");
_Static_assert(offsetof(boot_services_t, locate_handle) == 176, "UEFI locate handle ABI");
_Static_assert(offsetof(runtime_services_t, reset_system) == 104, "UEFI reset ABI");
_Static_assert(offsetof(file_protocol_t, flush) == 80, "UEFI file ABI");
_Static_assert(offsetof(serial_io_t, write) == 40, "UEFI Serial I/O ABI");
_Static_assert(offsetof(pci_io_t, pci_read) == 48, "UEFI PCI config read ABI");
_Static_assert(offsetof(pci_io_t, get_location) == 112, "UEFI PCI location ABI");
#endif
