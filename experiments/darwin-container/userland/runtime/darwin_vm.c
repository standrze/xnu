/* SPDX-License-Identifier: BSD-2-Clause
 * Project-specific own-task VM adapters for the static Apple allocator.
 * This is deliberately not an implementation of remote Mach VM RPC.
 * Unsupported tasks/maximum-protection changes fail rather than pretend.
 */
#include <mach/mach.h>
#include <sys/mman.h>
#include <string.h>
#include <stdint.h>

kern_return_t vm_allocate(vm_map_t task, vm_address_t *address,
                          vm_size_t size, int flags)
{
    if (task != mach_task_self_ || !address) return KERN_INVALID_ARGUMENT;
    if (size > UINTPTR_MAX - 16383) return KERN_NO_SPACE;
    size = (size + 16383) & ~(vm_size_t)16383;
    if (!size) { *address = 0; return KERN_SUCCESS; }
    int anywhere = flags & VM_FLAGS_ANYWHERE;
    if (!anywhere && (*address & 16383)) return KERN_INVALID_ADDRESS;
    void *hint = anywhere ? NULL : (void *)(uintptr_t)*address;
    /* Allocator memory tags in high flag bits are diagnostic hints. Do not
     * use MAP_FIXED: Mach allocation must not replace an existing mapping. */
    void *result = mmap(hint, size, PROT_READ | PROT_WRITE,
                        MAP_PRIVATE | MAP_ANON, -1, 0);
    if (result == MAP_FAILED) return KERN_NO_SPACE;
    if (!anywhere && result != hint) {
        munmap(result, size);
        return KERN_NO_SPACE;
    }
    *address = (vm_address_t)(uintptr_t)result;
    return KERN_SUCCESS;
}

kern_return_t vm_deallocate(vm_map_t task, vm_address_t address, vm_size_t size)
{
    if (task != mach_task_self_) return KERN_INVALID_ARGUMENT;
    if (!size) return KERN_SUCCESS;
    return munmap((void *)(uintptr_t)address, size) == 0
        ? KERN_SUCCESS : KERN_INVALID_ADDRESS;
}

kern_return_t vm_protect(vm_map_t task, vm_address_t address, vm_size_t size,
                         boolean_t set_maximum, vm_prot_t protection)
{
    if (task != mach_task_self_) return KERN_INVALID_ARGUMENT;
    if (set_maximum) return KERN_NOT_SUPPORTED;
    return mprotect((void *)(uintptr_t)address, size, protection) == 0
        ? KERN_SUCCESS : KERN_PROTECTION_FAILURE;
}

kern_return_t vm_copy(vm_map_t task, vm_address_t source, vm_size_t size,
                      vm_address_t destination)
{
    if (task != mach_task_self_) return KERN_INVALID_ARGUMENT;
    memmove((void *)(uintptr_t)destination, (void *)(uintptr_t)source, size);
    return KERN_SUCCESS;
}
