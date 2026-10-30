#!/bin/sh
# Local development tools; not part of a port or production image.
set -eu
base=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
export PATH="$base/interop-venv/bin:$base/clang19/usr/bin:$base:$PATH"
export LD_LIBRARY_PATH="$base/clang19/usr/lib/aarch64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
exec "$@"
