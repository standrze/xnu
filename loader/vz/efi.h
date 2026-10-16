/* SPDX-License-Identifier: BSD-2-Clause
 * Minimal public UEFI AArch64 boot-services ABI for the source-built XNU loader.
 */
#ifndef DARWIN_VZ_EFI_H
#define DARWIN_VZ_EFI_H
#include <stddef.h>
#include <stdint.h>
typedef uint64_t efi_status;
typedef void *efi_handle;
struct efi_guid { uint32_t a; uint16_t b, c; uint8_t d[8]; };
struct efi_table_header { uint64_t signature; uint32_t revision, size, crc, reserved; };
struct efi_configuration_table { struct efi_guid guid; void *table; };
struct efi_text_output { void *reset; efi_status (*output)(void *, const uint16_t *); };
struct efi_memory_descriptor { uint32_t type, padding; uint64_t physical, virtual_address, pages, attributes; };
struct efi_boot_services {
    struct efi_table_header header;
    void *raise_tpl, *restore_tpl;
    efi_status (*allocate_pages)(uint32_t, uint32_t, uint64_t, uint64_t *);
    efi_status (*free_pages)(uint64_t, uint64_t);
    efi_status (*get_memory_map)(uint64_t *, void *, uint64_t *, uint64_t *, uint32_t *);
    void *allocate_pool, *free_pool;
    void *create_event, *set_timer, *wait_for_event, *signal_event, *close_event, *check_event;
    void *install_protocol, *reinstall_protocol, *uninstall_protocol;
    efi_status (*handle_protocol)(efi_handle, const struct efi_guid *, void **);
    void *reserved, *register_notify, *locate_handle, *locate_device_path, *install_configuration_table;
    void *load_image, *start_image, *exit, *unload_image;
    efi_status (*exit_boot_services)(efi_handle, uint64_t);
};
struct efi_runtime_services {
    struct efi_table_header header;
    void *before_reset[10];
    void (*reset_system)(uint32_t, efi_status, uint64_t, void *);
};
struct efi_system_table {
    struct efi_table_header header;
    uint16_t *firmware_vendor;
    uint32_t firmware_revision, padding;
    efi_handle console_in_handle; void *console_in;
    efi_handle console_out_handle; struct efi_text_output *console_out;
    efi_handle stderr_handle; struct efi_text_output *stderr_output;
    struct efi_runtime_services *runtime;
    struct efi_boot_services *boot;
    uint64_t table_count;
    struct efi_configuration_table *tables;
};
struct efi_loaded_image {
    uint32_t revision, padding;
    efi_handle parent;
    struct efi_system_table *system;
    efi_handle device;
    void *file_path, *reserved;
    uint32_t load_options_size, padding2;
    void *load_options, *image_base;
    uint64_t image_size;
};
_Static_assert(offsetof(struct efi_boot_services, allocate_pages) == 40, "AllocatePages ABI");
_Static_assert(offsetof(struct efi_boot_services, get_memory_map) == 56, "GetMemoryMap ABI");
_Static_assert(offsetof(struct efi_boot_services, exit_boot_services) == 232, "ExitBootServices ABI");
_Static_assert(offsetof(struct efi_system_table, boot) == 96, "SystemTable ABI");
_Static_assert(offsetof(struct efi_loaded_image, image_base) == 64, "LoadedImage ABI");
#endif
