# Native upstream regressions

These runners build snapshots from refs in ../../forks/, without switching or
modifying those repositories. Test sources remain in their owning Git commits;
there are no duplicate PR exports or SHA256 export verifiers.

From the workspace root, using fresh absolute output directories:

```sh
python3 tests/upstream/lwip.py --case combined --compiler gcc --ci --output "$OUT"
python3 tests/upstream/lwip.py --case recvmsg --compiler clang --output "$OUT"
python3 tests/upstream/lwip.py --release --case combined --compiler clang --output "$OUT"
python3 tests/upstream/nghttp2.py --case all --negative-controls --unit-tests --output "$OUT"
```

lwIP supports arm64, loopback, mqtt, recvmsg and combined cases. --release uses
2.2.1 plus the four patches from lib-lwip/patches/2.2.1/fixes; master mode uses
the corresponding independent branch (combined/recvmsg use the combination).
GCC13/Clang18 use tools/check; --ci additionally uses tools/lwip-ci Doxygen.
Sanitizers halt on errors; alignment retains upstream's wire-structure exclusion.
Release2.2.1 Clang tests keep its existing unused-but-set-variable warning
visible without treating that one warning as an error. No unrelated source fix
or sanitizer exception is added.

nghttp2 uses the isolated Clang21/libstdc++15/Go toolchain in tools/nghttp2-ci.
Snapshots include cached initialized submodules; optional nested urlparse test
submodules remain uninitialized as in the development checkout. Port3009 is
serialized by build/locks/nghttp2-integration.lock.
nghttp2-ci.py retains the local CI subset: run --stage archive, then distcheck,
autotools, cmake and no-http3 against the same output and case. These are local
checks; remote Actions results live on GitHub.

libslirp-audit.py --output "$OUT" builds the pending candidate and reproduces
four known limitations as expected failures. It is an audit, not an accepted
correctness patch or proof of complete TCP compatibility.

The 2026-10-30 nghttp2 base requires quic-go v0.64.1. Before the offline
runner, populate cache/go-mod from the selected branch's integration-tests/
go.mod with the documented Go toolchain (`go mod download`); module checksums
come from upstream go.sum. No source-version substitution is used.
libslirp audit now also builds a Git archive snapshot, avoiding dependence on
local tag naming when upstream release commits and signed tags differ.
