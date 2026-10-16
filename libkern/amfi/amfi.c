#include <libkern/libkern.h>
#include <libkern/section_keywords.h>
#include <libkern/amfi/amfi.h>

SECURITY_READ_ONLY_LATE(const amfi_t*) amfi = NULL;
SECURITY_READ_ONLY_LATE(const CEKernelAPI_t*) libCoreEntitlements = NULL;

void
amfi_interface_register(const amfi_t *mfi)
{
	if (amfi) {
		panic("AppleMobileFileIntegrity interface already set");
	}
	amfi = mfi;
}

void
#if defined(ARM64_BOARD_CONFIG_BCM2712)
__attribute__((noreturn))
#endif
amfi_core_entitlements_register(const CEKernelAPI_t *implementation)
{
#if defined(ARM64_BOARD_CONFIG_BCM2712)
	(void)implementation;
	panic("CoreEntitlements V2 is unsupported on BCM2712 DEVELOPMENT");
#else
	if (libCoreEntitlements) {
		panic("libCoreEntitlements interface already set");
	}
	libCoreEntitlements = implementation;
#endif
}
