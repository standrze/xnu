# SPDX-License-Identifier: BSD-2-Clause
"""Exact, offline-only Apple serial dispatch overlay; original sources unchanged."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'osfmk/console/serial_console.c'
HEADER = ROOT / 'loader/rpi5/console_mirror.h'
ANCHOR = 'SECURITY_READ_ONLY_EARLY(struct console_ops) cons_ops[] = {'
WRAPPER = '''/* Project-owned optional mirror. No caller enables it in this candidate. */
#include "HEADER_PATH"
static unsigned rpi5_console_mirror_state;
bool
rpi5_console_mirror_publish(void)
{
    unsigned expected = 0;
    return __atomic_compare_exchange_n(&rpi5_console_mirror_state, &expected, 1,
        false, __ATOMIC_RELEASE, __ATOMIC_RELAXED);
}
void
rpi5_console_mirror_revoke(void)
{
    __atomic_store_n(&rpi5_console_mirror_state, 2, __ATOMIC_RELEASE);
}
static void
rpi5_console_mirror_putc(char c, bool poll)
{
    serial_putc_options(c, poll);
    if (!poll && __atomic_load_n(&rpi5_console_mirror_state, __ATOMIC_ACQUIRE) == 1) {
        vcputc_options(c, false);
    }
}

'''.replace('HEADER_PATH', str(HEADER))


def overlay(text):
    old = '.putc = serial_putc_options, .getc = _serial_getc,'
    if text.count(ANCHOR) != 1 or text.count(old) != 1:
        raise ValueError('Original Apple serial console dispatch boundary changed')
    return text.replace(ANCHOR, WRAPPER + ANCHOR).replace(
        old, '.putc = rpi5_console_mirror_putc, .getc = _serial_getc,')


def original_body(text, signature):
    """Extract one exact C function, retaining its body, not a rewritten oracle.

    These specific pinned functions have no braces in comments/string literals.
    Reject ambiguous signatures; the complete original files are closure inputs.
    """
    if text.count(signature) != 1:
        raise ValueError('Ambiguous original function: ' + signature)
    start = text.index(signature)
    brace = text.index('{', start)
    depth = 1
    end = brace + 1
    while depth:
        if end >= len(text): raise ValueError('Truncated original function')
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end] + '\n'
