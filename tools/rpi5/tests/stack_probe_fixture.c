/* SPDX-License-Identifier: BSD-2-Clause
 * Compiler ABI fixture only. Not linked into the kernel.
 */
extern void consume_stack_buffer(void *, unsigned long);

__attribute__((noinline)) void
rpi5_probe_fixture(unsigned long size)
{
	if (size == 0) {
		return;
	}
	char buffer[size];
	buffer[0] = 1;
	consume_stack_buffer(buffer, size);
}
