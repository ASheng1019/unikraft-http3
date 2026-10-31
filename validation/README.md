# Current validation

The 2026-10-30 source refresh rebases development branches onto the fetched
upstream heads. Fixed third-party release archives remain unchanged. Exact
published development checkouts are pinned by workspace submodules; archive
and upstream-base provenance is in sources.lock.json and patch headers.

The initial refresh results are local under build/publication/; the later
ARM64 existing-PR replacement is under build/arm64-prs/ as described below.
Raw logs, credentials, initrds, tool installations and object trees are not uploaded.

| Check | Result |
|---|---|
| GitHub recursive checkout | 19/19 exact module commits; clean rebuild and wire/defaults suites PASS |
| Empty-output Clang19 ARM64 service build | PASS against updated core plus two ARM64 prerequisite commits |
| Ordinary HTTP/3 service | 11/11 suites PASS, including repeated IPv4/IPv6 MTU decrease, cooldown, re-probe and second decrease |
| Actual IPv4 QUIC DF on Ethernet | PASS; old image fails the new assertion as expected |
| Socket contracts, metadata off/on | 40+40 address cases PASS; sendmsg/sendto both return EMSGSIZE for oversized DF output |
| lwIP source selection | 10 cases PASS |
| lwIP IP-family/metadata compile matrix | Both pinned versions × IPv4/IPv6/dual × metadata off/on: 12 selections, 36 translation units PASS |
| LLVM runtime selection and normal C++ consumer | Three ports × three selections PASS; old leaked build macro fails the consumer control |
| Independent target ngtcp2/nghttp3 suites | 297/297 and 61/61 PASS |
| Independent ngtcp2/OpenSSL crypto probe | Real entropy/time, 32 lifecycles and upstream crypto/token suite PASS |
| ngtcp2 latest-main PMTU proposal | 303/303 native tests PASS, plain and strict ASan/UBSan with leak detection |
| lwIP latest-main four-fix composition | GCC/Clang strict ASan/UBSan: 144 checks each PASS; GCC local upstream CI including docs/iteropts/examples/CMake PASS |
| nghttp2 latest-main Retry and truncation fixes | Both native regressions, existing HTTP/3 suite, three C/C++ suites and all defect-specific negative controls PASS |
| nghttp2 source distribution | make dist and Autotools distcheck PASS on the common new base with Retry fix |
| OpenSSL generated ARM64 manifest | Regeneration check PASS against configured 3.5.9 source graph |
| libslirp latest-main experimental candidate | Original test PASS; four previously documented boundary counterexamples still fail as expected |

The IPv4 DF check inspects actual emitted IP headers, covering both UDP
listener setup and lwIP's separate-header pbuf path. The compile matrix does
not claim single-family runtime qualification. Ordinary service tests do not
claim allocator peaks or multi-day stability. libslirp remains experimental,
with known sequence-number/control-flag/IPv6 gaps; it is not an accepted fix.

Commands are in README.md and tests/upstream/README.md. Regressions always use
fresh output directories. The current service image is
build/arm64-prs/out/app-nghttpx_qemu-arm64. The earlier build/current RX-flags
injector results still document the unchanged truncation guard; that separate
fault-injection image was not rebuilt in this refresh.

## Existing ARM64 PR adoption (2026-10-30)

The active core is now `20fd3975606e4fe4ab7e56796de2d7a35fa312f4` on
`dev/arm64-clang-prerequisites`, based on the unchanged `359307a2a4cc9c1feb22683d841650902b799e4d`.
It cherry-picks the original changes from [#1875](https://github.com/unikraft/unikraft/pull/1875)
and [#1876](https://github.com/unikraft/unikraft/pull/1876) with Cristian Andrei's
authorship/sign-offs and original commit IDs preserved. Both patch IDs match
their originals. The previous local assembly-feature workaround and duplicate
native-only enum fix are no longer in the active series.

The service was rebuilt from an empty output directory with Clang19, `-O2`
and `CONFIG_FPSIMD=y`, using the same pinned ports and release archives.
The actual `ectx.c` build command no longer has file-level
`-mgeneral-regs-only`/`__INTERRUPTSAFE__`; function-level `__isr` attributes remain.
The patch-export setup helper was independently run against a fresh upstream
clone: `git am` produces a clean checkout with exactly the same source tree,
authors and source references as the active integration.

The complete **11/11 ordinary-image HTTP/3 suites PASS**: RX checksum rejection,
deployment validation/drain, discovery, HTTP/1.1 and HTTP/2 origins with TLS/DNS,
session ticket rotation/resumption, rebinding, dual-stack Ethernet/DF/ECN,
default configuration, clear/TLS backend failure recovery, and IPv4/IPv6 PMTU.
Each PMTU family completes 80 transfers on one connection through MTU decrease,
cooldown, restored large packets and a second decrease. All suites used the same
new image, whose identity is recorded in the local runner result.

Build commands from the workspace root:

```sh
mkdir -p build/arm64-prs/out
tools/run.sh make -C app-nghttpx O="$PWD/build/arm64-prs/out" \
  C="$PWD/build/arm64-prs/config" COMPILER=clang-19 defconfig
tools/run.sh make -C app-nghttpx O="$PWD/build/arm64-prs/out" \
  C="$PWD/build/arm64-prs/config" COMPILER=clang-19 \
  WGET="python3 $PWD/tools/cache-fetch.py" -j8
tools/run.sh python3 tests/run.py \
  --image "$PWD/build/arm64-prs/out/app-nghttpx_qemu-arm64" \
  --client-prefix "$PWD/tools/http3-client" \
  --linux-image "$PWD/tools/linux-vm/Image" \
  --slirp-dir "$PWD/tools/slirp/out" \
  --output "$PWD/build/arm64-prs/regression"
```

Use new output paths when repeating the commands. This run did not rebuild the
separate EAGAIN/RX-flags injector images or rerun the independent protocol/native
sanitizer suites from the earlier refresh. Xen code from #1876 is preserved but
has not been runtime-tested. This is correctness qualification, not a new
performance comparison or a universal compiler/LTO guarantee.

The local performance-reference/ retains the earlier ports1/Linux VM study and
its statistical limits. This refresh measures correctness and packaging, not
performance; historical throughput/tail results are not relabeled as new data.

## Reusable-port cleanup and policy separation (2026-10-30)

Fresh outputs are under build/port-cleanup/. No upstream issue, PR or comment
was posted. c-ares/zlib configuration, metadata, tests and documentation were
made reusable; lwIP's production source is unchanged by its commit split.
ngtcp2 and lwIP each have one deferred policy commit after a policy-free base.
Exact submission endpoints are recorded in sources.lock.json/submission_series;
the workspace gitlinks continue to pin the development composition.

| Check | Result |
|---|---|
| c-ares standalone musl/IPv4 contract | PASS: public DNS parsing, truncated-response rejection, channel configuration and poll event-thread lifecycle; no forced IPv6 |
| zlib standalone file and memory profiles | Both PASS: compression round trip, corrupt stream, CRC, gzip memory stream; gzip file write/read/EOF on RAMFS when enabled |
| zlib file API selection | PASS: gzopen absent when disabled and present when enabled; compress2 retained; no legacy VFS/filesystem forced |
| Policy-free ngtcp2 target suite | 266/266 PASS, 0 skipped; no custom PMTU patch or patch hook |
| Independent nghttp3 suite | 61/61 PASS, 0 skipped |
| Policy-free lwIP socket contracts | Metadata off/on: 40+40 address cases PASS; DF sendmsg/sendto errors PASS |
| Development lwIP source selections | 10/10 PASS, original defaults retained and poll-only/deferred-RX exclusion preserved |
| Development service empty-output build | PASS, Clang19/ARM64/FPSIMD, reusable c-ares/zlib profiles and retained policies |
| Development service HTTP/3 regression | Complete 11/11 ordinary-image suites PASS, including real DNS, backend faults and repeated in-connection IPv4/IPv6 MTU transitions |
| Policy boundaries | Base branches contain no custom PMTU/ACK implementation or configuration; each development policy is exactly one subsequent commit |

The base protocol count differs from the historical development count of 297
because the PMTU policy adds tests. Those extra tests are not presented as
unmodified-upstream coverage. The independent OpenSSL helper probe was not
rerun on the policy-free branch in this cleanup. Full HTTP/3 regressions above
qualify the development composition, not the policy-free application profile;
the custom cooldown/black-hole contract is deliberately absent from the latter.

Run tests/run-library-contracts.py for standalone library contracts and
tests/run-ports.py --libs-root for a separate base-port snapshot. Both use
fresh output directories. Runtime checks used actual ARM64/QEMU KVM; no new
performance comparison was performed. Separate EAGAIN/RX-flags injector images
and native sanitizer suites were not rebuilt in this cleanup.

The new c-ares cleanup commit has zero checkpatch errors and one reviewed
split-string warning for the multiline test-result message. The zlib cleanup
commit passes with the upstream API CamelCase diagnostic excluded; those names
are zlib's public API. These checks do not replace the final complete-series
checkpatch/CI required before upstream submission.


## App-local reproduction walkthrough (2026-10-31)

The app README now documents fixed dependency checkout, build, private initrd,
origin and client verification. Its tools/demo.py is host tooling only and
imports no workspace QA fixture. The app changes are published in the personal
repository at e503664; the workspace pins that commit. The Discussion remains
a local draft and has not been posted upstream.

Fresh local outputs are under build/app-readme/. The same app-local script was
checked on both the retained development image and a freshly built policy-free
image using dev/lwip-native-integration and dev/ngtcp2-base-port, with the ACK
Kconfig selection removed from the latter's build profile. Both pass verified
CA/hostname TLS, curl --http3-only negotiation, exact response-body checking,
HTTP/1.1 origin handling and authenticated graceful guest shutdown.

The policy-free image also passed the documented keep-running workflow with a
second independent curl request and Ctrl-C. Existing-output rejection and
private directory/key permissions were checked. These basic demos used stock
QEMU user networking, without the experimental libslirp preload used by the
broader high-frequency fault tests. The default one-shot demo also passes.

The demo is a public-interface reproduction check, not an 11-suite run, a
performance measurement or a multi-worker/other-architecture qualification.
The subsequent policy-free qualification is recorded separately below; the
custom black-hole recovery contract remains specific to the policy branch.

## Policy-free complete applicable qualification (2026-10-31)

The app README/demo is published at app-nghttpx e503664, with workspace gitlink
update 36fc2e2. The ownership/dependency/catalog/CI preparation is in
[upstream-integration.md](../docs/upstream-integration.md). No upstream
Discussion, issue, comment or PR was posted. Ownership here is a local design
proposal: clock/network/control runtime implementations were not relocated,
and management/STATS have not become optional.

Fresh committed snapshots/builds are under build/base-qualification/. The new
`tests/build-base-service.py` exports all port/app sources from workspace
commits, substituting exactly the two base endpoints in sources.lock.json:

- lib-lwip d6cf36b1b99804988b7d587f5ef4a272efbddc1a;
- lib-ngtcp2 1b95dc975271a4bd56932ab579335a47965ee7c5.

Core remains 20fd397 with the attributed ARM64 prerequisites. No development
checkout/branch was switched. All three configs omit ACK deadline selection;
ngtcp2's custom PMTU patch and application hook are absent. The manifest records
the workspace/module commits; runner results record image identities, client
identity, logs and actual start/end UTC timestamps. Images and private raw
results remain local rather than being uploaded as source.

| Fresh check | Result |
|---|---|
| Service + EAGAIN + RX-flags clean builds | 3/3 PASS, Clang19 ARM64 |
| Ordinary policy-free service | 9/9 PASS; pmtu4/pmtu6 explicitly excluded (custom policy contracts) |
| Isolated EAGAIN image | PASS: three failures, identical replayed datagram/metadata, large and next response, graceful shutdown |
| Isolated RX-flags image | PASS: MSG_TRUNC/MSG_CTRUNC skipped, zero flagged parser calls, large and next response, graceful shutdown |
| Standalone ngtcp2/nghttp3 | 266/266 and 61/61 PASS, zero skips |
| lwIP metadata off/on socket contracts | 40+40 PASS; UDP DF/EMSGSIZE contracts PASS |
| Base profile selection guard | PASS: explicitly selecting pmtu4 with --profile base is rejected before output creation |
| Python syntax, Markdown local links/fences, diff whitespace | PASS |

Ordinary coverage includes RX checksum rejection, deployment/config failure
and bounded drain, discovery, HTTP/1.1 and HTTP/2 origins including TLS/DNS,
session tickets/resumption, rebinding, actual dual-stack Ethernet, IPv4 DF,
ECN feedback/bleaching, fresh-connection MTUs 1500→1280→1500, wildcard
listeners and 1200-byte fallback, default settings and clear/TLS backend
failure recovery. EAGAIN and RX-flags wrappers are in separate test-only
applications; none are added to the ordinary service image.

The two omitted suites pmtu4/pmtu6 assert the custom same-connection black-hole
fallback, cooldown, restored large packets and second decrease. They remain
policy-specific, **not passing tests of the unmodified ngtcp2 transport**.
`tests/run.py --profile base` defaults to the nine applicable ordinary suites
and records these two exclusions. It is a test selection label; source identity
is established separately by the build manifest, not inferred from that label.

An earlier independent pass of all nine suites is under
build/base-service-regression/ using the first base-service image. The new
snapshot run is authoritative for the reproducible builder. Full build/run
commands are in the root README. Local cached builds additionally used
`--fetch-command "python3 $PWD/tools/cache-fetch.py"`; that optional cache
helper is not an upstream build prerequisite.

Broader service runs explicitly selected tools/slirp/out's experimental host
candidate; its known boundary gaps remain. The app-local basic demo used stock
QEMU usernet. These functional passes do not establish stock-usernet behavior
under high-frequency faults, multi-worker support, multi-day stability, peak
allocator usage or new performance results. No Linux VM comparison or native
sanitizer rerun was performed in this round.

## Deployment ownership and optional runtime support (2026-10-31)

Runtime ownership is implemented, replacing the previous proposal-only state.
The app owns Config.uk-selected epoch wrappers, UDP management, separate
shutdown/STATS commands and optional FD scanning. nghttpx owns its profile,
lifecycle hooks, opaque control handle and read-only worker counters; lwIP
owns explicit named-interface IPv6 setup and DAD synchronization. Epoch and
control credentials are now separate files. See the app README and
[ownership document](../docs/upstream-integration.md) for contracts and limits.

Initial fresh build/functional evidence is local under build/runtime-ownership/
and build/runtime-variants/. The complete runtime-options suite passes 19/19:
no management token/socket implementation when disabled; H3 small/large/POST,
verified TLS and concurrent H2 origins; disabled/wrong-token commands;
shutdown-only and STATS-only modes; explicit FD scans versus default no-scan;
clock wrapper absence with an alternate test-only platform provider and
verified TLS origin, missing provider/epoch failures; unknown/missing IPv6
interface, missing multicast contract, invalid address, DAD timeout and
link-local/SLAAC initialization. This does not qualify global SLAAC acquisition.

The nine applicable ordinary service suites also pass. The first run completed
seven suites and correctly rejected tx-burst, then stopped because the defaults
test expected the old service-owned error message. Its assertion now checks
the rejected key and failed boot. defaults/backend-faults pass in the new
regression-tail output on the identical service image; no behavior was relaxed.
The wire suite now also passes real DAD rejection of the Linux peer's address.
Separate EAGAIN and RX-flags images, rebuilt with the actual app feature config,
pass both fault tests. Profile verification detects dropped Kconfig includes;
isolated test apps use $(UK_APP) when sourcing the shared app Config.uk.

The IP-family/metadata compile matrix passes 12 selections/44 translation
units: the original 36 socket/IP units plus the new helper in both pinned
versions' IPv6 and dual-stack selections. A first attempt used a build cache
without the 2.1 archive; rerunning against the verified archive cache completes
all selections. This is compile coverage, not single-family runtime testing.

The ACK deadline remains exactly one separate policy commit after the new
IPv6 base. The Config.uk append conflict was resolved preserving both features;
policy patches/lwipopts match the original strategy. ngtcp2 is unchanged.
No new throughput/CPU/tail-latency or native sanitizer result is claimed.
Further immutable-snapshot build checks are recorded below after completion.
