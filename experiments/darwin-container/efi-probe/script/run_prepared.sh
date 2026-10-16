#!/bin/bash
# SPDX-License-Identifier: BSD-2-Clause
set -euo pipefail

if [[ "$#" != 1 ]]; then
    echo "usage: $0 /private/tmp/darwin-efi-probe.XXXXXX" >&2
    exit 2
fi
probe_directory="$1"
case "$probe_directory" in
    /private/tmp/darwin-efi-probe.*) ;;
    *) echo "Refusing a path outside the disposable probe namespace." >&2; exit 2 ;;
esac
if [[ ! -d "$probe_directory" || -L "$probe_directory" || "$probe_directory" == */../* ||
      "$probe_directory" == */./* || "$probe_directory" == */*/*/*/* ]]; then
    echo "Expected one existing, direct mktemp child of /private/tmp." >&2
    exit 2
fi
probe_nonce="$(/usr/bin/plutil -extract nonce raw -o - "$probe_directory/prepared.json")"
exec "$probe_directory/efi-probe" run "$probe_directory" "$probe_nonce" 30
