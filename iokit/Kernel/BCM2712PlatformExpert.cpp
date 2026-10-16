/* SPDX-License-Identifier: APSL-2.0 */
/* Experimental Raspberry Pi 5 platform matching, DEVELOPMENT only. */

#if defined(ARM64_BOARD_CONFIG_BCM2712) && DEVELOPMENT

#include <pexpert/arm64/board_config.h>
#include <IOKit/IODeviceTreeSupport.h>
#include <IOKit/IOPlatformExpert.h>
#include <IOKit/IOCPU.h>
#include <libkern/c++/OSData.h>
#include <libkern/libkern.h>
#include <machine/machine_routines.h>
#include <kern/processor.h>
#include <pexpert/arm/protos.h>
extern "C" {
/* osfmk's private cpu_internal.h is not exported to the built-in IOKit
 * compilation unit. Keep the physical handoff ABI explicit here. */
bool rpi5_publish_secondary_handoff(int cpu, vm_offset_t *entry_paddr,
    vm_offset_t *reset_vector_paddr);
uint64_t rpi5_psci_cpu_on(uint64_t affinity, uint64_t entry_pa,
    uint64_t context_id);
void rpi5_gate3_start_tlb_test(void);
void rpi5_gate3_start_user_tlb_test(void);
void rpi5_gate3_start_concurrency_test(void);
bool rpi5_gate3_enable_soak(uint32_t seconds);
bool rpi5_terminal_watchdog_start(void);
}

#define super IODTPlatformExpert

class BCM2712PlatformExpert : public IODTPlatformExpert {
	OSDeclareDefaultStructors(BCM2712PlatformExpert);

public:
	IOService *probe(IOService *provider, SInt32 *score) APPLE_KEXT_OVERRIDE;
	bool configure(IOService *provider) APPLE_KEXT_OVERRIDE;
	bool registerCPUNubs(IORegistryEntry *cpus, bool includeSecondaries,
	    unsigned int bootSecondaries);
	const char *deleteList(void) APPLE_KEXT_OVERRIDE;
	const char *excludeList(void) APPLE_KEXT_OVERRIDE;
};

OSDefineMetaClassAndStructors(BCM2712PlatformExpert, IODTPlatformExpert)

/* CPU_ON is reachable only through a secondary processor_boot request. */
class BCM2712CPU : public IOCPU {
	OSDeclareDefaultStructors(BCM2712CPU);
	ml_topology_cpu_t topologyCPU = {};
	OSPtr<const OSSymbol> cpuName;
	uint32_t sgiTargetMask = 0;

public:
	void setTopologyCPU(const ml_topology_cpu_t &cpu) { topologyCPU = cpu; }
	bool start(IOService *provider) APPLE_KEXT_OVERRIDE;
	void initCPU(bool boot) APPLE_KEXT_OVERRIDE;
	void quiesceCPU(void) APPLE_KEXT_OVERRIDE;
	kern_return_t startCPU(vm_offset_t, vm_offset_t) APPLE_KEXT_OVERRIDE;
	void haltCPU(void) APPLE_KEXT_OVERRIDE;
	void signalCPU(IOCPU *target) APPLE_KEXT_OVERRIDE;
	const OSSymbol *getCPUName(void) APPLE_KEXT_OVERRIDE { return cpuName; }
};

OSDefineMetaClassAndStructors(BCM2712CPU, IOCPU)

bool
BCM2712CPU::start(IOService *provider)
{
	if (!IOCPU::start(provider)) {
		return false;
	}
	cpuName = OSSymbol::withCStringNoCopy("BCM2712CPU");
	setCPUNumber(topologyCPU.cpu_id);
	setCPUState(kIOCPUStateStopped);
	ml_processor_info_t info = {};
	info.cpu_id = reinterpret_cast<cpu_id_t>(this);
	info.phys_id = topologyCPU.phys_id;
	info.log_id = topologyCPU.cpu_id;
	info.cluster_id = topologyCPU.cluster_id;
	info.cluster_type = topologyCPU.cluster_type;
	info.l2_cache_id = topologyCPU.l2_cache_id;
	info.l2_cache_size = topologyCPU.l2_cache_size;
	info.l3_cache_id = topologyCPU.l3_cache_id;
	info.l3_cache_size = topologyCPU.l3_cache_size;
	perfmon_interrupt_handler_func pmiHandler = nullptr;
	if (ml_processor_register(&info, &machProcessor, &ipi_handler,
	    &pmiHandler) != KERN_SUCCESS) {
		return false;
	}
	return true;
}

static bool
rpi5_cpu_on_trial_enabled(void)
{
	int enabled = 0;
	if (PE_parse_boot_argn("bcm2712_cpu_on_1", &enabled, sizeof(enabled)) && enabled == 1) {
		return true;
	}
	return PE_parse_boot_argn("bcm2712_cpu_on_all", &enabled, sizeof(enabled)) && enabled == 1;
}

void
BCM2712CPU::initCPU(bool)
{
	if (rpi5_cpu_on_trial_enabled()) {
		uint32_t target = pe_rpi5_sgi_local_target();
		if (target == 0 || !pe_rpi5_sgi_enable_local()) {
			panic("BCM2712 CPU %u: SGI1 setup failed", topologyCPU.cpu_id);
		}
		__atomic_store_n(&sgiTargetMask, target, __ATOMIC_RELEASE);
		kprintf("RPI5XNU:SGI1:LOCAL CPU=%u MASK=0x%x\n", topologyCPU.cpu_id, target);
		/* XNU initializes every CPU, including the boot CPU, with
		 * SIGPdisabled. The first self-SGI clears it after StartedState is
		 * published. Without this, boot-CPU self-xcalls fail with KR=5. */
		if (!pe_rpi5_sgi_send(target)) {
			panic("BCM2712 CPU %u: self-SGI1 failed", topologyCPU.cpu_id);
		}
	}
	setCPUState(kIOCPUStateRunning);
}
void BCM2712CPU::quiesceCPU(void) { setCPUState(kIOCPUStateStopped); }
kern_return_t
BCM2712CPU::startCPU(vm_offset_t, vm_offset_t)
{
	if (topologyCPU.cpu_id == ml_get_boot_cpu_number()) {
		return KERN_INVALID_ARGUMENT;
	}
	vm_offset_t entryPA = 0;
	vm_offset_t resetPA = 0;
	if (!rpi5_publish_secondary_handoff(topologyCPU.cpu_id, &entryPA, &resetPA)) {
		kprintf("RPI5XNU:CPU_ON:HANDOFF_FAIL CPU=%u\n", topologyCPU.cpu_id);
		return KERN_FAILURE;
	}
	uint64_t result = rpi5_psci_cpu_on(topologyCPU.phys_id, entryPA, resetPA);
	kprintf("RPI5XNU:CPU_ON:RETURN CPU=%u PSCI=0x%llx\n",
	    topologyCPU.cpu_id, (unsigned long long)result);
	return result == 0 ? KERN_SUCCESS : KERN_FAILURE;
}
void BCM2712CPU::haltCPU(void) { panic("BCM2712 CPU halt is not implemented"); }

void
BCM2712CPU::signalCPU(IOCPU *target)
{
	if (!rpi5_cpu_on_trial_enabled()) {
		return;
	}
	BCM2712CPU *destination = OSDynamicCast(BCM2712CPU, target);
	uint32_t mask = destination ?
	    __atomic_load_n(&destination->sgiTargetMask, __ATOMIC_ACQUIRE) : 0;
	if (mask == 0 || !pe_rpi5_sgi_send(mask)) {
		panic("BCM2712: SGI1 target unavailable");
	}
}

bool
BCM2712PlatformExpert::registerCPUNubs(IORegistryEntry *cpus,
    bool includeSecondaries, unsigned int bootSecondaries)
{
	const ml_topology_info *topology = ml_get_topology_info();
	processor_t trialProcessors[4] = { PROCESSOR_NULL, PROCESSOR_NULL,
	    PROCESSOR_NULL, PROCESSOR_NULL };
	if (bootSecondaries == 3 && topology->num_cpus != 4) {
		return false;
	}
	for (unsigned int i = 0; i < topology->num_cpus; i++) {
		if (!includeSecondaries && topology->cpus[i].cpu_id != ml_get_boot_cpu_number()) {
			continue;
		}
		OSIterator *entries = IODTFindMatchingEntries(cpus, kIODTExclusive, nullptr);
		if (!entries) {
			return false;
		}
		IORegistryEntry *entry;
		IOService *nub = nullptr;
		while ((entry = OSDynamicCast(IORegistryEntry, entries->getNextObject()))) {
			OSData *reg = OSDynamicCast(OSData, entry->getProperty("reg"));
			uint32_t affinity;
			memcpy(&affinity, reg->getBytesNoCopy(), sizeof(affinity));
			if (affinity == topology->cpus[i].phys_id) {
				nub = createNub(entry);
				break;
			}
		}
		entries->release();
		if (!nub || !nub->attach(this)) {
			if (nub) nub->release();
			return false;
		}
		nub->setProperty("logical-cpu-id", topology->cpus[i].cpu_id, 32U);
		nub->setProperty("logical-cluster-id", topology->cpus[i].cluster_id, 32U);
		nub->registerService();
		BCM2712CPU *cpu = new BCM2712CPU;
		if (!cpu || !cpu->init()) {
			if (cpu) cpu->release();
			nub->release();
			return false;
		}
		cpu->setTopologyCPU(topology->cpus[i]);
		bool ok = cpu->attach(nub) && cpu->start(nub);
		if (ok && bootSecondaries && topology->cpus[i].cpu_id > 0 &&
		    topology->cpus[i].cpu_id <= bootSecondaries) {
			trialProcessors[topology->cpus[i].cpu_id] = cpu->getMachProcessor();
		}
		if (ok) cpu->registerService();
		cpu->release();
		nub->release();
		if (!ok) return false;
	}
	for (unsigned int cpu = 1; cpu <= bootSecondaries; cpu++) {
		if (trialProcessors[cpu] == PROCESSOR_NULL) {
			return false;
		}
		kprintf("RPI5XNU:CPU_ON:REQUEST CPU=%u\n", cpu);
		processor_boot(trialProcessors[cpu]);
	}
	if (bootSecondaries == 3) {
		int terminalWatchdog = 0;
		if (PE_parse_boot_argn("bcm2712_terminal_watchdog", &terminalWatchdog,
		    sizeof(terminalWatchdog)) && terminalWatchdog == 1 &&
		    !rpi5_terminal_watchdog_start()) {
			kprintf("RPI5XNU:TERMINAL:WATCHDOG_FAIL\n");
		}
		int soakSeconds = 0;
		if (PE_parse_boot_argn("bcm2712_soak_seconds", &soakSeconds,
		    sizeof(soakSeconds)) && soakSeconds > 0) {
			if (!rpi5_gate3_enable_soak((uint32_t)soakSeconds)) {
				kprintf("RPI5XNU:SOAK:FAIL STAGE=ARM\n");
			}
		}
		int enabled = 0;
		if (PE_parse_boot_argn("bcm2712_tlb_trial", &enabled,
		    sizeof(enabled)) && enabled == 1) {
			rpi5_gate3_start_tlb_test();
		}
		enabled = 0;
		if (PE_parse_boot_argn("bcm2712_user_tlb_trial", &enabled,
		    sizeof(enabled)) && enabled == 1) {
			rpi5_gate3_start_user_tlb_test();
		}
		enabled = 0;
		if (PE_parse_boot_argn("bcm2712_concurrency_trial", &enabled,
		    sizeof(enabled)) && enabled == 1) {
			rpi5_gate3_start_concurrency_test();
		}
	}
	return true;
}

/* A CPU nub must name exactly one CPU already discovered by the machine
 * topology parser.  The Pi 5's MPIDR Aff1 is part of this identity. */
static bool
validateCPUNubs(IORegistryEntry *cpus)
{
	const ml_topology_info *topology = ml_get_topology_info();
	if (!topology || topology->num_cpus == 0 || topology->num_cpus > MAX_CPUS) {
		return false;
	}

	OSIterator *entries = IODTFindMatchingEntries(cpus, kIODTExclusive, nullptr);
	if (!entries) {
		return false;
	}
	uint32_t seen = 0;
	bool valid = true;
	IORegistryEntry *entry;
	while ((entry = OSDynamicCast(IORegistryEntry, entries->getNextObject()))) {
		OSData *reg = OSDynamicCast(OSData, entry->getProperty("reg"));
		uint32_t affinity = 0;
		if (!reg || reg->getLength() != sizeof(affinity)) {
			valid = false;
			break;
		}
		memcpy(&affinity, reg->getBytesNoCopy(), sizeof(affinity));
		unsigned int i;
		for (i = 0; i < topology->num_cpus; i++) {
			if (topology->cpus[i].phys_id == affinity) {
				break;
			}
		}
		if (i == topology->num_cpus || (seen & (1u << i))) {
			valid = false;
			break;
		}
		seen |= 1u << i;
	}
	entries->release();
	return valid && seen == ((1u << topology->num_cpus) - 1u);
}

IOService *
BCM2712PlatformExpert::probe(IOService *provider, SInt32 *score)
{
	if (!super::probe(provider, score)) {
		return nullptr;
	}

	/* The root name alone is insufficient: reject any non-Pi Apple DT. */
	OSData *compatible = OSDynamicCast(OSData, provider->getProperty("compatible"));
	static constexpr char pi5[] = "raspberrypi,5-model-b";
	static constexpr char soc[] = "brcm,bcm2712";
	if (!compatible || compatible->getLength() != sizeof(pi5) + sizeof(soc)) {
		return nullptr;
	}
	const char *bytes = static_cast<const char *>(compatible->getBytesNoCopy());
	if (memcmp(bytes, pi5, sizeof(pi5)) != 0 ||
	    memcmp(bytes + sizeof(pi5), soc, sizeof(soc)) != 0) {
		return nullptr;
	}

	return this;
}

bool
BCM2712PlatformExpert::configure(IOService *provider)
{
	if (!IOPlatformExpert::configure(provider)) {
		return false;
	}

	/* No /options or NVRAM controller exists on this board. Do not invoke
	 * IODTPlatformExpert::processTopLevel(), which requires one. Its NVRAM
	 * methods report not-ready when no controller was installed. */
	IORegistryEntry *cpus = provider->childFromPath("cpus", gIODTPlane);
	IORegistryEntry *io = provider->childFromPath("arm-io", gIODTPlane);
	if (!cpus || !io) {
		if (cpus) cpus->release();
		if (io) io->release();
		return false;
	}
	if (!validateCPUNubs(cpus)) {
		cpus->release();
		io->release();
		return false;
	}

	int registerSecondaries = 0;
	int registerBootCPU = 0;
	int cpuOn1 = 0;
	bool bootCPU1 = PE_parse_boot_argn("bcm2712_cpu_on_1", &cpuOn1,
	    sizeof(cpuOn1)) && cpuOn1 == 1;
	int cpuOnAll = 0;
	bool bootAll = PE_parse_boot_argn("bcm2712_cpu_on_all", &cpuOnAll,
	    sizeof(cpuOnAll)) && cpuOnAll == 1;
	bool all = PE_parse_boot_argn("bcm2712_register_secondaries",
	    &registerSecondaries, sizeof(registerSecondaries)) && registerSecondaries == 1;
	bool boot = PE_parse_boot_argn("bcm2712_register_boot_cpu",
	    &registerBootCPU, sizeof(registerBootCPU)) && registerBootCPU == 1;
	if ((all && boot) || ((bootCPU1 || bootAll) && (!all || boot)) ||
	    (bootCPU1 && bootAll) ||
	    (bootAll && ml_get_topology_info()->num_cpus != 4)) {
		cpus->release();
		io->release();
		return false;
	}
	bool enabled = all || boot;
	OSIterator *cpuEntries = enabled ? nullptr :
	    IODTFindMatchingEntries(cpus, kIODTExclusive, nullptr);
	bool ok = enabled ? registerCPUNubs(cpus, all, bootAll ? 3U : bootCPU1 ? 1U : 0U) :
	    (cpuEntries && createNubs(this, cpuEntries));
	IOService *ioNub = createNub(io);
	if (ioNub) {
		bool attached = ioNub->attach(this);
		if (attached) {
			ioNub->registerService();
		}
		ok = attached && ok;
		ioNub->release();
	} else {
		ok = false;
	}
#if RPI5_STORAGE_PROVIDER
	int sdReadonly = 0;
#if RPI5_STORAGE_WRITE_PROVIDER
	int sdWriteTrial = 0;
	PE_parse_boot_argn("bcm2712_sd_readonly", &sdReadonly, sizeof(sdReadonly));
	if (!sdReadonly && PE_parse_boot_argn("bcm2712_sd_write_trial", &sdWriteTrial,
	    sizeof(sdWriteTrial)) && sdWriteTrial == 1) {
#else
	if (PE_parse_boot_argn("bcm2712_sd_readonly", &sdReadonly,
	    sizeof(sdReadonly)) && sdReadonly == 1) {
#endif
		/* The removable host is a root physical node, outside arm-io.
		 * Publishing it neither changes rails nor initializes the card. */
		IORegistryEntry *sd = provider->childFromPath("sdio1", gIODTPlane);
		IOService *sdNub = sd ? createNub(sd) : nullptr;
		if (sdNub) {
			bool attached = sdNub->attach(this);
			if (attached) sdNub->registerService();
			ok = attached && ok;
			sdNub->release();
		} else {
			kprintf("RPI5XNU:SD:NUB_FAIL\n");
			ok = false;
		}
		if (sd) sd->release();
	}
#endif
	cpus->release();
	io->release();
	return ok;
}

const char *
BCM2712PlatformExpert::deleteList(void)
{
	return nullptr;
}

const char *
BCM2712PlatformExpert::excludeList(void)
{
	return nullptr;
}

#endif /* ARM64_BOARD_CONFIG_BCM2712 && DEVELOPMENT */
