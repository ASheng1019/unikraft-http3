#!/bin/sh
# SPDX-License-Identifier: BSD-3-Clause
set -eu
base=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
target=${1:-"$base/unikraft"}
# A fresh checkout avoids applying these prerequisite fixes to a user's checkout.
# git am retains their original authors and source references; a Git committer
# identity (user.name/user.email) must be configured by the caller.
test ! -e "$target"
git clone --no-checkout https://github.com/unikraft/unikraft.git "$target"
git -C "$target" checkout --detach 359307a2a4cc9c1feb22683d841650902b799e4d
for patch in "$base"/core-patches/*.patch; do
    git -C "$target" am "$patch"
done
