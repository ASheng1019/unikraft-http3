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
