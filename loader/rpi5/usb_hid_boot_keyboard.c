/* SPDX-License-Identifier: BSD-2-Clause */
#include "usb_hid_boot_keyboard.h"

enum {
	RPI5_HID_MOD_LEFT_CONTROL = 1u << 0,
	RPI5_HID_MOD_LEFT_SHIFT = 1u << 1,
	RPI5_HID_MOD_RIGHT_CONTROL = 1u << 4,
	RPI5_HID_MOD_RIGHT_SHIFT = 1u << 5,
	RPI5_HID_USAGE_CAPS_LOCK = 0x39,
};

static int
contains(const uint8_t keys[RPI5_USB_HID_BOOT_KEYS], uint8_t usage)
{
	for (size_t i = 0; i < RPI5_USB_HID_BOOT_KEYS; i++) {
		if (keys[i] == usage) {
			return 1;
		}
	}
	return 0;
}

static int
append(uint8_t *buffer, size_t *length, size_t capacity,
	const uint8_t *bytes, size_t count)
{
	if (count > capacity - *length) {
		return -3;
	}
	for (size_t i = 0; i < count; i++) {
		buffer[(*length)++] = bytes[i];
	}
	return 0;
}

static int
translate(uint8_t usage, uint8_t modifiers, uint8_t caps_lock,
	uint8_t output[3], size_t *count)
{
	static const uint8_t plain_digits[] = "1234567890";
	static const uint8_t shift_digits[] = "!@#$%^&*()";
	static const uint8_t plain_punctuation[] = "-=[]\\#;'`,./";
	static const uint8_t shift_punctuation[] = "_+{}|~:\"~<>?";
	const int shift = (modifiers &
	    (RPI5_HID_MOD_LEFT_SHIFT | RPI5_HID_MOD_RIGHT_SHIFT)) != 0;
	const int control = (modifiers &
	    (RPI5_HID_MOD_LEFT_CONTROL | RPI5_HID_MOD_RIGHT_CONTROL)) != 0;

	*count = 0;
	if (usage >= 0x04 && usage <= 0x1d) {
		uint8_t letter = (uint8_t)('a' + usage - 0x04);
		if (control) {
			output[0] = (uint8_t)(letter - 'a' + 1);
		} else if (shift != !!caps_lock) {
			output[0] = (uint8_t)(letter - 'a' + 'A');
		} else {
			output[0] = letter;
		}
		*count = 1;
		return 0;
	}
	if (usage >= 0x1e && usage <= 0x27) {
		output[0] = shift ? shift_digits[usage - 0x1e] :
		    plain_digits[usage - 0x1e];
		*count = 1;
		return 0;
	}
	if (usage >= 0x2d && usage <= 0x38) {
		output[0] = shift ? shift_punctuation[usage - 0x2d] :
		    plain_punctuation[usage - 0x2d];
		*count = 1;
		return 0;
	}
	switch (usage) {
	case 0x28: output[0] = '\n'; *count = 1; break;
	case 0x29: output[0] = 0x1b; *count = 1; break;
	case 0x2a: output[0] = 0x7f; *count = 1; break;
	case 0x2b: output[0] = '\t'; *count = 1; break;
	case 0x2c: output[0] = ' '; *count = 1; break;
	case 0x4f: output[0] = 0x1b; output[1] = '['; output[2] = 'C'; *count = 3; break;
	case 0x50: output[0] = 0x1b; output[1] = '['; output[2] = 'D'; *count = 3; break;
	case 0x51: output[0] = 0x1b; output[1] = '['; output[2] = 'B'; *count = 3; break;
	case 0x52: output[0] = 0x1b; output[1] = '['; output[2] = 'A'; *count = 3; break;
	default: break;
	}
	return 0;
}

int
rpi5_usb_hid_boot_keyboard_report(struct rpi5_usb_hid_boot_keyboard *state,
	const uint8_t report[RPI5_USB_HID_BOOT_REPORT_BYTES], uint8_t *output,
	size_t output_capacity, size_t *output_count)
{
	if (state == NULL || report == NULL || output_count == NULL ||
	    (output == NULL && output_capacity != 0)) {
		return -1;
	}
	for (size_t i = 2; i < RPI5_USB_HID_BOOT_REPORT_BYTES; i++) {
		if (report[i] >= 1 && report[i] <= 3) {
			return -2;
		}
		if (report[i] != 0) {
			for (size_t j = i + 1; j < RPI5_USB_HID_BOOT_REPORT_BYTES; j++) {
				if (report[i] == report[j]) {
					return -2;
				}
			}
		}
	}

	uint8_t staged[RPI5_USB_HID_BOOT_MAX_OUTPUT];
	size_t staged_count = 0;
	uint8_t caps_lock = state->caps_lock;
	for (size_t i = 2; i < RPI5_USB_HID_BOOT_REPORT_BYTES; i++) {
		const uint8_t usage = report[i];
		if (usage == 0 || contains(state->keys, usage)) {
			continue;
		}
		if (usage == RPI5_HID_USAGE_CAPS_LOCK) {
			caps_lock ^= 1;
			continue;
		}
		uint8_t bytes[3];
		size_t count;
		translate(usage, report[0], caps_lock, bytes, &count);
		if (append(staged, &staged_count, sizeof(staged), bytes, count) != 0) {
			return -3;
		}
	}
	if (staged_count > output_capacity) {
		return -3;
	}
	for (size_t i = 0; i < staged_count; i++) {
		output[i] = staged[i];
	}
	state->modifiers = report[0];
	for (size_t i = 0; i < RPI5_USB_HID_BOOT_KEYS; i++) {
		state->keys[i] = report[i + 2];
	}
	state->caps_lock = caps_lock;
	*output_count = staged_count;
	return 0;
}
