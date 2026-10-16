# Actual controller / IRQ lease composition — 2026-10-12

## Actual GPIO32 reset and C22 management pass — 2026-10-14 UTC

Frozen `pcie-id-trial-q5lw58tf` passes all59 diagnostic records and the complete
zero-TX serial capture. PHY1 returns ID1=600d/ID2=84a2, BMCR1140 and BMSR7949
twice; link/autoneg remain0. Five transfers use25reads/7writes/12polls; NCR
0→10→0 and NCFGR00540000 unchanged. These are valid management observations,
not link readiness or packets, and do not prove reset was the sole cause of the
earlier all-ones failure.

Reset completes19reads/12writes in22,750us within40,000us. Input low3/high13
confirms the sampled bit4 transitions; exact CTRL9f/PADd6/OUT1/OE1 restore.
Fresh rootLINK_CONTROL is0. All5 maps revoke and original root/endpoint
COMMAND/window/BARs restore. Actual PM64420/FW16103 remain within the unchanged
65536 ceiling; this phase is not extended for future ring/DMA work.

Full capture `pcie-phy-reset-capture-20261014`:35539bytes, zero UART payload TX,
SHA `e1f1b0102ffea65d707aa441c7d30fdc959804b081daf8a10092101a6fe04941`,
ended04:02:06.876101UTC. Independent SSD Linux return verifies boot
`5893543b-80df-4594-bef7-9e6c4833a8b4`; original firmware/image restoration
passes24.084s, catalog404→409→414. Install seal
`0c153e98c82b206db6df4c04fff7155334c64dfe9ef107af01045494a809c692`, plan
`9e0a566559108a45d25bed6fb4d83352b01a94544b8d6d28b93c8bf4aad46963`.
Restore seal `9db245ae4b843afcd07108024169411469d3c3532a48c45b518d374add8ad7a9`,
plan `b012548fdefc92a152ed278ab761f137b02cdb07ac95d53d2ab6b589b8362838`,
result `235ae47daced02d0eec58d9155ecd4244aecc4548a7e9eb1b05426bc90c5a891`.
No new soak or unchanged PHY replay is required. IRQ delivery,
DMA addressability/activation and Ethernet packet transfer remain unproven.

## Reset/C22 successor is software-qualified, not executed — 2026-10-14 UTC

Frozen `pcie-id-trial-q5lw58tf` binds a fresh GPIO32-only5ms reset pulse,
no-ASPM/clock-PM admission and bounded C22 observations, then exact original
GPIO/map/root/BAR restoration. It preserves the admitted0x80 filter field;
post-access faults quarantine without compensation. Main independently
repeats worst-poll/F_M/ASPM3 groups in7.188s; independent access/wait fault
review passes2 groups27.980s. Worst native model: PM65244/FW16309,292 PM
checks below the unchanged65536 ceiling. This is not board timing evidence.

Kernel-v2 manifest `0dafc8e47ab3226833c36c9aab2a2da1116abb2ca4c814e1a81a852e372c0fb8`;
package manifest `0c8b015a71ce65269e4b4d2373745f399673c95db2e5e59f86b72231f658c6fb`;
image `6627559f8dc8e3a78329203300b85507403a5a32c2d4b21a473834dac44c892f`.
Saved checker report at `pcie-phy-reset-qualification-20261014/checker-report.json`
has SHA `8228cabe8e6f0a003bd898158250df177166ca20f28df475353da7cfbc4118f1`.
The separate controller/zero-TX recorder/evidence11 groups pass, including
actual compact374 intake and preserved propagated-RC=-6 failure. Any future
trial must use the then-current completed restoration, now display-XNU384,
not stale374. No reset pulse, PHY-management success, IRQ/DMA, packets or
working Ethernet has been established on hardware by this successor.

## GPIO32 observation and complete restoration pass — 2026-10-14 UTC

Distinct `pcie-id-trial-hsqaaaqu` passes all53 ordered records, including12
GPIO reads in two identical raw snapshots. Fresh original FDT binds the Pi5
active-low PHY-reset declaration to GPIO32 and only three additional16KiB
Device pages. All five maps revoke, GEM/clock checks pass and original root
COMMAND/window, endpoint COMMAND and all six BARs restore. Actual PM63476
and FW15867 remain below the unchanged limits. This is a read-only observation:
no GPIO/reset/MDIO/PHY writes, DMA, interrupt delivery or packets.

Both snapshots: STATUS04400000, CTRL0000009f, PAD000000d6,
RIO OUT00000001/OE00000001/IN00000003. The selected pin has function31
and RIO bit4 is not output-enabled; this differs from Linux's owned GPIO32
output-high reset configuration. Raw values do not prove the electrical PHY
state or establish that reset is the only missing prerequisite.

Full continuous capture34899bytes, zero UART payload TX, ended
`2026-10-14T01:02:35.911263+00:00`, SHA
`cf7817e4b68b64085b6864676f076de9f548a57fb8fe859e0f891ed2b110c3cc`.
Complete capture/tail validation, independent SSD Linux return, exact original
firmware/zsh restoration and byte-only replay pass, catalog344→349→354.
Linux boot `47392e3e-8254-4780-ae41-82ecd22f67ef`, root `/dev/nvme0n1p2`.

Package manifest
`b4b84a4ef35b1e941bced191bf294504d8388d67e0029f10353193d3fd94dad6`,
image `8aabb20c07538d142ed16a0820d098773345c121058b556dbb1ff867095290cb`,
18196056bytes, TAG `2dfd0258ff424c0ba125f9d3886a6023`.
Install `pcie-phy-gpio-installed-20261014`: seal
`41e81b1cfb1e3ac72b2084033e2111919de6d48c691f183a28df6f5da12a9beb`, plan
`2d3b46dc8f39c576e1f84dfca91a8fe26ecd13814a5b56b9595302ffc0573dca`, result
`2fb71e73b23484b9f11c42c9d360a128e147bafaacbd5905e7b3451e4e8500ef`.
Restore `pcie-phy-gpio-restored-20261014`: seal
`388b4e0f46a9afdc32f52ed04e0aa32ae1ddd71f47f5b809bacfebc9daa96913`, plan
`06bd87d1fd9c39233bc0ee5605b7abbb75942bcd5299f445eded960d6b37dfba`, result
`3920d6c90691627e8a9f35f424bc0cc373a7530ca28231f99d9d74030679140e`.
Sole prepare32.446s/28984closure files; publish23.954s/restore26.911s.
Main core/handoff/kernel9groups25.913s, controller10groups69.380s;
independent controller4groups25.918s and byte-only admission10.329s.

Next is explicit exclusive reset ownership, source-backed field preservation
and five-millisecond reset pulse followed by fresh bounded MDIO. A distinct
timed-access composition passes native32-poll accounting at PM64540 while
retaining every actual MMIO pre/post guard and the65536 ceiling. The pure
reset cycle passes452 native fault cases; integrated adapter/whole-path budget
and linked-image checks remain required. These software results are not reset
or PHY hardware acceptance, and the previous all-ones failure stays failed.

## PHY responses are all ones; failed trial and exact restoration — 2026-10-14 UTC

Distinct masked-ID package `pcie-id-trial-qthzh5e7`, manifest
`6c18b4c7b24346fdd08cda0f8e187d502b694e5f8d0bb8f79973641d24a44173`, image
`181e58ee6326b625b3c58a1d2c288d16db0e0c1498fdf4f9ed8bb965e7436026`,
18,193,720 bytes, TAG `bff69a28a78d4f3087da5f4ac6ec8b22`, attempts all five
Clause22 reads at PHY1. ID1/ID2/BMCR/first-BMSR/current-BMSR all returnffff.
MDIO STATE3/STAGE7/RC-6/TRANSFERS5 correctly refuses the all-ones identity. No
valid PHY identity or Ethernet operation is established.

MDIO reads25,writes7,polls12,time callbacks34,divider unchanged. NCR
00000000→00000010→00000000; NCFGR00540000 remains unchanged (CLK code5/DIV96).
Local MAC management settings are read back restored before ID rejection.
Core counter46439698→46456947us remains below46459698us deadline. Whole-path
map/BAR/root restoration is not committed: GEM RC-6/stage6/reads17, decode
RC-6/state9/transfers22/writes1/mapped03/unmapped00; root-memory RC-6/stage8/
reads47/writes2. END OK0/phase6/last14/life3. After fields in quarantined
parent state are not readback proof. Actual PM56164/FW14039; no unsafe
compensating writes occur before watchdog recovery.

There is a separate evidence-parser failure: the frozen inherited root parser
allows errors only through-5 and rejects the propagated MDIO-6 as
`Root-forward progress exceeds bounded state machine`. Keep its capture-valid
result false. A distinct reader/successor must explicitly support and validate
this propagation; it must not rewrite the old capture or receipt as passed.
Raw diagnostic rows above remain inspectable in the retained capture.

Capture `pcie-gem-mdio-capture-20261014`:34,808 continuous bytes,zero TX, SHA
`16f7a487db6ac4766a1f9b51b43934db619f4f3234affa44da75658ebfd7e68b`, ended
`2026-10-14T00:18:32.069339+00:00`. Independent normal SSD Linux return is
`1bef80be-d4c1-4f98-b333-8062bb6a9103`. Original config, firmware and working
zsh are verified restored. Full byte-only chain replay verifies failed capture,
independent recovery and restoration separately, catalog324→329→334.

Install `pcie-gem-mdio-installed-20261014`: seal
`0eca0dce4a30aa91fc495a5313ff2d59ea57a7bd663a7393bcaae01845264e56`, plan
`e734b8acfa30630415d0f3fe7fcd3acf555d8be3208e669a5a4ffa38f93af757`, result
`639aa9d10f2de80c3c5cb26e9a71e1f6183140f73262978de598ab1e80758a08`.
Restore `pcie-gem-mdio-restored-20261014`: seal
`5b941840028983040a4e50ec74018e48b63350e4d5db6fdc96bd0f233106c733`, plan
`1d5dd2a8b7b40aa88527df530882a855531be92556966e4996c9f497228f74cf`, result
`8f478d1ed7794cf913fc9789f21bdfa35dce67ec9a6a1ebd622b34f6e56fb569`.
Prepare32.534s/28,715 closure files; publish24.575s/restore24.434s. Main
controller10 groups56.483s, refined native/linked3 groups16.643s, fresh package
checker21.442s all pass as software evidence. Independent source review and
byte-only admission pass; they do not override the physical failure.

The v2 kernel changes only the source-backed no-device ID predicate, rejecting
all eight `(id&0x1fffffff)==0x1fffffff` forms. Kernel SHA
`ec2a37b7421a84cd0ccd2ac2d82e1e926cf44a82254be4dd2c82c8bf53886326`, manifest
`67d614b3324db922eb8d155236155002851f2096a78df583f94d009040ddafd1`.
Earlier prototypes/v1 source remain separate and are not this trial image.

### Next PHY prerequisite, not a proven diagnosis

Pinned Pi5 DTS declares Ethernet `phy-reset-gpios=<&rp1_gpio 32 GPIO_ACTIVE_LOW>`
and5ms reset duration. Original Linux MAC/MDIO setup drives that line through
its reset sequence before discovery; this image has no GPIO reset provider.
No standard GPIO MDC/MDIO pinmux selection is present in that binding. A held
reset is plausible, not yet observed in the standalone boot. Implement a
fresh-FDT-bound nondestructive GPIO32 observer, followed by explicit reset-line
ownership and source-backed setup/restore. Do not guess or loosen floating-ID
admission.

After verified SSD recovery, read-only Linux debugfs reports RP1 GPIO32
`ETH_RST_N |phy-reset`, output-high/active-low, GPIO function, input-high and
output enabled,4mA drive. Pinctrl reports mux unclaimed while the GPIO consumer
owns the line; logical/debug views are not standalone MMIO proof. No GPIO
request, direction/value change or debugfs mount change was performed.

## Bounded PHY management implemented; software evidence only — 2026-10-13

The distinct MDIO core/profile repeats fresh original-FDT decoding and live
clock/MID/design admission before management access. It rejects unknown or
command NCR bits and active RX/TX/MPE. Temporary NCR.MPE and, where needed,
NCFGR.CLK DIV96 changes are read back and exactly restored. Five Clause22 READ
commands obtain PHY ID1/ID2, BMCR and two latch-aware BMSR snapshots. Link-up
is not an admission requirement. No PHY reset/advertisement/data writes, DMA,
IRQ delivery or packets are implemented here.

Six software groups pass independently and in the main rerun (15.938s):
1,458 core faults, 192 actual transport pre/post owner/map/FDT/reentry faults,
three fresh FDT rejection cases before any management I/O, primary ABI and
unchanged-parent checks, and the actual complete worst32-poll model. That model
performs46 reads,9 writes,57 time callbacks; PM65420/FW16353/guards8176 remain
inside unchanged65536 limits, with116 modeled PM checks left. This is explicit
native MMIO/PHY modeling, not observed board timing or physical MDIO operation.
Failure tests require unchanged ordinary output and no compensating I/O/retry.
An early main test rerun failed two in-progress assertions; they were diagnosed
as a wrong primary-helper lookup and a post-time-guard fault detected by the
next owner check. The corrected tests still forbid any further data I/O.

Distinct `pcie-gem-mdio-kernel-20261014-v1` replaces one transport object and
adds one MDIO C object, preserving all owner/GEM/capability cores. Kernel SHA
`d141dd28afcd6ed56b4b1bcfd6d89d4ff4fb766c3cfc1d186a9dc3b2ce7fdc00`,
manifest `143f21c2d0cae4d9495aebca78b6cc9aed7d79c67fe0ba4b7493051c32b55862`.
Two additional main-rerun groups pass (1.334s), including actual Apple bounded
log encoding:24 calls,max40 bytes. No package has yet been admitted to hardware.

## GEM design capabilities and complete restoration pass — 2026-10-13

Distinct package `pcie-id-trial-s24bfjnh`, manifest
`a8c1234b5087767af25dbe8bb8d914d754d2f58ac6824c542c122510aa318ce0`, probe
`fc9d136a4373831cc662c09bb73e17cbb0f200051447fd26ab20987c17818c00`,
passes all 47 records. The 16 design-word reads agree across two passes within
the retained before/after clock bracket (48 total endpoint reads):

```
MID=00070109 DCFG1=08508513 DCFG2=6eb13fff DCFG5=502e5b45
DCFG6=08820000 DCFG8=00000000 DCFG10=24444444 DCFG12=00000000
```

The source-backed decode reports one queue, 128-bit internal bus, 64-bit DMA
descriptor support, write-clear ISR policy, RX/TX packet buffers, TSU and LSO.
Descriptor support does not qualify actual DMA reachability or operation.
Root forwarding, endpoint COMMAND, all BARs and both mappings restore; END
OK=1, phase=5, life=3. Actual PM=63188 and firmware sequence=15795 remain
within unchanged bounds. No endpoint device writes, BME, DMA, IRQ delivery,
PHY access or packets occurred. A successor must repeat fresh capability and
clock admission under its own live owner; this receipt is not boot authority.

Capture `pcie-gem-capabilities-capture-20261014`: 34,496 continuous bytes,
zero TX, SHA `56890ccd0da407e4b4ce086eb07d5d18f00e168e4ff20c99b07769e173141eff`,
ended `2026-10-13T23:35:25.914631+00:00`. The folder suffix is an identifier;
the capture timestamp is the observation date. Complete fault-tail checks
pass. Independent SSD Linux boot is
`2ada421c-8073-4006-b3ef-a5a9e458054a` on `/dev/nvme0n1p2`.

Install `pcie-gem-capabilities-installed-20261014`: seal
`382bed41f5a5643c320f7250c322c6250057d3b998b94429b7026d2bbe46324a`, plan
`a171ca2a101b9d735f796f023c441c5c8000f6132e103d9f934472c66e660b0e`, result
`abe4fd9a42cd8b84417f3a3035ec094b9601d9bf445c4add632aef0a28bb5e91`.
Restore `pcie-gem-capabilities-restored-20261014`: seal
`5fad6fef41d0f25c052ac4a376288fdfb104e626ce61c246851151bf1b5fdccb`, plan
`be09e9e2354626d7547757fe27d142b232dd2b93275241708b76100384d6f288`, result
`ac1f4897640be154cac3fc11119b311722a5ae8dc77839d4fd261cd12cd9def7`.
Catalog 294 → 299 → 304; publication/restore 23.474 / 23.852 seconds.
Full byte-only chain replay passes with no compiler or historical semantic
audit calls. Ethernet and SSH remain unfinished.

## Selected-clock/GEM identity and complete restoration pass — 2026-10-13

Distinct `pcie-id-trial-vf78_802`, manifest
`a287f869e27bd1926dfcc2147ea998e673e02dd0aff8b2f9a45816324dc90904`, probe
`ca6dec70af6773bf656a955909cbba9c27eeddeaaad75b460bfcd9a9450c5dda`,
passes all 42 records. The only changed GEM predicate admits exact SYS CTRL2
or0x802 with SEL4, retaining the PLL/rational-rate/ETH/TSU checks and complete
before/after comparison. Both actual MID words are `00070109`. All 15 clock
words in the earlier snapshot below repeat identically before and after.
The SYS/ETH/TSU decoded rates are 200/125/50 MHz, not independently measured
frequencies or a generic physical clock-gate qualification.

GEM CALL=2/RC=0/STAGE=5/READS=32/READY=1. Root memory forwarding performs
79 reads/four writes and restores COMMAND0000 and windowbff08000; no pending
restoration remains. Endpoint decode performs 34 transfers/two halfword writes,
maps03/unmaps03 and restores COMMAND0000. All six original BARs restore,
ASSIGNED07/RESTORED07. Actual PM=62940, FW sequence15733, SMC calls15734,
all existing bounds unchanged. No endpoint device writes, BME, DMA, IRQ
delivery, clock/reset/PHY writes or packets occurred. IRQ ownership telemetry
does not establish interrupt delivery. The two earlier failed GEM trials
remain failures; this distinct boot supplies the new success evidence.

Capture `pcie-gem-selected-capture-20261013`: 34,072 continuous bytes / zero
TX, SHA `63eec34d80aab320e632763edf5f6fcc267c4c69e6a307b4f5a2ccbb6ec87a66`,
ended `2026-10-13T22:19:54.551213+00:00`. Complete raw-capture fault checks
include the tail after END through normal NVMe selection. Independent normal
SSD Linux boot `deb8426f-ab2f-497f-bddd-0cca0984c0d3` verifies the exact root
and SD identity separately. Original firmware/zsh pair restoration passes.

Install `pcie-gem-selected-installed-20261013`: seal
`cdc2bb986c48c978d3362e058524bb9cada842265a2cadadc977ae06cd0eafbe`, plan
`4b7b0ae9550ca5f7baaf910b09e752c55ebd7a7049b97689febca77344f45ddb`, result
`d6f6231875abefc276000a629a463a291c2392910c392997d32d4f43c481b3e0`.
Restore `pcie-gem-selected-restored-20261013`: seal
`dacf40cebd666ffc360131917f555e9fc5abbaf09462354f9be1af0d312ecef1`, plan
`ab979e75de9ef6bdbe8927acc3f73ba834cbd34989ce267b0bfcf54173c52266`, result
`822bdb50194466c283abe2845989140c887bab080c75e8c8cd9a62bac9cee563`.
Catalog 276 → 281 → 286; install/restore 28.407 / 24.187 seconds. Compressed
bounded uploads precede the unchanged sealed SD publisher. Next source-backed
MAC/PHY management and IRQ/DMA/packet implementation; no network claim yet.
Full byte-only chain replay passes: complete valid capture, diagnostic success,
independent normal Linux return and original pair restoration are verified
separately, with zero compiler or historical semantic-audit calls.

## Root-forward readbacks reach live state; clock profile rejects — 2026-10-13

Distinct `pcie-id-trial-adb7yr9w` (manifest
`2754ff2de036d035219a2a93bd85474f8095da17339b2bab40b2ae629eecc988`, probe
`cbc208206bf4d8b15afd793697031d0b2cba84b49b6925dfa51cda1a2fe5c8d6`)
reaches root COMMAND 0000 → 0002 and window bff08000 → 00400000 readbacks.
It attempts 47 root reads/two writes and all 15 initial endpoint clock reads.
Unlike the earlier all-ones snapshot, actual words are:

```
SYS_CTRL=00000002 SYS_DIV=00000001 SYS_SEL=00000004 PLL_CS=80000001
PLL_PWR=00000004 FBDIV_INT=00000014 FBDIV_FRAC=00000000 PRIM=00051010
ETH_CTRL=10000800 ETH_DIV=00000001 ETH_SEL=00000001 TSU_CTRL=10000800
TSU_DIV=00000001 TSU_SEL=00000001 SEC=80000800
```

The unchanged profile rejects SYS CTRL=2 because it requires ENABLE11, before
either MID read. GEM RC=-5/STAGE=6/READS=15/READY=0, ROOT RC=-5/STAGE=8,
DECODE STATE=9/MAPPED=03/UNMAPPED=00. Root/endpoint/maps/BAR runtime restoration
is not proven; zero after/output fields are uncommitted, not actual readbacks.
Quarantine prevents unsafe compensation until autonomous reset. No endpoint
register writes, BME, DMA, IRQ, clock/reset/PHY writes or packets occurred.
Actual PM=54828, FW sequence=13705, all existing bounds unchanged.

All 42 rows and the full capture are valid and fault-free:
`pcie-root-forward-serial-20261013`, 33,945 continuous bytes, zero TX, SHA
`e907497c3882c08ecf41de83aa58e6f7777731c6f81fcdf8d4ccc3af4867a265`,
ended `2026-10-13T21:38:15.143941+00:00`. Independent SSD Linux boot is
`d2af120f-0361-43af-a909-c1674e7a3030`. The diagnostic remains failed even
though recovery and original firmware/zsh restoration pass.

Install `pcie-root-forward-installed-20261013`: seal
`e13be68259a2690d1ffa112af85c78498944c42fdfc94914fad65de02f61ea86`, plan
`6857cd70502857af9d4b0c31b76d7a1dd1e7103a7bbe78f46c089c07406e44dd`.
Restore `pcie-root-forward-restored-20261013-fresh`: seal
`bda0a185c163873ea6ca22325dcd9e5cad5dcd32471812e258702d61cf5eb9c8`, plan
`4936db726f9a163efe707d640b6077f7f8e1b4d0c22920cd6794100224803dba`, result
`b609aecc5d97270b22fbcb10d5ff4712d617cb523842465e7b87b001331e50cd`.
Catalog 266 → 271 → 276; publication 23.595 / 25.159 seconds. Two Wi-Fi upload
timeouts occurred before SD-program generation/intent; read-only SD hashing
confirmed the exact trial pair. A compressed upload completed the known stopped
pre-publication plan, then the unchanged sealed publisher ran once. Both failed
uploads are preserved; no unknown SD dispatch was replayed. Full byte-only
chain replay verifies capture, independent return and restored original pair.

Next distinct candidate `pcie-id-trial-vf78_802` (manifest
`a287f869e27bd1926dfcc2147ea998e673e02dd0aff8b2f9a45816324dc90904`, probe
`ca6dec70af6773bf656a955909cbba9c27eeddeaaad75b460bfcd9a9450c5dda`)
changes only the GEM C decoder object. It accepts exact SYS CTRL2 or0x802 with
SEL4 and unchanged locked-PLL/rational-rate/ETH/TSU checks. Selected source is
not independent frequency/gate measurement, and no always-on/RES0 claim is
made. Native full path remains PM63372/FW15841/guards7920. This proposal was
subsequently executed successfully in the distinct boot documented above;
the failed predecessor is preserved unchanged.

## Physical GEM trial fails on all-ones clocks; recovery/restoration pass — 2026-10-13

Distinct `pcie-id-trial-yjofwwhc/probe.bin`: 18,142,168 bytes, SHA
`173cf38c6dc3096657d593b37b037e2ee7f8475fbde5b4943b9f3ba310335913`;
manifest `1229ec948dff70945bbe5490728a1a40d21a9b8e1128c0fe884ee5f74757d356`.
Strict-CS/PWR kernel `pcie-gem-identify-kernel-20261013-v2` is SHA
`2959ed80b47c62aca7d74a648f15c18ef7c0fc3a7942f9165a9b4f118aad6643`.

The exact same-boot trial reaches both retained Device maps and endpoint MEM
enable, then attempts all 15 clock reads. Every word is `ffffffff`. GEM reports
CALL=1 RC=-5 STAGE=6 READS=15 READY=0; both MID reads are unattempted and no
frequency/MID observation is committed. DECODE reports CALL=1 RC=-5 STATE=9
TXNS=22 WRITES=1 MAPPED=03 UNMAPPED=00. Assignment remains ASSIGNED=07
RESTORED=00. Zero-valued final observation fields are uncommitted output, not
proof of live register restoration. Failed sessions deliberately quarantine
without unmapping/restoring through lost authority; watchdog reset ends them.
No endpoint device write, BME, DMA, IRQ or packet operation occurs.

Actual unchanged-owner counts: PM=54044, callbacks=216184, FW sequence=13509.
The full 35-row capture is valid and fault-free through normal NVMe selection:
`pcie-gem-identify-serial-20261013`, 31,751 bytes / zero TX, SHA
`9fe069793bff05fcf7f4ffafb4998d2e93f3ba7167e9343402834af547100fad`,
ended `2026-10-13T20:00:52.710097+00:00`. Independent SSD Linux boot is
`2c770b9b-58b5-4f22-86ed-7e42f18151ed`, root `/dev/nvme0n1p2`.
Original firmware/zsh restoration and full chain replay pass, while the actual
GEM identification result remains failed. Catalog 240 → 245 → 250.

Install `pcie-gem-identify-installed-20261013`: seal
`e3c891f09d289a1e3347458fc3e99876ef1a4f4e301ddcb89e2020366b04252b`,
plan `e7a4954e75c7a4bc0ce47f48a69e25367a1f0c6fed64cda8bc777f799c65c2a6`,
result `dfeab2b715830712d9d82d163bec9989eeee80f2ece01c4b61a1f3671c77ebc1`.
Restore `pcie-gem-identify-restored-20261013`: seal
`0115e916311ff95663a641b98b9d17adf2e9ee8c93c9ae6ddb2e0c9e17116500`,
plan `36ebbbb3d9664fc9fbf2f66429110ffe7bb2310757fc131dbef090b8e3981b9a`,
result `2ca142b9831779a7a644c6a1cf26c843bcd1803e6ce9d36557d895469f9557dd`.
Install/restore 23.713 / 24.416 seconds. The once-audit seals 27,477 files and
112 actual recorder source members; replay invokes no compiler/history audit.

Primary-source review finds that root bridge COMMAND0x04 and nonprefetchable
MEMORY_BASE/LIMIT0x20 were not qualified/configured by the current controller.
Existing endpoint decode and valid CPU mappings alone do not prove forwarding
through that bridge. This is the next concrete correction, not a claim that
the physical cause is already proven. Preserve this failed image/capture; a
successor must separately authorize and test minimal root MEM/window writes,
readbacks/restoration, current owner/geometry, and unchanged cumulative limits.

## Physical MEM-only Device-map/revoke and full restoration — 2026-10-13

`pcie-id-trial-omaujuxp/probe.bin` SHA
`84982e24a8f1cfbb7ed1e841d28aadc1dfdafc4c8fbff4538b681b72e9ab0f7c`,
18,141,552 bytes, manifest
`2013d9e58efdb62253a96c86d273f1fc53df1311e58c7f5d17684240663186d1`,
passes all 25 records. The loader declares exactly six additional 16-KiB
Device pages: GEM `[1f00100000,1f00104000)` and clocks
`[1f00018000,1f0002c000)`. The live owner rechecks the assigned inventory,
changes COMMAND from `0000` to `0002` through a halfword write, maps both
exact ranges with private host-only cache-inhibited descriptors, verifies
their actual backing/physical/virtual geometry, unmaps clocks then GEM,
restores COMMAND to `0000`, and restores all original BARs.

Actual DECODE: CALL=3 RC=0 STATE=8 TXNS=34 WRITES=2 MAPPED=03 UNMAPPED=03.
The ordinary original-owner checks remain: PM=61092, callbacks=244376,
FW sequence=15271; all limits/deadlines are unchanged. This establishes the
mapping/revocation path on the board. No device-register dereference, clock or
reset write, BME, interrupt activation, DMA or Ethernet traffic is claimed.

Capture `pcie-decode-cycle-serial-20261013`: 31,039 continuous bytes, zero TX,
SHA `cec5472b643d5a979d12c59cab52d0d70cde7a3e5fef0303e25a6090c3b5bbcf`.
Full capture health and normal NVMe selection pass. Independent SSD Linux
boot `8f2b1d32-7ea5-4a6c-8856-13126de4f14b` is verified; original firmware
and working zsh are restored. Full read-only chain replay passes. Catalog
230 → 235 → 240; install/restore
23.433 / 24.128 seconds.

Restore `pcie-decode-cycle-restored-20261013`: seal
`ed2219ca68a21d0aeffd4415bd0c493f8b67073c5951a0f11d6cb40c2322f15b`,
plan `44fb310aeb42bff2fcbccf264bacbe262843de8ace59962d269e0186c9cd8ecf`,
result `7dc7187242609b43689d060901c04aed8d51c7f2598909449a5781d80d52f970`.

## Physical BAR assignment/readback and exact original restoration — 2026-10-13

`pcie-id-trial-_w3ajzlm/probe.bin` SHA
`36bebc4324c098e1118a2e74f2f740744b5f97edbbb932ea4846882d1304e70b`,
18,140,560 bytes, manifest
`9275fbd5741bd4365a6f0461dd9d74fc2980fc6517a85a416bbc6f4fdb20f3f0`,
passes the complete 23-record diagnostic on the Pi. The same live owner sizes
all six BARs, assigns BAR0/1/2 to `00410000/00000000/00400000`, reads back every
slot, then restores `ffffc000/ffc00000/ffff0000`; BAR3–5 remain zero. Assignment
reports CALL=6 RC=0 STATE=6 TXNS=58 WRITES=6 ASSIGNED=07 RESTORED=07.
COMMAND remains zero. The pure mapping bounds are observations of proposed
geometry; no device map, register access, IRQ, DMA or Ethernet traffic occurs.

The real owner telemetry is FW sequence 13,753 and PM checks 55,020 / callbacks
220,088, within the unchanged 65,536 limits and finite deadlines. Continuous
capture `pcie-bars-assignment-serial-20261013` is 30,800 bytes, zero TX, SHA
`9ecc711558219b6b948181506c8f858baa56992f17d2b19a889ee436373384ff`.
The whole original capture is fault-checked through normal NVMe selection.
Independent SSD Linux boot `34e1027f-f0fc-42c7-b70e-f4a224e59e7b` is verified;
the original firmware and zsh image are restored, and full chain replay passes.

Restoration `pcie-bars-assignment-restored-20261013`: seal
`c655d73260f4f6998c8d8d73c2036b78c4e2dc13320396ff127195996aa24952`,
plan `24286e048e19a8d8a92c94f361a3a1f3212b66d7226bd3128ae9cfeb9d00e057`,
result `99f63f5d34b6a01f4943ad1837fce29d047617fd9387e975f27f1fb88c0ce729`.
Catalog 220 → 225 → 230; installation/restoration 24.044 / 24.988 seconds.

## Physical root-route success with a post-END logging failure — 2026-10-13

`pcie-id-trial-1fklcw3v/probe.bin` (18,122,448 bytes, SHA
`f370fa68e1cc6a40654e52b24cb3bb0db1bf3a657d9a06c785b18a69ccbd8b26`,
manifest `8e7325f77fe808fdd0a6855f1935b90fe19d5324c86f9d22304eadd273b04b4b`)
boots kernel `be374699c3b93dd7425b12920e22f50eceb18d36d9e10b6ca51d4749dc19fbc7`.
The actual diagnostic reports:

```
OK=1 PHASE=5 LAST=5 ID=00011de4 COMMAND=0000 BAR1=ffc00000 GEN=2 LANES=4
LINK_CALL=5 LINK_STEP=14 LINK_RC=0 RESET_US=100623 POLL_READS=1 POLL_US=541
RP1_CALL=5 RP1_RC=0 RP1_STEP=5 RP1_PASS=1 RP1_INDEX=15 RP1_XFER_RC=0 RP1_READS=32 RP1_ID=00011de4 RP1_HDR=00000000 RP1_BAR0=ffffc000 RP1_BAR1=ffc00000
ROOT_STEP=9 ROOT_RC=0 ROOT_READS=6 ROOT_WRITES=1 ROOT_ID=271214e4 ROOT_HDR=00010000 ROOT_BUS_BEFORE=00000000 ROOT_BUS_WANTED=00010100 ROOT_BUS_ACTUAL=00010100 ROOT_BUS_POST_LINK=00010100
```

Thus this board's route register really was zero, and the single guarded route
write restores RP1 discovery. Endpoint COMMAND stays disabled. BAR values are
observations, not valid CPU mappings, independently measured sizes or resource
assignments. No endpoint config write, IRQ delivery, DMA or packet evidence.

Immediately after the full END line, `panic(cpu 0 ...): log_encode.c:120
Assertion failed: log_fits_cmd(ctx, cmd_sz)` occurs. Source tracing shows
`kprintf` outputs to serial before invoking `os_log_with_args`; this expanded
53-scalar record exceeds the 256-byte encoding metadata buffer. The previous
43-scalar config trace also panicked after END (raw offset 26,317), previously
missed by the terminal-bounded fault check. **Do not call either run clean or
claim that its reset was exclusively the watchdog.** Preserve narrower valid
controller/ID observations, original receipts and full raw evidence unchanged.
The corrected candidate will use separately framed bounded telemetry calls,
and the new protocol must reject faults throughout the XNU-to-BOOTSYS interval.
No global logging assertion will be weakened or suppressed.

`pcie_capture_health_v1.py`, SHA
`3424df5a2bcee4bf50273ecf1fe89aab1d6f12c0e8ae68805d3c599da447ca27`,
adds a separate whole-file-digest-bound fault-signature observation, never an
acceptance replacement. Both capture directories now contain a new
`runtime-health-supplement.json`; neither original state nor seal is edited.
Five focused tests pass (0.001 s), including the two real captured panics,
before/after/missing/repeated terminal cases and bounded/digest negatives.
Absence of a fault signature alone never produces acceptance.

The root-route capture is 30,080 continuous bytes, zero TX, SHA
`cd2027571ae6b55d64b77772a6ec0d5c6af4248d5ba2d3b0807093dbc192f1b9`;
state SHA `f466a0700f5ff5fdba18579652989e3d998f41f34e90d6b307a9465820b4159e`.
Original automatic f6/NVMe serial return is independently confirmed in fresh
SSD Linux boot `ee1f125a-112c-4da6-9f06-635451451e94`. Explicit known-good pair
restoration and original chain replay pass (narrower ID/return/restore scope);
catalog 148 → 153 → 158. Install/restore dispatch: 22.461 / 22.890 seconds.

- Descriptor `root-route-case-20261013/descriptor.json`: `87d1594e1934e93f8981ef06a81e8130bf467fee3625ff70ae67700c8aa9ef92`.
- Install seal: `b7058a4cf693fc7e339d9a59127dfae8caebe5dc79463043887df5869e0dd1f2`.
- Install plan/result: `5c9f41c1a35fcae18e01eaace6ba4132ef466ddcdb0c4cf18f94078d9c09c8e9` / `c7640ecbe1c682debb986933194e8180beaf899c8c642446c8d3454df6af313a`.
- Restore seal: `6e2aa9126fa66ff25e369c634efb12e93dfcac35b26dad4ca04ffd93fb8e044c`.
- Restore plan/result: `68847d8ff74b243bfe2e9dff23ab14d70914c28cdf0df565061d644fad2656b9` / `7564d60bc1995fba4bb1d2cad464dfbd7a9fe7c012ad16187acc1047e0ded621`.

Independent checks include seven native/linked-kernel tests (1.510 s), six
actual package/mutation/protocol groups (97.557 s), all eight controller
integration tests, and independently rehashed 16,457-file admission closure.
Once-audit/seal took 14.710 s with no historical semantic replay. The fault
omission above was outside those original acceptance predicates; the new
whole-trace regression closes that explicit gap, not the physical logging bug.

## Physical RP1 configuration trace and bus-route gap — 2026-10-13

The distinct `pcie-id-trial-ukgc_lll` package physically completed 32 guarded
configuration reads (16 dwords twice). Its actual terminal suffix is:

```
RP1_CALL=3 RP1_RC=-4 RP1_STEP=4 RP1_PASS=1 RP1_INDEX=15 RP1_XFER_RC=0 RP1_READS=32 RP1_PREV=ffffffff RP1_VALUE=ffffffff RP1_ID=ffffffff RP1_HDR=ffffffff RP1_BAR0=ffffffff RP1_BAR1=ffffffff RP1_SELECTOR=00100000 RP1_STATUS=0003e0b0
```

`OK=0 LAST=14` remains failed RP1 identification. Link completes with
`LINK_CALL=5 LINK_STEP=14 LINK_RC=0`, settling 100,616 us and one poll in
541 us. The transfer callbacks succeeded, but every endpoint word read as all
ones; the unchanged profile validator correctly rejects it. No endpoint config
writes, BAR admission, IRQ, DMA or Ethernet result follows.

The linked root-complex core never programs PCI primary/secondary/subordinate
bus register `0x18`. Raspberry Pi's [generic PCI bridge scan](https://raw.githubusercontent.com/raspberrypi/linux/rpi-6.18.y/drivers/pci/probe.c)
sets bus numbers before scanning the child. Its [BCM2712 controller mapping](https://raw.githubusercontent.com/raspberrypi/linux/rpi-6.18.y/drivers/pci/controller/pcie-brcmstb.c)
maps root config directly, and selects bus 1 through `0x9000` with data at
`0x8000`, matching our endpoint selector. Fresh read-only Linux sysfs evidence
is retained in `rp1-config-v3-serial-20261013/linux-pci-reference.txt`: root
`0002:00:00.0` is `14e4:2712`, type 1, bus register `00010100`; RP1 child
`0002:01:00.0` is `1de4:0001`. The missing initialization is a source-level
gap; it is not yet proven to be the sole physical all-ones cause. The next
separate overlay changes only route low 24 bits under existing held-reset
guards and checks immediate/final readbacks. Do not copy Linux COMMAND/windows.

The continuous capture has 29,893 bytes, zero TX, SHA
`9e89d72db9a4d7d77707ad16ad03f6fc84d8a1f42e9032d814f4bcab839738f7`;
state SHA `ad03a0c33ca2140285af44710a4d42be8d38094b1973b047fbf1ff161cf36127`.
Terminal→BOOTSYS is 16.328 s and transfer→BOOTSYS 17.183 s, inside original
bounds. Later whole-trace review finds the post-END logging panic described
above, so these timings are not evidence of clean watchdog-only recovery.
Independent SSD Linux return boot is
`804c0ee2-a4a2-4db8-acc5-08857c983181`. Explicit original firmware/zsh
restoration and full read-only chain replay pass; catalog 138 → 143 → 148.
Historical payloads remain retained but not all reread, as explicitly reported.

- Descriptor: `rp1-config-case-20261013/descriptor.json`, raw SHA `2104bf8f37d6ad11bdf7c9a98f2e96506561fa9ca4cc1baf1f605896c9954bb0`.
- Install seal: `7654eb7a38cb3d7ffd4d6db62272768c6a27f364ff3672a0b3b643c9dd07afa5`.
- Install plan/result: `92aa2ced5df5db70fe3935bfdca58554a45e77ff27595eca7975da717eacf316` / `bdaa5e27f0cad20dcfc1d777d60f05e79c6008c8ab31ccb3a2a9e58d4d804db2`.
- Restore seal: `3f61edfb23248147a2758b295b44865065c39a7040b6f80b20377a2f881adaa0`.
- Restore plan/result: `2af00537d406b32033aa435610bd82e8c657449afad1a2201c8227dfcc58a184` / `07f5137893a430f2399671d5d1fac886e85fd744ea55cd197ebbaad0a88da8e7`.

V3 publication took 22.470 s; restoration 22.160 s. New-package audit/sealing
took 12.387 s without historical semantic audit calls. A post-capture local
API gap (`PREPARED_PREFIX` missing as a public export) prevented the original
return CLI from reaching SSH. Separate `rp1_config_return_compat_v1.py`, SHA
`bd608b18f7938307f9a8eb3c2bd1880d8fb9be3b578ee7052d3498e0e9077d57`,
exposes exactly the already-sealed inherited constant in a private facade.
The original parser, raw capture, recorder and installation seal stay intact.
`protocol-compatibility.json` records this supplemental provenance, explicitly
outside original admission; the new restoration seal binds it. Four focused
actual-capture/return-double/restoration-seal/tamper tests pass, independently
repeated. The real replay preserves `rp1_id_trial_pass=false` and verifies
both restored hashes; it is not another hardware observation or a successful
networking result.

## Physical elapsed-link result and faster trial path — 2026-10-13

The new image `pcie-id-trial-y60h5lfb/probe.bin` (18,122,328 bytes, SHA
`da66b97dfbd4fe36b97412b132c378aa758b8d1126e0f193de29a1d2da18821e`)
boots the exact elapsed kernel `6853562383a5e1e2d833a4990cc0cfd4d4c64a5bc4565ede7a01626b5ebf8f16`.
Actual telemetry:

```
RPI5XNU:PCIEID:END OK=0 PHASE=6 LAST=14 LIFE=3 FLAGS=1f ID=00000000 COMMAND=0000 BAR1=00000000 GEN=0 LANES=0 UBUS_STEP=5 UBUS_RC=0 UBUS_CB=23 GUARD=0 BANK=0 OFFSET=00004068 DIR=0 IO_STAGE=4 VALUE=0003e0b0 LINK_CALL=5 LINK_STEP=14 LINK_RC=0 LINK_CB=41 RESET_START_US=42790294 RESET_END_US=42890917 RESET_US=100623 POLL_READS=1 POLL_US=540
```

The real link core and its following guard complete. The 100,623-us reset
interval is inside the unchanged 100,000–110,000-us bounds; the first link-up
poll completes in 540 us. Exact phase 14 is RP1 configuration inspection,
after controller/clock-finishing success (phase 13). The generic MMIO field
`0x4068=0x0003e0b0` is stale: the separate config callbacks do not update it.
Top-level generation/lanes/ID remain zero because the overall output is not
committed after failure. Do not infer a config failure code before reproducing
or instrumenting the actual guard/config-init/snapshot/final-guard boundary.
No endpoint config write, inbound DMA, MSI, IRQ delivery or traffic occurred.

Evidence directories are `rp1-link-v2-installed-20261013`,
`rp1-link-v2-serial-20261013`, and `rp1-link-v2-restored-20261013`.
The capture has 28,543 continuous receive-only bytes, SHA
`792676e8312e1153a05672d916abd925ffd6b38d768561aa056afc5dec0c531d`;
state SHA `ab70862b9a29e88aeeacc80391285599090f7f70765801064745658d4fe9ef3e`.
Captured automatic f6/NVMe return is independently followed by SSD Linux boot
`dc5737b5-2559-4830-b4bd-d406c7a77522`. Explicit original-firmware/zsh
restoration and `replay_link_trial_v2.py` full read-only chain validation pass.
That replay records `rp1_id_trial_pass=false`, no compiler/historical semantic
audit calls, and the preserved catalog transition 128 → 133 → 138.

V2 uses canonical JSON digests for checkpoint/plan authority (not the raw
newline-formatted file SHA):

- Install seal: `96dbd0472682f714689c8dd38e09ed150b86ae78819e4439cd755cc950b14876`.
- Install plan/result: `9cd227c1c06430b3e42a9a791cdf08f203891f4786ccb8c149a200442bd8b42b` /
  `fb8ce70da37b5e5f3ffff5dddd5f8a10ea0b53fdc9db5048fa352da178b2e371`.
- Restore seal: `d11d4bc17480644af92323ba383f7bc2493fcf22a0f707f2f773ab5f277b5ad0`.
- Restore plan/result: `cf179f9a35c158ddb18701c11ed5fa0732ee26ac4adffdf12217590e2d091d11` /
  `bae452015cf3280eb120f16f24722c10497eb48bc96c92ae508c52ea93bd1108`.

The once-audited seal covers 16,284 files. Independent review rehashed that
closure and checked 130 current module pins while replacing semantic auditors
with failures to prove they were not rerun. Publication takes 22.634 seconds;
restoration takes 22.493 seconds, including post-dispatch byte validation.
All fresh raw SD extents, current files and rollback copies remain checked.
Only the two selected known-good historical payloads are rehashed; all other
archive metadata is carried honestly as `historical_archives_reverified=false`.
No archives are removed, unknown outcomes are never retried automatically,
and no power-loss atomicity is claimed. Keep frozen v2 tools immutable; derive
future ancestry from validated receipts rather than editing their fixed chain.

### Next passive RP1 configuration trace

`pcie-id-trial-ukgc_lll/probe.bin` is a distinct 18,122,400-byte image, SHA
`46d7f4c20b93bd6bb767c5cc2ca236b7316672d621f66f27d6d11ae43fdf5c27`;
manifest SHA `b781b3db8369d01d4cf162694ea51bd4ebad7d25b6f24b295038a852192f2d9e`.
It records the config-init/snapshot return codes, transfer result, pass/index,
read count, prior/current data, ID/header/BAR0/BAR1, and the already-read
selector/link status. No extra MMIO, endpoint writes, permissions or deadlines
are introduced. Only transport and snapshot objects replace the preceding
kernel's objects; elapsed link, AXI, clock and config transaction cores stay
unchanged. Twelve focused native/kernel/protocol tests independently pass in
3.356 seconds, including 416 callback failures, 16 header mismatches and 30
rejected BAR shapes. The package's seven actual native/dependency/mutation tests
also pass. These are offline results until this exact image is booted.

Frozen metadata erratum: the kernel manifest's unused `hardware_failure_receipt`
human-reference string omits `rp1-`. The correct preceding capture is
`build/rpi5/rp1-link-v2-serial-20261013`, with state/raw hashes recorded above.
No checker, compiler, protocol or admission consumer reads that field. Preserve
the frozen source/package rather than silently rewriting it; runtime authority
comes from the exact hash-bound package, descriptor and receipts.

## Passive UBUS trace and all-BAR preparation — 2026-10-13

### Corrected AXI physical result

The corrected image now completes UBUS, QoS, prelink clock and root-complex
configuration on the Pi, then fails later in link training:

```
RPI5XNU:PCIEID:END OK=0 PHASE=6 LAST=12 LIFE=3 FLAGS=1f ID=00000000 COMMAND=0000 BAR1=00000000 GEN=0 LANES=0 UBUS_STEP=5 UBUS_RC=0 UBUS_CB=23 GUARD=0 BANK=0 OFFSET=00004064 DIR=0 IO_STAGE=4 VALUE=00000004
```

The exact linked transport supports the 100-ms settling request as guarded
1-ms chunks; it does **not** retain the unmodified source's 100-us cap.
The last read follows PERST release, before the time/delay/time sequence and
link core's minimum/110-ms-upper elapsed checks. An elapsed-time failure is
plausible, but current telemetry does not prove it. PREPARED-to-END is a
0.239076-second host receive interval including all intervening setup and
UART transmission, not a device measurement of that delay. Preserve existing
deadlines and add passive link step/return/callback/elapsed fields next.

`rp1-axi-serial-20261013`: 28,414 continuous receive-only bytes, SHA
`358c100ab8e668f9bbbccc21aadad79c62747decf372bd53df546618ef600fe9`.
Fresh normal SSD Linux boot `64659855-bf91-4aeb-a8b6-f5cf196c9bc1` is independently
verified after captured f6/NVMe recovery. Both original firmware and working
zsh are restored, and full `pcie_axi_evidence.py` replay passes against
`rp1-axi-installed-20261013`, that capture and `rp1-axi-restored-20261013`.
The next inherited SSD artifact count is 128. Transfer-to-BOOTSYS host receive
interval is 17.182215 seconds, not an exact hardware watchdog-expiry measure.
Receipt hashes:

- Install plan/result: `5789ef1315cd0461aa228f0bb3cb2e18ccb831b8e232d20589fccf5293d8f81b` /
  `81cd946e98c6b6b0630007146c24f26d99f465bac1f0dfe17c507843b0bd9bac`.
- Restore plan/result: `390c73e43cf8b231ebe07b63160c4390178c82e11ed60180016fb507a7bc4d8b` /
  `d89c6f95984e3d99e1ed80e27f6842b25587dd954e2fb7463aa2becf7b7cd7ab`.

UBUS correction success is distinct from the failed RP1-ID result; no Ethernet,
endpoint write, IRQ delivery or DMA is claimed. A separate private elapsed-time
settling helper now counts guard execution within the requested interval, not
on top of 100 ms of delays. Per-chunk guards and the original 110-ms core ceiling
remain unchanged. Three actual-body ASan/UBSan groups independently pass in
0.537 seconds, including 201 guard failures, 200 backward-clock positions,
bounded stuck/under-reporting clocks and the unchanged link-core fault matrix.
New passive step/return/callback/elapsed telemetry is included. This corrects
a source-level additive-delay defect; it does not yet prove the physical cause
or a passing link. Full new kernel/package and board acceptance remain separate.

### Preserved prior failure and correction

The passive trace has now run once on the physical Pi. Exact final telemetry:

```
RPI5XNU:PCIEID:END OK=0 PHASE=6 LAST=7 LIFE=1 FLAGS=1f ID=00000000 COMMAND=0000 BAR1=00000000 GEN=0 LANES=0 UBUS_STEP=3 UBUS_RC=-5 UBUS_CB=16 GUARD=0 BANK=0 OFFSET=0000416c DIR=0 IO_STAGE=4 VALUE=00000060
```

All 16 callbacks completed; the guarded read itself succeeded. The original
UBUS predicate requires workaround bits `0x2800`, so `0x60` is rejected before
the timing-bit-reserved fallback. The original QoS and clock prerequisites
repeat that unsupported assumption. [Raspberry Pi's controller source](https://raw.githubusercontent.com/raspberrypi/linux/rpi-6.18.y/drivers/pci/controller/pcie-brcmstb.c)
in `brcm_pcie_post_setup_bcm2712` (AXI setup around lines 1013–1030) requests
all three workaround bits, then selects 15 outstanding
requests when timing bit 12 reads zero; it does not require bits 13/11 first.
The private correction preserves propagation-bit rejection and exact unrelated
field/final-fallback readback checks; known full-fix, timing-only-reserved and
observed all-fix-reserved shapes are separate explicit profiles. Unknown mixed
shapes remain rejected. This source/trace reasoning is not a corrected-board
success claim.

Five focused tests pass in 2.700 seconds for `pcie_axi_reserved_profile.py`:
all 65,536 low-register capability values, the actual three private C cores
under ASan/UBSan across three supported profiles and their original callback/
dependency/read failures, every single-bit corruption of both observed-C1 AXI
readbacks (64 rejection cases), and actual Cortex-A76 compilation. The latter
compares imports with the unchanged originals: no new imports, at most existing
`memcpy`; it does not pretend each isolated object is already a closed kernel.
The distinct full trace kernel is now linked at
`pcie-axi-trace-kernel-20261013-v2/kernel.rp1-config`, SHA
`4eab9039392a0fe027f8ee02330d3969c0f9d7a7d48c7297b94aa9052306b78c`;
manifest `fa38950c85264d4a635f1b20b511071f7af9d564f53c9600756312dc6924d644`.
Exactly the three private AXI objects replace the parent objects. The original
caller, access/firmware provider, mappings, trace, PE/watchdog and arm_init objects
remain unchanged. The complete kernel has no undefined symbols; three focused
source/object/link tests pass, independently repeated in 1.768 seconds.

Its separate `pcie-id-trial-v5t00fib` loader is 18,122,272 bytes, SHA
`0dae1bd1c1d2b1902161c246d80efccf5ec7da8abf56e481b236abf1aa237651`;
manifest `3e21f6fa338f3b9b274befbef14630d3f8fac2c24f543f78935e52c04209d322`.
Seven focused package tests pass, covering 34 checker predicates, 11,771 input
pins, the actual native 18-segment/105,832-relocation copy and retained Device/FDT
handoff. Unique trial tag is `29d4543aae9940768b877f02222e3b7a` under
`PCIE_ID_AXI_TRACE_TRIAL`. It retains the same secure firmware, single CPU,
no-init/zero-input behavior and bounded recovery. Its physical result is recorded
above; offline package success alone does not establish RP1 discovery or networking.

`rp1-trace-serial-20261013` contains 28,307 continuous bytes, zero serial TX,
SHA `38b27c5ee631a2d1268d55851383d9feea00d7457f5e1072531e6b6168af8fca`.
Automatic recovery selects f6/NVMe; PREPARED-to-BOOTSYS host receive interval is
16.634696 seconds, not an exact watchdog-expiry measurement. The independent
return receipt verifies SSD Linux boot `386225a6-2f95-4b53-a0e5-f6f6c56327f7`.
Both baseline files are explicitly restored. Full `pcie_trace_evidence.py`
replay passes; next inherited SSD artifact count is 110. Receipt hashes:

- Install plan/result: `db5bfb41956937140147bb6d9163e9041699c871b60a54147bf502dcecec232d` /
  `4c9fed906279e72ab45e6f7d2376e0f229cd08a7ae257a1e3c8bd3a6c6a1b759`.
- Restore plan/result: `b19a815e213dd46623ae72eb2e6791f2c698f9d3ffe0515c5158d255b0b56138` /
  `df963ee25196a7f3b9528b6fe75a8cc7814b2ee9224f11b50bb640eb56c0b993`.

The physical diagnostic remains failed. No RP1 ID, endpoint write, IRQ delivery,
DMA, packet traffic, full production ownership or storage durability follows.
No manual power action or soak was needed.

The first physical ID failure is recorded at the end of this document. The
distinct follow-up `pcie-id-trial-zyw6ujf_` adds the exact UBUS step/return code,
callback count, guard reason, bank, offset, direction, I/O stage and value to
the existing final diagnostic line. It adds no MMIO and changes no permission
or deadline. Image SHA
`ae96b496bdaf4b05923e7153bb3fc0474f7aa138b231cd8ceaa8e5db4faae759`;
manifest SHA `ec55c6f2a24fcbc274e708d55ea7bc0fb7cd986b1f5f8d842acd62a77699dc0f`.
The 18,122,272-byte image passes 32 package checks and six mutation tests with
11,729 matching pins. It retains single-CPU/no-init/zero-TX operation and the
paired secure firmware. The physical trace outcome above is separate from
these package checks.

Further offline work now handles all six endpoint BAR slots before any future
COMMAND.MEM enable; enabling that command affects every implemented BAR, not
just BAR1. `rp1-all-bars-kernel-20261013-checked/kernel.rp1-config`, SHA
`b37505e9efe7eddced272b47377ba5ba856856e77d9c524ca31b9a339fccbb0d`, links the
actual snapshot, size/restore and pure allocation-plan calls. Manifest SHA
`1402041446cde952c27b18e6ce10894bd7f0845df1a5a6c152ceb3b99a4ec14e`;
11,673 source/generated pins match. Five focused ASan/UBSan tests cover 649
callback failures, all 37 endpoint readback corruptions, 90 unsupported type
shapes, 4,256 nonoverlapping layouts, 83 malformed plans, and the actual
integrated caller's guard failures. Native loading agrees across 18 segments
and 105,832 relocations.

Exact original BAR restoration is proven only on successful access. After
an access/ownership failure, a write may already have posted; the code stops
and quarantines the transport without unauthorized cleanup writes. No
COMMAND, BME, ROM or device-BAR MMIO writes, DMA, interrupt delivery or packets
are authorized by these offline results. The all-BAR kernel is not packaged
or staged. A distinct composition with the corrected AXI objects also links,
but a BAR hardware trial remains held until actual controller/link/RP1-ID
success; the current physical failure is now in link training, not UBUS.

## Physical ABI / automatic return / dual restoration passed — 2026-10-13

Fresh SSH verified `kamidana`, normal NVMe Linux `/dev/nvme0n1p2`, original
boot `3977a538-fae5-434d-a94f-50c9422fea84`. The old pair installer stopped before
SD writes because FAT had only 6,565,888 bytes free. Its complete raw backups
and failed run remain preserved. The new, separate `firmware_pair_reuse_core.py`
and four wrappers reuse only the already protected, size/hash-verified
`probe.socket-identity-pre-pcie-access-20261012.bin`; they never overwrite or
delete that backup. Seven focused tests passed (32.301s), including wrong/
missing/symlinked backup refusal, actual file preservation, all five pre-rename
copy failures, space accounting, and full synthetic receipt replay. Evidence:
`build/rpi5/fwabi-reuse-verification-gcZPsND9/validation.json`.

Exactly one physical trial followed. Both new images were staged after full
SSD raw/file backups; exclusive receive-only recording was actually armed
before the SSH reboot. All 19 tagged markers complete: QUERY, CLAIM and three
CHECK calls, RC 0, final sequence 4/facts 0x1f, 485 PM checks, one PM reload,
three selective GIC-disable writes, no PCIe controller writes and no DMA.
Continuous capture records the subsequent BOOTSYS/bootloader sequence, actual
`0xf6` override, and NVMe boot. Host receive time from owned-watchdog ARMED to
BOOTSYS is **16.633365 seconds**; this is not exact watchdog-expiry timing or a
separately decoded reset cause.

Independent read-only SSH then verifies normal NVMe Linux boot
`54e0eebb-058e-4954-91b1-b1fed9aa37bd`, the exact root/card, unmounted SD
partitions, and boot-mode 6/partition 1/tryboot 0. Explicit pair restoration
preserved trial artifacts and restored the full original hashes:

- `bl31.bin`: `413a050eb17258087bafa8025d7ae456636f44f9cf9d8503fc8ed9c568d75b46`.
- `probe.bin`: `f2aee33a3e0269bce0cbe9299ee0aa95091a764d4ce77dd30181875c6b10f536`.

Full `pcie_fw_reuse_recovery_evidence.py` replay passes against:

- `build/rpi5/fwabi-reuse-pair-installed-20261013`, result SHA
  `66493ddd3d3502fd3e89e0a268440d646e07cb32f62b10abb63ae0368f0a2651`.
- `build/rpi5/fwabi-reuse-capture-20261013`, 45,071-byte serial SHA
  `ac4becf22f83cc24c6e6c1e2b062f3fa4161d2fda2783b322ed80ee5eac78d23`.
- `build/rpi5/fwabi-reuse-pair-restored-20261013`, result SHA
  `fa5ed50d9bd2bb6ed6209e6b6584c16c2fd7698b60b4383f1aad8a5f69b7ccda`.

The inherited verified SSD artifact chain is now **70**. Config, DTB, MBR and
HFS remain unchanged; no HFS mount, manual power cycle, retry or soak. Firmware
ABI operation and bounded recovery are physically demonstrated. This does
**not** establish the remaining power/shared-domain/source/endpoint/DMA
contract, XNU PE/IOKit execution, link/RP1 discovery, Ethernet or durability.
Next close the concrete provider/caller and test bounded controller bring-up;
root/SSH diagnostics continue independently.

## Latest verification — full trial/return/restoration replay, 2026-10-13

Added `tools/rpi5/pcie_fw_recovery_evidence.py` and
`capture_pcie_fw_linux_return.py`, with a separate nine-test module. The
previously accepted pair installer, recorder and all **16 source pins** remain
unchanged. These complete the recorded recovery-verification path, **not** a
physical trial, controller admission or Ethernet result.

The replay requires the validated installed-pair receipt, matching archived
publication sources, exact source-bound terminal capture, actual armed snapshot,
zero serial TX, complete bounded receive-journal coverage and nonregressing
monotonic/zoned times. It independently replays the full 19-line tagged ABI
sequence, one fresh SD boot, ordered subsequent BOOTSYS/bootloader/NVMe selection
and one actual `0xf6` override. The host receive interval from owned-watchdog
marker to BOOTSYS must be within the 10–45-second diagnostic window; it is not
an exact hardware-expiry measurement or independently decoded reset cause.
Missing/duplicate/fallback boot, partial/faulted traces, malformed types and
premature hardware claims fail closed.

ABI/boot bytes alone do not prove a normal Linux return. The new collector
requires an already completed receipt-bound capture and the cooperating board
lease before **one read-only SSH attempt**. It uses the unchanged real exact-
card/root/boot identity helper twice around the selected bootloader-property
reads. It requires a new boot UUID, exact `/dev/nvme0n1p2` root/UUID/card layout,
both SD partitions unmounted and normal boot-mode 6/partition 1/tryboot 0.
The saved local return binds the installed pair, serial digest, read-only
collector/source pins and observation time. It never overwrites an old outcome,
waits/retries automatically, mounts/writes the SD, sends serial data, reboots,
repairs or restores. Timeout writes no success receipt.

Finally the full replay requires explicit **dual-pair restoration**, its exact
ancestry/install hashes and fresh Linux UUID, archived source hashes, both old
firmware/zsh digests, typed protected-extent/file receipts and the modeled
65→70 inheritance chain. It grants no controller/domain/source/endpoint/DMA
permission, new XNU PE/IOKit runtime, Ethernet or durability claim. Actual
execution remains separate from consistency of supplied evidence files.

All **nine targeted tests pass in 23.591 seconds**. They exercise actual
validators/local replay and collector code with **synthetic** serial/receipt/
timestamp/SSH fixtures, malformed journal/capture/return/restore/armed fields,
wrong/fallback/missing boot sequence, deadline failures, timeout/no-overwrite
and both package/CLI import paths. No physical result is derived from these
fixtures, and no broad suite was rerun. Direct CLI help/import checks and
`git diff --check` pass. Exact source hashes and limits are preserved in
`build/rpi5/fwabi-recovery-verification-20261013/validation.json`.

One fresh SSH check again timed out. Read-only Mac network inspection now shows
the Pi address uses the **default route via `10.0.0.1` on `en0`**, rather than a
specific/direct route to the `192.168.4.x` LAN. `kamidana.local` returned no
address and the Pi IP has no ARP entry. This is a reachability clue, **not proof
of Pi power/OS or a reason to power-cycle it**. No serial port was opened, SD
mounted/written, firmware installed, reboot/power requested or live return
collector invoked. Current Pi OS/boot remains unverified.

**Next:** restore Mac reachability to the Pi LAN or an authorized route/VPN,
then freshly verify normal SSD Linux, the exact card/baseline and sole board
ownership. Follow the already prepared single guarded install→armed capture→
ABI/recovery boot→independent Linux return→explicit pair restoration sequence.
Do not change Mac networks silently, repeatedly probe/reboot an unknown Pi,
retry unknown outcomes or repeat a soak. Offline implementation of the remaining
network/userland scope can continue meanwhile; full objective and Gate 4 hold
are unchanged.

## Latest tooling — guarded dual-file publication/restore and recorder, 2026-10-13

The actual pair installer and receive-only trial recorder are implemented and
narrowly tested. **Neither has been run against the board.** New sources:
`tools/rpi5/firmware_pair_install_core.py`, `stage_pcie_fw_trial.py`,
`serial_pcie_fw_trial.py`, `rpi5_board_lease.py`, plus their two test modules.
Earlier accepted firmware/kernel/loader sources and artifacts remain unchanged.

The pair publisher uses the existing unchanged exact-card/root/boot identity,
full raw snapshot, file-copy/hash and owned-mount helpers. Its separate profile
explicitly changes **both** `bl31.bin` and `probe.bin`; it does not extend or
silently repurpose a single-file install profile. It requires the current
restored FAT `fd2d2072…` and **60 inherited SSD artifacts**, not the older FAT or
backup counts. Complete fresh MBR/FAT/HFS snapshots and both old files are
fsynced/readback-verified on SSD before FAT remount-RW. Both FAT backups and
both temporary images must verify before the first publication. Actual free
space is checked on both SSD and FAT. Config, DTB, MBR/HFS content and every
prior protected boot file remain protected; HFS is never mounted.

Firmware publishes first, loader second. Each rename has guarded source,
protected-file, mount/root/boot checks, fsync/readback and distinct durable SSD
before/after journal files. There is **no claim of two-file or FAT power-loss
atomicity**. Exceptions preserve the exact partial state and all backups;
never automatically retry, reboot, delete a temporary, clean up a foreign
mount or roll back a mixed pair. The owned directory FD closes before unmount.
Typed receipts must match the exact locally reconstructed ancestry, baseline,
fixed transitions and complete backup chain. Explicit restore requires a
distinct verified SSD Linux return, preserves both trial files, and restores
the exact old firmware and working zsh bytes with distinct names. Modeled chain
counts become 65 after trial staging and 70 after restoration; **the actual
current chain remains 60**, because nothing was installed.

The recorder requires a validated **installed trial-pair receipt**; a plan or
restore receipt cannot arm it. It binds both digests and the image tag, refuses
any existing serial opener/ambiguous ownership lookup, then uses TIOCEXCL.
New publication/capture coordinators share a nonblocking local OS board lease;
metadata alone is never proof of a live owner. Legacy tools/humans must still
cooperate, so fresh external-state/ownership inspection remains required.
The recorder only receives at 115200 baud, journals/fsyncs all chunks, enforces
a finite capture/size bound, and never sends commands, reboots or reopens after
a disconnect. The armed marker is published only after actual port setup and
receipt/source revalidation. Partial/faulted ABI traces return failure even if
stream capture was continuous. Full ABI observation still **does not prove**
new XNU PE/IOKit execution, autonomous reset or normal SSD return; continuous
boot evidence and independent fresh Linux verification remain separate.

All **17 narrowly targeted tests pass in 43.927 seconds**; no broad suite was
rerun for this tooling step. Actual regular-file operations are exercised with
explicit mount/block/identity/port/time/receipt doubles: all six backup/temp-copy
failure positions, both post-rename failures, all five SSD journal boundaries,
all four stale SD artifact names, wrong candidates/baseline/config/space,
foreign mounts, explicit restore, typed/ancestry/chain mutation, zero-TX
receive loop, partial/fault/disconnect, existing serial handles and real OS
lease exclusion/reacquisition. This is not physical publication or recovery
evidence. Earlier 101-test/package/kernel evidence remains historical and
separate.

Local plan-only artifact `build/rpi5/fwabi-pair-plan-20261013/`:
plan SHA256 `2ea653343d251e4567b48c63829856a3178f35a1e8329cbbe0b1bcaadc22e211`,
all **16 current/archived source pins** match, no remote run. Its boot ID is
only the last verified `3977a538…`; it is **not a fresh live-write authority**.
See `validation.json` for exact tests and limits. The Mac probe callout
`/dev/cu.usbmodem102` exists and lsof finds no reader; no other trial coordinator
was observed. Both fresh SSH checks to `sandrzej@192.168.4.23` timed out, so
**the Pi's current OS/boot is unverified**. No serial open/input, SD mount/write,
firmware install, reboot or power action was performed.

**Next:** freshly verify normal `/dev/nvme0n1p2` Linux, exact card/current raw
baseline and sole board ownership. Create a fresh guarded pair installation
run, validate the installed receipt, arm the receive-only continuous recorder,
then one bounded ABI/recovery boot. Independently confirm a new normal NVMe
Linux boot and explicitly restore both old files before further controller
work. An unknown publication/boot outcome requires inspection of the same run,
journal/mount or live process handle, never a blind retry or another boot.
Controller writes remain held until independent domain/source/endpoint/DMA
prerequisites are met. Full Ethernet, zsh/TTY, SSH/Apple CLI/layout and the
separate Gate 4 durability hold remain active.

## Latest preparation — standalone paired firmware ABI trial, 2026-10-13

The next **actual standalone BL33 caller** is built and audited separately. It
executes the unchanged watchdog lease, selective NS IRQ core, NS firmware client
and real SMCCC64 leaf against the separately built EL3 verifier. This is **not
new XNU PE/IOKit execution**, a full power/source/endpoint/DMA owner, controller
initialization or Ethernet. No board installation/execution is claimed.

New sources: `loader/rpi5/pcie_fw_trial.{h,inc}`, `pcie_fw_trial_mmio.S` and
`probe_fw_trial_main.c`. The unchanged primary-only recovery entry validates
actual placement and transitions EL2→EL1 with MMU/cache off and DAIF masked.
Actual original-FDT decoders validate RAM/reservations, UART/PM, CPU topology,
PSCI-SMC and PCIe2/RP1 bindings before admission; other CPUs must be off.
The diagnostic retains its primary affinity and checks local DAIF at every
platform callback. One invocation until reset, no cancellation/retry/release.

Sequence: one real 15-second watchdog reload → three exact selective GIC W1C
disable writes → firmware QUERY/CLAIM → three CHECK calls separated by bounded
at-least-two-millisecond waits → final watchdog check → non-servicing park.
Each firmware call is bracketed by fresh NS IRQ checks, including the real
watchdog checks around every NS GIC read. The complete success path has
**five SMCs, 229 NS GIC reads and 485 watchdog checks**, with no extra lease or
reload. NVMe interrupt bits, pending/active/group state and all controller/
calibration/endpoint/DMA registers remain unwritten. The secure service reads
its own GIC/reset43/RESCAL/PM view; these observations remain distinct from full
controller ownership. Any returned failure quarantines all three local sessions;
fatal exceptions park without resuming or cleanup. A hung access/SMC is not
converted into an invented error: autonomous hardware reset is still a board
requirement for this new paired image.

Accepted local package `build/rpi5/pcie-fwabi-y_995zop/`:

- BL33 **55,552 bytes**, SHA256
  `3cd15bad801917b12352122cbf226f502cad043737730cf5e2bccc51636d9de6`.
- Manifest SHA256
  `c37e42b3925fb58ec4474511ec34accaccd8779c83682b170a076be30025c69a`;
  tag `8d86ee6660a94fbea98236832bcfc155`.
- Paired firmware SHA256
  `dc8dcbd30a9aac2b622fc876f5e3577699ae12e312183b11bb7ffaf71897d64b`;
  exact prior firmware manifest/producer chain included, no firmware rebuilt or
  installed. **9,088 unique pins** (9,063 inputs plus 25 outputs) match.
- **17 package checks / 11 exact emitted leaf checks** pass, including all 18
  SMC instructions, fixed PM/GIC access leaves, DAIF/affinity, PSCI and counter.
  Static A76 warning-as-error compilation, zero undefined symbols, raw/ELF
  agreement and no controller/secondary implementation. Conservative sum of all
  linked nonrecursive C frames is **15,440 bytes**; 16-KiB stack with a separate
  512-byte assembly reserve. This is not a measured physical high-water.

`tools/rpi5/pcie_fw_trial_serial_core.py` strictly replays all **19 tagged lines**,
exact field/call order, fixed write/check budgets, same opaque owner, advancing
firmware counters, ABI/facts/sequence, bounded CHECK intervals and terminal
non-servicing result. Installed firmware/image hashes must be independently
verified by the future installer/recorder; merely passing hash strings or a
fixture to this parser is **not** installed-image or recovery proof. It never
opens a serial port or sends bytes. A continuous capture spanning reset/actual
NVMe boot plus a new independently verified normal SSD Linux boot remains
required separately.

All **101 focused regressions pass in 40.210 seconds**. ASan/UBSan runs the
actual trial protocol, PM/IRQ/client cores and firmware producer/service with
explicit MMIO/counter/context/SMC/UART/lock doubles. It covers all **982 PM-read**
failure positions, **15 record** failures, **20 ABI** mutations, absent/busy
firmware, active/group/reset/RESCAL failures, reentry/retry/context/affinity,
stalled time/countdown and malformed model binding. Its actual modeled event
trace also passes the strict parser; fixture missing/duplicate/reorder/tag/field
and timing cases remain explicitly nonphysical. The complete earlier kernel's
**11,505 pins** reverify unchanged, and saved physical recovery/access/zsh/socket
evidence replays within the selected suite. See the package's `validation.json`.

Fresh read-only SSH verifies SSD Linux boot `3977a538-fae5-434d-a94f-50c9422fea84`,
root `/dev/nvme0n1p2`, both SD partitions unmounted. No serial open/input,
SD mount/write, firmware install, reboot/power operation or new XNU execution.
**Next:** implement/test the guarded **dual-file** `bl31.bin` + `probe.bin`
installer and restore, inheriting the current restored FAT and **60 artifacts**;
do not reuse a single-image installer to silently replace firmware. Then bind
and arm a receive-only continuous recorder before one ABI/recovery trial.
Only after the new pair's autonomous return is proven, continue concrete
domain/source/endpoint/DMA ownership and the real XNU controller caller, RP1,
IRQ delivery, DMA/GEM and wire packets. Full zsh/TTY, SSH, Apple CLI/layout and
separate Gate 4 durability remain in scope.

## Latest integration — real XNU firmware client, 2026-10-13

The actual retained PE owner, pure NS protocol client and real SMCCC64 assembly
are now linked into a distinct complete kernel. Copied production controller
startup calls **one PM claim → selective NS IRQ claim → EL3 QUERY/CLAIM →
reset44/RESCAL/SerDes**. Every controller guard freshly checks NS IRQ and the
EL3 verifier before/after the independent provider callback. Existing power/
clock/source/endpoint/DMA obligations remain mandatory; the provider is not
replaced by an unconditional-success callback. No boot caller, activation,
firmware install, combined loader or board execution is added here.

Actual implementation:

- `loader/rpi5/pcie_fw_client.{h,c}`: QUERY ABI/masked Group-1 checks, one
  owner CLAIM, exact facts/sequence, strictly advancing returned counter,
  conservative nine-second NS deadline and 65,536-check cap. Status errors,
  `SMC_UNK`, malformed ABI, stale/overflowed time, reentry and reuse fail closed;
  disjoint output stays unchanged on failure. No cancellation/retry/release.
- `loader/rpi5/pcie_fw_smccc.S`: actual four-register call/return, x2..x7
  cleared before SMC, output pointer retained in callee-saved x19, preserved
  x19/x20/frame/LR, ordered call and four raw reply stores. All 18 emitted
  Mach-O text words are independently checked, not merely disassembled.
- `pexpert/arm/rpi5_pcie_fw_owner.inc`: one permanent nonblocking owner gate,
  actual retained `current_thread()` reference, same PM/IRQ owner and real NS
  IRQ/PM checks around every SMC. Claim requires masked local I/F; check may
  run IRQ-enabled. No new mapping or hardware register write is introduced.
- `iokit/Kernel/BCM2712PCIeFirmwareTransport.inc`: actual firmware handoff/
  guard. It uses XNU's interrupt API and restores prior state only on successful
  firmware claim. Failure is terminal with local interrupts left masked;
  future boot code must park for the owned watchdog, never resume/sleep/retry.
  The previously accepted IRQ handoff is copied mechanically without changes.

Each successful new controller guard makes **14 PM checks**, 120 modeled GIC
reads and two firmware CHECK calls. The actual retained IRQ API supplies PM
checks around those secure calls; no extra watchdog lease or reload exists.
These counts consume the existing finite global allowance, not a new allowance
per guard. They are model/source sequencing evidence, not physical latency or
hung-SMC recovery measurements. Foreign threads/interrupt context cannot take
over the firmware owner. Both PE thread references remain held until reset.

Accepted local artifact: `build/rpi5/pcie-fw-client-kernel-20261013-final/`:

- Kernel **17,973,584 bytes**, SHA256
  `59f76af5ffac9e5f81f9ab149ed5a4c0f156c40f7724e2e92ad8bb945c24407e`.
- Manifest SHA256
  `4a2c9170a0413415410cf7719310ad1bd65e207f2d62d951e2b35502304d990e`.
- **11,505 unique pins** (11,474 inputs, 35 generated entries, four overlaps),
  including the exact accepted firmware producer and prior IRQ kernel chain.
- Three actual C/C++ units are warning-free, SMCCC object has exact audited
  bytes, complete linkage has zero undefined symbols and the same ten old
  linker warnings. All 25 selected controller/IRQ/firmware entries are uniquely
  executable and all seven previous C++ initializers/rebases remain intact.
- Native loader host-buffer validation agrees: 18 segments, 105,829 local
  relocations, 19,038,208 materialized bytes and 17,973,712 container bytes.
  Entry/trampoline remain `0xfffffe0007513488` → `0xfffffe000751505c`.
  This is not physical loading or new kernel initialization proof.

All **94 focused regressions pass in 34.200 seconds**. One native ASan/UBSan
harness runs the actual NS client and PE include through the actual firmware
producer/service; MMIO, counter, XNU thread/IRQ, SMCCC transfer and EL3 lock are
explicit doubles. It tests 12 ABI-result mutations, six NS IRQ failures,
missing firmware, owner/reentry/retry/thread/context, timer/deadline/check-cap,
alias refusal and atomic output. A second executes mechanically selected real
`runInitialPHY` and the new guard with actual PE/IRQ/client code: all **222 PM**,
**32 firmware-call** and **15 provider** returned-failure positions, provider
state/IRQ/closure/reentry attacks, both caller interrupt states, all ten access
phases, and unchanged legacy initial-PHY-only behavior. PHY cores and firmware
responses in that transport harness are explicit doubles; separate unchanged
core tests and the real full-kernel build remain distinct evidence.

The Pi remains on verified SSD Linux boot
`3977a538-fae5-434d-a94f-50c9422fea84`, both SD partitions unmounted. No serial,
SD write/mount, firmware change, reboot, power operation or new XNU execution
occurred. The working zsh image and tested old firmware remain preserved.

**Next:** add a distinct firmware-ABI trial caller/package and a guarded dual
`bl31.bin`/`probe.bin` installer/restore using the current FAT baseline and
**60 inherited artifacts**. Test the exact new firmware ABI/ownership/checks
and autonomous SSD return before allowing controller writes. Then close the
remaining concrete power/shared-domain/source/endpoint/DMA provider, wire the
actual controller boot caller and continue RP1/BAR, IRQ delivery, GEM and wire
packets. Firmware observations are not a blanket permission or secure-DRAM
isolation guarantee. Full zsh/TTY, SSH, Apple CLI/layout and recovery scope
stays active, with Gate 4 durability separately held.

## Latest implementation — actual EL3 firmware verifier, verified 2026-10-13

The next concrete producer is implemented in `firmware/rpi5/pcie_verifier.*`,
with actual ordered ARM64 read/counter/lock leaves and a registered TF-A fast
SiP64 service. A separately copied complete TF-A image builds and links; it is
**not installed or board-tested**. The existing IRQ/controller kernels and
installed firmware remain unchanged. This closes an implementation gap for
independent secure-view checks, not the entire physical ownership contract.

The pinned TF-A source initializes SPI groups as non-secure but does not clear
all existing enables in that helper. Consequently we must not infer a disabled
source or secure-group ownership from its setup call or NS RAZ/WI reads. The
new service reads the GIC from EL3's secure Device mapping, requiring GICv2
security extensions and enough INTIDs, selected Group-1 membership, no selected
active bits and (for ownership) selected enables already cleared by the real
NS IRQ lease. Masks remain IDs 160..223 and 261..266; NVMe bits are excluded.
It never changes grouping, routing, enable, pending or active state.

The [reference controller driver](https://raw.githubusercontent.com/raspberrypi/linux/rpi-6.18.y/drivers/pci/controller/pcie-brcmstb.c)
also identifies shared RESCAL's dependency on controller 1. The verifier freshly
checks reset43 stays released and reads RESCAL, without writing either reset or
turning controller 1 off. These are accessible-state observations, **not** proof
of all clock/power/source/endpoint/DMA ownership. The retained-domain provider
and actual XNU owner/caller must still supply the rest of that contract.

Private development ABI (not an allocated public SiP standard): QUERY
`0xc2007f10`, CLAIM `0xc2007f11`, CHECK `0xc2007f12`. Only trusted non-secure
callers with reserved x2..x4 zero are accepted; no address or register value is
passed from NS. QUERY precedes claim and returns observations, not permission.
CLAIM binds one nonzero opaque NS-kernel owner token until reset, requires an
already armed full-reset watchdog with >=13 seconds actual margin, and refuses
an already-running calibration. CHECK revalidates group/mask/active, retained
controller-1 domain, PM route/countdown, unchanged frequency and monotonic
counter. Own reset44/calibration may legitimately be in flight after claim.
It never reloads PM, calibrates, changes clocks, starts DMA, enables interrupts
or exposes a release/retry. Failure quarantines; public output stays unchanged.

The service uses one actual LDAXR/STXR attempt with only forward failure
branches, never a blocking spin loop. Concurrent/reentrant SMCs fail without
waiting. The producer adds a ten-second independent counter deadline and
65,536-check cap, requires countdown decrease after one counter millisecond,
and keeps >2 seconds actual margin. Neither finite software bounds nor a
successful build bound a hung secure MMIO transaction: the modified firmware
still needs its own guarded board/recovery trial. Pi 5's unprotected DRAM and
opaque owner token do **not** create trusted isolation against hostile NS
kernel code or Apple secure-boot guarantees.

Accepted local build: `build/rpi5/pcie-el3-verifier-20261012-checked/`:

- Firmware **45,174 bytes**, SHA256
  `dc8dcbd30a9aac2b622fc876f5e3577699ae12e312183b11bb7ffaf71897d64b`.
- Manifest SHA256
  `cd2fc81f2576f44a63587b917ef42eb421b317061a35311163a3d2c27c069a60`.
- **9,024 unique pins**: 4,513 original/project inputs and 4,511 generated/
  copied-source entries. Actual clang/llvm-nm/Zig binary identities are pinned.
- Actual ELF/raw agreement, no undefined/dynamic symbols, entry `0x1000`,
  firmware memory ending at `0x14000` within the reserved `0x80000`, exactly one
  real fast-SiP service descriptor pointing to the emitted handler, and exact
  emitted read/counter/one-attempt-lock/unlock bytes pass.
- Added nonrecursive C frame sum **336 bytes**; this is the new service's frame
  increment, not total TF-A runtime stack high-water. Platform stack is 4 KiB.
- Full verbose make commands, patch/compile/link output and source copies are
  retained. Original checkout remains clean at pinned revision 332b62e; original
  installed-candidate `bl31.bin` retains SHA256 `413a050e…`.

All **91 selected regressions pass in 25.379 seconds**: the real firmware build,
actual core/service with explicit MMIO/clock/SMCCC/lock host doubles, every one
of 30 modeled claim/check MMIO failure positions, bad TYPER/security extension,
owner/reentry/retry/counter/deadline/stall/check-cap/ABI cases, and existing
physical access/watchdog/zsh/socket saved replay. The old accepted IRQ kernel
pin sets and unchanged zsh/socket package remain separate evidence. This is
not a new physical firmware or XNU execution result.

Next implement the actual XNU SMC consumer/retained controller owner against
this fail-closed API, wire the real controller startup and terminal park path,
then prepare a dual firmware/loader trial against the current restored SD and
60-artifact chain. Preserve/verify the old TF-A as well as zsh; the old
single-image installers must not silently publish a new `bl31.bin`. First
validate the firmware ABI and recovery on the board before controller writes.
Continue remaining domain/endpoint/DMA admission, controller/RP1/BAR, IRQ/GEM
and packets; no “all ownership granted” flag substitutes for that work.

## Historical accepted kernel composition

A distinct complete kernel now calls the actual selective non-secure GIC lease
from the real controller startup path. The ordering is **one PM watchdog claim,
IRQ claim, then reset44 / shared RESCAL / SerDes**, followed by the existing
UBUS, unused-window, QoS, clock, RC/window and link methods. Every actual
controller register guard rechecks the same IRQ lease before and after the
independent lifecycle callback. No boot caller, personality, combined loader
package, installation, board execution or Ethernet acceptance is claimed.

## Immutable artifact and verification

```
python3 tools/rpi5/build_pcie_irq_transport_kernel.py \
  --output-dir build/rpi5/pcie-irq-transport-kernel-NEW
PYTHONPATH=tools/rpi5/tests:tools/rpi5 python3 -m unittest \
  tools.rpi5.tests.test_pcie_irq_transport -v
python3 tools/rpi5/compare_native_macho.py \
  build/rpi5/pcie-irq-transport-kernel-20261012-final/kernel.pcie-irq-transport
```

Preserved kernel: `build/rpi5/pcie-irq-transport-kernel-20261012-final/kernel.pcie-irq-transport`,
**17,972,680 bytes**, SHA256
`8412084e8c6af2224b66a5da414cb8792ac3fea063aa814dae22988f71883104`.
Manifest SHA256:
`563cf343a50bdeafd5bcaac7e105f5f1188a6839ac744291b6ee57d46055a4f7`.
All **2,435 unique pins** revalidate: 2,419 inputs plus 18 generated entries,
with the two copied source files present in both lists. The unchanged physically
tested zsh/socket package retains all 35 checks.

The builder verifies the accepted IRQ receipt and all dependencies, copies the
accepted controller source/header, and applies the new zero-fuzz patch only to
those copies. It compiles the actual IOKit unit with real XNU headers and the
accepted invocation, adding explicit diagnostic opt-ins. Only the old
controller object is replaced in the accepted IRQ kernel's complete filelist;
the actual PE IRQ/PM and C-core objects remain byte-for-byte unchanged. No
host doubles, fake definitions or duplicate cores enter the kernel.

The new unit is warning-free; the complete link has zero undefined symbols and
the same ten pre-existing linker warnings. All **18 selected actual controller,
IRQ and handoff implementations** are uniquely executable. The seven original
added C++ initializers and their real rebases remain intact. Emitted actual
transport assembly retains real interrupt-API/PE/core calls and ordered
halfword `LDRH` / `STRH` accesses. The API definition inspected in this tree is
`osfmk/arm/machine_routines_common.c:ml_set_interrupts_enabled_with_debug`.

Actual native-loader host-buffer validation agrees: 18 segments, 105,826 local
relocations, 19,021,824 materialized bytes and a 17,972,808-byte container.
Entry `0xfffffe0007513488` branches to `start_first_cpu` at
`0xfffffe000751505c`. This is not physical loading, initialization or access
proof, and the old loader is not silently changed to embed this new kernel.

## Ownership and interrupt-state sequencing

The new production include is `iokit/Kernel/BCM2712PCIeIRQTransport.inc`.
The copied real `runInitialPHY` still self-retains, sets claim-attempted and
calls the PM API once. In controller mode it immediately calls the new IRQ
handoff, before even initializing reset callbacks. Legacy initial-PHY-only
mode remains unchanged; it does not gain controller/IRQ authorization.

The handoff checks the actual preparing thread, singleton, phase and open
retained provider. It masks standard local asynchronous exceptions through
**XNU's own `ml_set_interrupts_enabled(false)`**, including the kernel's
interrupt-disable accounting, then calls the actual PE IRQ API using `this`:
the same identity that owns the already-armed PM lease. It does not issue raw
DAIF writes, acquire a second watchdog lease or invent completed IRQ state.

On success it marks the transport's claim and uses the same XNU API to restore
the caller's prior standard interrupt state. If restoring interrupts services
an AST/preemption, the first controller callback must still freshly recheck
watchdog, thread, provider and GIC state before touching hardware. The private
`irqClaimed` field is a one-shot sequencing condition, not physical admission;
real PE reads, ownership and watchdog checks are still mandatory.

**A failed IRQ claim is terminal and leaves local interrupts disabled.** Some
W1C writes may already have taken effect. There is no restoration, retry,
cleanup/unmap, reset/calibration access or output publication on that path.
The object/provider/maps and PE thread reference remain held until autonomous
reset. Future admitted boot code must park for that reset rather than resume
ordinary execution, sleep or restore interrupts after the returned failure.
There is deliberately no such boot caller in this artifact.

The real guard calls `pe_rpi5_pcie_irq_check(this, ...)` both before and after
the independent provider. It also rechecks the thread, singleton, open provider
and phase after that callback, refusing reentry, provider closure, mapping loss,
selected re-enable/activation or ownership change before the next access.
One successful guard makes **six PM lease checks**, including the checks inside
the two PE IRQ operations. These consume the existing finite global budget;
no new allowance or timer reload is introduced. Host counts are not physical
latency measurements or proof the watchdog can recover a hung access.

## Actual-body host tests and limits

Four focused tests pass. The native ASan/UBSan harness executes the production
new handoff/guard, actual PE IRQ include and real IRQ C core. It mechanically
selects the patched real `runInitialPHY` and actual observation structure from
the copied source/header, rather than retyping the startup algorithm.
IOService/thread/interrupt/PM behavior, GIC registers and the initial PHY core
interfaces are **explicit test doubles**; these tests do not execute IOKit,
real reset/calibration, interrupts, timing or autonomous recovery.

The harness exercises every one of its **92 watchdog-check failure positions**
and **15 provider failure positions**, atomic public output, one self-retain /
PM claim / PE thread reference, exact three GIC writes before any reset access,
both caller interrupt states, active-before-claim and ignored-mask writes,
missing GIC mapping, insufficient TYPER, changed mask on interrupt restoration,
foreign/null thread, interrupt context, missing singleton/open provider,
provider reentry/closure/phase/mapping/enable/active changes and no retry.
All ten real transport access phases execute fresh two-API checks with exactly
40 modeled GIC reads and six watchdog checks per successful guard. Pending
changes remain allowed and no further GIC writes occur. Legacy mode's no-IRQ
behavior is separately exercised. The real kernel build, immutable pins,
filelist replacement, symbols, actual instructions and opt-in refusal are also
checked. The unchanged initial PHY and subsequent controller C cores retain
their separate existing tests; the new harness does not fabricate their
physical completion.

The expanded **286-test regression suite passes in 172.591 seconds**, including
the existing controller/PHY/IRQ/firmware/loader/serial-root/recovery and local
Unix/UDP/TCP checks. Local-loopback access was enabled for those socket tests;
this is not a Pi Ethernet or remote SSH test.

## Admission still needed / next sequence

The copied header now explicitly distinguishes **PRECLAIM** from later phases.
PRECLAIM verifies firmware cooperation, safe current interrupt delivery,
exclusive controller/endpoint/DMA state, accessible inherited/shared domains,
and bounded fault/reset/SSD-return prerequisites for the coming PM/IRQ handoff.
It cannot claim a lease that does not exist yet. INITIALIZING callbacks run
only after both real claims. Subsequent HELD_RESET and RELEASED obligations
remain phase-specific; training is not falsely required to be link-up.

The selective mask remains the [accepted non-secure-view component](GATE5-PCIE-IRQ-MASK.md),
not secure firmware ownership, GIC source/MIP quiescence, endpoint/DMA safety,
an interrupt handler/delivery driver or physical accessibility proof. RAZ/WI
zeros and absent clock properties cannot replace those requirements. Concrete
shared-domain/power/clock/source/endpoint/DMA and fault-recovery admission is
still required before opt-in registration and any physical controller trial.
Then combine the actual loader/new kernel/root, preflight and guardedly test
controller/RP1 discovery; continue config/BAR policy, IRQ routing, DMA/coherency,
GEM clocks/PHY and packets, followed by network services/SSH.

No accepted image/source/root changed. No Pi/serial/SD/power/firmware/reboot/soak
operation or fresh external OS/root observation occurred. Real serial zsh/TTY,
Ethernet, sockets/SSH, Apple utilities/Darwin layout and recovery remain in the
full active objective; Gate 4 durability is separately held.
# Physical first-ID trial: reached provider, failed in UBUS interval — 2026-10-13

`build/rpi5/pcie-id-trial-wpo7wy6_/probe.bin` (18,122,264 bytes,
SHA `69e0839ca3f54268e5ed10c26286db596caa0f7a7e4586e15222c5f0872175f5`)
was paired with secure firmware `dc8dcbd3…` for one receive-only trial.
The actual XNU single-CPU provider prepared successfully; final telemetry:
`OK=0 PHASE=6 LAST=7 LIFE=1 FLAGS=1f`, zero RP1 ID/BAR/link outputs.
Phase 7 is entered after the initial PHY sequence succeeds. This localizes the
remaining failure to the UBUS init/write/readback/guard interval; it does not
prove link training or controller completion. Current register policy matches
the reviewed Linux source; no unsupported mask relaxation is justified.

Capture `rp1-id-serial-20261013/serial.bin`: 28,202 bytes,
SHA `4bbd4d0e9df087f275c35d9094e8fb8a0609ff6cd3bfbc291115b2121113abdf`,
zero TX and continuous receive journal. Its firmware tail shows f6/NVMe; the
separate failed-return collector verifies new normal SSD Linux boot
`9dc47716-f98b-44d5-9d23-35f1f5c6b169` and exact card. Failure is preserved,
not reclassified as an ID or full acceptance pass.

`rp1-id-restored-20261013` restored normal firmware and known-good zsh, retaining
92 SSD artifacts and the exact good SD backup. Plan/result SHAs:
`4af93755cb3dbfc4d51b777b64819a9a604ac1cca71040d20ee0c03147dccfa3` and
`667b44eb067fac81de833ad6427f8c40650ddcaf7a3b3c6248a93dcc7a6ee850`.
No manual restart, repeat soak, enabled inbound DMA or Ethernet success claim.
Next: passive exact-failure telemetry; later all-BAR inventory/assignment,
interrupt routing, DMA coherency and real GEM/wire traffic remain outstanding.

# Contained BAR attempt with bounded logging — 2026-10-13

The distinct `pcie-id-trial-kbne7vjh` package uses 14 bounded framed records,
with the final END following all diagnostic log calls. Image SHA
`2b8b9dbdd14c8c12fa46d0e85d7f09ad4c3044aba99aeb867f1c431463cc9951`,
18,123,008 bytes; manifest SHA
`d3b6e58f9a941d309678624b1384dfe9e8bee5e3f4eb654749f7b7770d112775`.
It retains the corrected root-route/link/snapshot path and adds only guarded
all-six-BAR sizing/restoration plus a pure, unapplied allocation plan. No
COMMAND writes, endpoint MMIO, memory decode, bus mastering, IRQ or DMA.

Physical result: the root route and RP1 snapshot succeed, then the BAR caller
is refused before its first endpoint write:

```
BARS_CALL=1 BARS_RC=-4 BARS_STATE=6 BARS_SLOT=0 BARS_TXNS=9 BARS_WRITES=0 BARS_PRESENT=00
GUARD=4 BANK=0 OFFSET=00009000 DIR=1 IO_STAGE=1 VALUE=00100000
END OK=0 PHASE=6 LAST=14 LIFE=3 FLAGS=1f
```

All six committed BAR rows remain zero, correctly representing no admitted
measurement. `BARS_WRITES` counts attempted writes in failure cases; here it
is zero. Do not claim restored or assigned BARs from the failed diagnostic.
The next investigation is the actual linked guard path, not a relaxed success
predicate. The split logging causes no observed panic through the recorded
normal NVMe return, unlike both old expanded single-line traces.

Capture `rp1-bars-root-serial-20261013`: 29,772 bytes, zero TX; raw SHA
`f4dd88808efec1cf692f879cf1c65886f527e4af3c9eb07acf42049258549611`,
state SHA `25a9437053d73bf9dcc795dee28641a01e45ae9b60be9ce48bfc4970c8bd8c0c`.
The complete capture/continuity/fault checks pass with `bars_trial_pass=false`.
Independent SSD Linux return boot `761222f1-d187-4eba-bd97-531330b3c848` is
verified. Original firmware and working zsh are restored; no manual power
action or soak occurred.

Restore `rp1-bars-root-restored-20261013`: canonical seal
`d290b0c0235e21b9f703d0e96d3f731e26721574a2a24bcb5e61f6353093128d`,
plan `0252b869d376af90dc2352ad4b9b42bd3aac51db78d594768a2f161e5cf7d77e`,
result `0f12234ce36edce84a7948fb16a1785bc9d41bc1475a2babbd64158d72a91506`.
Catalog 166 → 171 → 176. Install/restore publication measured 22.805 / 22.879 s.
Independent checks: seven kernel/protocol tests (1.751 s), six actual package/
controller tests (61.615 s), plus the exact 26,638-file sealed closure.

## Passive owner trace identifies finite PM-budget exhaustion — 2026-10-13

The distinct `pcie-id-trial-h62s3uww` loader and two-object owner-trace kernel
preserve every original guard, deadline, firmware call and MMIO operation.
Five extra bounded records snapshot existing in-memory owner state; the getter
adds no MMIO, SMC, clock read, reload or release. Image SHA
`48d5eb48b009257d7ce82c73ac520cae4a5de66513e64d8b3ac5c253745bf5ea`,
manifest `d1230ae161b7ed904e157927ff024d50230e03f47d2a5a3e077e8ebab7fefb7d`.

Actual Pi outcome: PM stage 6, RC -1, quarantined state 4, exactly 65,536
checks / 262,152 callbacks. IRQ stage 8 identifies its post-core PM check;
RPC stage 5 fails before SMC, with zero raw return fields. FW stage 6 / RC -1
quarantines at sequence 9361. The 54 MHz PM clock reads 2267657240 against
deadline 2897015906; FW last 2267656785 precedes deadline 2735017397.
Thus the finite check budget is exhausted, not the elapsed deadline. The BAR
diagnostic remains failed at transaction 9, zero writes; committed BAR rows
remain zero. No sizing/restoration/assignment success is inferred.

Capture `pcie-owner-trace-serial-20261013`: 30,248 bytes, zero TX, SHA
`ddfe62de09bb44e99afd7b8f20f391ca5f26e637a11c5bcdd41b20f091a29af2`.
All 19 rows, continuity and fault rejection through normal NVMe selection pass.
Independent SSD Linux boot `4394f030-8e3b-4f58-92a4-bba03a824616` is verified.
`pcie-owner-trace-restored-20261013` restores the original firmware/zsh pair:
seal `601846622cdddb214c607ba8fba216391efa2b24583a93001f76041d58305861`,
plan `b0c7f127f1d0d19c51e42ee26e474becbb63c3c258f06a28a2460845fb693ec1`,
result `ed6fb5e75079f9d055e1d88394b8f9afa45077757cadb6b4c4c9ab7296a87841`.
Full read-only replay passes with failed BAR outcome preserved; catalog
184 → 189 → 194. Publication/restoration take 22.994 / 24.955 seconds.

Next assess full-path nested-check accounting and a separately tested reduction
of redundant checks only where the remaining fresh firmware check already
enforces the same PM/IRQ/owner conditions. Preserve each transport MMIO
pre/post guard and provider owner-check site, failure quarantine, finite
budgets and all 9/10/12/15-second bounds. Firmware checks bracket the whole
lifecycle callback, not each of its individual provider register reads. No cache,
blanket limit increase, new access authority or hardware acceptance is implied.

## Fresh nested guards unblock actual all-six BAR sizing — 2026-10-13

The distinct `pcie-id-trial-zcz8y3h6` image is 18,123,304 bytes, SHA
`417165eaa29556756616605257866b49372ad4ee6d4ffd9826c715ad77350456`,
manifest `5d72e57ee438b20f9cb12c5074c75416a487044c1e8ee156020d1625fcfef661`.
Its kernel replaces only the transport object, retaining the exact owner
implementations and secure firmware. Two fresh firmware checks still bracket
each full transport guard, each retaining its IRQ and nested PM checks. Only
the redundant outer PM/IRQ checks are removed: 14 → 8 PM checks per full guard.
Transport MMIO pre/post guards, provider owner-check sites, whole-callback
firmware brackets, quarantine, finite limits and deadlines remain intact.

Actual Pi result: `BARS_CALL=5 RC=0 STATE=5 SLOT=5 TXNS=49 WRITES=12 PRESENT=07`.
BAR0/1/2 report 16 KiB / 4 MiB / 64 KiB; BAR3–5 report zero. All six originals
are restored and COMMAND stays zero. The proposed, unapplied PCI bases are
`0x00410000`, `0`, `0x00400000`. RP1 ID `00011de4`, root route `00010100`,
Gen2 ×4 and successful END remain intact. There is no BAR assignment, Device
mapping, memory decode, bus mastering, interrupt delivery, DMA or packet proof.

Actual firmware sequence 11185 and PM checks 44748 satisfy
`12 + 8 * ((11185 - 1) / 2)`; callbacks 179000 satisfy `8 + 4 * 44748`.
The 65536 budgets and all time bounds are unchanged; no cached authority.
Host complete-path tests had used real reset/SerDes/UBUS/clock/config code
with explicit RAM/clock doubles, 47 guard-failure cases and exact old-operation
prefix comparisons. The real board receipt, not those doubles, establishes
this successful sizing/restoration result.

Capture `pcie-guard-composition-serial-20261013`: 30,318 continuous bytes, zero
TX, SHA `ac9bd1f0afe358112eb7056a4a65bdd706db3ea0188dbda8b5cf42eee9b8d7db`.
All 19 rows and the full fault scan through normal NVMe selection pass.
Independent SSD Linux boot `29cdf7ca-e495-4659-a46e-1eb3f8f8e0b0` is verified.
Original firmware/zsh restoration and full read-only chain replay pass:
`pcie-guard-composition-restored-20261013`, canonical seal
`d04a8bcf46f2bf286a46d7143871cddcedfff57112c2400779cc5a07745b759c`,
plan `14da992425ba256ae083b8034c0afdbdb886d2e54a708c81df9dc78631ee3651`,
result `5e225330c437fa72faa1e75c90206e695191613e46483bf9fb1fa74d865d080d`.
Catalog 202 → 207 → 212; install/restore 22.993 / 23.238 seconds. Next is a
separate same-boot-owned BAR assignment/readback/restoration implementation;
it must not consume historical size receipts as current access authority.

