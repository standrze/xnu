# Apple-source command-line userland

The normal Mac-hosted workspace now boots source-built XNU and Apple-published
zsh 5.9 with **23 additional/source-replacement external utilities**:

```
basename cat chmod comm cp dirname echo fold head ln ls mkdir
printenv pwd rev rm rmdir sleep tee touch uname uniq wc
```

They are static ARM64 executables compiled here, not copies of `/bin` from macOS,
Homebrew binaries, or renamed downstream bootstrap programs. zsh may still use
its own builtins for `echo`, `pwd`, etc.; `/bin/echo` and `/bin/pwd` explicitly
select the new external tools. PID 1, the managed agent, recovery `/bin/sh`,
`poweroff` and orchestration remain labeled project implementations.

## Use

From the repository root:

```sh
./experiments/darwin-container/darwin-workspace development
```

Inside the real guest shell:

```sh
mkdir -p /data/example
cd /data/example
print -r -- $'apple\napple\ndarwin' > input
cp input copied
chmod 600 copied
cat copied | uniq | wc -l
ls -ln copied
```

`/data` and shell history survive clean `exit`/restart. The RAM root remains
read-only. The current workspace package is `userland/build/darwin-workspace-0.4.2`;
the old 0.2.0 package and existing named disks were not replaced or reformatted.

New managed workload packages inherit these same utility bytes automatically:

```sh
./experiments/darwin-container/darwin-workload pack \
  experiments/darwin-container/examples/apple-userland/workload.json \
  --output /private/tmp/my-apple-userland-package
./experiments/darwin-container/darwin-workload run \
  /private/tmp/my-apple-userland-package --name first-run
```

Choose a new package directory and unique run name. The ready-built example is
`userland/build/apple-userland-workload-0.4.1`. Runtime 0.4.0 uses the new kernel
pin and utilities; existing runtime-0.3.0 packages are unchanged. This remains
one XNU VM per workload, not shared-kernel Linux/OCI containers.

## Official sources and adaptations

Exact pins are in [`userland/apple-utilities.sources.lock.json`](userland/apple-utilities.sources.lock.json).
Command sources are from Apple's published
[file_cmds-82](https://github.com/apple-oss-distributions/file_cmds/tree/file_cmds-82),
[text_cmds-47](https://github.com/apple-oss-distributions/text_cmds/tree/text_cmds-47), and
[shell_cmds-81](https://github.com/apple-oss-distributions/shell_cmds/tree/shell_cmds-81).
These historical releases fit the current static runtime; this is not a claim
to have built the latest macOS userland. The underlying selected Libc,
libplatform and Libm source pins remain in the existing runtime manifests.

The builder checks original checkout commits/cleanliness and selected Libc
files against pinned Apple archive bytes. Its manifest records each original
and generated-source hash, compiler/link command, static executable inspection,
runtime archive hashes, private headers and bounded syscall ABI. Every tool
links without unresolved imports or host LibSystem/dyld linkage. The package
retains original selected sources, generated adaptations and component notices.

Recorded adaptations include:

- Static entry/argv capture so original Apple `getopt`/error routines see the
  real argument vector; additional real XNU filesystem syscalls use Apple's
  `SYS.h` implementation.
- Old SDK/private header spellings, an unused `setmode` return-type correction,
  and 64-bit `wc` formatting using the selected Libc's supported `ll` modifier.
- Compiler hardware `floor`/`fabs` lowering; Apple's published ARM `ilogb` C code.
- `mkdir -p` accepts an existing read-only ancestor only after the original
  `stat`/directory checks. Newly requested read-only directories still fail.
- Apple Libc-391 `localtime`/`mktime`/`asctime` replace the older utility calendar
  closure; the original nonthreaded branch is selected. This fixes the observed
  `touch -t` hang without replacing Apple's calendar algorithms.
- Original Apple locale/conversion code with explicit C/POSIX-only integration.
  Project UID/GID rendering returns actual numeric IDs; no account database or
  invented user/group names are supplied.

The VM-only isolated kernel snapshot allows 96 RAM-root nodes, within the same
16-KiB metadata page. Host tooling defaults remain 32, as does the Pi header;
expanded images require the matching compiled VM kernel. The current workspace
uses 49 nodes and approximately 4.4 MiB, below the unchanged 8-MiB loader limit.

## Build and evidence

Build the command set into a new directory:

```sh
python3 experiments/darwin-container/userland/build_apple_utilities.py \
  --output-dir /private/tmp/new-apple-utilities
```

The three command checkouts must be present under `userland/upstream/apple-TAG`
at the pinned tags. Existing runtime archives must match the qualified zsh
manifest. `--resume` accepts only an incomplete utility build, never a completed
one. The frozen working build is `userland/build/apple-utilities-5`.

The root builder accepts `--apple-utilities MANIFEST --ramroot-max-nodes 96`;
the kernel builder accepts `--ramroot-max-nodes 96` for a **new** isolated VM
snapshot. The successful kernel is `kernel/build/vzgeneric-xs4lhgpl`, and root
build is `userland/build/workspace-root-apple-utilities-4`. Full build commands
and hashes are retained in package provenance; do not resume/rewrite qualified
historical kernels merely to add utilities.

Focused execution evidence:

- [Consolidated verification](results/2026-10-12-apple-userland/verification.json):
  identical source-built command bytes in both package types, default-32 versus
  opt-in-96 root validation, preserved old-package integrity, and final managed
  application output. Six focused existing packager/runner controls also pass.

- [`results/2026-10-12-apple-utilities-trial-4/verification.json`](results/2026-10-12-apple-utilities-trial-4/verification.json):
  all 23 actual guest executables exercised, text pipelines, recursive copying
  and removal, symbolic/hard links, permissions, timestamp setting, negative
  command status, read-only root, two clean shutdowns and saved-file readback.
- `results/2026-10-12-apple-userland-workload-final`: one offline packaged job
  using the same utilities, separate captured streams, complete managed cleanup
  and actual guest stop.

Earlier trial directories retain the bulk-terminal-input failure, the observed
read-only-ancestor issue and older calendar hang. They are not passing evidence.
The builders' `guest_executed: false` fields describe build-only evidence; the
separate trial records carry actual guest proof. No soak/full option suite was run.

## Still outside this increment

No full LibSystem/dyld, pthread runtime, Unicode locale suite, account/configuration
daemon, package manager or in-guest compiler has been added. `mv`, `cut`, `grep`,
`sed`, `sort`, `awk`, archive/build tools and service management are follow-ons,
not claimed available. Copying does not promise modern macOS ACL/resource-fork/
extended-attribute preservation; `rm -P` is not a secure-erasure guarantee.
The VM still has no proven wall-clock/RTC synchronization, so default file times
can show the guest's epoch clock. Linux/Intel hosts, graphics and shared-kernel
containers remain separate workstreams.
