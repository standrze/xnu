# SPDX-License-Identifier: BSD-2-Clause
"""Private elapsed-time settling and passive link-failure diagnostics.

No new MMIO, relaxed guard, widened timeout, retried operation or changed ABI.
The original train entry remains a wrapper with the original output contract.
"""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
FROZEN=ROOT/'build/rpi5/pcie-id-trace-kernel-20261013-checked/overlay'


def once(text,old,new):
    if text.count(old)!=1:raise ValueError('Exact link diagnostic source boundary changed: '+old[:80])
    return text.replace(old,new)


HEADER='''/* SPDX-License-Identifier: BSD-2-Clause */
#ifndef RPI5_PCIE_LINK_ELAPSED_TRACE_H
#define RPI5_PCIE_LINK_ELAPSED_TRACE_H
#include "pcie_link.h"
struct rpi5_pcie_link_elapsed_trace {
    unsigned step, poll_reads;
    uint64_t reset_start_us, reset_end_us, reset_wait_us, poll_elapsed_us;
};
int rpi5_pcie_link_train_elapsed_trace(struct rpi5_pcie_link *,
    struct rpi5_pcie_link_observation *, struct rpi5_pcie_link_elapsed_trace *);
#endif
'''

DELAY='''int BCM2712PCIePHYTransport::delayUS(void *p, uint32_t us)
{
    auto *self = static_cast<BCM2712PCIePHYTransport *>(p);
    if (!self->onOwnerThread()) return -1;
    if (!us) return self->fail();
    if (self->getPhase() == BCM2712_PHY_LINK_TRAINING) {
        if (!self->controllerMode || us > 100000) return self->fail();
        /* Include independent guard execution in the requested settling time.
         * An additive sum of IODelay chunks plus their guards can exceed the
         * unchanged link core's 110-ms ceiling even for a 100-ms request.
         * Every actual delay chunk remains <=1 ms and guarded on both sides.
         * No extra device access or guard bypass is introduced by clock reads. */
        if (!self->guard()) return -1;
        uint64_t absolute, start, last, now;
        clock_get_uptime(&absolute);
        absolutetime_to_nanoseconds(absolute, &start);
        last = start;
        const uint64_t wanted = static_cast<uint64_t>(us) * 1000;
        const unsigned limit = (us + 999) / 1000;
        for (unsigned count = 0; count < limit; count++) {
            if (!self->guard()) return -1;
            clock_get_uptime(&absolute);
            absolutetime_to_nanoseconds(absolute, &now);
            if (now < last) return self->fail();
            if (now - start >= wanted) return 0;
            last = now;
            uint64_t remaining = (wanted - (now - start) + 999) / 1000;
            uint32_t chunk = remaining > 1000 ? 1000 : static_cast<uint32_t>(remaining);
            IODelay(chunk);
            if (!self->guard()) return -1;
            clock_get_uptime(&absolute);
            absolutetime_to_nanoseconds(absolute, &now);
            if (now <= last) return self->fail(); /* Backward or stuck clock. */
            if (now - start >= wanted) return 0;
            last = now;
        }
        return self->fail(); /* Finite even if the clock under-reports time. */
    }
    if (us > 100) return self->fail();
    if (!self->guard()) return -1;
    IODelay(us);
    return self->guard() ? 0 : -1;
}
'''


def transport(text):
    start=text.index('int BCM2712PCIePHYTransport::delayUS(')
    end=text.index('bool BCM2712PCIePHYTransport::runInitialPHY(',start)
    return text[:start]+DELAY+text[end:]


def core(text):
    text=once(text,'#include "pcie_link.h"','#include "pcie_link_elapsed_trace.h"')
    text=once(text,'int rpi5_pcie_link_train(struct rpi5_pcie_link *session,\n'
        '    struct rpi5_pcie_link_observation *out)\n{',
        'int rpi5_pcie_link_train_elapsed_trace(struct rpi5_pcie_link *session,\n'
        '    struct rpi5_pcie_link_observation *out, struct rpi5_pcie_link_elapsed_trace *trace)\n{\n'
        '    struct rpi5_pcie_link_elapsed_trace local = {0};\n'
        '    if (!trace) trace = &local;\n    *trace = local;\n    trace->step = 1;')
    stages=(
        ('    STEP(session->io.check_lifecycle(io->context, 0));\n    READ(STATUS, result.status_before);',
         '    trace->step = 2;\n    STEP(session->io.check_lifecycle(io->context, 0));\n    READ(STATUS, result.status_before);'),
        ('    STEP(io->now_us(io->context, &start));\n    STEP(io->delay_us(io->context, RESET_WAIT));\n'
         '    STEP(io->now_us(io->context, &now));\n'
         '    if (now < start || now - start < RESET_WAIT)',
         '    trace->step = 3;\n    STEP(io->now_us(io->context, &start));\n'
         '    trace->reset_start_us = start;\n    trace->step = 4;\n'
         '    STEP(io->delay_us(io->context, RESET_WAIT));\n    trace->step = 5;\n'
         '    STEP(io->now_us(io->context, &now));\n    trace->reset_end_us = now;\n'
         '    if (now >= start) trace->reset_wait_us = now - start;\n    trace->step = 6;\n'
         '    if (now < start || now - start < RESET_WAIT)'),
        ('    STEP(session->io.check_lifecycle(io->context, 1));\n    STEP(io->now_us(io->context, &start));',
         '    trace->step = 7;\n    STEP(session->io.check_lifecycle(io->context, 1));\n'
         '    trace->step = 8;\n    STEP(io->now_us(io->context, &start));'),
        ('        READ(STATUS, result.status_up);\n        result.poll_reads++;\n        STEP(io->now_us(io->context, &now));',
         '        trace->step = 9;\n        READ(STATUS, result.status_up);\n'
         '        result.poll_reads++;\n        trace->poll_reads = result.poll_reads;\n'
         '        trace->step = 10;\n        STEP(io->now_us(io->context, &now));'),
        ('        result.poll_elapsed_us = now - start;',
         '        result.poll_elapsed_us = now - start;\n        trace->poll_elapsed_us = result.poll_elapsed_us;'),
        ('        STEP(io->delay_us(io->context, POLL_WAIT));\n        STEP(io->now_us(io->context, &now));',
         '        trace->step = 11;\n        STEP(io->delay_us(io->context, POLL_WAIT));\n'
         '        trace->step = 12;\n        STEP(io->now_us(io->context, &now));'),
        ('    READ16(LINK_STATUS, result.negotiated);','    trace->step = 13;\n    READ16(LINK_STATUS, result.negotiated);'),
        ('    session->state = RPI5_PCIE_LINK_COMPLETE;',
         '    session->state = RPI5_PCIE_LINK_COMPLETE;\n    trace->step = 14;'))
    for old,new in stages:text=once(text,old,new)
    return text+'''\nint rpi5_pcie_link_train(struct rpi5_pcie_link *session,
    struct rpi5_pcie_link_observation *out)
{
    return rpi5_pcie_link_train_elapsed_trace(session, out, 0);
}
'''


def header(text):
    text=once(text,'extern "C" {','extern "C" {\n#include "pcie_link_elapsed_trace.h"')
    text=once(text,'    unsigned diagUBUSStep=0; int diagUBUSRC=0;',
        '    unsigned diagUBUSStep=0; int diagUBUSRC=0;\n'
        '    struct rpi5_pcie_link_elapsed_trace diagLink = {};\n'
        '    unsigned diagLinkCall=0; int diagLinkRC=0;')
    return once(text,'    unsigned traceGuard() const { return diagGuard; }',
        '    unsigned traceLinkCall() const { return diagLinkCall; }\n'
        '    int traceLinkRC() const { return diagLinkRC; }\n'
        '    unsigned traceLinkCallbacks() const { return link.completed_callbacks; }\n'
        '    const struct rpi5_pcie_link_elapsed_trace &traceLink() const { return diagLink; }\n'
        '    unsigned traceGuard() const { return diagGuard; }')


def controller(text):
    return once(text,'    if (!guard() || rpi5_pcie_link_init(&link, &ubus, &windows, &linkIO) ||\n'
        '        rpi5_pcie_link_train(&link, &result.link) || !guard()) { fail(); return false; }',
        '    diagLinkCall=1;\n    if(!guard()){fail();return false;}\n'
        '    diagLinkCall=2;diagLinkRC=rpi5_pcie_link_init(&link,&ubus,&windows,&linkIO);\n'
        '    if(diagLinkRC){fail();return false;}\n'
        '    diagLinkCall=3;diagLinkRC=rpi5_pcie_link_train_elapsed_trace(&link,&result.link,&diagLink);\n'
        '    if(diagLinkRC){fail();return false;}\n'
        '    diagLinkCall=4;\n    if(!guard()){fail();return false;}\n    diagLinkCall=5;')


FIELDS='LINK_CALL=%u LINK_STEP=%u LINK_RC=%d LINK_CB=%u RESET_START_US=%llu RESET_END_US=%llu RESET_US=%llu POLL_READS=%u POLL_US=%llu'


def trial(text):
    text=once(text,'IO_STAGE=%u VALUE=%08x\\n','IO_STAGE=%u VALUE=%08x '+FIELDS+'\\n')
    return once(text,'        transport?transport->traceValue():0);',
        '        transport?transport->traceValue():0,\n'
        '        transport?transport->traceLinkCall():0,transport?transport->traceLink().step:0,\n'
        '        transport?transport->traceLinkRC():0,transport?transport->traceLinkCallbacks():0,\n'
        '        (unsigned long long)(transport?transport->traceLink().reset_start_us:0),\n'
        '        (unsigned long long)(transport?transport->traceLink().reset_end_us:0),\n'
        '        (unsigned long long)(transport?transport->traceLink().reset_wait_us:0),\n'
        '        transport?transport->traceLink().poll_reads:0,\n'
        '        (unsigned long long)(transport?transport->traceLink().poll_elapsed_us:0));')


def emit(folder):
    folder.mkdir(exist_ok=False)
    for p in FROZEN.iterdir():
        if p.is_file():(folder/p.name).write_bytes(p.read_bytes())
    for name,fn in (('BCM2712PCIePHYTransport.cpp',transport),('BCM2712PCIePHYTransport.h',header),
                    ('BCM2712PCIeControllerRun.inc',controller),('BCM2712PCIeIDTrialProgress.inc',trial)):
        target=folder/name;source=target if target.exists() else ROOT/'iokit/Kernel'/name
        target.write_text(fn(source.read_text()))
    (folder/'pcie_link_elapsed_trace.h').write_text(HEADER)
    path=folder/'pcie_link.c';path.write_text(core((ROOT/'loader/rpi5/pcie_link.c').read_text()))
    return folder/'BCM2712PCIePHYTransport.cpp',path
