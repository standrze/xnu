# Persistent Darwin workspace 0.4.2

The current Mac environment now has a named, persistent workspace running our
source-built XNU and real Apple-source zsh 5.9. The normal launcher incorporates
the newer PTY and network capabilities. The older frozen workload 0.1.0 remains
a separate historical package.

The default now also includes 23 original Apple-source external commands,
including `ls`, `cp`, `rm`, `mkdir`, `rmdir`, `chmod`, `touch`, `ln`, `cat`, `head`,
`wc`, `uniq`, `comm`, `fold`, `rev`, `tee`, `basename`, `dirname`, `echo`, `pwd`,
`printenv`, `uname`, and `sleep`. These replace the corresponding bootstrap
commands in this profile; the recovery `/bin/sh`, PID 1 and agent remain
downstream code. [Sources, adaptations, evidence and limits](APPLE-USERLAND.md).
Existing named data disks are reused, never reformatted by this update.

## Use it

From the repository root, open the default workspace:

```sh
./experiments/darwin-container/darwin-workspace
```

Or choose a name; its disk is created automatically on first use:

```sh
./experiments/darwin-container/darwin-workspace development
```

You arrive in real zsh at `/data`, with editing, history, job control and the
Apple-source DHCP client already run. `/data` and history belong to that named
workspace and survive a normal restart. `/` remains the read-only RAM root.
Use `exit` to save history, unmount HFS+ and shut down the VM, then run the same
command to reopen it. Networking is acquired again on every boot; inspect it
with `/bin/ifconfig en0 inet` and `/bin/route -n get default`.

```sh
./experiments/darwin-container/darwin-workspace --list
./experiments/darwin-container/darwin-workspace development --status
./experiments/darwin-container/darwin-workspace another --create
```

`--create` prepares a disk without booting. `--workspace-root DIRECTORY` selects
another private storage directory. The default is
`experiments/darwin-container/workspaces/`, excluded from root Git tracking.
Each name has its own 128-MiB journaled HFS+ `data.raw`, metadata, lock and `runs/`
directory. The lock rejects a simultaneous launch of the same workspace; the
VM framework also locks the image. Status checks the actual held lock rather
than trusting a stale metadata record.

The session deadline is one hour by default; `--timeout-seconds 1..3600` changes
it. Exit before the deadline for normal history save and storage shutdown.
If automatic DHCP fails, the shell remains available and
`$DARWIN_NETWORK_STATUS` is `failed`; run `/bin/dhcpctl` to retry. Successful boot
setup reports `ready`. DHCP renewal is future work, so long-running sessions do
not yet have a full lease service.

The existing bounded Metal interface is optional:

```sh
./experiments/darwin-container/darwin-workspace development --shared-gpu
```

This enables the already qualified `/bin/gpuctl` typed compute API. The workspace
trial below did not repeat GPU qualification.

## Original workspace 0.2.0 changes

- A named workspace retains its writable disk automatically instead of asking
  the user to copy and remember disposable session images.
- PID 1 invokes the existing source-built Apple bootp/DHCP command before the
  shell. The existing Apple resolver, route and ifconfig programs remain in the
  root image. This adds startup orchestration, not a replacement DHCP protocol.
- The package contains a zero-filled, reserved EFI entropy slot. Before each
  launch, the launcher verifies the immutable inputs, copies the EFI disk and
  fills that slot with 256 fresh bytes from the host OS. The loader rejects a
  missing zero seed. The VZ CLI creates a fresh EFI variable store per run.
- The isolated VM kernel uses `sizeof(native_rand)` when clearing that buffer,
  fixing the inherited 192-byte-buffer/256-byte-clear mismatch. The shared root
  source and earlier qualified kernel artifacts were not rewritten by that fix.
- Host interruption is forwarded to the VM CLI, which owns shutdown; the
  launcher waits and records the actual result. A failed or forced stop is never
  labeled a clean persistence result.

The original package is `userland/build/darwin-workspace-0.2.0/`; the current
default is `userland/build/darwin-workspace-0.4.2/`. Their manifests record the
immutable images, host executable, source pins and build provenance. The launcher
uses the already qualified host CLI; no installed Apple container service is
needed. Generated run images and EFI state are private files and contain that
run's entropy; seed bytes are not logged. The template itself has no provisioned
boot seed and cannot be launched directly.

## Verification and completion

The [focused verification report](results/2026-10-12-workspace/verification.json)
contains the two successful launcher sessions, their exact package manifest hash
and independently observed network traffic. Preserved terminal and VM result
files are hashed in [the completion record](results/2026-10-12-workspace/completion.json).
An earlier failed formatting attempt and a trial-parser failure remain under
`userland/build/`; neither is counted as a passing VM trial.

| Requirement | Actual evidence |
| --- | --- |
| One normal launch reaches real zsh/PTY | Both launches reported `WS_READY:ready:5.9:/data:/data`; foreground Ctrl-C returned 130 |
| Named data and history persist | First guest wrote a fresh token and a zsh history command; second guest read both from the same disk |
| Network automatically configures | Both boots recorded DHCP leases and `DARWIN:WORKSPACE:NETWORK_READY` before the shell; no manual DHCP command in the trial |
| Networking actually works | Original Apple resolver completed fresh-token DNS/TCP, independently witnessed from the guest address on the host |
| Safe normal stop and reopen | Both sessions observed terminal exit 0 and actual guest shutdown through the init unmount/poweroff path |
| Concurrent attachment is rejected | A second invocation of the running name failed with `already running`; status reported the held lock |
| Names have independent data | Separate disk inodes; the other workspace's disk hash did not change |
| Fresh boot entropy | Both actual boot images had different nonzero 256-byte seed slots; immutable zero-seed template remained unchanged |
| Seed clearing size is corrected | New successful kernel source/build record includes `cc_clear(sizeof(native_rand), native_rand)` |

No soak was added. This remains a single-vCPU experimental development VM with
a selected static runtime, a small command set and bounded compute. It does not
yet provide full LibSystem/dyld, a compiler inside the guest, production isolation,
shared-kernel containers or power-loss recovery. The existing terminal controls
and GPU coverage are documented in [the earlier completion audit](COMPLETION-AUDIT.md).

## Rebuild this local package

Source changes are in `userland/workspace_launcher.py`,
`userland/package_workspace.py`, the automatic-network option in
`userland/build.py`/`src/init.c`, the loader entropy-slot metadata and the isolated
kernel build fix. Exact inputs are retained in the package's `provenance/`.
Build a distinct storage/network kernel and an automatic-network framed root,
then an EFI loader using `build_loader.py --storage --network`. Package them with:

```sh
python3 experiments/darwin-container/userland/package_workspace.py \
  --kernel-build experiments/darwin-container/kernel/build/vzgeneric-1fx0koif \
  --root-build experiments/darwin-container/userland/build/workspace-root-1 \
  --loader-build /private/tmp/darwin-vz-loader-hgx6num8 \
  --output /private/tmp/darwin-workspace-rebuild-0.2.0
```

The output must not exist. Kernel/SDK providers and original Apple source pins
are the existing source-build inputs, not installed macOS runtime binaries. The
loader build directory above is local and temporary; rebuild it if absent.
`create_data_disk.py` formats only a new regular VM image. To recheck an actual
package, use `userland/workspace_trial.py`; its launcher must point at that same
package. The completed local trial used the top-level launcher shown above.
