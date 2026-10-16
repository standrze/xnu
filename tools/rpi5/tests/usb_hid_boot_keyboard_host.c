/* SPDX-License-Identifier: BSD-2-Clause */
#include "usb_hid_boot_keyboard.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

static size_t
report(struct rpi5_usb_hid_boot_keyboard *keyboard, uint8_t modifiers,
	uint8_t key, uint8_t *output)
{
	uint8_t bytes[8] = { modifiers, 0, key };
	size_t count = 99;
	assert(rpi5_usb_hid_boot_keyboard_report(keyboard, bytes, output,
	    RPI5_USB_HID_BOOT_MAX_OUTPUT, &count) == 0);
	return count;
}

static void
release(struct rpi5_usb_hid_boot_keyboard *keyboard)
{
	uint8_t bytes[8] = { 0 };
	uint8_t output[18];
	size_t count = 99;
	assert(rpi5_usb_hid_boot_keyboard_report(keyboard, bytes, output,
	    sizeof(output), &count) == 0 && count == 0);
}

int
main(void)
{
	struct rpi5_usb_hid_boot_keyboard keyboard = { 0 };
	uint8_t output[18];
	size_t count;

	assert(report(&keyboard, 0, 0x0b, output) == 1 && output[0] == 'h');
	assert(report(&keyboard, 0, 0x0b, output) == 0);
	release(&keyboard);
	assert(report(&keyboard, 0x02, 0x0c, output) == 1 && output[0] == 'I');
	release(&keyboard);
	assert(report(&keyboard, 0, 0x28, output) == 1 && output[0] == '\n');
	release(&keyboard);

	assert(report(&keyboard, 0, 0x39, output) == 0 && keyboard.caps_lock == 1);
	release(&keyboard);
	assert(report(&keyboard, 0, 0x1d, output) == 1 && output[0] == 'Z');
	release(&keyboard);
	assert(report(&keyboard, 0x02, 0x1d, output) == 1 && output[0] == 'z');
	release(&keyboard);
	assert(report(&keyboard, 0x01, 0x06, output) == 1 && output[0] == 3);
	release(&keyboard);

	assert(report(&keyboard, 0x02, 0x1f, output) == 1 && output[0] == '@');
	release(&keyboard);
	assert(report(&keyboard, 0, 0x33, output) == 1 && output[0] == ';');
	release(&keyboard);
	assert(report(&keyboard, 0, 0x38, output) == 1 && output[0] == '/');
	release(&keyboard);
	assert(report(&keyboard, 0, 0x4f, output) == 3 &&
	    memcmp(output, "\033[C", 3) == 0);
	release(&keyboard);

	uint8_t chord[8] = { 0, 0, 0x04, 0x05, 0x06 };
	assert(rpi5_usb_hid_boot_keyboard_report(&keyboard, chord, output,
	    sizeof(output), &count) == 0 && count == 3 &&
	    memcmp(output, "ABC", 3) == 0);
	struct rpi5_usb_hid_boot_keyboard before = keyboard;
	uint8_t rollover[8] = { 0, 0, 1 };
	memset(output, 0xa5, sizeof(output)); count = 77;
	assert(rpi5_usb_hid_boot_keyboard_report(&keyboard, rollover, output,
	    sizeof(output), &count) == -2);
	assert(memcmp(&before, &keyboard, sizeof(before)) == 0 && count == 77 &&
	    output[0] == 0xa5);
	uint8_t duplicate[8] = { 0, 0, 4, 4 };
	assert(rpi5_usb_hid_boot_keyboard_report(&keyboard, duplicate, output,
	    sizeof(output), &count) == -2);

	release(&keyboard);
	uint8_t arrows[8] = { 0, 0, 0x4f, 0x50, 0x51, 0x52 };
	assert(rpi5_usb_hid_boot_keyboard_report(&keyboard, arrows, output,
	    11, &count) == -3);
	assert(keyboard.keys[0] == 0);
	assert(rpi5_usb_hid_boot_keyboard_report(&keyboard, arrows, output,
	    sizeof(output), &count) == 0 && count == 12);
	assert(memcmp(output, "\033[C\033[D\033[B\033[A", 12) == 0);

	printf("USB_HID_BOOT_KEYBOARD_PASS ASCII=1 CONTROL=1 CAPS=1 ANSI=1 ATOMIC=1 NO_HARDWARE=1\n");
	return 0;
}
