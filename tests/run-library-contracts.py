#!/usr/bin/env python3
"""Run independent c-ares and zlib public-API contracts on ARM64/KVM."""
import argparse
import json
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--core', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--compiler', default='clang-19')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    output = args.output.resolve()
    output.mkdir(mode=0o700)
    result = dict(status='FAIL', cases=[])
    try:
        for name, port, options, marker in [
            ('cares', 'c-ares', [], 'CARES_CONTRACT PASS'),
            ('zlib-file', 'zlib', ['CONFIG_LIBZLIB_GZFILE=y'],
             'ZLIB_CONTRACT PASS memory=1 gzip_stream=1 gzip_file=1'),
            ('zlib-memory', 'zlib', ['# CONFIG_LIBZLIB_GZFILE is not set'],
             'ZLIB_CONTRACT PASS memory=1 gzip_stream=1 gzip_file=0'),
        ]:
            case = output / name
            case.mkdir()
            app = root / 'libs' / ('lib-' + port) / 'tests/contract'
            conf = case / 'defconfig'
            conf.write_text((app / 'defconfig').read_text() + '\n' +
                            '\n'.join(options) + '\n')
            libs = ['musl', port] + (['lwip'] if port == 'c-ares' else [])
            make = ['make', '-C', str(args.core.resolve()), f'A={app}',
                    f'O={case}/out', f'C={case}/config',
                    'L=' + ':'.join(str(root/'libs'/('lib-'+p)) for p in libs),
                    f'UK_DEFCONFIG={conf}', 'COMPILER=' + args.compiler,
                    'WGET=python3 ' + str(root/'tools/cache-fetch.py')]
            for command, log in [(make+['defconfig'], 'configure.log'),
                                 (make+['-j8'], 'build.log')]:
                with (case/log).open('x') as stream:
                    subprocess.run(command, stdout=stream,
                                   stderr=subprocess.STDOUT, check=True,
                                   timeout=900)
            cfg = (case/'config').read_text()
            assert 'CONFIG_LIBNEWLIBC=y' not in cfg
            if port == 'c-ares':
                assert 'CONFIG_LWIP_IPV6=y' not in cfg
                for feature in ['LIBCARES', 'LIBPOSIX_POLL', 'LIBPOSIX_PIPE',
                                'LIBPOSIX_TIME', 'LIBUKRANDOM_GETRANDOM']:
                    assert 'CONFIG_'+feature+'=y' in cfg, feature
            else:
                for feature in ['LIBVFSCORE', 'LIBRAMFS', 'LIBDEVFS']:
                    assert 'CONFIG_'+feature+'=y' not in cfg, feature
                symbols = subprocess.check_output(
                    ['nm', '-g', str(case/'out/libzlib.o')], text=True)
                assert (' T gzopen\n' in symbols) == (name == 'zlib-file')
                assert ' T compress2\n' in symbols
            with (case/'serial.log').open('x') as stream:
                subprocess.run(['qemu-system-aarch64', '-machine',
                                'virt,gic-version=host', '-cpu', 'host',
                                '-accel', 'kvm', '-m', '512M', '-smp', '1',
                                '-display', 'none', '-monitor', 'none',
                                '-serial', 'stdio', '-no-reboot', '-nic', 'none',
                                '-kernel', str(case/'out/contract_qemu-arm64')],
                               stdout=stream, stderr=subprocess.STDOUT,
                               check=True, timeout=60)
            assert marker in (case/'serial.log').read_text()
            result['cases'].append(dict(name=name, status='PASS'))
            print('LIBRARY_CONTRACT', name, 'PASS', flush=True)
        result['status'] = 'PASS'
    finally:
        (output/'results.json').write_text(json.dumps(result, indent=2)+'\n')


if __name__ == '__main__':
    main()
