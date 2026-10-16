/* SPDX-License-Identifier: APSL-2.0
 * Darwin container project addition, 2026-10-12.
 * Based on the source-only IOCPU integration; no Apple private platform archive.
 */
#include <pexpert/arm64/board_config.h>
#include <IOKit/IODeviceTreeSupport.h>
#include <IOKit/IOPlatformExpert.h>
#include <IOKit/IOCPU.h>
#include <libkern/c++/OSData.h>
#include <libkern/libkern.h>
#include <machine/machine_routines.h>
#include <kern/processor.h>
#include <pexpert/arm/protos.h>
#if VZ_NETWORK_PROVIDER
extern bool vz_network_start(IOService *);
#endif

class VZGenericCPU : public IOCPU {
	OSDeclareDefaultStructors(VZGenericCPU);
	ml_topology_cpu_t topologyCPU = {};
	OSPtr<const OSSymbol> cpuName;
public:
	void setTopologyCPU(const ml_topology_cpu_t &cpu) { topologyCPU = cpu; }
	bool start(IOService *provider) APPLE_KEXT_OVERRIDE;
	void initCPU(bool boot) APPLE_KEXT_OVERRIDE;
	void quiesceCPU(void) APPLE_KEXT_OVERRIDE { panic("VZGENERIC: CPU sleep unsupported"); }
	kern_return_t startCPU(vm_offset_t, vm_offset_t) APPLE_KEXT_OVERRIDE { return KERN_NOT_SUPPORTED; }
	void haltCPU(void) APPLE_KEXT_OVERRIDE { panic("VZGENERIC: CPU halt unsupported"); }
	void signalCPU(IOCPU *target) APPLE_KEXT_OVERRIDE;
	const OSSymbol *getCPUName(void) APPLE_KEXT_OVERRIDE { return cpuName; }
};
OSDefineMetaClassAndStructors(VZGenericCPU, IOCPU)

bool
VZGenericCPU::start(IOService *provider)
{
	if (!IOCPU::start(provider)) return false;
	cpuName = OSSymbol::withCStringNoCopy("VZGenericCPU");
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
	return ml_processor_register(&info, &machProcessor, &ipi_handler, &pmiHandler) == KERN_SUCCESS;
}

void
VZGenericCPU::initCPU(bool boot)
{
	if (!boot) panic("VZGENERIC: only the boot CPU is supported");
	/* First self-SGI clears XNU's initial SIGPdisabled after StartedState. */
	pe_vz_send_self_sgi();
	setCPUState(kIOCPUStateRunning);
}

void
VZGenericCPU::signalCPU(IOCPU *target)
{
	if (target != this) panic("VZGENERIC: secondary CPU signal unsupported");
	pe_vz_send_self_sgi();
}

class VZGenericPlatformExpert : public IODTPlatformExpert {
	OSDeclareDefaultStructors(VZGenericPlatformExpert);
public:
	IOService *probe(IOService *provider, SInt32 *score) APPLE_KEXT_OVERRIDE;
	bool configure(IOService *provider) APPLE_KEXT_OVERRIDE;
	const char *deleteList(void) APPLE_KEXT_OVERRIDE { return nullptr; }
	const char *excludeList(void) APPLE_KEXT_OVERRIDE { return nullptr; }
	int haltRestart(unsigned int type) APPLE_KEXT_OVERRIDE { return pe_vz_halt_restart(type); }
};
OSDefineMetaClassAndStructors(VZGenericPlatformExpert, IODTPlatformExpert)

IOService *
VZGenericPlatformExpert::probe(IOService *provider, SInt32 *score)
{
	if (!IODTPlatformExpert::probe(provider, score)) return nullptr;
	OSData *compatible = OSDynamicCast(OSData, provider->getProperty("compatible"));
	static constexpr char expected[] = "apple,vz-generic";
	if (!compatible || compatible->getLength() != sizeof(expected) ||
	    memcmp(compatible->getBytesNoCopy(), expected, sizeof(expected)) != 0) return nullptr;
	return this;
}

bool
VZGenericPlatformExpert::configure(IOService *provider)
{
	if (!IOPlatformExpert::configure(provider)) return false;
	const ml_topology_info *topology = ml_get_topology_info();
	if (!topology || topology->num_cpus != 1 || topology->cpus[0].cpu_id != ml_get_boot_cpu_number()) return false;
	IORegistryEntry *cpus = provider->childFromPath("cpus", gIODTPlane);
	if (!cpus) return false;
	OSIterator *entries = IODTFindMatchingEntries(cpus, kIODTExclusive, nullptr);
	if (!entries) { cpus->release(); return false; }
	IORegistryEntry *entry = OSDynamicCast(IORegistryEntry, entries->getNextObject());
	OSData *reg = entry ? OSDynamicCast(OSData, entry->getProperty("reg")) : nullptr;
	uint32_t affinity = 0;
	bool valid = reg && reg->getLength() == sizeof(affinity) && entries->getNextObject() == nullptr;
	if (valid) memcpy(&affinity, reg->getBytesNoCopy(), sizeof(affinity));
	valid = valid && affinity == topology->cpus[0].phys_id;
	IOService *nub = valid ? createNub(entry) : nullptr;
	entries->release();
	cpus->release();
	if (!nub) return false;
	if (!nub->attach(this)) { nub->release(); return false; }
	nub->registerService();
	VZGenericCPU *cpu = new VZGenericCPU;
	bool ok = cpu && cpu->init();
	if (ok) {
		cpu->setTopologyCPU(topology->cpus[0]);
		ok = cpu->attach(nub) && cpu->start(nub);
		if (ok) cpu->registerService();
	}
	if (cpu) cpu->release();
	nub->release();
#if VZ_STORAGE_PROVIDER
	/* Publish only the loader's explicit writable virtual-disk nub. No Pi bus. */
	IORegistryEntry *block = provider->childFromPath("arm-io/virtio-block", gIODTPlane);
	IOService *blockNub = block ? createNub(block) : nullptr;
	if (block) block->release();
	if (!blockNub || !blockNub->attach(this)) {
		if (blockNub) blockNub->release();
		return false;
	}
	blockNub->registerService();
	blockNub->release();
#endif
#if VZ_NETWORK_PROVIDER
	IORegistryEntry *network = provider->childFromPath("arm-io/virtio-net", gIODTPlane);
	/* A packaged offline workload deliberately has no NIC/device-tree node.
	 * Absence is supported; a present but invalid device still fails closed. */
	if (network) {
		IOService *networkNub = createNub(network);
		network->release();
		if (!networkNub || !networkNub->attach(this)) {
			if (networkNub) networkNub->release();
			return false;
		}
		bool networkOK = vz_network_start(networkNub);
		networkNub->release();
		if (!networkOK) return false;
	} else {
		kprintf("VZXNU:NETWORK:ABSENT OFFLINE\n");
	}
#endif
	if (ok) kprintf("VZXNU:PLATFORM:READY CPUS=1\n");
	return ok;
}
