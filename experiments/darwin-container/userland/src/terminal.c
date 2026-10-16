/* SPDX-License-Identifier: BSD-2-Clause
 * Project PTY session/relay. Uses XNU's real /dev/ptmx and tty line discipline;
 * this is not a userspace emulation of terminal signals or foreground groups.
 */
#include "runtime.h"
#include <sys/ioctl.h>
#include <sys/ttycom.h>
#include <termios.h>
#include <fcntl.h>
#include <sys/wait.h>
#ifdef DARWIN_TERMINAL_FRAMED
#include "terminal_protocol.h"
#endif
#ifdef DARWIN_SHARED_GPU
#include "gpu_relay.h"
#endif

_Static_assert(sizeof(struct termios)==72, "Darwin arm64 termios ABI");
struct terminal_timeval { int64_t seconds; int32_t microseconds, padding; };
_Static_assert(sizeof(struct terminal_timeval)==16, "Darwin arm64 timeval ABI");

struct terminal_buffer { unsigned char bytes[4096]; size_t start, size; };

static long terminal_ioctl(int fd, unsigned long request, void *value)
{
    return rt_call(54, fd, (long)request, (long)value, 0, 0, 0);
}

static int terminal_nonblocking(int fd)
{
    long flags=rt_call(92, fd, F_GETFL, 0, 0, 0, 0);
    return flags<0 || rt_call(92, fd, F_SETFL, flags|O_NONBLOCK, 0, 0, 0)<0;
}

#ifndef DARWIN_TERMINAL_FRAMED
static int terminal_receive(int fd, struct terminal_buffer *buffer)
{
    if (buffer->size) return 0;
    long count=rt_read(fd, buffer->bytes, sizeof buffer->bytes);
    if (count==-4 || count==-35) return 0;
    if (count<=0) return -1;
    buffer->start=0; buffer->size=(size_t)count;
    return 0;
}
#endif

static int terminal_send(int fd, struct terminal_buffer *buffer)
{
    if (!buffer->size) return 0;
    long count=rt_write(fd, buffer->bytes+buffer->start, buffer->size);
    if (count==-4 || count==-35) return 0;
    if (count<=0 || (size_t)count>buffer->size) return -1;
    buffer->start+=(size_t)count; buffer->size-=(size_t)count;
    return 0;
}

#ifdef DARWIN_TERMINAL_FRAMED
struct terminal_wire {
    char session[33], line[DGT_LINE_MAX];
    size_t used;
    uint32_t host_sequence, guest_sequence;
};

/* Consume only one frame: input backpressure cannot drop the next frame. */
static int terminal_frame_read(struct terminal_wire *wire, struct dgt_frame *frame)
{
    for (;;) {
        char c;
        long n=rt_read(0, &c, 1);
        if (n==-4) continue;
        if (n==-35) return 0;
        if (n!=1) return -1;
        if (c=='\n') {
            while (wire->used && wire->line[wire->used-1]=='\r') wire->used--;
            const char *error=dgt_decode(frame, wire->line, wire->used);
            wire->used=0;
            if (error || frame->direction!='H' || wire->host_sequence==UINT32_MAX ||
                frame->sequence!=wire->host_sequence+1) return -1;
            if (wire->host_sequence && !rt_equal(frame->session, wire->session)) return -1;
            wire->host_sequence=frame->sequence;
            return 1;
        }
        if (wire->used==sizeof wire->line-1) return -1;
        wire->line[wire->used++]=c;
    }
}

static int terminal_frame_queue(struct terminal_wire *wire, struct terminal_buffer *buffer,
                                const char *type, const unsigned char *payload, size_t size)
{
    if (buffer->size || size>DGT_PAYLOAD_MAX || wire->guest_sequence==UINT32_MAX) return -1;
    struct dgt_frame frame;
    frame.direction='G'; frame.sequence=++wire->guest_sequence; frame.length=size;
    if (rt_copy(frame.session, sizeof frame.session, wire->session) ||
        rt_copy(frame.type, sizeof frame.type, type)) return -1;
    for (size_t i=0; i<size; i++) frame.payload[i]=payload[i];
    buffer->start=0;
    buffer->size=dgt_encode((char *)buffer->bytes, &frame);
    return buffer->size ? 0 : -1;
}

static int terminal_frame_flush(struct terminal_buffer *buffer)
{
    for (unsigned tries=0; buffer->size && tries<1000; tries++) {
        uint32_t writes=2;
        struct terminal_timeval timeout={.microseconds=10000};
        long result=rt_call(93, 2, 0, (long)&writes, 0, (long)&timeout, 0);
        if (result==-4) continue;
        if (result<0 || ((writes&2) && terminal_send(1, buffer))) return -1;
    }
    return buffer->size ? -1 : 0;
}

static int terminal_frame_size(const struct dgt_frame *frame, struct winsize *size)
{
    if (frame->length!=4) return -1;
    size->ws_row=(unsigned short)((frame->payload[0]<<8)|frame->payload[1]);
    size->ws_col=(unsigned short)((frame->payload[2]<<8)|frame->payload[3]);
    return !size->ws_row || !size->ws_col ? -1 : 0;
}
#endif

int terminal_main(char **env)
{
    struct termios original;
    long result=terminal_ioctl(0, TIOCGETA, &original);
    if (result<0) { rt_error("PTY console attributes", result); return 126; }
    struct termios raw=original;
    raw.c_iflag=0; raw.c_oflag=0; raw.c_lflag=0;
    raw.c_cc[VMIN]=1; raw.c_cc[VTIME]=0;
    result=terminal_ioctl(0, TIOCSETA, &raw);
    if (result<0) { rt_error("PTY console raw mode", result); return 126; }
    long master=rt_open("/dev/ptmx", RT_RDWR|O_NOCTTY);
    int status=126;
    long child=-1;
#ifdef DARWIN_SHARED_GPU
    struct gpu_relay gpu={.fd=-1};
#endif
    if (master<0 || master>=32) { rt_error("PTY master", master); goto done; }
    char name[128]={0};
    if (terminal_ioctl((int)master, TIOCPTYGRANT, 0)<0 ||
        terminal_ioctl((int)master, TIOCPTYUNLK, 0)<0 ||
        terminal_ioctl((int)master, TIOCPTYGNAME, name)<0 || name[127]) {
        rt_put(2, "PTY grant/unlock/name failed\n"); goto done;
    }
    long slave=rt_open(name, RT_RDWR|O_NOCTTY);
    if (slave<0) { rt_error("PTY slave", slave); goto done; }
    struct winsize size={.ws_row=24, .ws_col=80};
#ifdef DARWIN_TERMINAL_FRAMED
    struct terminal_wire wire;
    wire.used=0; wire.host_sequence=wire.guest_sequence=0;
    rt_put(1, "DARWIN:PTY:READY:1\n");
    struct dgt_frame hello;
    if (terminal_frame_read(&wire, &hello)!=1 || !rt_equal(hello.type, "HELLO") ||
        terminal_frame_size(&hello, &size) || rt_copy(wire.session, sizeof wire.session, hello.session)) {
        rt_close((int)slave); rt_put(2, "PTY handshake failed\n"); goto done;
    }
#endif
    result=terminal_ioctl((int)slave, TIOCSWINSZ, &size);
    if (result<0) { rt_close((int)slave); rt_error("PTY window size", result); goto done; }
#ifdef DARWIN_SHARED_GPU
    if (gpu_relay_open(&gpu)) { rt_close((int)slave); rt_put(2,"GPU local endpoint failed\n"); goto done; }
#endif
    child=rt_fork();
    if (!child) {
#ifdef DARWIN_SHARED_GPU
        rt_close(gpu.fd);
#endif
        rt_close((int)master);
        if (rt_call(147, 0, 0, 0, 0, 0, 0)<0 || terminal_ioctl((int)slave, TIOCSCTTY, 0)<0)
            rt_exit(126);
        int group=(int)rt_getpid();
        if (terminal_ioctl((int)slave, TIOCSPGRP, &group)<0) rt_exit(126);
        for (int i=0; i<3; i++) if (rt_dup2((int)slave, i)<0) rt_exit(126);
        if (slave>2) rt_close((int)slave);
        if (rt_chdir("/data")<0) rt_exit(126);
        char *argv[]={"/bin/zsh", "-i", 0};
        result=rt_call(59, (long)argv[0], (long)argv, (long)env, 0, 0, 0);
        rt_error("PTY exec zsh", result); rt_exit(126);
    }
    rt_close((int)slave);
    if (child<0) { rt_error("PTY fork", child); goto done; }
    if (terminal_nonblocking((int)master) || terminal_nonblocking(0) || terminal_nonblocking(1)) goto stop;
    struct terminal_buffer input, output;
    input.start=input.size=output.start=output.size=0;
#ifdef DARWIN_TERMINAL_FRAMED
    if (terminal_frame_queue(&wire, &output, "HELLO", hello.payload, hello.length)) goto stop;
#else
    rt_put(1, "DARWIN:PTY:READY 80x24\n");
#endif
    int child_done=0, child_status=0, failed=0;
    for (;;) {
        if (!child_done) {
            result=rt_call(7, child, (long)&child_status, WNOHANG, 0, 0, 0);
            if (result==child) child_done=1;
            else if (result<0 && result!=-4) { failed=1; break; }
        }
        uint32_t readfds=(!input.size && !child_done
#ifdef DARWIN_TERMINAL_FRAMED
                          && !output.size
#endif
                          ? 1U : 0U) |
                          (!output.size ? 1U<<(unsigned)master : 0U);
        uint32_t writefds=(output.size ? 2U : 0U) | (input.size ? 1U<<(unsigned)master : 0U);
        int highest=(int)master;
#ifdef DARWIN_SHARED_GPU
        if (!gpu.pending && !output.size && !child_done) readfds|=1U<<(unsigned)gpu.fd;
        if (gpu.fd>highest) highest=gpu.fd;
        if (gpu_relay_expired(&gpu)) {failed=1;break;}
#endif
        struct terminal_timeval timeout={.microseconds=10000};
        result=rt_call(93, highest+1, (long)&readfds, (long)&writefds, 0, (long)&timeout, 0);
        if (result==-4) continue;
        if (result<0) { failed=1; break; }
        if ((writefds&2U) && terminal_send(1, &output)) { failed=1; break; }
        if ((writefds&(1U<<(unsigned)master)) && terminal_send((int)master, &input)) {
            if (!child_done) failed=1;
            break;
        }
#ifdef DARWIN_TERMINAL_FRAMED
        if (readfds&1U) {
            struct dgt_frame frame;
            int received=terminal_frame_read(&wire, &frame);
            if (received<0) { failed=1; break; }
            if (received) {
                if (rt_equal(frame.type, "INPUT") && frame.length) {
                    for (size_t i=0; i<frame.length; i++) input.bytes[i]=frame.payload[i];
                    input.start=0; input.size=frame.length;
                } else if (rt_equal(frame.type, "RESIZE")) {
                    if (terminal_frame_size(&frame, &size) ||
                        terminal_ioctl((int)master, TIOCSWINSZ, &size)<0 ||
                        terminal_frame_queue(&wire, &output, "SIZE", frame.payload, frame.length)) {
                        failed=1; break;
                    }
                }
#ifdef DARWIN_SHARED_GPU
                else if (rt_equal(frame.type,"GPURES")) {
                    if (gpu_relay_reply(&gpu,frame.payload,frame.length)) {failed=1;break;}
                }
#endif
                else { failed=1; break; }
            }
        }
#ifdef DARWIN_SHARED_GPU
        if ((readfds&(1U<<(unsigned)gpu.fd)) && !output.size && !gpu.pending) {
            unsigned char payload[256];size_t length=0;
            int received=gpu_relay_request(&gpu,payload,&length);
            if (received<0 || (received && terminal_frame_queue(&wire,&output,"GPU",payload,length))) {failed=1;break;}
        }
#endif
        /* A resize ACK may now own the wire buffer even if select also marked the PTY readable. */
        int output_eof=0;
        if ((readfds&(1U<<(unsigned)master)) && !output.size) {
            unsigned char payload[DGT_PAYLOAD_MAX];
            long count=rt_read((int)master, payload, sizeof payload);
            if (count>0) {
                if (terminal_frame_queue(&wire, &output, "OUTPUT", payload, (size_t)count)) { failed=1; break; }
            } else if (count!=-4 && count!=-35) output_eof=1;
        }
        if (output_eof) {
#else
        if ((readfds&1U) && terminal_receive(0, &input)) { failed=1; break; }
        if ((readfds&(1U<<(unsigned)master)) && terminal_receive((int)master, &output)) {
#endif
            if (!child_done) {
                result=rt_wait(child, &child_status);
                if (result!=child) failed=1;
                child_done=1;
            }
            break;
        }
    }
    status=failed ? 126 : ((child_status&127) ? 128+(child_status&127) : (child_status>>8)&255);
    if (!child_done) goto stop;
#ifdef DARWIN_TERMINAL_FRAMED
    if (!failed) {
        unsigned char code=(unsigned char)status;
        if (terminal_frame_queue(&wire, &output, "EXIT", &code, 1) || terminal_frame_flush(&output)) status=126;
    }
#endif
    goto done;
stop:
    /* This process owns only the PTY shell's new session/process group. */
    if (child>0) { (void)rt_call(37, -child, 9, 0, 0, 0, 0); (void)rt_wait(child, &status); }
    status=126;
done:
#ifdef DARWIN_SHARED_GPU
    gpu_relay_close(&gpu);
#endif
    if (master>=0) rt_close((int)master);
    (void)terminal_ioctl(0, TIOCSETA, &original);
    return status;
}
