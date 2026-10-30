#!/usr/bin/env python3
"""Verify LLVM source URL/hash pairs through actual Kconfig and make."""
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
    source = Path(__file__).resolve().parent.parent
    output = args.output.resolve()
    output.mkdir(mode=0o700)
    app = source / 'tests/config-app'
    libs = ':'.join(str(source / 'libs' / ('lib-' + n)) for n in
                    'musl lwip nghttp3 ngtcp2 nghttp2 c-ares libev zlib openssl libcxx libcxxabi libunwind nghttpx'.split())
    base = [line for line in (source / 'app-nghttpx/defconfig').read_text().splitlines()
            if not re.match(r'(?:# )?CONFIG_(LIBCXX_RELEASE|LIBCXXABI_RELEASE|LIBUNWIND_RELEASE)', line)]
    result = dict(status='FAIL', cases=[])
    try:
        for name, choice, version in [('default', None, '21.1.8'),
                                     ('old', '1406', '14.0.6'),
                                     ('current', '2118', '21.1.8')]:
            case = output / name
            case.mkdir()
            options = [f'CONFIG_{lib}_RELEASE{choice}=y' for lib in
                       ['LIBCXX', 'LIBCXXABI', 'LIBUNWIND']] if choice else []
            (case / 'defconfig').write_text('\n'.join(base + options) + '\n')
            make = ['make', '-C', str(args.core.resolve()), f'A={app}',
                    f'O={case}/out', f'C={case}/config', f'L={libs}',
                    f'UK_DEFCONFIG={case}/defconfig']
            if args.compiler:
                make.append('COMPILER=' + args.compiler)
            with (case / 'configure.log').open('x') as log:
                subprocess.run(make + ['defconfig'], stdout=log, stderr=subprocess.STDOUT, check=True)
            run = subprocess.run(make + ['--no-print-directory', 'runtime-selection'],
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=True, text=True)
            (case / 'selection.log').write_text(run.stdout)
            values = dict(line.split('=', 1) for line in run.stdout.splitlines()
                          if re.match(r'(CXX|ABI|UNWIND)_\w+=', line))
            for key, port in [('CXX', 'libcxx'), ('ABI', 'libcxxabi'), ('UNWIND', 'libunwind')]:
                expected = re.search(re.escape(version) + r' sha256:([0-9a-f]{64})',
                                     (source / 'libs' / ('lib-' + port) / 'Library.uk').read_text()).group(1)
                assert values[key + '_VERSION'] == version
                assert values[key + '_SHA'] == expected
                assert f'/{port}-{version}.src.tar.xz' in values[key + '_URL']
            result['cases'].append(dict(name=name, resolved=values, status='PASS'))
        result['status'] = 'PASS'
        print('RUNTIME_SELECTION PASS cases=3 ports=3', flush=True)
    finally:
        (output / 'results.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
