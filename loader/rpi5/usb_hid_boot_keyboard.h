/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_USB_HID_BOOT_KEYBOARD_H
#define RPI5_USB_HID_BOOT_KEYBOARD_H

#include <stddef.h>
#include <stdint.h>

#define RPI5_USB_HID_BOOT_REPORT_BYTES 8u
#define RPI5_USB_HID_BOOT_KEYS 6u
#define RPI5_USB_HID_BOOT_MAX_OUTPUT (RPI5_USB_HID_BOOT_KEYS * 3u)

#ifdef __cplusplus
extern "C" {
#endif

struct rpi5_usb_hid_boot_keyboard {
	uint8_t modifiers;
	uint8_t keys[RPI5_USB_HID_BOOT_KEYS];
	uint8_t caps_lock;
};

/*
 * Convert one USB HID boot-protocol keyboard report to terminal bytes.
 *
 * Only newly pressed keys emit bytes.  Releases and modifier-only reports are
 * silent.  The US boot-keyboard layout covers printable ASCII, control-letter
 * combinations and the four ANSI cursor sequences.  Unknown usages are
 * ignored.  Rollover/error reports and malformed duplicate usages are rejected
 * without changing state or output.
 *
 * The caller owns all storage.  State is committed only when the entire result
 * fits in output.  On success, *output_count is the number of emitted bytes.
 */
int rpi5_usb_hid_boot_keyboard_report(
	struct rpi5_usb_hid_boot_keyboard *state,
	const uint8_t report[RPI5_USB_HID_BOOT_REPORT_BYTES],
	uint8_t *output,
	size_t output_capacity,
	size_t *output_count);

#ifdef __cplusplus
}
#endif

#endif
