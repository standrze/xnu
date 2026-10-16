/* SPDX-License-Identifier: BSD-2-Clause */
#include "rpi5_gem_queue_admission.h"

#if !defined(__BYTE_ORDER__) || __BYTE_ORDER__ != __ORDER_LITTLE_ENDIAN__
#error "RP1 GEM queue admission requires a little-endian target"
#endif

#define GEM_NCR UINT32_C(0x0000)
#define GEM_RBQP UINT32_C(0x0018)
#define GEM_TBQP UINT32_C(0x001c)
#define GEM_IMR UINT32_C(0x0030)
#define GEM_IMR_ALL_MASKED UINT32_C(0x3fffffff)
#define GEM_TBQPH UINT32_C(0x04c8)
#define GEM_RBQPH UINT32_C(0x04d4)
#define GEM_DMA_LIMIT (UINT64_C(1) << 40)

static const uint32_t queue_offsets[4] = {
	/* Both upper halves must be established before either lower half can
	 * publish a complete queue address. Restoration runs this in reverse. */
	GEM_TBQPH, GEM_RBQPH, GEM_TBQP, GEM_RBQP
};

static void
copy_bytes(void *destination, const void *source, size_t bytes)
{
	unsigned char *out = destination;
	const unsigned char *in = source;
	for (size_t index = 0; index < bytes; index++) {
		out[index] = in[index];
	}
}

static bool
same_bytes(const void *left, const void *right, size_t bytes)
{
	const unsigned char *a = left;
	const unsigned char *b = right;
	for (size_t index = 0; index < bytes; index++) {
		if (a[index] != b[index]) {
			return false;
		}
	}
	return true;
}

static bool
zero_bytes(const void *object, size_t bytes)
{
	const unsigned char *data = object;
	for (size_t index = 0; index < bytes; index++) {
		if (data[index] != 0) {
			return false;
		}
	}
	return true;
}

static bool
apart(const void *a, size_t a_bytes, const void *b, size_t b_bytes)
{
	uintptr_t left = (uintptr_t)a;
	uintptr_t right = (uintptr_t)b;
	return a != NULL && b != NULL && a_bytes <= UINTPTR_MAX - left &&
	    b_bytes <= UINTPTR_MAX - right &&
	    (left + a_bytes <= right || right + b_bytes <= left);
}

static bool
capability_profile(
	const uint32_t words[RPI5_GEM_QUEUE_ADMISSION_CAP_WORDS])
{
	return words[0] == UINT32_C(0x00070109) &&
	    ((words[1] >> 25) & 7u) == 4u && (words[1] & 1u) != 0 &&
	    ((words[2] >> 20) & 3u) == 3u &&
	    ((words[2] >> 22) & 15u) == 10u &&
	    (words[4] & 255u) == 0 && ((words[4] >> 23) & 1u) == 1u &&
	    ((words[6] >> 8) & 15u) == 4u &&
	    ((words[6] >> 12) & 15u) == 4u &&
	    (words[7] & (UINT32_C(1) << 26)) == 0;
}

static bool
ring_span(uint64_t address)
{
	return address != 0 && (address & 63u) == 0 &&
	    address < GEM_DMA_LIMIT &&
	    RPI5_GEM_STAGE_RING_BYTES <= GEM_DMA_LIMIT - address &&
	    (address >> 32) ==
	    ((address + RPI5_GEM_STAGE_RING_BYTES - 1) >> 32);
}

static bool
valid_request(const struct rpi5_gem_queue_admission_request *request)
{
	const struct rpi5_gem_stage_observation *rings;
	uint64_t tx_end;
	uint64_t rx_end;

	if (request == NULL || request->owner == NULL ||
	    request->mapping_provider == NULL ||
	    request->capability_source == NULL ||
	    request->same_boot_cookie == 0 || request->deadline == 0 ||
	    request->not_before >= request->deadline ||
	    !capability_profile(request->raw_capabilities) ||
	    (request->descriptor_memory != RPI5_GEM_MEMORY_COHERENT &&
	    request->descriptor_memory != RPI5_GEM_MEMORY_UNCACHED)) {
		return false;
	}
	rings = &request->rings;
	if (rings->generation == 0 ||
	    rings->ring_bytes != RPI5_GEM_STAGE_RING_BYTES ||
	    rings->descriptor_bytes != sizeof(struct rpi5_gem_descriptor) ||
	    rings->real_slots != RPI5_GEM_STAGE_SLOTS ||
	    rings->prefetch_bytes != RPI5_GEM_STAGE_TAIL_BYTES ||
	    rings->cpu_owned_descriptors !=
	    2u * RPI5_GEM_STAGE_RING_BYTES /
	    sizeof(struct rpi5_gem_descriptor) ||
	    rings->writes != 2u * RPI5_GEM_STAGE_WORDS ||
	    rings->reads != 2u * RPI5_GEM_STAGE_WORDS ||
	    rings->callbacks != RPI5_GEM_QUEUE_ADMISSION_RING_CALLBACKS ||
	    rings->current_checks !=
	    RPI5_GEM_QUEUE_ADMISSION_RING_CURRENT_CHECKS ||
	    !ring_span(rings->ring_dma[0]) ||
	    !ring_span(rings->ring_dma[1])) {
		return false;
	}
	if (request->provider_bytes != UINT32_C(0x48000) ||
	    request->packet_spans != 2u * RPI5_GEM_STAGE_SLOTS ||
	    request->packet_bytes != RPI5_GEM_BUFFER_BYTES ||
	    request->packet_mapped_bytes !=
	    2u * RPI5_GEM_STAGE_SLOTS * RPI5_GEM_BUFFER_BYTES ||
	    request->packet_spans_cpu_owned != request->packet_spans) {
		return false;
	}
	tx_end = rings->ring_dma[0] + RPI5_GEM_STAGE_RING_BYTES;
	rx_end = rings->ring_dma[1] + RPI5_GEM_STAGE_RING_BYTES;
	return tx_end <= rings->ring_dma[1] || rx_end <= rings->ring_dma[0];
}

struct run {
	struct rpi5_gem_queue_admission_session *session;
	const struct rpi5_gem_queue_admission_request *request_source;
	const struct rpi5_gem_queue_admission_io *io_source;
	struct rpi5_gem_queue_admission_request request;
	struct rpi5_gem_queue_admission_io io;
	uint32_t original[5];
};

static int
fail(struct run *run, int error)
{
	run->session->state = RPI5_GEM_QUEUE_ADMISSION_QUARANTINED;
	run->session->busy = 0;
	run->session->pending = RPI5_GEM_QUEUE_ADMISSION_NONE;
	run->session->error = error;
	return error;
}

static bool
intact(const struct run *run)
{
	const struct rpi5_gem_queue_admission_session *session = run->session;
	return session->self == session && session->busy == 1 &&
	    session->request == run->request_source &&
	    same_bytes(run->request_source, &run->request,
	    sizeof(run->request)) &&
	    same_bytes(run->io_source, &run->io, sizeof(run->io)) &&
	    same_bytes(&session->io, &run->io, sizeof(run->io));
}

static int
guard(struct run *run)
{
	struct rpi5_gem_queue_admission_session held;
	uint64_t now = 0;
	int result;

	if (!intact(run) ||
	    run->session->current_checks >=
	    RPI5_GEM_QUEUE_ADMISSION_CURRENT_CHECKS) {
		return fail(run, -3);
	}
	run->session->current_checks++;
	copy_bytes(&held, run->session, sizeof(held));
	result = run->io.current(run->io.context, run->session,
	    run->request_source, &now);
	if (result != 0 || !intact(run) ||
	    !same_bytes(&held, run->session, sizeof(held)) ||
	    now < run->request.not_before || now < run->session->last ||
	    now >= run->request.deadline) {
		return fail(run, result != 0 ? -3 : -4);
	}
	run->session->last = now;
	return 0;
}

bool
rpi5_gem_queue_admission_access_allowed(
	const struct rpi5_gem_queue_admission_session *session,
	enum rpi5_gem_queue_admission_operation operation, uint32_t offset,
	uint32_t value)
{
	bool register_operation;
	bool known_offset;

	if (session == NULL || session->self != session || session->busy != 1 ||
	    session->state == RPI5_GEM_QUEUE_ADMISSION_UNUSED ||
	    session->state == RPI5_GEM_QUEUE_ADMISSION_COMPLETE ||
	    session->state == RPI5_GEM_QUEUE_ADMISSION_QUARANTINED ||
	    session->pending != operation || session->operations == 0 ||
	    session->operations > RPI5_GEM_QUEUE_ADMISSION_OPERATIONS ||
	    session->offset != offset || session->value != value) {
		return false;
	}
	register_operation = operation == RPI5_GEM_QUEUE_ADMISSION_READ32 ||
	    operation == RPI5_GEM_QUEUE_ADMISSION_WRITE32;
	known_offset = offset == GEM_NCR || offset == GEM_IMR ||
	    offset == GEM_RBQP ||
	    offset == GEM_TBQP || offset == GEM_TBQPH || offset == GEM_RBQPH;
	if (register_operation) {
		return known_offset && (offset & 3u) == 0;
	}
	if (operation == RPI5_GEM_QUEUE_ADMISSION_RING_CHECK) {
		return offset == 0 && value == 0;
	}
	return false;
}

static int
begin_operation(struct run *run,
	enum rpi5_gem_queue_admission_operation operation, uint32_t offset,
	uint32_t value)
{
	if (run->session->operations >= RPI5_GEM_QUEUE_ADMISSION_OPERATIONS) {
		return fail(run, -3);
	}
	run->session->pending = operation;
	run->session->offset = offset;
	run->session->value = value;
	run->session->operations++;
	if (guard(run) != 0 ||
	    !rpi5_gem_queue_admission_access_allowed(run->session, operation,
	    offset, value)) {
		return fail(run, -3);
	}
	return 0;
}

static int
finish_operation(struct run *run,
	const struct rpi5_gem_queue_admission_session *held, int result)
{
	if (!same_bytes(held, run->session, sizeof(*held)) || guard(run) != 0) {
		return fail(run, -3);
	}
	if (result != 0) {
		return fail(run, -5);
	}
	run->session->pending = RPI5_GEM_QUEUE_ADMISSION_NONE;
	return 0;
}

static int
ring_check(struct run *run)
{
	struct rpi5_gem_queue_admission_session held;
	int result;
	if (begin_operation(run, RPI5_GEM_QUEUE_ADMISSION_RING_CHECK, 0, 0)) {
		return run->session->error;
	}
	copy_bytes(&held, run->session, sizeof(held));
	result = run->io.rings_cpu_owned(run->io.context, run->session);
	if (finish_operation(run, &held, result)) {
		return run->session->error;
	}
	run->session->ring_checks++;
	return 0;
}

static int
read32(struct run *run, uint32_t offset, uint32_t *value)
{
	struct rpi5_gem_queue_admission_session held;
	uint32_t result_value = 0;
	int result;
	if (begin_operation(run, RPI5_GEM_QUEUE_ADMISSION_READ32, offset, 0)) {
		return run->session->error;
	}
	copy_bytes(&held, run->session, sizeof(held));
	result = run->io.read32(run->io.context, run->session, offset,
	    &result_value);
	if (finish_operation(run, &held, result)) {
		return run->session->error;
	}
	run->session->reads++;
	*value = result_value;
	return 0;
}

static int
write32(struct run *run, uint32_t offset, uint32_t value)
{
	struct rpi5_gem_queue_admission_session held;
	int result;
	if (begin_operation(run, RPI5_GEM_QUEUE_ADMISSION_WRITE32, offset,
	    value)) {
		return run->session->error;
	}
	copy_bytes(&held, run->session, sizeof(held));
	result = run->io.write32(run->io.context, run->session, offset, value);
	if (finish_operation(run, &held, result)) {
		return run->session->error;
	}
	run->session->writes++;
	return 0;
}

static uint32_t
queue_value(const struct rpi5_gem_queue_admission_request *request,
	unsigned index)
{
	uint64_t address = (index == 0 || index == 2) ?
	    request->rings.ring_dma[0] : request->rings.ring_dma[1];
	return index < 2 ? (uint32_t)(address >> 32) : (uint32_t)address;
}

static int
read_queue_set(struct run *run, uint32_t values[4])
{
	for (unsigned index = 0; index < 4; index++) {
		if (read32(run, queue_offsets[index], &values[index])) {
			return run->session->error;
		}
	}
	return 0;
}

static bool
same_words(const uint32_t left[4], const uint32_t right[4])
{
	for (unsigned index = 0; index < 4; index++) {
		if (left[index] != right[index]) {
			return false;
		}
	}
	return true;
}

int
rpi5_gem_queue_admission_run(
	struct rpi5_gem_queue_admission_session *session,
	const struct rpi5_gem_queue_admission_request *request,
	const struct rpi5_gem_queue_admission_io *io,
	struct rpi5_gem_queue_admission_observation *output)
{
	const void *objects[4] = { session, request, io, output };
	const size_t sizes[4] = {
		sizeof(*session), sizeof(*request), sizeof(*io), sizeof(*output)
	};
	struct run run;
	uint32_t ncr;
	uint32_t imr;
	uint32_t values[4];
	uint32_t expected[4];

	if (session == NULL) {
		return -1;
	}
	if (!zero_bytes(session, sizeof(*session))) {
		if (session->state != RPI5_GEM_QUEUE_ADMISSION_UNUSED) {
			session->state = RPI5_GEM_QUEUE_ADMISSION_QUARANTINED;
			session->busy = 0;
			session->pending = RPI5_GEM_QUEUE_ADMISSION_NONE;
			session->error = -2;
			return -2;
		}
		return -1;
	}
	if (!valid_request(request) || io == NULL || output == NULL ||
	    io->current == NULL || io->rings_cpu_owned == NULL ||
	    io->read32 == NULL || io->write32 == NULL) {
		return -1;
	}
	for (unsigned left = 0; left < 4; left++) {
		for (unsigned right = 0; right < left; right++) {
			if (!apart(objects[left], sizes[left], objects[right],
			    sizes[right])) {
				return -1;
			}
		}
	}
	run.session = session;
	run.request_source = request;
	run.io_source = io;
	copy_bytes(&run.request, request, sizeof(*request));
	copy_bytes(&run.io, io, sizeof(*io));
	session->self = session;
	session->request = request;
	copy_bytes(&session->io, io, sizeof(*io));
	session->state = RPI5_GEM_QUEUE_ADMISSION_CHECKING;
	session->busy = 1;
	session->last = request->not_before;
	if (guard(&run) || ring_check(&run)) {
		return session->error;
	}
	if (read32(&run, GEM_NCR, &ncr) || read32(&run, GEM_IMR, &imr) ||
	    read_queue_set(&run, run.original)) {
		return session->error;
	}
	/* Exact-zero NCR excludes RE, TE, TSTART, THALT and every unrelated
	 * command or strobe bit.  GEM IMR uses one to mean disabled; this RP1
	 * GEM_GXL instance implements bits 0..29, so every implemented interrupt
	 * must remain masked.  A partial mask is not sufficient admission. */
	if (ncr != 0 || imr != GEM_IMR_ALL_MASKED) {
		return fail(&run, -6);
	}
	for (unsigned index = 0; index < 4; index++) {
		expected[index] = queue_value(request, index);
		if (write32(&run, queue_offsets[index], expected[index])) {
			return session->error;
		}
	}
	session->state = RPI5_GEM_QUEUE_ADMISSION_QUEUES_STAGED;
	if (read32(&run, GEM_NCR, &ncr) || read32(&run, GEM_IMR, &imr) ||
	    read_queue_set(&run, values) ||
	    ncr != 0 || imr != GEM_IMR_ALL_MASKED ||
	    !same_words(values, expected) ||
	    ring_check(&run)) {
		return session->state == RPI5_GEM_QUEUE_ADMISSION_QUARANTINED ?
		    session->error : fail(&run, -6);
	}
	session->state = RPI5_GEM_QUEUE_ADMISSION_RESTORING;
	for (unsigned index = 4; index-- > 0;) {
		if (write32(&run, queue_offsets[index], run.original[index])) {
			return session->error;
		}
	}
	if (read32(&run, GEM_NCR, &ncr) || read32(&run, GEM_IMR, &imr) ||
	    read_queue_set(&run, values) ||
	    ncr != 0 || imr != GEM_IMR_ALL_MASKED ||
	    !same_words(values, run.original) ||
	    ring_check(&run) || guard(&run)) {
		return session->state == RPI5_GEM_QUEUE_ADMISSION_QUARANTINED ?
		    session->error : fail(&run, -6);
	}
	if (session->operations != RPI5_GEM_QUEUE_ADMISSION_OPERATIONS ||
	    session->current_checks != RPI5_GEM_QUEUE_ADMISSION_CURRENT_CHECKS ||
	    session->ring_checks != 3 || session->reads != 18 ||
	    session->writes != 8) {
		return fail(&run, -3);
	}
	struct rpi5_gem_queue_admission_observation result = {
		.version = RPI5_GEM_QUEUE_ADMISSION_VERSION,
		.operations = session->operations,
		.current_checks = session->current_checks,
		.ring_checks = session->ring_checks,
		.reads = session->reads,
		.writes = session->writes,
		.bus_master_enabled = 0,
		.engines_enabled = 0,
		.dma_ownership_transfers = 0,
		.interrupts_enabled = 0,
		.same_boot_cookie = request->same_boot_cookie,
		.tx_ring_dma = request->rings.ring_dma[0],
		.rx_ring_dma = request->rings.ring_dma[1]
	};
	session->state = RPI5_GEM_QUEUE_ADMISSION_COMPLETE;
	session->busy = 0;
	*output = result;
	return 0;
}
