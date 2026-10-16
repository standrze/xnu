# Direct public API VZ trials

This opt-in harness compiles the local `ContainerizationDarwin` sources into its
own library and signed executable. It does not use SwiftPM or replace the CLI.
Building and `--help` never start a VM. Explicit trial invocations start one
dedicated foreground VM and require a fresh output directory.

```sh
bash experiments/darwin-container/agent/host-trial/build.sh
experiments/darwin-container/agent/host-trial/.build/host-trial --help
experiments/darwin-container/agent/host-trial/.build/host-trial --self-test
```

Run against a prepared managed-agent image, supplying the same optional EFI
variable-store template as the CLI trials:

```sh
experiments/darwin-container/agent/host-trial/.build/host-trial missing-exec \
  --boot-disk /absolute/managed.img --output-dir /absolute/new-missing-session \
  --variable-store /absolute/template.vars --timeout-seconds 30

experiments/darwin-container/agent/host-trial/.build/host-trial cancel-task \
  --boot-disk /absolute/managed.img --output-dir /absolute/new-task-cancel-session \
  --variable-store /absolute/template.vars --timeout-seconds 30 \
  --cancel-after-seconds 1
```

`missing-exec` submits direct argv `["/this-path-is-missing"]`, covering the
agent's exec failure rather than a shell's command lookup. `cancel-task` submits
`["/bin/agent-escape"]`, observes STARTED in raw serial for timing, waits the
requested delay, and calls `Task.cancel()` on the public `DarwinGuestSession.run`
task. The session independently validates all frame evidence and enforces its
normal bounded cancellation/shutdown path.

The executable prints the session result JSON. Exit zero means the intended
negative trial was observed with completed protocol and actual guest stop:
exit 127 for missing exec, or accepted cancellation and verified cleanup for
task cancellation. It does not mean the guest command succeeded. All raw serial,
separate command output, lifecycle files and result JSON remain in the session
directory. Inspect those records for full acceptance evidence.

The native `--self-test` checks every fragmentation boundary of LF, CRLF and
CRCRLF banner/STARTED input without launching a VM. An optional existing
`serial.bin` path checks timing detection against captured serial evidence.
The timing observer splits on LF bytes and accepts only complete lines; Swift
grapheme splitting cannot safely separate a CRLF sequence using a LF character.
