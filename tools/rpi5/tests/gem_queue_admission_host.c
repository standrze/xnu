/* SPDX-License-Identifier: BSD-2-Clause */
#include "rpi5_gem_queue_admission.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

#define GEM_NCR 0x0000u
#define GEM_RBQP 0x0018u
#define GEM_TBQP 0x001cu
#define GEM_IMR 0x0030u
#define GEM_IMR_ALL_MASKED 0x3fffffffu
#define GEM_TBQPH 0x04c8u
#define GEM_RBQPH 0x04d4u

static struct rpi5_gem_queue_admission_session session;
static struct rpi5_gem_queue_admission_request request;
static struct rpi5_gem_queue_admission_observation observation;
static uint32_t registers[0x500 / 4];
static unsigned fail_operation;
static unsigned fail_current;
static unsigned mutate_operation;
static unsigned corrupt_operation;
static unsigned callbacks;
static uint32_t write_offsets[8];
static unsigned write_count;
static uint64_t ticks;

static int
current(void *context, const struct rpi5_gem_queue_admission_session *active,
    const struct rpi5_gem_queue_admission_request *live, uint64_t *now)
{
	assert(context == registers);
	assert(active == &session);
	assert(live == &request);
	assert(active->current_checks > 0);
	if (active->current_checks == fail_current) {
		return -1;
	}
	*now = ++ticks;
	return 0;
}

static int
rings_cpu_owned(void *context,
    const struct rpi5_gem_queue_admission_session *active)
{
	assert(context == registers);
	assert(rpi5_gem_queue_admission_access_allowed(active,
	    RPI5_GEM_QUEUE_ADMISSION_RING_CHECK, 0, 0));
	callbacks++;
	if (active->operations == mutate_operation) {
		session.index++;
	}
	return active->operations == fail_operation ? -1 : 0;
}

static int
read32(void *context,
    const struct rpi5_gem_queue_admission_session *active, uint32_t offset,
    uint32_t *value)
{
	assert(context == registers);
	assert(value != NULL);
	assert(rpi5_gem_queue_admission_access_allowed(active,
	    RPI5_GEM_QUEUE_ADMISSION_READ32, offset, 0));
	callbacks++;
	*value = registers[offset / 4];
	if (active->operations == corrupt_operation) {
		*value ^= 1u;
	}
	if (active->operations == mutate_operation) {
		session.index++;
	}
	return active->operations == fail_operation ? -1 : 0;
}

static int
write32(void *context,
    const struct rpi5_gem_queue_admission_session *active, uint32_t offset,
    uint32_t value)
{
	assert(context == registers);
	assert(rpi5_gem_queue_admission_access_allowed(active,
	    RPI5_GEM_QUEUE_ADMISSION_WRITE32, offset, value));
	callbacks++;
	assert(write_count < 8);
	write_offsets[write_count++] = offset;
	registers[offset / 4] = value;
	if (active->operations == mutate_operation) {
		session.index++;
	}
	return active->operations == fail_operation ? -1 : 0;
}

static const struct rpi5_gem_queue_admission_io io = {
	.context = registers,
	.current = current,
	.rings_cpu_owned = rings_cpu_owned,
	.read32 = read32,
	.write32 = write32
};

static void
initialize(void)
{
	memset(&session, 0, sizeof(session));
	memset(&request, 0, sizeof(request));
	memset(&observation, 0xa5, sizeof(observation));
	memset(registers, 0, sizeof(registers));
	registers[GEM_IMR / 4] = GEM_IMR_ALL_MASKED;
	registers[GEM_TBQPH / 4] = 0x11;
	registers[GEM_TBQP / 4] = 0x22334400;
	registers[GEM_RBQPH / 4] = 0x55;
	registers[GEM_RBQP / 4] = 0x66778800;
	request.owner = &request;
	request.mapping_provider = &registers;
	request.capability_source = &io;
	request.same_boot_cookie = UINT64_C(0xfeed000000000524);
	request.not_before = 1;
	request.deadline = 10000;
	request.raw_capabilities[0] = 0x00070109;
	request.raw_capabilities[1] = (4u << 25) | 1u;
	request.raw_capabilities[2] = (3u << 20) | (10u << 22);
	request.raw_capabilities[4] = 1u << 23;
	request.raw_capabilities[6] = (4u << 8) | (4u << 12);
	request.descriptor_memory = RPI5_GEM_MEMORY_UNCACHED;
	request.rings.ring_dma[0] = UINT64_C(0x101234000);
	request.rings.ring_dma[1] = UINT64_C(0x101238000);
	request.rings.generation = 0x524;
	request.rings.ring_bytes = RPI5_GEM_STAGE_RING_BYTES;
	request.rings.descriptor_bytes = sizeof(struct rpi5_gem_descriptor);
	request.rings.real_slots = RPI5_GEM_STAGE_SLOTS;
	request.rings.prefetch_bytes = RPI5_GEM_STAGE_TAIL_BYTES;
	request.rings.cpu_owned_descriptors =
	    2u * RPI5_GEM_STAGE_RING_BYTES /
	    sizeof(struct rpi5_gem_descriptor);
	request.rings.writes = 2u * RPI5_GEM_STAGE_WORDS;
	request.rings.reads = 2u * RPI5_GEM_STAGE_WORDS;
	request.rings.callbacks = RPI5_GEM_QUEUE_ADMISSION_RING_CALLBACKS;
	request.rings.current_checks =
	    RPI5_GEM_QUEUE_ADMISSION_RING_CURRENT_CHECKS;
	request.provider_bytes = 0x48000;
	request.packet_spans = 2u * RPI5_GEM_STAGE_SLOTS;
	request.packet_bytes = RPI5_GEM_BUFFER_BYTES;
	request.packet_mapped_bytes =
	    2u * RPI5_GEM_STAGE_SLOTS * RPI5_GEM_BUFFER_BYTES;
	request.packet_spans_cpu_owned = request.packet_spans;
	fail_operation = fail_current = mutate_operation = corrupt_operation = 0;
	callbacks = 0;
	write_count = 0;
	memset(write_offsets, 0, sizeof(write_offsets));
	ticks = request.not_before;
}

static void
success(void)
{
	initialize();
	int run_result = rpi5_gem_queue_admission_run(&session, &request, &io,
	    &observation);
	if (run_result != 0) {
		fprintf(stderr, "success rc=%d state=%u error=%d ops=%u checks=%u "
		    "rings=%u reads=%u writes=%u pending=%u offset=%x value=%x\n",
		    run_result, session.state, session.error, session.operations,
		    session.current_checks, session.ring_checks, session.reads,
		    session.writes, session.pending, session.offset, session.value);
	}
	assert(run_result == 0);
	assert(session.state == RPI5_GEM_QUEUE_ADMISSION_COMPLETE);
	assert(session.operations == RPI5_GEM_QUEUE_ADMISSION_OPERATIONS);
	assert(session.current_checks ==
	    RPI5_GEM_QUEUE_ADMISSION_CURRENT_CHECKS);
	assert(session.ring_checks == 3 && session.reads == 18 &&
	    session.writes == 8);
	assert(callbacks == RPI5_GEM_QUEUE_ADMISSION_OPERATIONS);
	assert(observation.version == RPI5_GEM_QUEUE_ADMISSION_VERSION);
	assert(observation.operations == RPI5_GEM_QUEUE_ADMISSION_OPERATIONS);
	assert(observation.current_checks ==
	    RPI5_GEM_QUEUE_ADMISSION_CURRENT_CHECKS);
	assert(observation.ring_checks == 3 && observation.reads == 18 &&
	    observation.writes == 8);
	assert(observation.bus_master_enabled == 0 &&
	    observation.engines_enabled == 0 &&
	    observation.dma_ownership_transfers == 0 &&
	    observation.interrupts_enabled == 0);
	assert(observation.same_boot_cookie == request.same_boot_cookie);
	assert(observation.tx_ring_dma == request.rings.ring_dma[0]);
	assert(observation.rx_ring_dma == request.rings.ring_dma[1]);
	assert(registers[GEM_NCR / 4] == 0 &&
	    registers[GEM_IMR / 4] == GEM_IMR_ALL_MASKED);
	assert(registers[GEM_TBQPH / 4] == 0x11);
	assert(registers[GEM_TBQP / 4] == 0x22334400);
	assert(registers[GEM_RBQPH / 4] == 0x55);
	assert(registers[GEM_RBQP / 4] == 0x66778800);
	const uint32_t expected_write_offsets[8] = {
		GEM_TBQPH, GEM_RBQPH, GEM_TBQP, GEM_RBQP,
		GEM_RBQP, GEM_TBQP, GEM_RBQPH, GEM_TBQPH
	};
	assert(write_count == 8);
	assert(!memcmp(write_offsets, expected_write_offsets,
	    sizeof(expected_write_offsets)));
	assert(!rpi5_gem_queue_admission_access_allowed(&session,
	    RPI5_GEM_QUEUE_ADMISSION_WRITE32, GEM_TBQP, 0));
}

static void
request_rejections(void)
{
#define REJECT(field, value) do { \
	initialize(); request.field = (value); \
	assert(rpi5_gem_queue_admission_run(&session, &request, &io, \
	    &observation) == -1); \
	assert(session.state == RPI5_GEM_QUEUE_ADMISSION_UNUSED); \
} while (0)
	REJECT(owner, NULL);
	REJECT(same_boot_cookie, 0);
	REJECT(provider_bytes, 0x47fff);
	REJECT(packet_spans, 127);
	REJECT(packet_bytes, 2047);
	REJECT(packet_mapped_bytes, 0x3ffff);
	REJECT(packet_spans_cpu_owned, 127);
	REJECT(rings.generation, 0);
	REJECT(rings.writes, 639);
	REJECT(rings.reads, 639);
	REJECT(rings.callbacks, 80);
	REJECT(rings.current_checks, 163);
	REJECT(rings.ring_dma[0], 0);
	REJECT(rings.ring_dma[1], UINT64_C(0x101234000));
	REJECT(descriptor_memory, RPI5_GEM_MEMORY_UNPROVEN);
	REJECT(raw_capabilities[0], 0x00070108);
#undef REJECT
}

static void
faults(void)
{
	for (unsigned operation = 1;
	    operation <= RPI5_GEM_QUEUE_ADMISSION_OPERATIONS; operation++) {
		initialize();
		fail_operation = operation;
		struct rpi5_gem_queue_admission_observation before = observation;
		assert(rpi5_gem_queue_admission_run(&session, &request, &io,
		    &observation) < 0);
		assert(session.state == RPI5_GEM_QUEUE_ADMISSION_QUARANTINED);
		assert(!memcmp(&before, &observation, sizeof(before)));
	}
	for (unsigned check = 1;
	    check <= RPI5_GEM_QUEUE_ADMISSION_CURRENT_CHECKS; check++) {
		initialize();
		fail_current = check;
		assert(rpi5_gem_queue_admission_run(&session, &request, &io,
		    &observation) < 0);
		assert(session.state == RPI5_GEM_QUEUE_ADMISSION_QUARANTINED);
	}
	for (unsigned operation = 1;
	    operation <= RPI5_GEM_QUEUE_ADMISSION_OPERATIONS; operation++) {
		initialize();
		mutate_operation = operation;
		assert(rpi5_gem_queue_admission_run(&session, &request, &io,
		    &observation) < 0);
		assert(session.state == RPI5_GEM_QUEUE_ADMISSION_QUARANTINED);
	}
}

static void
readback_and_engine_rejections(void)
{
	/* Queue readback immediately after programming. */
	initialize(); corrupt_operation = 13;
	assert(rpi5_gem_queue_admission_run(&session, &request, &io,
	    &observation) < 0);
	assert(session.state == RPI5_GEM_QUEUE_ADMISSION_QUARANTINED);
	initialize(); registers[GEM_NCR / 4] = 1u << 3;
	assert(rpi5_gem_queue_admission_run(&session, &request, &io,
	    &observation) < 0);
	initialize(); registers[GEM_NCR / 4] = 1u << 4;
	assert(rpi5_gem_queue_admission_run(&session, &request, &io,
	    &observation) < 0);
	initialize(); registers[GEM_IMR / 4] ^= 1u;
	assert(rpi5_gem_queue_admission_run(&session, &request, &io,
	    &observation) < 0);
}

int
main(void)
{
	success();
	request_rejections();
	faults();
	readback_and_engine_rejections();
	puts("GEM_QUEUE_ADMISSION_PASS DEFAULT_OFF BME0 RE0 TE0 IRQ0 DMA0 PACKETS0");
	return 0;
}
