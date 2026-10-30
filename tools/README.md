# Local development and QA tools

run.sh selects the isolated Clang19, Kraft0.12.16 and aioquic1.3.0 Python
environment. No system installation is required. Compiler archive provenance
is in ../sources.lock.json. cache-fetch.py is an optional WGET override using
that lock and the verified ../cache/ archives; Unikraft verifies them again.

HTTP/3 tests take explicit absolute paths to http3-client/, linux-vm/Image
and slirp/out. The client prefix contains curl8.22.0, nghttpd and OpenSSL3.5.7;
it is independent of the guest server's OpenSSL3.5.9. Private test credentials
and generated logs belong under ../build/, outside submitted repositories.

slirp/build.py rebuilds the pinned4.9.5 host QA library with time-wait-syn.patch
from ../cache/tools. Tests explicitly select it; the system library is untouched.
The pending generic candidate has unresolved TCP boundaries documented in
../docs/maintenance.md; the QA backport is not a claim those are all resolved.

Native upstream regression runners live in ../tests/upstream/ and use ../forks/.
nghttp2-ci/ provides Clang21.1.8, libstdc++15.3 and Go1.26.10 with native
HTTP/3 dependencies; its source/package manifests remain for rebuilding tools.
nghttp2-ci/deps excludes libev's compatibility event.h so system libevent
headers remain usable. format21-venv is the matching nghttp2 formatter.
check/ provides Check0.15.2; lwip-ci/ provides isolated Doxygen1.9.8.
GCC13/Clang18 lwIP checks halt on sanitizer diagnostics, retaining upstream's
protocol-structure alignment exclusion.

Only this README, run/cache helpers, tool package manifests and the isolated
slirp build helper/backport are workspace source. Installed dependencies and
build results remain ignored; none of these belong in a port contribution.
