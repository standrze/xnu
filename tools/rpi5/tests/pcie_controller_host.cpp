/* SPDX-License-Identifier: BSD-2-Clause */
/* Actual production run/lifecycle methods and real C cores, modeled owner/
 * register callbacks. This does NOT execute IOKit or prove hardware admission. */
#include "BCM2712PCIeControllerPolicy.h"
extern "C" {
#include "pcie_clock.h"
#include "pcie_unused.h"
#include "pcie_watchdog_lease.h"
}
#include <cassert>
#include <cstdio>
#include <cstring>
class BCM2712PCIePHYTransport;
class IOService { public: BCM2712PCIePHYTransport *transport; bool opened = true;
    bool isOpen(const void *) const { return opened; }
};
struct bcm2712_phy_observation {
    rpi5_pcie_watchdog_observation watchdog; rpi5_pcie_reset_observation reset;
    rpi5_pcie_rescal_observation calibration; rpi5_pcie_serdes_observation serdes;
};
struct bcm2712_ubus_observation { bcm2712_phy_observation phy; rpi5_pcie_ubus_observation ubus; };
struct bcm2712_unused_observation { bcm2712_ubus_observation ubus; rpi5_pcie_unused_observation unused; };
struct bcm2712_qos_observation { bcm2712_unused_observation prior; rpi5_pcie_profile profile; rpi5_pcie_qos_observation qos; };
struct bcm2712_clock_observation { bcm2712_qos_observation prior; rpi5_pcie_clock_pre_observation clock; };
struct bcm2712_controller_admission { int (*check)(IOService *, unsigned); };
struct bcm2712_controller_observation {
    bcm2712_clock_observation prior; rpi5_pcie_rc_observation rc;
    rpi5_pcie_link_observation link; rpi5_pcie_clock_post_observation clock; uint32_t fresh_unused_checks;
};
class BCM2712PCIePHYTransport {
public:
    IOService provider = {this}; IOService *ownerProvider = &provider;
    rpi5_pcie_fdt binding = {}; rpi5_pcie_reset reset = {}; rpi5_pcie_rescal calibration = {};
    rpi5_pcie_serdes serdes = {}; rpi5_pcie_ubus ubus = {}; rpi5_pcie_qos qos = {};
    rpi5_pcie_clock clockPolicy = {}; rpi5_pcie_windows windows = {}; rpi5_pcie_rc rc = {};
    rpi5_pcie_link link = {}; bcm2712_controller_admission controllerAdmission = {};
    unsigned phase = BCM2712_PHY_PREPARED, lifecyclePhase = BCM2712_CONTROLLER_PRECLAIM;
    uint32_t freshUnusedChecks = 0; bool controllerMode = false, checkingLifecycle = false, foreign = false;
    uint32_t regs[0x4400/4] = {}; uint64_t clock = 1000000;
    unsigned calls = 0, failAt = 0, failRead = 0, reads = 0, writes = 0, halves = 0;
    unsigned providerCalls = 0, failProvider = 0, claimCount = 0, corruptUnusedAt = 0, closeBeforeClaim = 0;
    unsigned earlyUp = 0, lateUp = 0, rootWrites = 0, debugWrites = 0, failPrior = 0, failedPhase = 0;
    uint64_t releaseTime = 0; bool released = false, holdLinkDown = false;
    unsigned getPhase() const { return phase; } void setPhase(unsigned p) { phase = p; }
    bool onOwnerThread() const { return !foreign; }
    int fail() {
        if (phase != BCM2712_PHY_FAILED) failedPhase = phase;
        phase = BCM2712_PHY_FAILED; reset.state = RPI5_PCIE_RESET_QUARANTINED;
        calibration.state = RPI5_PCIE_RESCAL_QUARANTINED; serdes.state = RPI5_PCIE_SERDES_QUARANTINED;
        serdes.mdio.state = RPI5_PCIE_MDIO_QUARANTINED; ubus.state = RPI5_PCIE_UBUS_QUARANTINED;
        qos.state = RPI5_PCIE_QOS_QUARANTINED; clockPolicy.state = RPI5_PCIE_CLOCK_QUARANTINED;
        windows.state = RPI5_PCIE_WINDOWS_QUARANTINED; rc.state = RPI5_PCIE_RC_QUARANTINED;
        link.state = RPI5_PCIE_LINK_QUARANTINED; return -1;
    }
    static int admission(IOService *p, unsigned life) {
        auto *s = p->transport; assert(s->checkingLifecycle);
        assert(life <= BCM2712_CONTROLLER_RELEASED);
        s->providerCalls++;
        if (life == BCM2712_CONTROLLER_PRECLAIM && s->closeBeforeClaim) p->opened = false;
        if (life == BCM2712_CONTROLLER_RELEASED) {
            if (s->clock < s->releaseTime+100000) s->earlyUp++; else s->lateUp++;
        }
        return s->providerCalls == s->failProvider ? -1 : 0;
    }
    bool guard() {
        if (!onOwnerThread() || phase == BCM2712_PHY_FAILED) return false;
        calls++;
        if (calls == failAt || checkingLifecycle) { fail(); return false; }
        checkingLifecycle = true;
        int result = controllerAdmission.check(ownerProvider,lifecyclePhase);
        checkingLifecycle = false;
        if (result) { fail(); return false; } return true;
    }
    static int unusedOwner(void *p) { return static_cast<BCM2712PCIePHYTransport *>(p)->guard() ? 0 : -1; }
    static int bridgeRead(void *p, uint32_t off, uint32_t *out) {
        auto *s = static_cast<BCM2712PCIePHYTransport *>(p);
        assert(bcm2712_controller_access_allowed(s->phase,0,off,4,0) && off < sizeof s->regs);
        if (!s->guard()) return -1;
        s->reads++;
        if (s->reads == s->failRead) { s->fail(); return -1; }
        if (s->freshUnusedChecks == s->corruptUnusedAt && s->corruptUnusedAt) s->regs[0x40d4/4] = 1;
        *out = s->regs[off/4];
        if (off == 0x4068 && s->released && s->clock >= s->releaseTime+100000 && !s->holdLinkDown)
            *out = s->regs[off/4] = 0xb0;
        return s->guard() ? 0 : -1;
    }
    static int bridgeWrite(void *p, uint32_t off, uint32_t value) {
        auto *s = static_cast<BCM2712PCIePHYTransport *>(p);
        assert(bcm2712_controller_access_allowed(s->phase,0,off,4,1) && off < sizeof s->regs);
        if (!s->guard()) return -1;
        if (s->phase == BCM2712_PHY_LINK_TRAINING && off == 0x4064) {
            assert(s->lifecyclePhase == BCM2712_CONTROLLER_HELD_RESET && (value&5) == 4);
            s->lifecyclePhase = BCM2712_CONTROLLER_RELEASED;
            if (!s->guard()) return -1;
            s->released = true; s->releaseTime = s->clock;
        }
        s->writes++; s->regs[off/4] = value;
        if (s->phase == BCM2712_PHY_CLOCK_FINISHING) {
            if (off == 0x04f8) s->rootWrites++;
            if (off == 0x4304) s->debugWrites++;
        }
        return s->guard() ? 0 : -1;
    }
    static int order(void *p) { return unusedOwner(p); }
    static int nowUS(void *p, uint64_t *out) {
        auto *s = static_cast<BCM2712PCIePHYTransport *>(p);
        if (!s->guard()) return -1; *out = s->clock; return s->guard() ? 0 : -1;
    }
    static int delayUS(void *p, uint32_t us) {
        auto *s = static_cast<BCM2712PCIePHYTransport *>(p);
        assert(us && us <= (s->phase == BCM2712_PHY_LINK_TRAINING ? 100000u : 100u));
        while (us) {
            uint32_t chunk = us > 1000 ? 1000 : us;
            if (!s->guard()) return -1; s->clock += chunk;
            if (!s->guard()) return -1; us -= chunk;
        }
        return 0;
    }
    static int controllerRead16(void *p, uint32_t off, uint16_t *out) {
        auto *s = static_cast<BCM2712PCIePHYTransport *>(p);
        assert(bcm2712_controller_access_allowed(s->phase,0,off,2,0));
        if (!s->guard()) return -1;
        *out = uint16_t(s->regs[off/4] >> ((off&2)*8)); s->halves++;
        return s->guard() ? 0 : -1;
    }
    static int controllerWrite16(void *p, uint32_t off, uint16_t value) {
        auto *s = static_cast<BCM2712PCIePHYTransport *>(p);
        assert(bcm2712_controller_access_allowed(s->phase,0,off,2,1) && !(off&3));
        if (!s->guard()) return -1;
        s->regs[off/4] = (s->regs[off/4]&0xffff0000) | value; s->writes++;
        return s->guard() ? 0 : -1;
    }
    static int controllerQuiescent(void *);
    static int controllerLifecycle(void *, unsigned);
    bool runController(const bcm2712_controller_admission *, bcm2712_controller_observation *);
    bool runPHYUBUSQoSAndClock(bcm2712_clock_observation *out) {
        /* Modeled completed reset/SerDes only; every following core is REAL. */
        claimCount++; if (failPrior) return false;
        reset.state = RPI5_PCIE_RESET_COMPLETE; calibration.state = RPI5_PCIE_RESCAL_COMPLETE;
        serdes.state = RPI5_PCIE_SERDES_COMPLETE; serdes.mdio.state = RPI5_PCIE_MDIO_READY;
        serdes.bridge_reset = &reset; serdes.calibration = &calibration;
        serdes.mdio.io = {this,0x1000120000,0x9310,bridgeRead,bridgeWrite,order,nowUS,delayUS};
        setPhase(BCM2712_PHY_UBUS_CONFIGURING);
        if (rpi5_pcie_ubus_init(&ubus,&serdes) || rpi5_pcie_ubus_configure(&ubus,&out->prior.prior.ubus.ubus)) return false;
        setPhase(BCM2712_PHY_UNUSED_INSPECTING);
        rpi5_pcie_unused unused = {}; rpi5_pcie_unused_io io = {this,0x1000120000,0x9310,unusedOwner,bridgeRead};
        if (rpi5_pcie_unused_init(&unused,&ubus,&io) || rpi5_pcie_unused_inspect(&unused,&out->prior.prior.unused)) return false;
        setPhase(BCM2712_PHY_QOS_CONFIGURING);
        rpi5_pcie_profile profile = {2,4,qos.profile.clkreq,1,0,0};
        if (rpi5_pcie_qos_init(&qos,&ubus,&profile,unusedOwner) || rpi5_pcie_qos_configure(&qos,&out->prior.qos)) return false;
        setPhase(BCM2712_PHY_CLOCK_PREPARING);
        if (rpi5_pcie_clock_init(&clockPolicy,&qos) || rpi5_pcie_clock_prepare(&clockPolicy,&out->clock)) return false;
        setPhase(BCM2712_PHY_COMPLETE); return true;
    }
    void prepare(unsigned mode) {
        binding.bridge_regs = {0x1000120000,0x1000129310};
        binding.mip_regs = {0x1000130000,0x10001300c0};
        binding.mip_target = {0xfffffff000,0x10000000000};
        binding.outbound_count = 2; binding.dma_count = 3;
        binding.outbound[0] = {0x02000000,0,0x1f00000000,0xfffffffc};
        binding.outbound[1] = {0x43000000,0x400000000,0x1c00000000,0x300000000};
        binding.dma[0] = {0x02000000,0,0x1f00000000,0x400000};
        binding.dma[1] = {0x43000000,0x1000000000,0,0x1000000000};
        binding.dma[2] = {0x03000000,0xfffffff000,0x1000130000,0x1000};
        regs[0x4068/4] = 0x80; regs[0x416c/4] = 0x2800;
        regs[0x04dc/4] = 0x81000c43; regs[0x184c/4] = 0x80000012;
        regs[0x4304/4] = 0x40000000; regs[0xbc/4] = 0x30420543;
        regs[0xdc/4] = 0x1234b5a3; regs[0x04f8/4] = 0xa5a502ff;
        regs[0x4078/4] = regs[0x407c/4] = 0x0000fff0; /* Disabled unused outbound 2/3. */
        qos.profile.clkreq = mode;
    }
};
#define RPI5_PCIE_CONTROLLER_DIAGNOSTIC 1
#include "BCM2712PCIeControllerLifecycle.inc"
#include "BCM2712PCIeControllerRun.inc"
static bool run(BCM2712PCIePHYTransport &s)
{
    bcm2712_controller_observation out, before;
    std::memset(&out,0xa5,sizeof out); before = out;
    bcm2712_controller_admission check = {BCM2712PCIePHYTransport::admission};
    bool ok = s.runController(&check,&out);
    if (!ok) assert(!std::memcmp(&out,&before,sizeof out));
    else {
        assert(s.phase == BCM2712_PHY_COMPLETE && s.claimCount == 1);
        assert(s.windows.state == RPI5_PCIE_WINDOWS_COMPLETE && s.rc.state == RPI5_PCIE_RC_COMPLETE);
        assert(s.link.state == RPI5_PCIE_LINK_COMPLETE && s.clockPolicy.state == RPI5_PCIE_CLOCK_COMPLETE);
        assert(out.fresh_unused_checks == 12 && s.freshUnusedChecks == 12);
        assert(out.rc.window_callbacks == 112 && out.link.generation == 2 && out.link.lanes == 4);
        assert(out.link.reset_wait_us == 100000 && s.earlyUp && s.lateUp && s.halves);
        assert(out.clock.declared_mode == s.qos.profile.clkreq && out.clock.final_status == 0xb0);
        assert(s.regs[0xbc/4] == 0x30420440); /* Adjacent link status untouched. */
    }
    return ok;
}
int main()
{
    unsigned failures = 0, providerFailures = 0;
    for (unsigned mode = 0; mode < 4; mode++) {
        BCM2712PCIePHYTransport good; good.prepare(mode);
        bool ok = run(good);
        if (!ok) std::fprintf(stderr,"unexpected failure phase=%u calls=%u reads=%u writes=%u fresh=%u\n",
            good.failedPhase,good.calls,good.reads,good.writes,good.freshUnusedChecks);
        assert(ok);
        assert(good.debugWrites == 1 && good.rootWrites == (mode == 1 || mode == 3));
        unsigned calls = good.calls, providers = good.providerCalls;
        for (unsigned fail = 1; fail <= calls; fail++) {
            BCM2712PCIePHYTransport s; s.prepare(mode); s.failAt = fail;
            assert(!run(s) && s.calls == fail && s.phase == BCM2712_PHY_FAILED);
            unsigned after = s.calls; assert(!run(s) && s.calls == after); failures++;
        }
        for (unsigned fail = 1; fail <= providers; fail++) {
            BCM2712PCIePHYTransport s; s.prepare(mode); s.failProvider = fail;
            assert(!run(s) && s.providerCalls == fail && s.phase == BCM2712_PHY_FAILED);
            if (fail == 1) assert(!s.claimCount && !s.reads && !s.writes);
            providerFailures++;
        }
    }
    for (unsigned check = 1; check < 12; check++) {
        BCM2712PCIePHYTransport s; s.prepare(2); s.corruptUnusedAt = check;
        assert(!run(s) && s.phase == BCM2712_PHY_FAILED && !s.released);
    }
    BCM2712PCIePHYTransport timeout; timeout.prepare(2); timeout.holdLinkDown = true;
    assert(!run(timeout) && timeout.released && timeout.clock == timeout.releaseTime+200000);
    BCM2712PCIePHYTransport prior; prior.prepare(2); prior.failPrior = 1;
    assert(!run(prior) && !prior.reads && !prior.writes);
    BCM2712PCIePHYTransport missing; missing.prepare(2);
    bcm2712_controller_admission null = {}; bcm2712_controller_observation out;
    assert(!missing.runController(&null,&out) && !missing.calls && !missing.claimCount);
    assert(!missing.runController(nullptr,&out) && !missing.calls);
    missing.foreign = true; null.check = BCM2712PCIePHYTransport::admission;
    assert(!missing.runController(&null,&out) && !missing.calls);
    BCM2712PCIePHYTransport closed; closed.prepare(2); closed.closeBeforeClaim = 1;
    assert(!run(closed) && !closed.claimCount && !closed.reads && !closed.writes);
    std::printf("PCIE_CONTROLLER_HOST_PASS GUARD_FAILURES=%u PROVIDER_FAILURES=%u FRESH_CHECKS=12 NO_MMIO=1\n",
        failures,providerFailures);
}
