#!/usr/bin/env python3
"""Clean-build the policy-free service and isolated fault-injection images.

Archive committed port sources rather than switching developers' checkouts.
Only lwIP/ngtcp2 use submission_series.base; other inputs use workspace gitlinks.
"""
import argparse
import json
from pathlib import Path
import subprocess

LIBS = 'musl lwip nghttp3 ngtcp2 nghttp2 c-ares libev zlib openssl libcxx libcxxabi libunwind nghttpx'.split()
APPS = {'service': 'app-nghttpx', 'eagain': 'tests/eagain-app',
        'rxflags': 'tests/rxflags-app'}


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args], text=True).strip()


def archive(repo, ref, output):
    output.mkdir(parents=True)
    data = subprocess.check_output(['git', '-C', str(repo), 'archive', ref])
    subprocess.run(['tar', '-x', '-C', str(output)], input=data, check=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--compiler', default='clang-19')
    p.add_argument('--jobs', type=int, default=8)
    p.add_argument('--apps', nargs='+', choices=list(APPS), default=list(APPS))
    p.add_argument('--fetch-command', help='optional make WGET command for a local archive cache')
    a = p.parse_args()
    if a.jobs < 1:
        p.error('--jobs must be positive')
    root = Path(__file__).resolve().parent.parent
    output = a.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir(mode=0o700)  # Never overwrite an earlier attempt.
    snapshot = output / 'sources'
    snapshot.mkdir()
    result = dict(status='FAIL', profile='base', workspace_commit=git(root, 'rev-parse', 'HEAD'),
                  inputs={}, images={})
    try:
        lock = json.loads(git(root, 'show', 'HEAD:sources.lock.json'))
        # Reject modified inputs; do not silently qualify different working trees.
        modules = ['unikraft', 'app-nghttpx'] + ['libs/lib-' + n for n in LIBS]
        for name in modules:
            repo = root / name
            ref = git(root, 'rev-parse', 'HEAD:' + name)
            assert git(repo, 'rev-parse', 'HEAD') == ref, name + ': gitlink mismatch'
            assert not git(repo, 'status', '--porcelain'), name + ': dirty checkout'
            if name.startswith('libs/'):
                ref = lock['submission_series'].get(repo.name, {}).get('base', ref)
            result['inputs'][name] = ref
            if name != 'unikraft':
                archive(repo, ref, snapshot / name)
        # Includes the two isolated test applications and their relative app source.
        assert not git(root, 'status', '--porcelain', '--', 'tests/eagain-app', 'tests/rxflags-app')
        archive(root, 'HEAD:tests', snapshot / 'tests')
        for name in a.apps:
            case = output / name
            case.mkdir()
            app = snapshot / APPS[name]
            conf = case / 'defconfig'
            conf.write_text('\n'.join(line for line in (app/'defconfig').read_text().splitlines()
                                      if not line.startswith('CONFIG_LWIP_TCP_ACK_DELAY_MS=')) + '\n')
            make = ['make', '-C', str(root/'unikraft'), f'A={app}', f'O={case}/out',
                    f'C={case}/config', f'UK_DEFCONFIG={conf}',
                    'L=' + ':'.join(str(snapshot/'libs'/('lib-'+n)) for n in LIBS),
                    'COMPILER=' + a.compiler]
            if a.fetch_command:
                make.append('WGET=' + a.fetch_command)
            for args, log in [(['defconfig'], 'configure.log'),
                              (['-j' + str(a.jobs)], 'build.log')]:
                with (case/log).open('x') as stream:
                    subprocess.run(make+args, stdout=stream, stderr=subprocess.STDOUT,
                                   check=True, timeout=900)
            assert 'CONFIG_LWIP_TCP_ACK_DELAY_MS=' not in (case/'config').read_text()
            image = case/'out'/(app.name+'_qemu-arm64')
            assert image.is_file(), image
            result['images'][name] = str(image)
            print('BASE_BUILD', name, 'PASS', image, flush=True)
        result['status'] = 'PASS'
    finally:
        (output/'manifest.json').write_text(json.dumps(result, indent=2)+'\n')


if __name__ == '__main__':
    main()
