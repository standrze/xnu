# Raw file-ABI diagnostic, prepared but not installed

Historical preparation below. The diagnostic is now installed and separately
Pi-executed; see [physical result, current media baseline and next correction](GATE6-STAT-PHYSICAL.md).
The strict mount-marker trial remains failed; no zsh fix is claimed.

2026-10-12. This follows the [physical zsh result](GATE6-PHYSICAL-ZSH.md).
Interactive zsh passed; its script loader still fails. This checkpoint prepares
the next finite diagnosis, not a fix or a new Pi runtime result. Gate 4 remains
held and the installed zsh/recovery image is unchanged.

## Implementation

`tools/rpi5/user/statprobe.c` is a separate static executable, not a replacement
for zsh or the recovery shell. It directly uses Darwin access (33), stat64 (338),
lstat64 (340), fstat64 (339), open (5), fcntl (92), read (3) and close (6).
There is no libc stat wrapper, file/device write, mount, reboot or kernel change.
Its only writes are diagnostic output to inherited stdout/stderr.

Fixed targets: `/etc/zsh-smoke.zsh`, `/etc/motd`, directory `/etc`, and absent
negative control `/etc/statprobe-missing`. Arbitrary arguments are refused.
Each metadata call reports its actual signed result and all 144 output bytes,
initially filled with A5. Sixteen-byte canaries precede/follow the buffer.
Successful metadata reports the actual mode at offset 4 and its regular/directory
interpretation. A wrong type is never replaced with a fabricated type.

For both files, separately test O_RDONLY and O_RDONLY|O_NOCTTY, reporting actual
open, fstat64, F_GETFD/F_GETFL and F_DUPFD(minimum 10) results. Read up to 16 bytes
from the duplicate and then the original to expose shared offset behavior; close
only descriptors actually acquired. Negative errno results remain evidence.
Buffer damage or a suspicious duplicate stops subsequent diagnosis.
`END:DIAGNOSTIC_ONLY`/exit zero means bounded diagnostic completion, **not** syscall,
script, POSIX, networking or Gate 6 acceptance.

The frozen zsh's linked `_stat` was independently disassembled: syscall 338.
Its fcntl adapter reads a variadic uintptr_t; kernel F_DUPFD casts its argument
to int. These facts do not prove the runtime cause. Do not modify the frozen VM
capsule or guess a kernel patch before collecting raw results.

## Distinct preserved-root artifacts

Builder: `tools/rpi5/prepare_statprobe_root.py`. It pins the physically executed
24-node zsh root, adds only `/bin/statprobe`, and verifies every existing file
and mode. Default init still starts recovery `/bin/sh`. Compiler explicitly
targets Cortex-A76; SDK stat size/offsets and fcntl/open constants are asserted.
Static linkage has no unresolved symbols.

Use **`build/rpi5/statprobe-root-20261012-v2`**:

- Executable SHA256: `a5f7121221bc2ffafb91b599bf2bcc1a6003e8c88da00cc855b398a38fa47917`.
- Root: 1,441,792 bytes, 25 nodes, SHA256
  `5644490c8969d930ad706101ab0656dcfafac78846aca51933f2eb3ec128cc23`.
- Root manifest SHA256: `af34dc5936541586b3ed4ecd0a81860995527757aec81811f89d4f6ab09f54b2`.

The earlier non-v2 directory is a historical build before tightening immediate
stop behavior after canary damage; retained, not overwritten or selected.
Neither root has been installed or executed on the Pi.

Boot package **`build/rpi5/bl33-probe-cijenc9s`** reuses the unchanged proven shell
kernel; no kernel rebuild:

- Image: 18,057,920 bytes, SHA256
  `822e52de88303be9edfe20dec51d14fe1476a0604c77040b56d6254f1a953e99`.
- Loader manifest SHA256: `4f1841f2cf0a2881d0e94e3c2897613db8b32e69dcfdbb390ca8f144ba48ad0b`.
- Preflight: `build/rpi5/statprobe-package-preflight-20261012.json`, **29 checks**
  passed for reconstruction/pins, recovery/zsh preservation, actual ELF/raw
  correspondence/entry, loader source/output and diagnostic SDK/source hashes,
  declaration-only topology, disabled storage/MMIO/reset/DMA and C-frame budget.

Seven focused tests cover the real ARM link/root preservation plus host models:
open profiles, shared-offset observations, errno preservation, wrong type,
buffer-overrun stops, descriptor alias, usage, collision/hash/output-reuse
rejection and package pin rejection. None substitutes for Pi evidence.

## Next physical step

Fresh SSH to `192.168.4.23` timed out. That does not prove OS, power, current
serial output or eventual SSD fallback. No serial/media/power operation occurred
for this checkpoint and no live recorder remains.

After SSD Linux is actually verified on `/dev/nvme0n1p2`, derive a new installer
from the current protected baseline/full backup chain, not older installers'
former hashes. Preserve the installed zsh image separately. Run the new package
preflight; arm an exclusive recorder before one software SD reboot. Require
fresh exact image extent, 25-node/1,441,792-byte root and recovery nonce before
`/bin/statprobe`. Capture bounded raw output and another recovery nonce/prompt.
No unchanged-image repeat or soak is needed.

Do not infer cause from just `[[ -f ]]` or zero buffers. Compare access,
stat/lstat/fstat raw modes, plain-vs-NOCTTY open, duplication and actual bytes.
Choose a kernel/VFS, descriptor or userland ABI fix only after that evidence;
then rerun original script and interactive acceptance. Ethernet work remains
independent of this diagnosis and Gate 4's spare-card hold.
