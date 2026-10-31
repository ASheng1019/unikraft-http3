# Unikraft HTTP/3 workspace

This is a pinned development workspace for the ARM64 nghttpx HTTP/3 reverse proxy. The
application, external-library ports and Unikraft core are separate repository
boundaries. This whole directory is not a contribution to the core repository.

```
app-nghttpx/     thin application and deployment configuration
libs/lib-*/     external ports, their own source patches and library tests
unikraft/       core checkout with existing ARM64 PRs #1875 and #1876
core-patches/   attributed integration exports of those upstream PR commits
forks/          four upstream Git repositories for fixes and PR maintenance
tests/          cross-library integration and independent contract tests
tools/          local compiler, Kraft and explicit QA dependencies
cache/          checksum-verified source archives
build/          disposable local build outputs
validation/     current validation summary and measured performance reference
docs/           maintenance rules, patch ownership and upstream status
```

Each port uses Config.uk and Makefile.uk. Downloaded release sources stay in
build output; their changes are carried by the owning port's patches. Port
code, configuration headers and build rules are maintained directly. Licenses
and source versions are recorded in each port and sources.lock.json.

See [docs/maintenance.md](docs/maintenance.md) for patch ownership, version alignment,
upstream status and target repositories. Superseded experiments and development journals have
been removed. `unikraft/` preserves the original core Git repository. Eight existing ports retain their Git histories and contributor commits. Five new
port candidates and the thin application have independent personal repositories;
upstream acceptance is pending.

## Checkout

```sh
git clone --recurse-submodules https://github.com/ASheng1019/unikraft-http3.git
cd unikraft-http3
```

Git submodules pin the actual development commits; sources.lock.json records
release archives and upstream provenance. To skip upstream-fix development
checkouts, initialize only unikraft/, libs/* and app-nghttpx/. The four forks/
checkouts are not build inputs. Do not update submodules to floating branch
heads when reproducing this version.

## Local Git layout and maintenance

The workspace is a normal repository with its Git metadata in the top-level
`.git/`. Each dependency remains an independent Git submodule: its `.git`
file points into the workspace's `.git/modules/` directory. This matches a
normal recursive clone and keeps every module's branches, history and remotes
separate. Git metadata must never live under build/, cache/ or another
regenerable directory.

Use ordinary Git commands from the workspace root:

```sh
git status
git submodule status --recursive
git -C libs/lib-nghttpx status
```

Make a module change on its own branch, commit and push that module first,
then commit its new reference in the workspace. For example, after committing
the service-port change:

```sh
git -C libs/lib-nghttpx push origin HEAD
git add libs/lib-nghttpx
git commit -m "Update the nghttpx service port"
git push origin main
```

A fresh recursive clone checks out module commits directly; create or switch
to the intended module branch before developing there. Keep build/cache
outputs and private deployment files out of Git. To back up local work that
has not been pushed, preserve the top-level `.git/` (including modules/) as
well as uncommitted files; the workspace commit records module OIDs, not
uncommitted module changes.

## Build

Use ARM64 Linux with make, binutils, Clang19 or newer, flex, bison, Perl,
Python3, patch and archive tools. The qualified runtime is LLVM21.1.8; the
14.0.6 option of the general-purpose runtime ports is not a qualified nghttpx
configuration. KVM and QEMU are needed for execution, not target compilation.

If unikraft/ is absent, ./setup-core.sh prepares a new pinned checkout with
the prerequisites; it refuses to overwrite an existing checkout. The
helper imports the patches with git am, preserving Cristian Andrei's authorship,
sign-offs and original commit references; configure a Git committer identity
(user.name/user.email) before using it. sources.lock.json records both original
and integrated commit IDs. The two earlier local implementations are replaced.
The application defaults to the sibling core and libs directories. UK_ROOT and
LIBS_ROOT can be supplied explicitly for another workspace layout.

The optional local tool runner selects the preserved Clang19/Kraft/aioquic tools:
`tools/run.sh COMMAND`. From app-nghttpx, use `../tools/run.sh make ...`.

```sh
cd app-nghttpx
make COMPILER=clang-19 defconfig
make COMPILER=clang-19 -j8
```

For separate outputs, pass absolute O and C paths to both commands. The
native image is app-nghttpx_qemu-arm64. From the same application directory,
Kraft0.12.16 can use its checked-in local source declarations:

```sh
kraft build --no-update --validate --no-rootfs --toolchain COMPILER=clang-19
```

An existing Kraft .config can override manifest defaults. Use a fresh output
when changing versions. Core patches are dependency exports for this local
integration; upstream core changes belong in the core repository itself.

## Deployment

Supply a private initrd containing /nghttpx.conf and certificate/key.
The app deployment profile explicitly selects trusted boot time
(/native-epoch.txt), management (/native-control.token), shutdown and STATS.
All are optional Config.uk features, default n; FD scans default off. The app
owns /native-runtime.conf parsing, optional wrappers and the UDP management
adapter. lib-nghttpx owns service validation, lifecycle callbacks and read-only
worker snapshots. It adds no time wrappers or management socket by itself.
See the [app README](app-nghttpx/README.md) for unmanaged/platform-clock modes,
explicit IPv6 interface settings and teardown contracts. Never commit secrets.

Recommended configuration: one worker/thread, epoll,16KiB backend reads,
one-packet TX, PMTUD up to1452 bytes, ECN off, RX software checksums, deferred
RX dispatcher, independent50ms TCP ACK deadline, detected ARM64 OpenSSL
acceleration with conservative fallback. Input must provide complete wire
checksums; partial-checksum/GSO input is not supported at the device boundary.
The PMTU recovery policy uses60-second cooldown and600-second periodic search.

ARM64 is qualified. Other architectures, multiple workers,0-RTT, QUIC
DATAGRAM, WebTransport, sendmmsg/GSO and alternative TLS stacks need separate
qualification. The port does not implement arbitrary Linux process semantics.

## Tests

Protocol suites live in the protocol ports; workspace tests exercise real
HTTP/3, deployment, fault recovery, PMTU and socket contracts. Test outputs
must be new directories outside the source repositories.

```sh
python3 tests/run-ports.py --core "$CORE" --output "$PORT_TEST_OUTPUT"
python3 tests/run-library-contracts.py --core "$CORE" --output "$LIBRARY_TEST_OUTPUT"
python3 tests/test-lwip-selection.py --core "$CORE" --output "$LWIP_CONFIG_OUTPUT"
python3 tests/test-runtime-selection.py --core "$CORE" --output "$CXX_CONFIG_OUTPUT"
python3 tests/run-socket-contracts.py --core "$CORE" --output "$SOCKET_TEST_OUTPUT"
python3 tests/run.py --image "$IMAGE" --client-prefix "$CLIENT_PREFIX" \
  --linux-image "$LINUX_IMAGE" --slirp-dir "$SLIRP_DIR" --output "$H3_TEST_OUTPUT"
```

Use a Python environment with aioquic1.3.0, an HTTP/3 curl/OpenSSL/nghttpd
client prefix, a bootable ARM64 Linux Image and KVM-capable QEMU. These are
explicit external QA tools. High-frequency backend tests use the explicitly
selected experimental libslirp TIME_WAIT candidate, which still has known
boundary gaps; these tests do not qualify stock QEMU for that load. Client
tools/kernels and benchmark artifacts are not part of any port source repository.

EAGAIN and receive-flags injectors live in separate test-only applications;
they are excluded from the production build. Socket tests use test-only
loopback to check actual address lengths and copy limits. Ordinary-image tests
do not claim internal allocator peaks or multi-day stability measurements.

Generic fixes are developed first in forks/ and carried as independent release
backports in the owning port. See [maintenance](docs/maintenance.md) for PRs,
versions, directory purposes and removal rules. Native regression runners are
in tests/upstream/. Builds use release archives and never depend on forks/.

c-ares and zlib have independent public-API applications in their own
tests/contract directories. c-ares declares its musl/socket/POSIX profile without
forcing IPv6. zlib exposes memory APIs with HAVE_LIBC; optional LIBZLIB_GZFILE
adds file APIs when HAVE_VFS is available, leaving filesystems/mounts to the app.
The contract runner tests c-ares and both zlib profiles without nghttpx.

## Contribution boundaries

Prepare separate changes for each lib repository, the application/catalog,
and generic fixes for ngtcp2/nghttp2. Coordinate the core prerequisites through
the existing upstream PRs rather than resubmitting duplicate changes.
Do not submit this entire workspace to core. The local candidate lib-nghttpx name and target
repository still require agreement. Preserve the authorship of the reused
LLVM/OpenSSL ports and Quinn attribution. Personal repository publication preserves original histories and signed-off fixes.
Upstream CI, maintainer agreement and policy acceptance remain submission steps.

The workspace pins the measured development composition. Initial submission
branches exclude behavior-policy commits: lib-lwip's dev/lwip-ipv6-setup-base
has no independent ACK deadline; lib-ngtcp2's dev/ngtcp2-base-port has no custom
PMTU recovery. Each policy is one separate final commit on its development
branch. sources.lock.json records both endpoints under submission_series.
Use run-ports.py --libs-root to qualify a separate snapshot of the base ports;
the unmodified ngtcp2 transport has 266 tests, versus 297 with the policy patch.

For the policy-free service and isolated send/receive fault images, use a new
output directory and committed module inputs (no branch switching is needed):

```sh
BASE_OUTPUT="$PWD/build/base-service"
python3 tests/build-base-service.py --output "$BASE_OUTPUT"
python3 tests/run.py --profile base \
  --image "$BASE_OUTPUT/service/out/app-nghttpx_qemu-arm64" \
  --client-prefix "$CLIENT_PREFIX" --linux-image "$LINUX_IMAGE" \
  --slirp-dir "$SLIRP_DIR" --output "$BASE_OUTPUT/ordinary"
python3 tests/run.py --profile base --suites eagain \
  --image "$BASE_OUTPUT/eagain/out/eagain-app_qemu-arm64" \
  --client-prefix "$CLIENT_PREFIX" --slirp-dir "$SLIRP_DIR" \
  --output "$BASE_OUTPUT/eagain-tests"
python3 tests/run.py --profile base --suites rx-flags \
  --image "$BASE_OUTPUT/rxflags/out/rxflags-app_qemu-arm64" \
  --client-prefix "$CLIENT_PREFIX" --slirp-dir "$SLIRP_DIR" \
  --output "$BASE_OUTPUT/rxflags-tests"
```

The builder exports lwIP/ngtcp2's fixed base endpoints from sources.lock.json,
uses the workspace gitlinks for other inputs, removes the ACK policy selection,
and records source identities in manifest.json. It refuses dirty/mismatched
module checkouts and never rewrites developers' branches. `--fetch-command` can
select a local archive cache; otherwise normal make download rules apply.
`--profile base` runs nine ordinary suites; the two custom PMTU recovery suites
are explicitly excluded and rejected if selected. Upstream PMTUD/DF/ECN and
conservative 1200-byte transfers still have wire coverage. The fault images
add test wrappers only; production libraries come from the same snapshot.
To build the complete deployment matrix, choose a new output and explicitly
include all profiles (the default build remains service + two fault images):

```sh
RUNTIME_OUTPUT="$PWD/build/runtime-matrix"
python3 tests/build-base-service.py --output "$RUNTIME_OUTPUT" \
  --apps service unmanaged shutdown-only stats-only fd-stats platform-clock eagain rxflags
python3 tests/run.py --profile base --suites runtime-options \
  --runtime-variants "$RUNTIME_OUTPUT" \
  --image "$RUNTIME_OUTPUT/service/out/app-nghttpx_qemu-arm64" \
  --client-prefix "$CLIENT_PREFIX" --slirp-dir "$SLIRP_DIR" \
  --output "$RUNTIME_OUTPUT/runtime-options-tests"
```

The platform-clock image supplies a test-only platform time provider; it does
not implement an RTC. Runtime-options checks code exclusion, disabled commands,
TLS/H3/H1/H2/POST transfers, clock-provider success/failure and named-interface
IPv6 error paths. The ordinary wire suite additionally checks actual DAD
rejection against the Linux peer's IPv6 address.

See [upstream integration](docs/upstream-integration.md) for the proposed
clock/network/control ownership, official dependency locations and native
catalog/CI changes. These proposals have not been sent upstream.

Current build and regression commands/results are described in
[validation/README.md](validation/README.md). The retained Linux VM comparison
under validation/performance-reference describes the measured ports1 version;
it is not a performance measurement of later correctness backports.

## Repository map and source ownership

| Checkout | Personal GitHub repository | Role |
|---|---|---|
| `unikraft/` | [unikraft](https://github.com/ASheng1019/unikraft) | core fork; two ARM64 prerequisites |
| `libs/lib-*` | `ASheng1019/lib-*` (13 independent repos) | build glue, private configuration and owned source patches |
| `app-nghttpx/` | [app-nghttpx](https://github.com/ASheng1019/app-nghttpx) | public entrypoint and deployment profile |
| `forks/nghttp2`, `forks/lwip`, `forks/ngtcp2` | respective `ASheng1019` forks | generic fixes and upstream review branches |
| `forks/libslirp` | [libslirp](https://github.com/ASheng1019/libslirp) | GitLab upstream mirror and experimental host QA candidate |
| this workspace | [unikraft-http3](https://github.com/ASheng1019/unikraft-http3) | dependency pins and cross-library integration tests |

The upload excludes binaries, compiler environments, archives, raw benchmark
outputs, generated certificates, initrds and control tokens. Only tool-selection/build helpers, package provenance and their instructions
are source-controlled in tools/. validation/README.md records qualification; raw measured reference
artifacts remain local. A fresh clone needs the explicitly documented external
QA dependencies before running integration tests.

The [upstream contribution plan](docs/upstream-plan.md) records target
repositories, existing work to coordinate with, readiness gaps, and unpublished
Discussion/issue/PR drafts. Publication on personal GitHub does not imply upstream acceptance
or permission to post those drafts.
