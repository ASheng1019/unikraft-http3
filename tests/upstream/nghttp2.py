#!/usr/bin/env python3
"""Build and reproduce the independent nghttp2 correctness branches.

No network operations, pushes, PR creation, or production port changes.
"""
import argparse
import hashlib
import fcntl
import contextlib
import runpy
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from source import snapshot

ROOT = Path(__file__).resolve().parents[2]
CASES = {
    'retry': ('dev/review-retry-state', 'src/shrpx_http3_upstream.cc',
              'TestH3RetryPreservesTerminalState'),
    'truncation': ('dev/drop-truncated-quic-input', 'src/shrpx_quic_listener.cc',
                   'TestH3DropsTruncatedDatagrams'),
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', choices=['all', *CASES], default='all')
    parser.add_argument('--output', type=Path, required=True, help='fresh output directory')
    parser.add_argument('--jobs', type=int, default=8)
    parser.add_argument('--negative-controls', action='store_true')
    parser.add_argument('--unit-tests', action='store_true',
                        help='run the three unmodified upstream C/C++ suites')
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, mode=0o700)
    env = runpy.run_path(str(Path(__file__).with_name('nghttp2-ci.py')))['environment']()
    prefix = ROOT / 'tools/nghttp2-ci/deps'
    result = dict(status='FAIL', cases=[], skipped_mruby_tests=0,
                  profile='Clang21.1.8/libstdc++15.3/Go1.26.10; ASan+UBSan, Werror, mruby',
                  production_ports_modified=False, pushes=False, PR_created=False)
    try:
        for key in (CASES if args.case == 'all' else [args.case]):
            name, source_name, test_name = CASES[key]
            repo = ROOT / 'forks/nghttp2'
            base = subprocess.check_output(
                ['git', '-C', str(repo), 'merge-base', name, 'upstream/master'],
                text=True).strip()
            case = output / key
            case.mkdir()
            source = case / 'source'
            head = snapshot(repo, name, source)
            out = case / 'out'
            local = dict(env, GODEBUG='cgocheck=0',
                         CGO_CFLAGS=f'-I{source}/lib/includes -I{out}/lib/includes',
                         CGO_CPPFLAGS=env['CPPFLAGS'],
                         CGO_LDFLAGS=f'-L{out}/lib ' + env['LDFLAGS'])
            record = dict(name=key, head=head,
                base_commit=base, checks=[])
            result['cases'].append(record)
            expected_source_sha = sha(source / source_name)

            def run(command, label, cwd=None, fail=False):
                log = case / (label + '.log')
                lock_path = ROOT / 'build/locks/nghttp2-integration.lock'
                lock_path.parent.mkdir(parents=True, exist_ok=True)
                context = lock_path.open('w') if command[0].endswith('/go') else contextlib.nullcontext()
                with context as lock, log.open('x') as stream:
                    if lock is not None:
                        fcntl.flock(lock, fcntl.LOCK_EX)
                    command_env = dict(local)
                    if lock is not None:
                        command_env['LD_LIBRARY_PATH'] = f'{out}/lib:' + env['LD_LIBRARY_PATH']
                    proc = subprocess.run(command, cwd=cwd, env=command_env, stdout=stream,
                                          stderr=subprocess.STDOUT, timeout=900)
                text = log.read_text(errors='replace')
                assert (proc.returncode != 0) == fail, f'{key}/{label}: see local log'
                assert not re.search(r'(?:ERROR: (?:AddressSanitizer|LeakSanitizer)|runtime error:)', text), f'{key}/{label}: sanitizer diagnostic'
                item = dict(name=label, exit_code=proc.returncode,
                            expected_failure=fail, log_sha256=sha(log))
                record['checks'].append(item)
                print(key, label, 'EXPECTED_FAIL' if fail else 'PASS', flush=True)
                return text

            run(['cmake', '-S', str(source), '-B', str(out), '-DENABLE_APP=ON',
                 '-DENABLE_HTTP3=ON', '-DENABLE_WERROR=ON', '-DENABLE_EXAMPLES=OFF',
                 '-DENABLE_HPACK_TOOLS=OFF', '-DENABLE_DOC=OFF',
                 '-DBUILD_STATIC_LIBS=ON', '-DBUILD_TESTING=ON',
                 '-DWITH_LIBXML2=OFF', '-DWITH_MRUBY=ON', '-DWITH_NEVERBLEED=OFF',
                 '-DCMAKE_C_COMPILER=' + env['CC'], '-DCMAKE_CXX_COMPILER=' + env['CXX'],
                 '-DCMAKE_C_FLAGS=' + env['CFLAGS'] + ' ' + env['CPPFLAGS'],
                 '-DCMAKE_CXX_FLAGS=' + env['CXXFLAGS'] + ' ' + env['CPPFLAGS'],
                 '-DCMAKE_EXE_LINKER_FLAGS=' + env['LDFLAGS'],
                 '-DCMAKE_SHARED_LINKER_FLAGS=' + env['LDFLAGS'],
                 '-DCMAKE_PREFIX_PATH=' + str(prefix)], 'configure')
            build = ['cmake', '--build', str(out), '--parallel', str(args.jobs), '--target']
            run(build + ['nghttpx', 'nghttp2'], 'build')
            work = out / 'integration-tests'
            # Existing out-of-tree Go setup needs a module root and config.go together.
            for path in (source / 'integration-tests').glob('*.go'):
                shutil.copy2(path, work / path.name)
            for filename in ['go.mod', 'go.sum']:
                shutil.copy2(source / filename, work / filename)
            go = [str(ROOT / 'tools/nghttp2-ci/go/bin/go'), 'test', '-v', '-tags=quic', '-count=1']
            focused = go + ['-run', '^' + test_name + '$']

            def fixed(label):
                text = run(focused, label, work)
                assert '--- PASS: ' + test_name in text and '--- SKIP:' not in text
                if key == 'truncation':
                    for mode in ['payload', 'control', 'both']:
                        assert f'--- PASS: {test_name}/{mode}' in text
                return text

            run([str(ROOT / 'tools/nghttp2-ci/go/bin/go'), 'test', '-run', '^$', '-count=1'],
                'compile-without-quic', work)
            fixed('fixed')
            text = run(go + ['-run', '^TestH3'],
                       'http3-supported', work)
            assert len(re.findall(r'^--- PASS:', text, re.M)) == 13
            assert '--- SKIP:' not in text
            record['supported_http3_top_level_tests'] = 13
            record['truncation_flag_subcases'] = 3 if key == 'truncation' else 0

            if args.negative_controls:
                path = source / source_name
                original = path.read_bytes()
                try:
                    before = subprocess.check_output(['git', '-C', str(repo), 'show',
                        base + ':' + source_name])
                    path.write_bytes(before)
                    run(build + ['nghttpx'], 'baseline-build')
                    text = run(focused, 'baseline-fails', work, fail=True)
                    marker = 'retry-type-lost' if key == 'retry' else 'truncated-input-reached-parser'
                    assert marker in text and '--- FAIL: ' + test_name in text
                    if key == 'truncation':
                        guard = b'(msg.msg_flags & (MSG_TRUNC | MSG_CTRUNC))'
                        assert original.count(guard) == 1
                        for missing, remaining in [('payload', 'MSG_CTRUNC'), ('control', 'MSG_TRUNC')]:
                            path.write_bytes(original.replace(guard,
                                ('(msg.msg_flags & ' + remaining + ')').encode()))
                            run(build + ['nghttpx'], 'missing-' + missing + '-build')
                            text = run(focused, 'missing-' + missing + '-fails', work, fail=True)
                            assert f'--- FAIL: {test_name}/{missing}' in text
                            other = 'control' if missing == 'payload' else 'payload'
                            assert f'--- PASS: {test_name}/{other}' in text
                            assert f'--- PASS: {test_name}/both' in text
                finally:
                    path.write_bytes(original)
                    run(build + ['nghttpx'], 'restored-build')
                fixed('restored')

                # A static ELF has no interposable imports: explicit skip, never a false pass.
                binary = out / 'src/nghttpx'
                backup = binary.with_name('nghttpx.fixed')
                old_sha = sha(binary)
                probe = case / 'static-probe.c'
                probe.write_text('int main(void) { return 0; }\n')
                run(['cc', '-static', str(probe), '-o', str(case / 'static-probe')], 'static-probe-build')
                binary.rename(backup)
                try:
                    shutil.copy2(case / 'static-probe', binary)
                    text = run(focused, 'static-skip', work)
                    assert '--- SKIP: ' + test_name in text or (
                        key == 'truncation' and text.count('--- SKIP:') == 3)
                    assert 'fault injection requires dynamic' in text
                finally:
                    binary.unlink()
                    backup.rename(binary)
                assert sha(binary) == old_sha
                record['static_control'] = 'static ELF preflight only, not a full static nghttpx build'

            if args.unit_tests:
                text = run(build + ['check'], 'unit-check')
                assert '100% tests passed, 0 tests failed out of 3' in text
                record['unit_tests'] = dict(test_source_overlay=False, c_cpp_suites=3)
            assert sha(source / source_name) == expected_source_sha
            record['status'] = 'PASS'
        result['status'] = 'PASS'
    finally:
        (output / 'results.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
