# Bounded smoke of the actual Apple-source executables, not zsh builtins.
emulate -R zsh
setopt errexit pipefail
export LC_ALL=C
fail() { print -u2 -r -- "UTIL_FAIL:$1"; exit 1; }
check() { [[ "$2" == "$3" ]] || fail "$1"; print -r -- "UTIL_PASS:$1"; }
root=/data/apple-utility-smoke
[[ ! -e $root ]] || fail preexisting-test-directory
/bin/mkdir -p -m 700 $root/a/b
builtin cd $root
check pwd "$(/bin/pwd)" "$root"
check basename "$(/bin/basename /example/file.txt .txt)" file
check dirname "$(/bin/dirname /example/file.txt)" /example
check echo "$(/bin/echo -n hello)" hello
export APPLE_UTILITY_PROOF=real-source
check printenv "$(/bin/printenv APPLE_UTILITY_PROOF)" real-source
check uname "$(/bin/uname -s)" Darwin
/bin/sleep 0.01
print -r -- UTIL_PASS:sleep
print -r -- $'alpha\nalpha\nbeta' > input
check cat "$(/bin/cat input)" $'alpha\nalpha\nbeta'
check head "$(/bin/head -n 2 input)" $'alpha\nalpha'
check wc "$(/bin/wc -l < input | /bin/uniq)" '       3'
check wc-words "$(/bin/wc -w < input)" '       3'
check wc-bytes "$(/bin/wc -c < input)" '      17'
check uniq "$(/bin/uniq input)" $'alpha\nbeta'
/bin/uniq input > unique
check comm "$(/bin/comm -12 unique unique)" $'alpha\nbeta'
check fold "$(print -rn -- abcdef | /bin/fold -w 3)" $'abc\ndef'
check rev "$(/bin/head -n 1 input | /bin/rev)" ahpla
check tee "$(print -r -- tee-proof | /bin/tee tee-file)" tee-proof
check tee-file "$(/bin/cat tee-file)" tee-proof
/bin/touch -t 202401020304.05 touched
[[ -f touched ]] || fail touch
print -r -- UTIL_PASS:touch
/bin/chmod u=rw,go= touched
listing=$(/bin/ls -ln touched)
[[ $listing == '-rw------- '* ]] || fail chmod-ls
print -r -- UTIL_PASS:chmod-ls
/bin/ln input hardlink
/bin/ln -s input symlink
check ln-hard "$(/bin/cat hardlink)" "$(<input)"
check ln-symbolic "$(/bin/cat symlink)" "$(<input)"
/bin/cp input copied
check cp "$(/bin/cat copied)" "$(<input)"
print -r -- nested > a/b/content
/bin/cp -R a tree-copy
check cp-recursive "$(/bin/cat tree-copy/b/content)" nested
/bin/rm -r tree-copy
[[ ! -e tree-copy ]] || fail rm-recursive
/bin/rm copied symlink hardlink touched tee-file input unique a/b/content
/bin/rmdir a/b a
[[ ! -e a ]] || fail rmdir
print -r -- UTIL_PASS:filesystem-cleanup
if /bin/cat definitely-missing > /etc/empty; then fail readonly-root; fi
if /bin/cat definitely-missing; then fail error-status; fi
print -r -- UTIL_PASS:error-status
builtin cd /data
/bin/rmdir $root
print -r -- APPLE_USERLAND_PERSISTENCE > /data/apple-userland-proof
print -r -- UTIL_ALL_OK
