# SPDX-License-Identifier: BSD-2-Clause
"""Distinct passive PE owner snapshots; no new guards, hardware or deadlines."""
from pathlib import Path
from tools.rpi5.rp1_bars_root_profile import once
ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'build/rpi5/rp1-bars-root-kernel-20261013-v2'
PE=ROOT/'build/rpi5/pcie-fw-client-kernel-20261013-final/pe_fiq.c'
HEADER=ROOT/'loader/rpi5/pcie_owner_trace.h'


def pm_source(text):
    text=once(text,'#include "../../loader/rpi5/pcie_watchdog_gate.h"',
        '#include "'+str(ROOT/'loader/rpi5/pcie_watchdog_gate.h')+'"')
    text=once(text,'static struct rpi5_pcie_watchdog_gate rpi5_pcie_wdog_gate;',
        '#include "'+str(HEADER)+'"\nstatic struct rpi5_pcie_owner_trace rpi5_owner_trace;\n'
        'static struct rpi5_pcie_watchdog_gate rpi5_pcie_wdog_gate;')
    return once(text,'''    if (!owner || ml_at_interrupt_context() ||
        !rpi5_pcie_watchdog_gate_owner(&rpi5_pcie_wdog_gate, owner)) return false;
    bool ok = rpi5_pcie_watchdog_check(&rpi5_pcie_wdog_lease) == 0;''', '''    rpi5_owner_trace.pm_stage=1;
    if (!owner) {rpi5_owner_trace.pm_stage=2;return false;}
    if (ml_at_interrupt_context()) {rpi5_owner_trace.pm_stage=3;return false;}
    if (!rpi5_pcie_watchdog_gate_owner(&rpi5_pcie_wdog_gate, owner)) {
        rpi5_owner_trace.pm_stage=4;return false;
    }
    rpi5_owner_trace.pm_stage=5;
    int rc=rpi5_pcie_watchdog_check(&rpi5_pcie_wdog_lease);
    rpi5_owner_trace.pm_rc=rc;rpi5_owner_trace.pm_stage=rc?6:7;
    bool ok = rc == 0;''')


def irq_source(text):
    return once(text,'''    if (!owner || !out || ml_at_interrupt_context() ||
        !rpi5_pcie_watchdog_gate_owner(&rpi5_pcie_irq_gate, owner)) return false;
    bool ok = false;
    if (current_thread() == rpi5_pcie_irq_thread) {
        struct rpi5_pcie_irq_observation result;
        ok = pe_rpi5_watchdog_check_pcie(owner) &&
            rpi5_pcie_irq_check(&rpi5_pcie_irq_session, &result) == 0 && pe_rpi5_watchdog_check_pcie(owner);
        if (ok) *out = result;
        else rpi5_pcie_irq_session.state = RPI5_PCIE_IRQ_QUARANTINED;
    }''', '''    rpi5_owner_trace.irq_stage=1;
    if (!owner || !out) {rpi5_owner_trace.irq_stage=2;return false;}
    if (ml_at_interrupt_context()) {rpi5_owner_trace.irq_stage=3;return false;}
    if (!rpi5_pcie_watchdog_gate_owner(&rpi5_pcie_irq_gate, owner)) {
        rpi5_owner_trace.irq_stage=4;return false;
    }
    bool ok = false;
    rpi5_owner_trace.irq_stage=5;
    if (current_thread() == rpi5_pcie_irq_thread) {
        struct rpi5_pcie_irq_observation result;
        rpi5_owner_trace.irq_stage=6;
        if (pe_rpi5_watchdog_check_pcie(owner)) {
            rpi5_owner_trace.irq_stage=7;
            int rc=rpi5_pcie_irq_check(&rpi5_pcie_irq_session, &result);
            rpi5_owner_trace.irq_rc=rc;
            if (!rc) {rpi5_owner_trace.irq_stage=8;ok=pe_rpi5_watchdog_check_pcie(owner);}
        }
        if (ok) {rpi5_owner_trace.irq_stage=9;*out = result;}
        else rpi5_pcie_irq_session.state = RPI5_PCIE_IRQ_QUARANTINED;
    }''')


def fw_source(text):
    text=once(text,'''    if(!raw || rpi5_pcie_fw_owner(context) ||
        !((fid==RPI5_FW_PCIE_QUERY && !token) ||
          ((fid==RPI5_FW_PCIE_CLAIM || fid==RPI5_FW_PCIE_CHECK) && token==(uintptr_t)rpi5_pcie_fw_identity)) ||
        !pe_rpi5_pcie_irq_check(rpi5_pcie_fw_identity,&irq))return -1;
    rpi5_pcie_fw_smccc(fid,token,raw);
    /* Real SMC may hang/abort, not return a synthetic I/O error. A returned
     * SMC_UNK/error is interpreted by the actual client, never as success. */
    return rpi5_pcie_fw_owner(context) || !pe_rpi5_pcie_irq_check(rpi5_pcie_fw_identity,&irq) ? -1:0;''', '''    rpi5_owner_trace.rpc_stage=1;rpi5_owner_trace.rpc_calls++;rpi5_owner_trace.rpc_fid=fid;
    for(unsigned i=0;i<4;i++)rpi5_owner_trace.rpc_raw[i]=0;
    if(!raw){rpi5_owner_trace.rpc_stage=2;return -1;}
    rpi5_owner_trace.rpc_stage=3;
    if(rpi5_pcie_fw_owner(context))return -1;
    rpi5_owner_trace.rpc_stage=4;
    if(!((fid==RPI5_FW_PCIE_QUERY && !token) ||
          ((fid==RPI5_FW_PCIE_CLAIM || fid==RPI5_FW_PCIE_CHECK) && token==(uintptr_t)rpi5_pcie_fw_identity)))return -1;
    rpi5_owner_trace.rpc_stage=5;
    if(!pe_rpi5_pcie_irq_check(rpi5_pcie_fw_identity,&irq))return -1;
    rpi5_owner_trace.rpc_stage=6;
    rpi5_pcie_fw_smccc(fid,token,raw);
    for(unsigned i=0;i<4;i++)rpi5_owner_trace.rpc_raw[i]=raw[i];
    rpi5_owner_trace.rpc_stage=7;
    if(rpi5_pcie_fw_owner(context))return -1;
    rpi5_owner_trace.rpc_stage=8;
    if(!pe_rpi5_pcie_irq_check(rpi5_pcie_fw_identity,&irq))return -1;
    rpi5_owner_trace.rpc_stage=9;return 0;''')
    text=once(text,'''    if(!owner || !out || ml_at_interrupt_context() || !rpi5_pcie_watchdog_gate_owner(&rpi5_pcie_fw_gate,owner))return false;
    bool ok=false;
    if(current_thread()==rpi5_pcie_fw_thread){
        struct rpi5_fw_observation result;
        ok=!rpi5_pcie_fw_client_check(&rpi5_pcie_fw_session,&result) && !rpi5_pcie_fw_owner(&rpi5_pcie_fw_gate);
        if(ok)*out=result;else rpi5_pcie_fw_session.state=RPI5_FW_CLIENT_QUARANTINED;
    }''', '''    rpi5_owner_trace.fw_stage=1;
    if(!owner || !out){rpi5_owner_trace.fw_stage=2;return false;}
    if(ml_at_interrupt_context()){rpi5_owner_trace.fw_stage=3;return false;}
    if(!rpi5_pcie_watchdog_gate_owner(&rpi5_pcie_fw_gate,owner)){
        rpi5_owner_trace.fw_stage=4;return false;
    }
    bool ok=false;rpi5_owner_trace.fw_stage=5;
    if(current_thread()==rpi5_pcie_fw_thread){
        struct rpi5_fw_observation result;
        rpi5_owner_trace.fw_stage=6;
        int rc=rpi5_pcie_fw_client_check(&rpi5_pcie_fw_session,&result);
        rpi5_owner_trace.fw_rc=rc;
        if(!rc){rpi5_owner_trace.fw_stage=7;ok=!rpi5_pcie_fw_owner(&rpi5_pcie_fw_gate);}
        if(ok){rpi5_owner_trace.fw_stage=8;*out=result;}
        else rpi5_pcie_fw_session.state=RPI5_FW_CLIENT_QUARANTINED;
    }''')
    return text+'''
int pe_rpi5_pcie_owner_trace(const void *owner,struct rpi5_pcie_owner_trace *out)
{
    /* Terminal caller only. No fresh check/access or mutation: snapshot the
     * already-owned thread's last operation, including quarantine state. */
    if(!owner || !out || owner!=rpi5_pcie_fw_identity ||
        current_thread()!=rpi5_pcie_fw_thread || ml_at_interrupt_context())return -1;
    struct rpi5_pcie_owner_trace result=rpi5_owner_trace;result.available=1;
    result.fw_state=rpi5_pcie_fw_session.state;result.fw_sequence=rpi5_pcie_fw_session.sequence;
    result.fw_frequency=rpi5_pcie_fw_session.frequency;result.fw_last=rpi5_pcie_fw_session.last_counter;
    result.fw_deadline=rpi5_pcie_fw_session.deadline;
    result.pm_state=rpi5_pcie_wdog_lease.state;result.pm_checks=rpi5_pcie_wdog_lease.checks;
    result.pm_callbacks=rpi5_pcie_wdog_lease.callbacks;result.pm_first=rpi5_pcie_wdog_lease.first_countdown;
    result.pm_count=rpi5_pcie_wdog_lease.last_countdown;result.pm_start=rpi5_pcie_wdog_lease.start;
    result.pm_last=rpi5_pcie_wdog_lease.last_counter;result.pm_deadline=rpi5_pcie_wdog_lease.deadline;
    result.irq_state=rpi5_pcie_irq_session.state;result.irq_callbacks=rpi5_pcie_irq_session.callbacks;
    *out=result;return 0;
}
'''


ROWS=(
 ('FW','AVAILABLE=%u STAGE=%u RC=%d STATE=%u SEQ=%u FREQ=%llu LAST=%llu DEADLINE=%llu',
  ('available','fw_stage','fw_rc','fw_state','fw_sequence','fw_frequency','fw_last','fw_deadline')),
 ('RPC','STAGE=%u CALLS=%u FID=%08x X0=%016llx X1=%016llx X2=%016llx X3=%016llx',
  ('rpc_stage','rpc_calls','rpc_fid','rpc_raw[0]','rpc_raw[1]','rpc_raw[2]','rpc_raw[3]')),
 ('PM','STAGE=%u RC=%d STATE=%u CHECKS=%u CALLBACKS=%u FIRST=%u COUNT=%u',
  ('pm_stage','pm_rc','pm_state','pm_checks','pm_callbacks','pm_first','pm_count')),
 ('TIME','START=%llu LAST=%llu DEADLINE=%llu',('pm_start','pm_last','pm_deadline')),
 ('IRQ','STAGE=%u RC=%d STATE=%u CALLBACKS=%u',('irq_stage','irq_rc','irq_state','irq_callbacks')))
FIELDS=ROWS[0][1]


def trace_calls():
    lines=[]
    for label,fmt,fields in ROWS:
        values=[]
        for field in fields:
            wide=field in ('fw_frequency','fw_last','fw_deadline','pm_start','pm_last','pm_deadline') or field.startswith('rpc_raw')
            values.append(('(unsigned long long)' if wide else '')+'owner_trace.'+field)
        lines.append('    kprintf("RPI5XNU:PCIEID:'+label+' '+fmt+'\\n",\n        '+',\n        '.join(values)+');')
    return '\n'.join(lines)+'\n'


def trial_source(text):
    text=once(text,'    /* Bounded scalar metadata: keep normal kprintf -> os_log enabled.',
        '    struct rpi5_pcie_owner_trace owner_trace={};\n'
        '    (void)pe_rpi5_pcie_owner_trace(transport,&owner_trace);\n'
        '    /* Bounded scalar metadata: keep normal kprintf -> os_log enabled.')
    return once(text,'    kprintf("RPI5XNU:PCIEID:END ',trace_calls()+'    kprintf("RPI5XNU:PCIEID:END ')


def emit(folder):
    folder.mkdir(exist_ok=False)
    for path in (BASE/'overlay').iterdir():
        if path.is_file():(folder/path.name).write_bytes(path.read_bytes())
    for name,fn in (('rpi5_pcie_watchdog_owner.inc',pm_source),('rpi5_pcie_irq_owner.inc',irq_source),
                    ('rpi5_pcie_fw_owner.inc',fw_source)):
        (folder/name).write_text(fn((ROOT/'pexpert/arm'/name).read_text()))
    source=PE.read_text()
    for name in ('rpi5_pcie_watchdog_owner.inc','rpi5_pcie_irq_owner.inc','rpi5_pcie_fw_owner.inc'):
        source=once(source,'#include <pexpert/arm/'+name+'>','#include "'+str(folder/name)+'"')
    (folder/'pe_fiq.c').write_text(source)
    cpp=folder/'BCM2712PCIePHYTransport.cpp'
    cpp.write_text('#include "'+str(HEADER)+'"\n'+cpp.read_text())
    trial=folder/'BCM2712PCIeIDTrialProgress.inc';trial.write_text(trial_source(trial.read_text()))
    return cpp,folder/'pe_fiq.c'
