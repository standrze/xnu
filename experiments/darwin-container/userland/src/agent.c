/* SPDX-License-Identifier: BSD-2-Clause */
#include "runtime.h"
#include "agent_protocol.h"

/* Exact arm64 Darwin ABI, independently recorded in the build manifest.
 * Console is ASCII even in raw mode: kmoutput masks each byte with 0x7f.
 */
struct agent_termios {
    uint64_t input, output, control, local;
    unsigned char characters[20];
    uint64_t input_speed, output_speed;
};
struct agent_timeval { int64_t seconds; int32_t microseconds; int32_t padding; };
_Static_assert(sizeof(struct agent_termios) == 72, "Darwin LP64 termios ABI");
_Static_assert(sizeof(struct agent_timeval) == 16, "Darwin LP64 timeval ABI");

struct agent_job {
    uint32_t id;
    long pid;
    int output[2], eof[2], leader_done, status;
    int cancelled, output_limit, cleanup_phase, cleanup_verified;
    uint64_t deadline;
    size_t emitted;
};
struct agent_state {
    char session[33], line[DGA_LINE_MAX];
    char wire[16384];
    size_t line_size;
    size_t wire_start, wire_size;
    uint64_t write_deadline;
    uint32_t incoming, outgoing, last_command, child_mask;
    int hello, shutting_down, shutdown_acked, cancel_intent, output_limited;
    struct agent_job job;
};

static long broadcast(int signal)
{
    /* kern_sig.c: non-POSIX -1 excludes PID1, P_SYSTEM and this agent.
     * Includes zombies; ESRCH proves even adopted descendants were reaped.
     * This is safe only in this exclusive init + agent + one-job RAM root.
     */
    return rt_call(37, -1, signal, 0, 0, 0, 0);
}

static int milliseconds(uint64_t *value)
{
    struct agent_timeval now = {0, 0, 0};
    if (rt_call(116, (long)&now, 0, 0, 0, 0, 0) < 0 || now.seconds < 0 ||
        now.microseconds < 0 || now.microseconds >= 1000000) return -1;
    *value = (uint64_t)now.seconds * 1000 + (unsigned)now.microseconds / 1000;
    return 0;
}

static int nonblocking(int fd)
{
    long flags = rt_call(92, fd, 3, 0, 0, 0, 0);
    return flags < 0 || rt_call(92, fd, 4, flags | 4, 0, 0, 0) < 0 ? -1 : 0;
}

static int configure_console(void)
{
    struct agent_termios attributes;
    if (rt_call(54, 0, UINT32_C(0x40487413), (long)&attributes, 0, 0, 0) < 0) return -1;
    attributes.input = 0;
    attributes.output = 0;
    /* CREAD | CS8 | CLOCAL; preserve speed, change no console ownership. */
    attributes.control = UINT64_C(0x00000b00) | UINT64_C(0x00008000);
    attributes.local = 0;
    attributes.characters[16] = 1; attributes.characters[17] = 0;
    if (rt_call(54, 0, UINT32_C(0x80487414), (long)&attributes, 0, 0, 0) < 0) return -1;
    return nonblocking(0) || nonblocking(1) ? -1 : 0;
}

static int send_frame(struct agent_state *state, uint32_t command, const char *type,
                      const void *payload, size_t length)
{
    struct dga_frame frame = {.direction = 'G', .command = command, .length = length};
    char line[DGA_LINE_MAX];
    if (!state->outgoing || state->outgoing == UINT32_MAX || length > DGA_PAYLOAD_MAX ||
        rt_copy(frame.session, sizeof(frame.session), state->session) ||
        rt_copy(frame.type, sizeof(frame.type), type)) return -1;
    frame.sequence = state->outgoing++;
    for (size_t i = 0; i < length; i++) frame.payload[i] = ((const unsigned char *)payload)[i];
    size_t size = dga_encode(line, &frame);
    if (!size || size > sizeof(state->wire) - state->wire_size) return -1;
    if (!state->wire_size) {
        uint64_t now;
        if (milliseconds(&now)) return -1;
        state->write_deadline = now + 3000;
    }
    if (state->wire_start + state->wire_size + size > sizeof(state->wire)) {
        for (size_t i = 0; i < state->wire_size; i++) state->wire[i] = state->wire[state->wire_start + i];
        state->wire_start = 0;
    }
    for (size_t i = 0; i < size; i++) state->wire[state->wire_start + state->wire_size + i] = line[i];
    state->wire_size += size;
    return 0;
}

static int write_pending(struct agent_state *state, uint64_t now)
{
    if (!state->wire_size) return 0;
    long size = rt_write(1, state->wire + state->wire_start, state->wire_size);
    if (size == -4 || size == -35) return now >= state->write_deadline ? -1 : 0;
    if (size <= 0 || (size_t)size > state->wire_size) return -1;
    state->wire_start += (size_t)size; state->wire_size -= (size_t)size;
    state->write_deadline = now + 3000;
    if (!state->wire_size) state->wire_start = 0;
    return 0;
}

static int begin_cleanup(struct agent_state *state, uint64_t now)
{
    struct agent_job *job = &state->job;
    if (job->cleanup_phase) return 0;
    long result = broadcast(15);
    if (result < 0 && result != -3) return -1;
    job->cleanup_phase = 1;
    job->deadline = now + 1000;
    return 0;
}

static void close_captures(struct agent_job *job)
{
    for (int i = 0; i < 2; i++) if (job->output[i] >= 0) {
        rt_close(job->output[i]); job->output[i] = -1;
    }
}

static int fail(struct agent_state *state, const char *code)
{
    (void)send_frame(state, state->job.id, "ERROR", code, rt_len(code));
    if (state->job.id) {
        (void)broadcast(9);
        /* This final bounded wait never authorizes another command. */
        for (unsigned i = 0; i < 30; i++) {
            int status;
            (void)rt_call(7, state->job.pid, (long)&status, 1, 0, 0, 0);
            if (broadcast(0) == -3) break;
            struct agent_timeval delay = {0, 100000, 0};
            (void)rt_call(93, 0, 0, 0, 0, (long)&delay, 0);
            (void)broadcast(9);
        }
        close_captures(&state->job);
    }
    /* Preserve partial-write cursors while delivering the fatal diagnostic. */
    uint64_t now, deadline;
    if (!milliseconds(&now)) {
        deadline = now + 3000;
        while (state->wire_size && now < deadline) {
            uint32_t writes = 2;
            struct agent_timeval delay = {0, 100000, 0};
            long result = rt_call(93, 2, 0, (long)&writes, 0, (long)&delay, 0);
            if (milliseconds(&now) || (result < 0 && result != -4)) break;
            if (result > 0 && write_pending(state, now)) break;
        }
    }
    return 1;
}

static const char *start_job(struct agent_state *state, const struct dga_frame *frame)
{
    char arguments[DGA_PAYLOAD_MAX], *argv[DGA_ARGS_MAX + 1];
    unsigned argc = 0;
    if (!frame->length || frame->payload[frame->length - 1] || frame->payload[0] != '/') return "exec_argv";
    for (size_t i = 0; i < frame->length; i++) arguments[i] = (char)frame->payload[i];
    for (size_t i = 0; i < frame->length;) {
        if (argc == DGA_ARGS_MAX) return "exec_argv";
        argv[argc++] = arguments + i;
        while (arguments[i]) i++;
        i++;
    }
    argv[argc] = 0;
    int capture[2][2] = {{-1, -1}, {-1, -1}};
    long input = rt_open("/etc/empty", RT_RDONLY);
    if (input < 0) return "launch_io";
    for (int i = 0; i < 2; i++) if (rt_pipe(capture[i]) < 0) {
        rt_close((int)input);
        for (int j = 0; j < 2; j++) for (int k = 0; k < 2; k++)
            if (capture[j][k] >= 0) rt_close(capture[j][k]);
        return "launch_io";
    }
    long pid = rt_fork();
    if (!pid) {
        if (rt_dup2((int)input, 0) < 0 || rt_dup2(capture[0][1], 1) < 0 ||
            rt_dup2(capture[1][1], 2) < 0) rt_exit(126);
        rt_close((int)input);
        for (int i = 0; i < 2; i++) for (int j = 0; j < 2; j++) rt_close(capture[i][j]);
        if (rt_call(48, 3, (long)&state->child_mask, 0, 0, 0, 0) < 0 ||
            rt_call(82, 0, 0, 0, 0, 0, 0) < 0 || rt_chdir("/") < 0) rt_exit(126);
#ifdef DARWIN_APPLE_USERLAND
#ifdef DARWIN_WRITABLE_STORAGE
        char *env[] = {"PATH=/bin:/sbin", "PWD=/", "HOME=/data", "TERM=dumb",
                       "TERMINFO=/etc/terminfo", "HISTFILE=/data/.zsh_history", "HISTSIZE=1000", "SAVEHIST=1000", 0};
#else
        char *env[] = {"PATH=/bin:/sbin", "PWD=/", "HOME=/", "TERM=dumb",
                       "TERMINFO=/etc/terminfo", 0};
#endif
#else
        char *env[] = {"PATH=/bin", "PWD=/", "HOME=/", "TERM=dumb", 0};
#endif
        long result = rt_call(59, (long)argv[0], (long)argv, (long)env, 0, 0, 0);
        rt_error("agent exec", result);
        rt_exit(result == -2 ? 127 : 126);
    }
    rt_close((int)input);
    for (int i = 0; i < 2; i++) rt_close(capture[i][1]);
    if (pid < 0) {
        for (int i = 0; i < 2; i++) rt_close(capture[i][0]);
        return "launch_fork";
    }
    state->job = (struct agent_job){.id = frame->command, .pid = pid,
                                   .output = {capture[0][0], capture[1][0]}};
    state->last_command = frame->command;
    /* Child does this before exec; tolerate the parent racing exec/exit. */
    long result = rt_call(82, pid, pid, 0, 0, 0, 0);
    if (result < 0 && result != -13 && result != -3) return "launch_group";
    for (int i = 0; i < 2; i++)
        if (capture[i][0] >= 32 || nonblocking(capture[i][0])) return "launch_io";
    unsigned char payload[] = {(unsigned char)((unsigned long)pid >> 24), (unsigned char)((unsigned long)pid >> 16),
                               (unsigned char)((unsigned long)pid >> 8), (unsigned char)pid};
    return send_frame(state, frame->command, "STARTED", payload, sizeof(payload)) ? "transport_write" : 0;
}

static const char *accept_frame(struct agent_state *state, const struct dga_frame *frame, uint64_t now)
{
    if (frame->direction != 'H') return "frame_direction";
    if (!state->hello) {
        if (!rt_equal(frame->type, "HELLO") || frame->command || frame->sequence != 1 || frame->length)
            return "hello_required";
        rt_copy(state->session, sizeof(state->session), frame->session);
        state->incoming = 2; state->hello = 1;
        static const char capabilities[] = "exec,streams,cancel,shutdown";
        return send_frame(state, 0, "HELLO", capabilities, sizeof(capabilities) - 1) ? "transport_write" : 0;
    }
    if (!rt_equal(frame->session, state->session)) return "stale_session";
    if (frame->sequence != state->incoming || state->incoming == UINT32_MAX) return "frame_sequence";
    state->incoming++;
    if (state->shutting_down) return "shutdown_pending";
    if (rt_equal(frame->type, "EXEC")) {
        if (state->output_limited) return "exec_after_limit";
        if (state->cancel_intent) return "exec_after_cancel";
        if (state->job.id) return "exec_busy";
        if (!frame->command || frame->command != state->last_command + 1 || frame->command > DGA_COMMAND_MAX)
            return "stale_command";
        return start_job(state, frame);
    }
    if (rt_equal(frame->type, "CANCEL")) {
        if (frame->length || !frame->command || frame->command != state->last_command) return "stale_command";
        state->cancel_intent = 1;
        unsigned char accepted = state->job.id ? 1 : 0;
        if (send_frame(state, frame->command, "CANCELLED", &accepted, 1)) return "transport_write";
        if (accepted) {
            state->job.cancelled = 1;
            if (begin_cleanup(state, now)) return "cleanup_signal";
        }
        return 0;
    }
    if (rt_equal(frame->type, "SHUTDOWN")) {
        if (frame->command || frame->length) return "shutdown_payload";
        state->shutting_down = 1;
        if (state->job.id) {
            state->job.cancelled = 1;
            if (begin_cleanup(state, now)) return "cleanup_signal";
        }
        return 0;
    }
    return "frame_type";
}

static const char *read_console(struct agent_state *state, uint64_t now)
{
    char data[256];
    long size = rt_read(0, data, sizeof(data));
    if (size == -4 || size == -35) return 0;
    if (size <= 0 || size > (long)sizeof(data)) return "transport_read";
    for (long i = 0; i < size; i++) {
        if (data[i] == '\n') {
            size_t count = state->line_size;
            while (count && state->line[count - 1] == '\r') count--;
            struct dga_frame frame;
            const char *error = dga_decode(&frame, state->line, count);
            state->line_size = 0;
            if (error) return error;
            error = accept_frame(state, &frame, now);
            if (error) return error;
        } else {
            if (state->line_size + 1 >= sizeof(state->line)) return "frame_length";
            state->line[state->line_size++] = data[i];
        }
    }
    return 0;
}

static const char *read_output(struct agent_state *state, int stream, uint64_t now)
{
    struct agent_job *job = &state->job;
    unsigned char data[DGA_PAYLOAD_MAX];
    long size = rt_read(job->output[stream], data, sizeof(data));
    if (size == -4 || size == -35) return 0;
    if (size < 0 || size > (long)sizeof(data)) return "stream_read";
    if (!size) {
        rt_close(job->output[stream]); job->output[stream] = -1; job->eof[stream] = 1;
        return send_frame(state, job->id, stream ? "ERR_EOF" : "OUT_EOF", 0, 0) ? "transport_write" : 0;
    }
    size_t emit = (size_t)size;
    if (emit > DGA_OUTPUT_MAX - job->emitted) emit = DGA_OUTPUT_MAX - job->emitted;
    if (emit && send_frame(state, job->id, stream ? "ERR" : "OUT", data, emit)) return "transport_write";
    job->emitted += emit;
    if (emit != (size_t)size) {
        job->output_limit = 1;
        state->output_limited = 1;
        if (begin_cleanup(state, now)) return "cleanup_signal";
    }
    return 0;
}

static const char *update_job(struct agent_state *state, uint64_t now)
{
    struct agent_job *job = &state->job;
    if (!job->leader_done) {
        long result = rt_call(7, job->pid, (long)&job->status, 1, 0, 0, 0);
        if (result == job->pid) job->leader_done = 1;
        else if (result < 0 && result != -4) return "child_wait";
        else if (result > 0) return "child_wait";
    }
    if (job->leader_done && begin_cleanup(state, now)) return "cleanup_signal";
    if (!job->cleanup_phase) return 0;
    long remaining = broadcast(0);
    if (remaining == -3) job->cleanup_verified = 1;
    else if (remaining < 0) return "cleanup_probe";
    if (job->leader_done && job->eof[0] && job->eof[1] && job->cleanup_verified) {
        int signal = job->status & 127;
        if (signal == 127 || signal > 31) return "child_status";
        unsigned char payload[] = {(unsigned char)(signal ? 1 : 0),
                                   (unsigned char)(signal ? signal : (job->status >> 8) & 255),
                                   (unsigned char)job->cancelled, 1, (unsigned char)job->output_limit};
        if (send_frame(state, job->id, "EXIT", payload, sizeof(payload))) return "transport_write";
        *job = (struct agent_job){.output = {-1, -1}};
        return 0;
    }
    if (now >= job->deadline) {
        if (job->cleanup_phase == 2) return "cleanup_timeout";
        long result = broadcast(9);
        if (result < 0 && result != -3) return "cleanup_signal";
        job->cleanup_phase = 2; job->deadline = now + 2000;
    } else if (job->cleanup_phase == 2 && !job->cleanup_verified) {
        long result = broadcast(9);
        if (result < 0 && result != -3) return "cleanup_signal";
    }
    return 0;
}

int agent_main(void)
{
    struct agent_state state = {.session = "00000000000000000000000000000000", .outgoing = 1,
                                .job = {.output = {-1, -1}}};
    /* No signal trampoline: block SIGPIPE in agent only; child restores mask. */
    const uint32_t pipe_mask = UINT32_C(1) << (13 - 1);
    if (rt_call(48, 1, (long)&pipe_mask, (long)&state.child_mask, 0, 0, 0) < 0) return 1;
    if (configure_console()) return fail(&state, "console_setup");
    static const char banner[] = "\nDARWIN:AGENT:READY:1\n";
    for (size_t i = 0; i < sizeof(banner) - 1; i++) state.wire[i] = banner[i];
    state.wire_size = sizeof(banner) - 1;
    uint64_t initial_time;
    if (milliseconds(&initial_time)) return 1;
    state.write_deadline = initial_time + 3000;
    for (;;) {
        uint64_t now;
        if (milliseconds(&now)) return fail(&state, "clock_read");
        if (state.shutting_down && !state.job.id) {
            if (!state.shutdown_acked) {
                if (send_frame(&state, 0, "SHUTDOWN", 0, 0)) return fail(&state, "transport_write");
                state.shutdown_acked = 1;
            }
            if (!state.wire_size) {
                (void)rt_call(55, 8, 0, 0, 0, 0, 0);
                return fail(&state, "shutdown_returned");
            }
        }
        if (state.wire_size && now >= state.write_deadline) return fail(&state, "transport_timeout");
        uint32_t reads = 1;
        uint32_t writes = state.wire_size ? 2 : 0;
        int max_fd = 0;
        if (writes) max_fd = 1;
        /* Reserve queue capacity for control, EOF, EXIT and fatal records. */
        if (state.job.id && state.wire_size < 8192) for (int i = 0; i < 2; i++) if (state.job.output[i] >= 0) {
            reads |= UINT32_C(1) << state.job.output[i];
            if (state.job.output[i] > max_fd) max_fd = state.job.output[i];
        }
        struct agent_timeval delay = {0, 100000, 0};
        long result = rt_call(93, max_fd + 1, (long)&reads, (long)&writes, 0, (long)&delay, 0);
        if (result < 0 && result != -4) return fail(&state, "transport_select");
        if (milliseconds(&now)) return fail(&state, "clock_read");
        if (result > 0 && (writes & 2) && write_pending(&state, now)) return fail(&state, "transport_write");
        const char *error = 0;
        if (result > 0 && (reads & 1)) error = read_console(&state, now);
        if (error) return fail(&state, error);
        if (state.job.id) {
            for (int i = 0; i < 2; i++) if (result > 0 && state.job.output[i] >= 0 &&
                (reads & (UINT32_C(1) << state.job.output[i]))) {
                error = read_output(&state, i, now);
                if (error) return fail(&state, error);
            }
            error = update_job(&state, now);
            if (error) return fail(&state, error);
        }
    }
}
