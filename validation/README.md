# Current validation

The 2026-10-30 source refresh rebases development branches onto the fetched
upstream heads. Fixed third-party release archives remain unchanged. Exact
published development checkouts are pinned by workspace submodules; archive
and upstream-base provenance is in sources.lock.json and patch headers.

Fresh results are local under build/publication/; raw logs, credentials,
initrds, tool installations and object trees are not uploaded.

| Check | Result |
|---|---|
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
build/publication/out/app-nghttpx_qemu-arm64. The earlier build/current RX-flags
injector results still document the unchanged truncation guard; that separate
fault-injection image was not rebuilt in this refresh.

The local performance-reference/ retains the earlier ports1/Linux VM study and
its statistical limits. This refresh measures correctness and packaging, not
performance; historical throughput/tail results are not relabeled as new data.
