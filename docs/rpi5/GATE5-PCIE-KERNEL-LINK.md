# Complete PCI/FDT kernel linkage — 2026-10-12

This is a distinct, **uninstalled complete kernel**, not another relocatable
component and not physical PCIe/Ethernet acceptance. The original Apple PCI
family, real reset/RESCAL/SerDes/UBUS transport, watchdog owner and retained-FDT
kernel path now resolve together with the tested kernel's original source-built
crypto, pthread and IOStorageFamily/HFS providers.

## Artifact and reproduction

```
python3 tools/rpi5/build_pcie_kernel.py \
  --output-dir build/rpi5/pcie-kernel-NEW
PYTHONPATH=tools/rpi5/tests:tools/rpi5 python3 -m unittest \
  tools.rpi5.tests.test_pcie_kernel -v
python3 tools/rpi5/compare_native_macho.py \
  build/rpi5/pcie-kernel-20261012-final/kernel.pcie-fdt
```

The builder requires a new direct `build/rpi5` child or a fresh temporary
directory. It cannot overwrite existing outputs or write into source/accepted
object directories. No kernel source, original object, loader, RAM root,
installed image, SD card or Pi state is modified.

- Kernel: `build/rpi5/pcie-kernel-20261012-final/kernel.pcie-fdt`
- Size: **17,936,240 bytes**.
- Kernel SHA256: `7fa90127ece43ba19f8817fe43113381cfc652faa919520e7ac56cdc6a43d101`.
- Manifest SHA256: `39628890ad03a7d255e1a9d9e36fadf21435542c6005d73834053fbd7fe3d52c`.
- Manifest: **2,228 input + 13 generated entries = 2,241 unique files**.
- Real complete link and development strip both succeed, with zero undefined
  symbols and exactly the original replay's ten linker warnings; none added.
- Native real-loader parser/materializer agrees with the host inventory:
  **18 segments, 105,819 local relocations, 18,989,056 materialized bytes**.
  The direct entry branch resolves to the actual `start_first_cpu` symbol.
  This runs in host buffers, not Pi physical memory.

## Baseline and intentional integration

Before adding anything, the builder replays the original actual `.LDFLAGS`,
object filelist, sentinel/version/non-LTO objects, three source-built providers
and exact SDK firehose archive. Every byte of the resulting development kernel
matches the accepted `674e6a76...` kernel **except its 16-byte LC_UUID payload**.
The manifest records both UUIDs and explicitly reports whole-file equality as
false. There is no broad normalization: a single changed executable byte fails
the replay, and both complete Mach-O inventories must validate.

The final link replaces exactly one original `arm_init.o` and one `pe_fiq.o`.
It uses the **14 pinned constituent objects** from the accepted retained-FDT
composition rather than its already partially linked aggregate. That matters:
`ld -r` localizes the private `_arm_init` entry, preventing the startup assembly
in a different object from resolving it. Adding the aggregate produces a real
undefined reset entry. Passing the actual constituent early-boot object to the
final linker fixes this without changing visibility, suppressing undefined
symbols or defining an alternate boot entry. The final map excludes both
superseded objects and includes every constituent.

The final MH_EXECUTE linker supplies its synthetic `___dso_handle` boundary
at the real read-only `__mh_execute_header`. There is no dummy data definition
or explicit alias: either would replace the genuine image identity or collide
with the linker's boundary. The sole zero-size linker-owned map entry is checked
against the actual file-backed kernel header. This matches the real logging
API's `&__dso_handle` image-identity argument; it is not a new logging runtime.

All seven added translation-unit initializers appear exactly once in the
existing **120-entry read-only `__DATA_CONST,__mod_init_func` table**, and nowhere
else in the kernel's other initializer sections. Each target is executable and
each pointer site has a genuine local loader-rebase entry. No special
constructor-calling shim or second initialization loop is added. The original
`OSlibkernInit` / `OSRuntimeInitializeCPP(NULL)` code scans the kernel's ordinary
initializer sections. The other original `__LASTDATA_CONST` and `__KLDDATA`
initializer sections remain present; they are not mistaken for duplicates of
the main table.

The seven units are original `IOPCIBridge`, `IOPCIDevice`,
`IOPCIMessagedInterruptController`, the adapted original `IOPCIConfigurator`,
and board `BCM2712PCIConfigBridge`, `BCM2712PCIResourceBridge`,
`BCM2712PCIePHYTransport`. Original `IOPCIBridge::initialize` creates shared
symbols/flags and parses PCI logging boot arguments; no new driver personality,
concrete root bridge or boot-time MMIO caller is introduced here.

## Validation and limits

Five focused tests perform the real complete link, revalidate every input and
generated pin, reject overwriting and unsafe output locations, and reject
receipt drift, real baseline byte changes, wrong/duplicate logging DSO entries,
missing/duplicate initializer symbols, corrupt/duplicate pointers and a removed
initializer relocation. UUID-only changes are accepted and accurately labeled.

All **246 selected regressions pass in 85.373 seconds**, covering the preceding
FDT/Device/PHY/UBUS/PCI/watchdog stages and preserved zsh/socket/userland paths.
The initial sandbox run denied two localhost UDP binds; the same full suite
passes with local loopback access enabled. No Pi or external-network test was
substituted. Final Device (190), PHY (716), UBUS (747), retained-FDT (1,294) and
complete-kernel (2,241) unique-file pin sets revalidate, as do all 35 checks on
the unchanged physically tested zsh/socket boot package.

Constructor **placement and relocation are proved locally**, not constructor
execution on the Pi. This kernel has not been packaged with the new loader or
installed/booted. The prior retained-FDT loader candidate still embeds the old
tested kernel, not this file. Do not stage that loader expecting this integration.

Next: close concrete provider/boot-caller and genuine inherited power/clock/
shared-controller/RP1-quiescence/recovery ownership; connect unused-window/RC/
windows/link/config/BAR operations, then interrupts, DMA and GEM Ethernet.
Do not convert source constants or booleans into hardware permission. A fresh
combined loader/kernel/root package and independent preflight must precede any
physical trial. Gate 4 durable storage stays on hold; accepted serial zsh/socket
images and source bytes remain protected. No serial, media, power, firmware,
reboot or soak operation occurred, and no fresh Pi OS/root observation is claimed.
