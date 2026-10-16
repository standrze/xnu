/* SPDX-License-Identifier: BSD-2-Clause
 * Original Apple path/TTY logic; all filesystem, TTY, signal and random input
 * callbacks below are test-only. No terminal, filesystem or secrets are read.
 * Locale is the actual namespaced Apple group with host-reserved-key mapping.
 */
#define main original_locale_contract_main
#include "ssh_locale_host.c"
#undef main
#include <assert.h>
#include <dirent.h>
#include <fcntl.h>
#include <paths.h>
#include <readpassphrase.h>
#include <signal.h>
#include <stdarg.h>
#include <sys/stat.h>
#include <termios.h>
#include <unistd.h>

extern char *fixture_mkdtemp(char *);
extern char *fixture_readpassphrase(const char *,char *,size_t,int);
extern char *fixture_devname_r(dev_t,mode_t,char *,int);
static unsigned random_calls,stat_calls,mkdir_calls;
static int stat_error,base_is_directory,mkdir_error,collisions;
static char paths[8][128];
uint32_t fixture_arc4random_uniform(uint32_t bound)
{ assert(bound==62);random_calls++;return 0; }
int fixture_fstatat(int fd,const char *p,struct stat *s,int flags)
{
    assert(fd==AT_FDCWD&&strcmp(p,"/fixture")==0&&flags==0);stat_calls++;
    if(stat_error){errno=stat_error;return -1;}
    memset(s,0,sizeof *s);s->st_mode=base_is_directory?S_IFDIR:S_IFREG;return 0;
}
int fixture_mkdirat(int fd,const char *p,mode_t mode)
{
    assert(fd==AT_FDCWD&&mode==0700&&mkdir_calls<8&&strlen(p)<128);
    strcpy(paths[mkdir_calls++],p);
    if(collisions){collisions--;errno=EEXIST;return -1;}
    if(mkdir_error){errno=mkdir_error;return -1;}return 0;
}
static void temp_reset(void)
{random_calls=stat_calls=mkdir_calls=0;stat_error=mkdir_error=collisions=0;base_is_directory=1;errno=0;}
static unsigned temp_tests(void)
{
    char p[128];temp_reset();strcpy(p,"/fixture/XXXXXX");
    assert(fixture_mkdtemp(p)==p&&!strcmp(p,"/fixture/000000")&&random_calls==6&&stat_calls==1&&mkdir_calls==1);
    temp_reset();collisions=2;strcpy(p,"/fixture/XXXXXX");
    assert(fixture_mkdtemp(p)==p&&mkdir_calls==3&&!strcmp(paths[0],"/fixture/000000")&&
           !strcmp(paths[1],"/fixture/100000")&&!strcmp(paths[2],"/fixture/200000"));
    temp_reset();stat_error=EACCES;strcpy(p,"/fixture/XXXXXX");
    assert(!fixture_mkdtemp(p)&&errno==EACCES&&!mkdir_calls&&!strcmp(p,"/fixture/000000"));
    temp_reset();base_is_directory=0;strcpy(p,"/fixture/XXXXXX");
    assert(!fixture_mkdtemp(p)&&errno==ENOTDIR&&!mkdir_calls);
    temp_reset();mkdir_error=EROFS;strcpy(p,"/fixture/XXXXXX");
    assert(!fixture_mkdtemp(p)&&errno==EROFS&&mkdir_calls==1);
    temp_reset();collisions=1;strcpy(p,"/fixture/no-template");
    assert(!fixture_mkdtemp(p)&&errno==EEXIST&&random_calls==0&&mkdir_calls==1);
    temp_reset();char large[PATH_MAX+1];memset(large,'a',PATH_MAX);large[PATH_MAX]=0;
    assert(!fixture_mkdtemp(large)&&errno==ENAMETOOLONG&&!stat_calls&&!mkdir_calls);
    return 7;
}

static int open_error,read_error,signal_to_raise,opens,reads,closes,writes,signal_calls;
static int terminal_calls,restore_retry,kill_calls,last_kill;
static const char *input;static size_t input_at;static char output[256];static size_t output_at;
static struct termios initial,installed;
static struct sigaction actions[NSIG];
/* Match the actual original noncancel declarations after native namespacing. */
int fixture_open(const char *,int,...) __asm("_fixture_open$NOCANCEL");
ssize_t fixture_read(int,void *,size_t) __asm("_fixture_read$NOCANCEL");
ssize_t fixture_write(int,const void *,size_t) __asm("_fixture_write$NOCANCEL");
int fixture_close(int) __asm("_fixture_close$NOCANCEL");
int fixture_open(const char *p,int flags,...)
{assert(!strcmp(p,_PATH_TTY)&&flags==(O_RDWR|O_CLOEXEC));opens++;if(open_error){errno=open_error;return -1;}return 9;}
ssize_t fixture_read(int fd,void *p,size_t n)
{
    assert((fd==0||fd==9)&&n==1);reads++;
    if(signal_to_raise){int s=signal_to_raise;signal_to_raise=0;assert(actions[s].sa_handler);actions[s].sa_handler(s);errno=EINTR;return -1;}
    if(read_error){errno=read_error;return -1;}
    if(!input[input_at])return 0;*(char *)p=input[input_at++];return 1;
}
ssize_t fixture_write(int fd,const void *p,size_t n)
{assert((fd==2||fd==9)&&output_at+n<sizeof output);writes++;memcpy(output+output_at,p,n);output_at+=n;return (ssize_t)n;}
int fixture_close(int fd){assert(fd==9);closes++;return 0;}
int fixture_tcgetattr(int fd,struct termios *t){assert(fd==9);*t=initial;return 0;}
int fixture_tcsetattr(int fd,int option,const struct termios *t)
{
    assert(fd==9&&option==(TCSAFLUSH|TCSASOFT));terminal_calls++;
    if(terminal_calls>1&&restore_retry){restore_retry=0;errno=EINTR;return -1;}
    installed=*t;return 0;
}
int fixture_sigaction(int s,const struct sigaction *a,struct sigaction *old)
{assert(s>0&&s<NSIG&&a);signal_calls++;if(old)*old=actions[s];actions[s]=*a;return 0;}
pid_t fixture_getpid(void){return 1234;}
int fixture_kill(pid_t pid,int sig){assert(pid==1234);kill_calls++;last_kill=sig;return 0;}
static void tty_reset(const char *text)
{
    open_error=read_error=signal_to_raise=opens=reads=closes=writes=signal_calls=0;
    terminal_calls=restore_retry=kill_calls=last_kill=0;input=text;input_at=output_at=0;
    memset(output,0,sizeof output);memset(actions,0,sizeof actions);
    memset(&initial,0,sizeof initial);initial.c_lflag=ECHO|ECHONL;initial.c_cc[VSTATUS]='x';
    installed=initial;errno=0;
}
static unsigned tty_tests(void)
{
    char b[16];tty_reset("Abc\n");
    assert(fixture_readpassphrase("Prompt:",b,sizeof b,0)==b&&!strcmp(b,"Abc")&&opens==1&&closes==1);
    assert(!strcmp(output,"Prompt:\n")&&terminal_calls==2&&!memcmp(&initial,&installed,sizeof initial)&&signal_calls==18);
    tty_reset("AbC\r");assert(fixture_readpassphrase("",b,sizeof b,RPP_STDIN|RPP_FORCELOWER)==b&&!strcmp(b,"abc")&&!opens&&!closes&&!writes&&!terminal_calls);
    tty_reset("AbC\n");assert(fixture_readpassphrase("",b,sizeof b,RPP_STDIN|RPP_FORCEUPPER)==b&&!strcmp(b,"ABC"));
    tty_reset("\301b\n");assert(fixture_readpassphrase("",b,sizeof b,RPP_STDIN|RPP_SEVENBIT)==b&&!strcmp(b,"Ab"));
    tty_reset("abcdef\n");assert(fixture_readpassphrase("",b,3,RPP_STDIN)==b&&!strcmp(b,"ab")&&reads==7);
    tty_reset("abcdef\n");assert(fixture_readpassphrase("",b,1,RPP_STDIN)==b&&!strcmp(b,"")&&reads==7);
    tty_reset("x\n");assert(!fixture_readpassphrase("",b,0,0)&&errno==EINVAL&&!opens&&!reads&&!signal_calls);
    tty_reset("x\n");open_error=ENOENT;assert(!fixture_readpassphrase("",b,sizeof b,RPP_REQUIRE_TTY)&&errno==ENOTTY&&opens==1&&!reads&&!signal_calls);
    tty_reset("ok\n");open_error=ENOENT;assert(fixture_readpassphrase("P",b,sizeof b,0)==b&&!strcmp(b,"ok")&&!closes&&!terminal_calls&&!strcmp(output,"P"));
    tty_reset("");assert(fixture_readpassphrase("",b,sizeof b,RPP_STDIN)==b&&!strcmp(b,"")&&reads==1);
    tty_reset("ignored");read_error=EIO;assert(!fixture_readpassphrase("P",b,sizeof b,0)&&errno==EIO&&closes==1&&terminal_calls==2&&!memcmp(&installed,&initial,sizeof initial));
    tty_reset("ok\n");restore_retry=1;assert(fixture_readpassphrase("",b,sizeof b,0)==b&&!strcmp(b,"ok")&&terminal_calls==3&&!memcmp(&installed,&initial,sizeof initial));
    tty_reset("ok\n");signal_to_raise=SIGINT;assert(!fixture_readpassphrase("",b,sizeof b,0)&&errno==EINTR&&kill_calls==1&&last_kill==SIGINT&&!memcmp(&installed,&initial,sizeof initial));
    tty_reset("ok\n");signal_to_raise=SIGTSTP;assert(fixture_readpassphrase("",b,sizeof b,0)==b&&!strcmp(b,"ok")&&kill_calls==1&&last_kill==SIGTSTP&&opens==2&&closes==2);
    tty_reset("ok\n");assert(fixture_readpassphrase("",b,sizeof b,RPP_ECHO_ON)==b&&!strcmp(b,"ok")&&output_at==0);
    return 15;
}

static int directory_error,dir_closed,dir_index;
static unsigned dir_mode;static dev_t dir_device;
static struct dirent entry;
static char directory_token;
DIR *fixture_opendir(const char *p)
{assert(!strcmp(p,_PATH_DEV));if(directory_error){errno=EACCES;return NULL;}return (DIR *)&directory_token;}
struct dirent *fixture_readdir(DIR *d)
{assert(d==(DIR *)&directory_token);if(dir_index++)return NULL;memset(&entry,0,sizeof entry);strcpy(entry.d_name,"tty-fixture");entry.d_namlen=11;return &entry;}
int fixture_closedir(DIR *d){assert(d==(DIR *)&directory_token);dir_closed++;return 0;}
int fixture_lstat(const char *p,struct stat *s)
{assert(!strcmp(p,"/dev/tty-fixture"));memset(s,0,sizeof *s);s->st_mode=dir_mode;s->st_rdev=dir_device;return 0;}
static unsigned device_tests(void)
{
    char buf[32];for(unsigned i=0;i<5;i++){
        directory_error=i==1;dir_closed=dir_index=0;dir_mode=i==2?S_IFBLK:S_IFCHR;dir_device=i==3?4:3;
        memset(buf,0x55,sizeof buf);char *result=fixture_devname_r(3,S_IFCHR,buf,i==4?3:32);
        if(i==0)assert(result==buf&&!strcmp(buf,"tty-fixture"));else assert(!result&&buf[0]==0x55);
        assert(dir_closed==(i!=1));
    }return 5;
}
int main(int argc,char **argv)
{
    char *args[]={"locale",NULL};if(original_locale_contract_main(1,args))return 1;
    unsigned a=temp_tests(),b=tty_tests(),c=device_tests();
    if(argc>1&&!strcmp(argv[1],"bad-expected"))return 29;
    printf("APPLE_TTY_TEMP PASS TEMP=%u TTY=%u DEVICE=%u IO_SIGNAL_ENTROPY_DOUBLES\n",a,b,c);return 0;
}
