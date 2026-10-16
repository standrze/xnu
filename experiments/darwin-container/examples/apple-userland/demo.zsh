emulate -R zsh
setopt errexit pipefail
/bin/mkdir -p /data/apple-userland-demo
builtin cd /data/apple-userland-demo
print -r -- $'apple\napple\ndarwin' > input
/bin/cp input copied
/bin/chmod 600 copied
/bin/ls -ln copied
lines=$(/bin/cat copied | /bin/uniq | /bin/wc -l)
[[ $lines == '       2' ]] || exit 1
print -r -- "APPLE_USERLAND_WORKLOAD:zsh=${ZSH_VERSION}:unique-lines=${lines// /}"
/bin/rm copied input
/bin/uname -s
