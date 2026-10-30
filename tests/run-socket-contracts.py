#!/usr/bin/env python3
"""Build and execute real lwIP socket address contracts; optional baseline control."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--core', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cache-dir', type=Path)
    parser.add_argument('--libs-root', type=Path)
    parser.add_argument('--compiler')
    parser.add_argument('--metadata', action='store_true')
    parser.add_argument('--expect-failure', action='store_true')
    args = parser.parse_args()
    source = Path(__file__).resolve().parent.parent
    libs = (args.libs_root or source / 'libs').resolve()
    app = source / 'tests/socket-contracts'
    output = args.output.resolve()
    output.mkdir(mode=0o700)
    out = output / 'out'
    out.mkdir()
    if args.cache_dir:
        for name in ['libmusl', 'liblwip']:
            for path in (args.cache_dir / name).iterdir():
                if path.is_file() and path.name.endswith(('.xz', '.gz', '.zip')):
                    (out / name).mkdir(exist_ok=True)
                    shutil.copyfile(path, out / name / path.name)
    conf = output / 'defconfig'
    conf.write_text((app / 'defconfig').read_text() + ('\nCONFIG_LWIP_NETBUF_RECVINFO=y\n' if args.metadata else ''))
    make = ['make', '-C', str(args.core.resolve()), f'A={app}', f'O={out}',
            f'C={output}/config', f'L={libs}/lib-musl:{libs}/lib-lwip',
            f'UK_DEFCONFIG={conf}']
    if args.compiler:
        make.append('COMPILER=' + args.compiler)
    result = dict(status='FAIL', expected_failure=args.expect_failure,
                  scope='test-only loopback; four real socket entrypoints, two families, five capacities')
    try:
        for command, filename in [(make + ['defconfig'], 'configure.log'),
                                  (make + ['-j4'], 'build.log')]:
            with (output / filename).open('x') as log:
                subprocess.run(command, stdout=log, stderr=subprocess.STDOUT,
                               check=True, timeout=900)
        image = out / 'socket-contracts_qemu-arm64'
        result['image_sha256'] = hashlib.sha256(image.read_bytes()).hexdigest()
        with (output / 'serial.log').open('x') as log:
            run = subprocess.Popen(['qemu-system-aarch64', '-machine', 'virt,gic-version=host',
                                  '-cpu', 'host', '-accel', 'kvm', '-m', '512M', '-smp', '1',
                                  '-display', 'none', '-monitor', 'none', '-serial', 'stdio',
                                  '-no-reboot', '-nic', 'none', '-kernel', str(image)],
                                 stdout=log, stderr=subprocess.STDOUT)
            deadline = time.monotonic() + 45
            while run.poll() is None and time.monotonic() < deadline:
                text = (output / 'serial.log').read_text()
                if 'SOCKET_CONTRACTS PASS' in text or 'SOCKET_CONTRACTS FAIL' in text:
                    break
                time.sleep(0.02)
            run.terminate() if run.poll() is None else None
            run.wait(timeout=10)
        text = (output / 'serial.log').read_text()
        if args.expect_failure:
            assert 'SOCKET_CONTRACTS FAIL' in text
            assert 'SOCKET_CONTRACTS PASS' not in text
            result['status'] = 'EXPECTED_FAILURE_CONFIRMED'
        else:
            assert 'SOCKET_CONTRACTS PASS cases=40' in text
            if args.metadata:
                assert 'UDP_DF_CONTRACTS PASS' in text
            result.update(status='PASS', cases=40, df_errno=args.metadata)
        print('SOCKET_CONTRACTS', result['status'], flush=True)
    finally:
        (output / 'results.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
