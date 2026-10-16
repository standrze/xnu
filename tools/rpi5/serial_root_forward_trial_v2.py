#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-2-Clause
"""Exact receive-only body with explicit pre-ARM Probe modem assertion."""
import fcntl
import inspect
from pathlib import Path
import struct
import sys
import termios
sys.path.insert(0,str(Path(__file__).resolve().parent))
import root_forward_trial_v2 as stage
import serial_link_trial_v2 as original
bound_sources=stage.private(original.bound_sources,stage=stage,__name__=__name__)
revalidate=stage.private(original.revalidate,stage=stage,bound_sources=bound_sources)
base_bindings=stage.private(original.bindings,stage=stage,revalidate=revalidate,__file__=__file__,__doc__=__doc__)


def assert_modem_ready(fd):
    # This controls USB CDC modem state, not UART payload or RX qualification.
    required=termios.TIOCM_DTR|termios.TIOCM_RTS
    fcntl.ioctl(fd,termios.TIOCMBIS,struct.pack('=I',required))
    actual=struct.unpack('=I',fcntl.ioctl(fd,termios.TIOCMGET,struct.pack('=I',0)))[0]
    if actual&required!=required:raise ValueError('DTR and RTS must be asserted before ARMED; RX remains unqualified')


def bindings(context):
    bound=base_bindings(context)
    source=inspect.getsource(original.original.main)
    old='            termios.tcsetattr(fd,termios.TCSANOW,config);termios.tcflush(fd,termios.TCIFLUSH)'
    new='            termios.tcsetattr(fd,termios.TCSANOW,config)\n            assert_modem_ready(fd)\n            termios.tcflush(fd,termios.TCIFLUSH)'
    if source.count(old)!=1:raise ValueError('Exact frozen receive-only termios boundary changed')
    namespace=dict(bound.__globals__,assert_modem_ready=assert_modem_ready)
    exec(compile(source.replace(old,new),__file__,'exec'),namespace)
    return namespace['main']
main=stage.private(original.main,stage=stage,bindings=bindings,__doc__=__doc__)
if __name__=='__main__':raise SystemExit(main())
