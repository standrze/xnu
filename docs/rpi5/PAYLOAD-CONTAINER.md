# Payload container version 1

This integrity envelope is not directly bootable and provides no authenticity.
It does not contain seed bytes or replace runtime FDT/firmware provenance.
All integer fields are little-endian; payload contents require separate format
validation before loading.

The 64-byte header contains: magic `RPI5XNU\0` at 0, uint32 version 1 at 8,
uint32 header size 64 at 12, uint64 exact total length at 16, uint32 entry count
at 24, zero uint32 flags at 28, and SHA-256 of the entry table at 32.

One or two 64-byte entries immediately follow. Each contains uint32 kind at 0,
zero uint32 flags at 4, uint64 offset at 8, uint64 length at 16, payload SHA-256
at 24, and eight zero reserved bytes at 56. Entry order is kernel (kind 1), then
optional init image (kind 2). No unknown entries or duplicate types are accepted.

Payloads follow the table in entry order, each starting at the next 64-byte
boundary. Inter-payload padding must be zero. No trailing bytes are allowed.
Each payload is nonempty and at most 256 MiB; total input is at most 512 MiB.
The parser requires the exact complete readable/stable input, checks metadata
and every hash, then publishes offsets atomically. No address is dereferenced
outside that input. It does not copy, execute or authenticate the payloads.

`payload_container.encode` constructs bytes in memory. `rpi5_container_parse`
uses the pinned native SHA-256 implementation. Host tests compare both formats,
reject every truncated prefix of small fixtures and mutate header/table/data.
Tests also recompute the table hash after malformed metadata changes to exercise
structural rejection. Larger capacity cases still need further coverage. The
actual built kernel has passed container-to-native-validator-to-host-buffer-copy
comparison; this does not establish physical loading or source-buffer ownership.

Runtime location, loader-prefix packaging, source-buffer lifetime, firmware
identity, physical placement and final transfer remain separate integration work.

`build_probe.py --load-address 0x200000 --kernel PATH` now embeds a host-audited
kernel container in a dedicated aligned linker section. The raw-image audit
checks exact payload presence/alignment and records its physical range. Its
storage is inside the complete probe extent, including in early FDT-overlap and
runtime live-range checks. The address above remains a host-build example, not
an approved board placement. Runtime inventory verifies container hashes and
kernel segment/symbol metadata and local relocation records, then reports
NOT_LOADED. The build sizes a bounded relocation hash table from the audited
kernel (1 MiB for the current 93,292 records), caps it at 4 MiB and records its
size in the manifest. This scratch lives inside the probe's BSS/live extent;
it does not borrow firmware-advertised RAM. Validation does not apply relocations.
There is no copying or XNU transfer in this probe path. The no-kernel build
retains an empty payload section and reports NO_EMBEDDED_PAYLOAD.
