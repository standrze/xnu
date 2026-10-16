# Darwin filesystem conventions

2026-10-12: explicit user requirement. Use Darwin/macOS path conventions for
the XNU userland, not a Linux distribution layout. This is a layout contract,
not a claim that this port implements macOS, APFS, SIP or a sealed system volume.

## Placement policy

Preserve each reused Apple component's upstream install location, modes and
eventual owner/group requirements; check its pinned build settings before
packaging. Current examples are `/bin/zsh`, `/sbin/ifconfig` and `/sbin/route`.
The pinned `network_cmds-396.6/network_cmds.xcodeproj/project.pbxproj` specifies
`/sbin`, mode 0555, owner root and group wheel for both networking commands.
The preparation receipt captures that project file along with source evidence.

- `/bin`, `/sbin`, `/usr/bin`, `/usr/sbin`: Apple command locations, determined
  per component rather than putting every executable in `/bin`.
- `/usr/lib`, `/usr/libexec`, `/usr/share`: libraries, internal helpers and
  shared data, respectively; retain upstream subpaths such as terminfo.
- `/usr/local`: locally added, non-system tools. Future project-only probes
  belong here, not among shipped Apple commands.
- `/Users/<name>` and `/Users/<name>/Library`: user homes and user-specific
  support data; do not introduce `/home` in the Darwin guest.
- `/Library`: machine-local support and configuration resources;
  `/System/Library`: system resources. Do not place project-only additions in
  `/System/Library` merely to make them appear Apple-supplied.
- `/private/etc`, `/private/var`, `/private/tmp`: configuration, variable data
  and temporary files, with conventional `/etc`, `/var`, `/tmp` symlink aliases
  once the root format and vnode operations can implement them correctly.
- `/Volumes`: mounted volume locations; `/dev`: device filesystem.

Use the conventional system command search path
`/usr/bin:/bin:/usr/sbin:/sbin`, adding `/usr/local/bin:/usr/local/sbin` when local
tools exist. Review real launch environments before changing PATH; packaging a
command at its correct location does not prove shell discovery or execution.

## Current limitations and migration sequence

The accepted Pi root is a bounded read-only `RPI5RFS1`/mockfs bootstrap image,
not a complete Darwin filesystem. Its format accepts only regular files and
derived directories, at most 32 nodes; it cannot encode symbolic links,
writable state or per-file ownership. mockfs readlink/symlink vnode operations
are unsupported. `/etc/zsh-smoke.zsh` is currently a direct path, not the
conventional alias. Existing `/bin/statprobe` and bootstrap diagnostic tools
are explicit temporary layout exceptions.

1. Correct new Apple additions now: a distinct unstaged root installs the
   unchanged ifconfig/route binaries in `/sbin`. Preserve previous artifacts
   and the physically accepted image; never rewrite hash-bound evidence.
2. Audit remaining command locations and hard-coded callers together. Move
   project diagnostics to `/usr/local` only in a separately checked image;
   preserve recovery and compare all unchanged file bytes/modes.
3. Add and test root-format/vnode symlink support before moving configuration
   under `/private`. Test lookup, readlink, lstat/stat, relative targets, loop
   bounds and recovery paths. Do not simulate aliases with divergent copies.
4. Introduce writable `/private/var`, temporary storage and `/Users` only with
   tested ownership, permissions and mount/lifecycle behavior. Keep Gate 4
   durable-storage acceptance independent of directory naming.

Do not create empty macOS-looking directories as evidence of implemented
services. APFS, authenticated/sealed system volumes, firmlinks, SIP and full
launchd are separate capabilities, not implied requirements or completed work.
The bootstrap executable currently named `/sbin/launchd` is not Apple's full
launchd implementation.

## References

- [Apple File System Programming Guide: File System Basics](https://developer.apple.com/library/archive/documentation/FileManagement/Conceptual/FileSystemProgrammingGuide/FileSystemOverview/FileSystemOverview.html)
- [Apple network_cmds pinned build settings](https://github.com/apple-oss-distributions/network_cmds/blob/network_cmds-396.6/network_cmds.xcodeproj/project.pbxproj)
- Current constraints: `tools/rpi5/ramroot.py`,
  `bsd/miscfs/mockfs/rpi5_ramroot_format.h`,
  `bsd/miscfs/mockfs/mockfs_vnops.c`.
