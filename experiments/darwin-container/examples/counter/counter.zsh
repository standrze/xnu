# This application uses the real, source-built Apple-distributed zsh.
set -e
[[ $PWD == /data && $HOME == /data && $ZSH_VERSION == 5.9 ]]
[[ $1 == 'argument with spaces' && $2 == "literal ' quote; \$HOME" ]]
[[ $LITERAL == "quote ' and \$HOME; not evaluated" ]]
integer count=0
if [[ -f /data/count ]]; then count=$(</data/count); fi
(( count += 1 ))
print -r -- $count > /data/count
print -r -- "DARWIN_WORKLOAD:zsh=${ZSH_VERSION}:count=${count}:cwd=${PWD}"
print -r -- "$WORKLOAD_MESSAGE"
print -u2 -r -- 'separate stderr from Darwin workload'
/bin/uname
# Opt-in qualification only; ordinary counter packages always exit normally.
if [[ $DARWIN_PACKAGE_TRIAL == 1 ]]; then
  if (( count == 3 )); then exit 7; fi
  if (( count >= 4 )); then /bin/sleep 120; fi
fi
