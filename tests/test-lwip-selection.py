#!/usr/bin/env python3
"""Exercise real Kconfig choices and native make source resolution, without fetching."""
import argparse
import json
from pathlib import Path
import re
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--core', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--compiler')
    args = parser.parse_args()
    core = args.core.resolve(strict=True)
    output = args.output.resolve()
    output.mkdir()
    source = Path(__file__).resolve().parent.parent
    app = source / 'tests/config-app'
    libraries = ':'.join(str(source/'libs'/('lib-'+n)) for n in
                         'musl lwip nghttp3 ngtcp2 nghttp2 c-ares libev zlib openssl libcxx libcxxabi libunwind nghttpx'.split())
    base = (source/'app-nghttpx/defconfig').read_text().splitlines()
    base = [s for s in base if not re.match(r'(?:# )?CONFIG_(?:LIBNGHTTPX|LWIP_(?:PINNED22X|PINNED21X|UNIKRAFT21X|LATEST21X|RELEASE212|NETBUF_RECVINFO|TCP_ACK_DELAY_MS|UKNETDEV_DEFER_STATUS_RX))\b', s)]
    cases = [
        ('default', [], '/refs/heads/UNIKRAFT-2_1_x.zip', False, None),
        ('unikraft', ['CONFIG_LWIP_UNIKRAFT21X=y'], '/refs/heads/UNIKRAFT-2_1_x.zip', False, None),
        ('latest', ['CONFIG_LWIP_LATEST21X=y'], '/refs/heads/STABLE-2_1_x.zip', False, None),
        ('release', ['CONFIG_LWIP_RELEASE212=y'], '/refs/tags/STABLE-2_1_2_RELEASE.zip', False, '8f0ae46e2702720ce852b00de5d304adb2809b0203741f299876594bb8be7890'),
        ('pinned', ['CONFIG_LWIP_PINNED21X=y', 'CONFIG_LWIP_NETBUF_RECVINFO=y', 'CONFIG_LWIP_TCP_ACK_DELAY_MS=50'], '/archive/bef26c44236a078d4352e76392ef16f019bea501.zip', True, '0e7de8cd81d29194b6eb587968d11b9d30f74f0230351e63a4178a72cd307cac'),
        ('pinned-defaults', ['CONFIG_LWIP_PINNED21X=y'], '/archive/bef26c44236a078d4352e76392ef16f019bea501.zip', True, '0e7de8cd81d29194b6eb587968d11b9d30f74f0230351e63a4178a72cd307cac'),
        ('pollonly', ['CONFIG_LWIP_PINNED21X=y', 'CONFIG_LWIP_UKNETDEV_POLLONLY=y', 'CONFIG_LWIP_UKNETDEV_DEFER_STATUS_RX=y'], '/archive/bef26c44236a078d4352e76392ef16f019bea501.zip', True, '0e7de8cd81d29194b6eb587968d11b9d30f74f0230351e63a4178a72cd307cac'),
    ]
    for name, options in [('pinned22', ['CONFIG_LWIP_NETBUF_RECVINFO=y', 'CONFIG_LWIP_TCP_ACK_DELAY_MS=50']), ('pinned22-defaults', []), ('pinned22-pollonly', ['CONFIG_LWIP_UKNETDEV_POLLONLY=y', 'CONFIG_LWIP_UKNETDEV_DEFER_STATUS_RX=y'])]:
        cases.append((name, ['CONFIG_LWIP_PINNED22X=y']+options, '/archive/77dcd25a72509eb83f72b033d219b1d40cd8eb95.zip', True, 'e09bf3518f1d23204cdd38203e1bdbbb5c634a1dce8dde487b7eaca3f2407245'))
    result = dict(status='FAIL', cases=[])
    try:
        for name, options, suffix, patched, checksum in cases:
            case = output/name
            case.mkdir()
            conf = case/'defconfig'
            conf.write_text('\n'.join(base+options)+'\n')
            make = ['make', '-C', str(core), f'A={app}', f'O={case}/out',
                    f'C={case}/config', f'L={libraries}', f'UK_DEFCONFIG={conf}']
            if args.compiler:
                make += ['COMPILER='+args.compiler]
            with (case/'configure.log').open('x') as log:
                subprocess.run(make+['defconfig'], stdout=log, stderr=subprocess.STDOUT, check=True)
            run = subprocess.run(make+['lwip-selection'], capture_output=True, text=True, check=True)
            (case/'selection.log').write_text(run.stdout+run.stderr)
            actual = dict(re.findall(r'^(LWIP_[A-Z_]+)=(.*)$', run.stdout, re.M))
            assert actual['LWIP_URL'].endswith(suffix), (name, actual)
            assert bool(actual['LWIP_FIX_STAGE']) == patched, (name, actual)
            assert actual['LWIP_SHA'] == (checksum or ''), (name, actual)
            if name in ('pinned', 'pinned22'):
                assert actual['LWIP_ACK_MS'] == '50' and actual['LWIP_RECVINFO'] == 'y'
            elif name in ('pinned-defaults', 'pinned22-defaults'):
                assert actual['LWIP_ACK_MS'] == '0' and not actual['LWIP_RECVINFO']
            elif name in ('pollonly', 'pinned22-pollonly'):
                assert not actual['LWIP_DEFER_RX'], 'poll-only mode cannot defer to RX interrupt dispatcher'
            assert not (case/'out/liblwip/.origin').exists(), 'selection test must not fetch/patch sources'
            result['cases'].append(dict(name=name, status='PASS', resolved=actual))
            print('LWIP_SELECTION', name, 'PASS', flush=True)
        result['status'] = 'PASS'
    finally:
        (output/'results.json').write_text(json.dumps(result, indent=2)+'\n')

if __name__ == '__main__':
    main()
