#!/usr/bin/env python3
"""Run ordinary-image regressions with explicitly supplied external test tools."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

SCRIPTS = {
    'rx-checksums': ('test-rx-checksum.py', []),
    'rx-flags': ('test-rx-flags.py', []),
    'eagain': ('test-eagain.py', []),
    'deployment': ('run-deployment-tests.py', []),
    'discovery': ('test-h3-discovery.py', []),
    'proxy': ('test-proxy-capabilities.py', []),
    'tickets': ('test-session-resumption.py', []),
    'rebinding': ('test-rebinding.py', []),
    'wire': ('test-wire-network.py', []),
    'defaults': ('test-default-tx.py', ['--tag', 'standard', '--name', 'standard']),
    'backend-faults': ('test-backend-faults.py', []),
    'pmtu4': ('test-pmtu.py', ['--tag', 'standard', '--family', '4', '--attempt', 'a1']),
    'pmtu6': ('test-pmtu.py', ['--tag', 'standard', '--family', '6', '--attempt', 'a1']),
}

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--image', type=Path, required=True)
    p.add_argument('--client-prefix', type=Path, required=True,
                   help='prefix containing curl (ngtcp2 HTTP/3), openssl and nghttpd')
    p.add_argument('--linux-image', type=Path, help='ARM64 Linux Image for Ethernet tests')
    p.add_argument('--slirp-dir', type=Path, help='optional explicitly selected libslirp.so.0')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--suites', nargs='+', choices=list(SCRIPTS), default=[n for n in SCRIPTS if n not in ('eagain', 'rx-flags')])
    a = p.parse_args()
    a.image = a.image.resolve(strict=True)
    a.client_prefix = a.client_prefix.resolve(strict=True)
    a.output = a.output.resolve()
    a.output.mkdir(mode=0o700)  # Never reuse previous attempts.
    (a.output/'build').mkdir()
    for binary in ['curl', 'openssl', 'nghttpd']:
        assert (a.client_prefix/'bin'/binary).is_file(), binary
    if any(n in a.suites for n in ['wire', 'pmtu4', 'pmtu6']):
        assert a.linux_image and a.linux_image.is_file(), '--linux-image required'
    env = dict(os.environ, QUIC_TEST_IMAGE=str(a.image),
               QUIC_TEST_CLIENT_PREFIX=str(a.client_prefix), QUIC_TEST_OUTPUT=str(a.output),
               QUIC_NATIVE_RUNTIME_PROFILE='throughput')
    if a.linux_image: env['QUIC_TEST_LINUX_IMAGE'] = str(a.linux_image.resolve())
    if a.slirp_dir: env['QUIC_QEMU_SLIRP_DIR'] = str(a.slirp_dir.resolve())
    result = dict(status='FAIL', image_sha256=sha(a.image), suites=[],
                  started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  client_sha256=sha(a.client_prefix/'bin/curl'),
                  allocator_statistics='unavailable in ordinary image; no heap-growth claim')
    try:
        for name in a.suites:
            script, args = SCRIPTS[name]
            with (a.output/(name+'.log')).open('x') as stream:
                run = subprocess.run([sys.executable, str(Path(__file__).with_name(script)), *args],
                                     env=env, stdout=stream, stderr=subprocess.STDOUT, timeout=450)
            result['suites'].append(dict(name=name, exit_code=run.returncode,
                                        log_sha256=sha(a.output/(name+'.log'))))
            assert run.returncode == 0, f'{name}: see private suite log'
            assert sha(a.image) == result['image_sha256'], 'image changed'
            print('STANDARD_REGRESSION', name, 'PASS', flush=True)
        result['status']='PASS'
    finally:
        result['finished_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
        (a.output/'results.json').write_text(json.dumps(result, indent=2)+'\n')

if __name__ == '__main__': main()
