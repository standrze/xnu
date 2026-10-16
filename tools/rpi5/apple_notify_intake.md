# Original notification service: next concrete boundary

Upstream: [Apple Libnotify](https://github.com/apple-oss-distributions/Libnotify),
commit `715d461778f6b93c821d99390a0078bd6f6d8c04`, retrieved unmodified into
`build/rpi5/apple-libnotify-main-candidate-20261014`.

The actual whole-unit A76 intake is retained in
`build/rpi5/apple-notify-intake-qoe_qyyl`. It uses the original product's
`__DARWIN_NON_CANCELABLE=1`, Blocks, the installed public SDK, and already present
genuine platform/private kernel headers. No service feature is disabled. The
first compiler failures are `bootstrap_priv.h` for `notify_client.c` and
`os/collections.h` for `libnotify.c`. The report labels observed header pins as
partial: it does not claim a complete build closure or create a runtime provider.

This is a real service integration boundary, not four independent leaf functions:

- `notify_register_check` reaches `_notify_lib_init`, real bootstrap service
  lookup, version-3 notifyd check-in, MIG registration, shared-memory state and
  regeneration. The selected source also evaluates real XPC entitlement objects.
- `notify_check` consults registration state/shared memory or the actual server.
- `notify_monitor_file` rejects self tokens and loopback operation; it needs an
  actual server registration and monitoring request.
- `notify_cancel` removes/releases actual registration state. Returning a made-up
  failure code would not be this provider implementation.

The source's `NOTIFY_OPT_DISABLE`, simulator and loopback paths are not selected
to force a smaller link. Current Apple timezone remains compiled with `NOTIFY_TZ`.
Its explicit NULL_BOOTSTRAP fallback does not erase those linked notification
dependencies. A genuine next integration needs the remaining original private
headers, generated original IPC clients, the reachable dispatch/XPC/bootstrap
providers, and an honest service availability/startup contract. Neither the
client nor notifyd has been executed here.
