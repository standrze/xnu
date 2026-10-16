/* SPDX-License-Identifier: BSD-2-Clause
 * Actual generated console ring, original printbuf, actual dispatch and new
 * FIFO guard bodies. pthread/MMIO/formatter/clock doubles are HOST ONLY. */
#include <assert.h>
#include <pthread.h>
#include <sched.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdarg.h>
#include <string.h>
#include <stdatomic.h>
#define RPI5_CONSOLE_RECORDS 1
#define ARM64_BOARD_CONFIG_BCM2712 1
#define PL011_UART 1
#define TRUE 1
#define FALSE 0
#define THREAD_NULL 0
#define SERIAL_CONS_OPS 0
#define SERIAL_CONS_BUF_SIZE 256
#define CPU_CONS_BUF_SIZE 256
#define MAX_FLUSH_SIZE_LOCK_HELD 16
#define MAX_TOTAL_FLUSH_SIZE 1024
#define SERIALMODE_SYNCDRAIN 4
#define CONS_PB_WRITE_NEWLINE 1
#define CONS_PB_CANBLOCK 2
#define STARTUP_SUB_EARLY_BOOT 10
#define __improbable(x) (x)
#define __probable(x) (x)
#define MIN(a,b) ((a)<(b)?(a):(b))
#define LCK_GRP_NULL NULL
#define SCHED_HYGIENE_DEBUG 0
#define MP_DEBUG_KPRINTF(...)
#define OS_LOG_DEFAULT 0
#define OS_LOG_TYPE_DEFAULT 0
#define os_atomic_load(p,o) __atomic_load_n(p,__ATOMIC_ACQUIRE)
#define os_atomic_store(p,v,o) __atomic_store_n(p,v,__ATOMIC_RELEASE)
#define os_atomic_inc(p,o) __atomic_add_fetch(p,1,__ATOMIC_SEQ_CST)
#define os_atomic_dec(p,o) __atomic_sub_fetch(p,1,__ATOMIC_SEQ_CST)
typedef int boolean_t;
typedef void *thread_call_t;
typedef void *thread_call_param_t;
static _Thread_local int irq=1, preempt, interrupt_context, ppl, debug, panicking;
static _Thread_local uintptr_t thread_identity=1;
static _Thread_local int reenter_uart, reenter_console;
static int startup_phase=20, initialized=1, disableConsoleOutput, console_suspended;
static int serialmode, index_console, allow_printf_from_interrupts_disabled_context;
#define kernel_debugger_entry_count debug
static int panic_active(void){return panicking;}
static int ml_get_interrupts_enabled(void){return irq;}
static boolean_t ml_set_interrupts_enabled(boolean_t b){int old=irq;irq=b;return old;}
static int get_preemption_level(void){return preempt;}
static int ml_at_interrupt_context(void){return interrupt_context;}
static int pmap_in_ppl(void){return ppl;}
static uintptr_t current_thread(void){return thread_identity;}
static int is_console_initialized(void){return initialized;}
static int get_cons_ops_index(void){return index_console;}
static void mp_disable_preemption(void){preempt++;}
static void mp_enable_preemption(void){assert(preempt>0);preempt--;}
static void cpu_pause(void){sched_yield();}
static void panic(const char *s){fprintf(stderr,"unexpected panic %s\n",s);abort();}
static int console_lck_grp;
static struct {
    char *buffer; int len,used,nreserved; char *write_ptr,*read_ptr;
    pthread_mutex_t flush_lock,write_lock;
} console_ring;
static void lck_ticket_lock(pthread_mutex_t *m,void *g){(void)g;pthread_mutex_lock(m);preempt++;}
static void lck_ticket_unlock(pthread_mutex_t *m){assert(preempt);preempt--;pthread_mutex_unlock(m);}
static int lck_mtx_try_lock(pthread_mutex_t *m){assert(irq&&!preempt);return pthread_mutex_trylock(m)==0;}
static void lck_mtx_lock(pthread_mutex_t *m){assert(irq&&!preempt);pthread_mutex_lock(m);}
static void lck_mtx_unlock(pthread_mutex_t *m){pthread_mutex_unlock(m);}
static unsigned wire_count,wire_overflows,fifo_occupied,video_count,recursive_refusals;
static char wire[262144];
static int fifo_blocked;
static int slow_fifo;
struct pe_serial_functions { int(*transmit_ready)(void);void(*transmit_data)(uint8_t); };
static int pl011_uart_transmit_ready(void);
static void pl011_uart_transmit_data(uint8_t c);
static struct pe_serial_functions pl011_uart_serial_functions={pl011_uart_transmit_ready,pl011_uart_transmit_data};
#include "pexpert/arm/rpi5_console_uart.inc"
static int pl011_uart_transmit_ready(void){
    if(reenter_uart){reenter_uart=0;assert(!rpi5_console_uart_try('!',&pl011_uart_serial_functions));assert(!irq);recursive_refusals++;}
    return !fifo_blocked && !__atomic_load_n(&fifo_occupied,__ATOMIC_ACQUIRE);
}
static void pl011_uart_transmit_data(uint8_t c){
    if(__atomic_exchange_n(&fifo_occupied,1,__ATOMIC_ACQ_REL)) __atomic_add_fetch(&wire_overflows,1,__ATOMIC_RELAXED);
    unsigned offset=__atomic_fetch_add(&wire_count,1,__ATOMIC_RELAXED);
    assert(offset<sizeof(wire));wire[offset]=(char)c;
    if(slow_fifo)sched_yield();
    __atomic_store_n(&fifo_occupied,0,__ATOMIC_RELEASE);
}
struct console_printbuf_state { int pos,total,flags;char str[SERIAL_CONS_BUF_SIZE]; };
static void _cnputs(char *,int,bool);
static void console_ring_try_empty(bool);
void console_write(char *,int);
void console_printbuf_state_init(struct console_printbuf_state *,int,int);
void console_printbuf_putc(int,void *);
void console_printbuf_clear(struct console_printbuf_state *);
static int __doprnt(const char *fmt,va_list ap,void(*put)(int,void *),void *o,int radix,int log){
    (void)radix;(void)log;char b[4096];int n=vsnprintf(b,sizeof(b),fmt,ap);assert(n>=0&&n<(int)sizeof(b));
    for(int i=0;i<n;i++)put(b[i],o);return n;
}
#include "actual_console_bodies.inc"
static int submit(const char *fmt,...){va_list ap;va_start(ap,fmt);int r=rpi5_console_kprintf_record(fmt,ap);va_end(ap);return r;}
static void _cnputs(char *p,int n,bool poll){
    (void)poll;
    for(int i=0;i<n;i++){
        while(!rpi5_console_uart_try(p[i],&pl011_uart_serial_functions))sched_yield();
        /* Actual optional mirror invokes video AFTER serial. Model a nested
         * log in that callback and verify it cannot wait on its own mutex. */
        assert(!rpi5_console_uart_busy&&irq&&!preempt);video_count++;
        if(reenter_console){reenter_console=0;assert(!submit("recursive\n"));recursive_refusals++;}
    }
}
static int disable_serial_output,disable_kprintf_output,cpu_last_locked;
static unsigned log_calls,raw_calls;
static pthread_mutex_t kprintf_lock=PTHREAD_MUTEX_INITIALIZER;
static int simple_lock_try(pthread_mutex_t *m,void *g){(void)g;return pthread_mutex_trylock(m)==0;}
static void simple_unlock(pthread_mutex_t *m){pthread_mutex_unlock(m);}
static int cpu_number(void){return 0;}
static void raw_putc(char c){while(!rpi5_console_uart_try(c,&pl011_uart_serial_functions))sched_yield();}
static void (*PE_kputc)(char)=raw_putc;
static void raw_adapter(int c,void *o){(void)o;PE_kputc(c);}
static void _doprnt_log(const char *fmt,va_list *ap,void(*put)(char),int radix){(void)put;assert(!irq);raw_calls++;__doprnt(fmt,*ap,raw_adapter,NULL,radix,1);}
static void os_log_with_args(int a,int b,const char *fmt,va_list ap,void *caller){(void)a;(void)b;(void)caller;char s[4096];assert(vsnprintf(s,sizeof(s),fmt,ap)>=0);log_calls++;}
#include "actual_kprintf.inc"
static bool rpi5_terminal_watchdog_enabled,rpi5_gate3_soak_enabled;
static thread_call_t rpi5_terminal_watchdog_call;
static bool rpi5_terminal_console_call_armed;
static int allocate_fail,enable_fail,queued,active,services,run_callout_during_enqueue;
static uint64_t now=10,epoch,terminal_deadline,queued_deadline;
#define THREAD_CALL_PRIORITY_HIGH 1
#define NSEC_PER_SEC 1000000000
static void rpi5_terminal_watchdog_callout(thread_call_param_t,thread_call_param_t);
static thread_call_t thread_call_allocate_with_priority(void(*f)(void*,void*),void *a,int p){(void)f;(void)a;(void)p;return allocate_fail?NULL:(void*)1;}
static void thread_call_free(void *p){assert(p);}
static int pe_rpi5_watchdog_enable_terminal(void){if(enable_fail)return 0;epoch=now;terminal_deadline=now+180;active=1;return 1;}
static int pe_rpi5_watchdog_terminal_active(void){return active&&now<terminal_deadline;}
static void pe_rpi5_watchdog_timer_tick(bool b){assert(b);services++;}
static void clock_interval_to_deadline(int a,int b,uint64_t *p){assert(a==1&&b==NSEC_PER_SEC);*p=now+1;}
static int thread_call_enter_delayed(void *p,uint64_t d){assert(p);assert(d==now+1);queued++;queued_deadline=d;
    if(run_callout_during_enqueue){run_callout_during_enqueue=0;rpi5_terminal_watchdog_callout(0,0);}return 0;}
#include "actual_callout.inc"
static void reset(void){
    irq=1;preempt=interrupt_context=ppl=debug=panicking=0;initialized=1;startup_phase=20;
    disableConsoleOutput=console_suspended=index_console=0;thread_identity=1;
    wire_count=wire_overflows=video_count=recursive_refusals=0;fifo_blocked=slow_fifo=0;
    rpi5_console_drain_thread=0;rpi5_console_uart_busy=0;
    console_ring.used=console_ring.nreserved=0;console_ring.read_ptr=console_ring.write_ptr=console_ring.buffer;
}
static void contexts(void){
    int *bad[]={&disableConsoleOutput,&console_suspended,&preempt,&interrupt_context,&ppl,&debug,&panicking,&index_console};
    for(unsigned i=0;i<sizeof(bad)/sizeof(*bad);i++){reset();*bad[i]=1;assert(!submit("bad\n"));assert(!wire_count);}
    reset();irq=0;assert(!submit("irq\n"));
    reset();initialized=0;assert(!submit("early\n"));
    reset();startup_phase=0;assert(!submit("early\n"));
    reset();thread_identity=0;assert(!submit("threadless\n"));
    reset();rpi5_console_drain_thread=thread_identity;assert(!submit("nested\n"));
    reset();assert(!rpi5_console_write_record(NULL,1));assert(!rpi5_console_write_record("",0));
    assert(!rpi5_console_write_record((const char *)(UINTPTR_MAX-2),4));assert(!rpi5_console_write_record(wire,256));
}
static void records(void){
    reset();reenter_console=1;assert(submit("WATCHDOG_READY %u\n",180));
    assert(wire_count==19&&!memcmp(wire,"WATCHDOG_READY 180\n",19));assert(recursive_refusals==1);
    char longline[1601];memset(longline,'L',1600);longline[1600]=0;
    reset();assert(submit("%s",longline));assert(wire_count==1600&&!memcmp(wire,longline,1600));
    reset();log_calls=raw_calls=0;candidate_kprintf("normal %d\n",42);assert(log_calls==1&&raw_calls==0&&irq);
    irq=0;candidate_kprintf("raw %d\n",7);assert(log_calls==2&&raw_calls==1&&!irq);
    irq=1;disable_kprintf_output=1;unsigned n=wire_count;candidate_kprintf("logonly\n");assert(log_calls==3&&wire_count==n);disable_kprintf_output=0;
}
static void *producer(void *arg){
    thread_identity=(uintptr_t)arg+2;irq=1;
    for(int i=0;i<1000;i++){char b[40];int n=snprintf(b,sizeof(b),"T%lu:%04d:abcdefghijklmnop\n",(unsigned long)(uintptr_t)arg,i);
        if((uintptr_t)arg==3)console_write(b,n);else assert(submit("%s",b));}
    return NULL;
}
static void concurrent_records(void){
    reset();pthread_t t[4];for(uintptr_t i=0;i<4;i++)assert(!pthread_create(&t[i],NULL,producer,(void*)i));
    for(int i=0;i<4;i++)pthread_join(t[i],NULL);console_ring_try_empty(false);
    unsigned seen[4]={0};char *cursor=wire;wire[wire_count]=0;
    for(int i=0;i<4000;i++){unsigned id,seq;int used=0;assert(sscanf(cursor,"T%u:%u:abcdefghijklmnop\n%n",&id,&seq,&used)==2);assert(id<4&&seq==seen[id]++&&used>0);cursor+=used;}
    assert(cursor==wire+wire_count&&!wire_overflows&&video_count==wire_count);
}
static void fifo(void){
    reset();fifo_blocked=1;assert(!rpi5_console_uart_try('a',&pl011_uart_serial_functions));assert(!wire_count&&irq&&!rpi5_console_uart_busy);
    fifo_blocked=0;rpi5_console_uart_busy=1;assert(!rpi5_console_uart_try('a',&pl011_uart_serial_functions));assert(irq);
    rpi5_console_uart_busy=0;reenter_uart=1;assert(rpi5_console_uart_try('a',&pl011_uart_serial_functions));assert(irq&&wire_count==1&&recursive_refusals==1);
    irq=0;assert(rpi5_console_uart_try('b',&pl011_uart_serial_functions));assert(!irq);
    /* Exception escape intentionally bypasses a stale normal owner. */
    panicking=1;rpi5_console_uart_busy=1;assert(rpi5_console_uart_try('p',&pl011_uart_serial_functions));assert(rpi5_console_uart_busy==1);
    rpi5_console_uart_busy=0;
}
static void *uart_producer(void *arg){
    irq=1;thread_identity=(uintptr_t)arg+2;
    for(int i=0;i<1000;i++)while(!rpi5_console_uart_try((char)('A'+(uintptr_t)arg),&pl011_uart_serial_functions))sched_yield();
    assert(irq&&!preempt);return NULL;
}
static void fifo_contention(void){
    reset();slow_fifo=1;pthread_t threads[4];
    for(uintptr_t i=0;i<4;i++)assert(!pthread_create(&threads[i],NULL,uart_producer,(void*)i));
    for(int i=0;i<4;i++)pthread_join(threads[i],NULL);
    assert(wire_count==4000&&!wire_overflows&&!rpi5_console_uart_busy);
    unsigned n[4]={0};for(unsigned i=0;i<wire_count;i++){assert(wire[i]>='A'&&wire[i]<='D');n[wire[i]-'A']++;}
    for(int i=0;i<4;i++)assert(n[i]==1000);
    /* Original split check/store allows both writers to observe the last
     * free slot. Explicit FIFO model preserves the resulting old overflow. */
    reset();assert(pl011_uart_transmit_ready());assert(pl011_uart_transmit_ready());
    fifo_occupied=1;pl011_uart_transmit_data('X');assert(wire_overflows==1);
}
static void callouts(void){
    reset();allocate_fail=1;assert(!rpi5_terminal_watchdog_start());assert(!queued&&!active);
    allocate_fail=0;enable_fail=1;assert(!rpi5_terminal_watchdog_start());assert(!queued&&!active);
    enable_fail=0;assert(rpi5_terminal_watchdog_start());assert(queued==1&&queued_deadline==11&&epoch==10&&terminal_deadline==190);
    assert(rpi5_terminal_console_thread_owner());irq=0;assert(!rpi5_terminal_console_thread_owner());rpi5_terminal_watchdog_callout(0,0);assert(!services);
    irq=1;interrupt_context=1;assert(!rpi5_terminal_console_thread_owner());interrupt_context=0;
    rpi5_terminal_console_call_armed=false;rpi5_terminal_watchdog_callout(0,0);assert(!services);rpi5_terminal_console_call_armed=true;
    void *held=rpi5_terminal_watchdog_call;rpi5_terminal_watchdog_call=NULL;
    assert(!rpi5_terminal_console_thread_owner());rpi5_terminal_watchdog_callout(0,0);assert(!services);rpi5_terminal_watchdog_call=held;
    now=11;rpi5_terminal_watchdog_callout(0,0);assert(services==1&&queued==2&&epoch==10&&terminal_deadline==190);
    now=190;rpi5_terminal_watchdog_callout(0,0);assert(services==1&&queued==2);
    assert(!rpi5_terminal_watchdog_start());
    /* Model the earliest possible execution after enqueue.  Armed state must
     * already be visible, so the first service runs and requeues itself. */
    rpi5_terminal_watchdog_enabled=false;rpi5_terminal_console_call_armed=false;
    rpi5_terminal_watchdog_call=NULL;active=services=queued=0;now=10;
    run_callout_during_enqueue=1;assert(rpi5_terminal_watchdog_start());
    assert(services==1&&queued==2&&rpi5_terminal_console_call_armed&&epoch==10&&terminal_deadline==190);
}
int main(void){
    static char storage[1024];console_ring.buffer=storage;console_ring.len=sizeof(storage);
    pthread_mutex_init(&console_ring.flush_lock,NULL);pthread_mutex_init(&console_ring.write_lock,NULL);
    contexts();records();concurrent_records();fifo();fifo_contention();callouts();
    puts("CONSOLE_RECORD PASS ACTUAL_RING_PRINTBUF_DISPATCH HOST_ONLY_MMIO_FORMATTER_CLOCK NO_HARDWARE");return 0;
}
