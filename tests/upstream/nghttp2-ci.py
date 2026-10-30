#!/usr/bin/env python3
"""Local ARM64 subset of nghttp2 build.yml, using distribution archives.

No publication, host configuration changes, or test-source portability overlays.
Requires workspace-local dependencies recorded in tools/nghttp2-ci/manifest.json.
"""
import argparse
import hashlib
import fcntl
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tarfile
import time
from source import snapshot

ROOT = Path(__file__).resolve().parents[2]
REPOS = {'retry': 'dev/review-retry-state', 'truncation': 'dev/drop-truncated-quic-input'}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def environment():
    prefix = ROOT / 'tools/nghttp2-ci/deps'
    ci = ROOT / 'tools/nghttp2-ci'
    headers = ci / 'lib/gcc/aarch64-conda-linux-gnu/15.3.0/include/c++'
    env = dict(os.environ, CC=str(ci / 'bin/clang'), CXX=str(ci / 'bin/clang++'),
               PATH=f'{ci}/go/bin:' + os.environ['PATH'],
               PKG_CONFIG_PATH=str(prefix / 'lib/pkgconfig'),
               GOCACHE=str(ROOT / 'cache/go-build'),
               GOMODCACHE=str(ROOT / 'cache/go-mod'),
               GOPATH=str(ROOT / 'tools/go-work'), GOPROXY='off', GOTOOLCHAIN='local',
               GOFLAGS='-count=1',
               CFLAGS='-O1 -g',
               CXXFLAGS=f'-O1 -g -nostdinc++ -isystem {headers} -isystem {headers}/aarch64-conda-linux-gnu',
               CPPFLAGS=f'-I{prefix}/include -fsanitize=address,undefined -fno-sanitize-recover=undefined',
               LDFLAGS=f'-L{ci}/lib -L{prefix}/lib -Wl,-rpath,{ci}/lib -Wl,-rpath,{prefix}/lib -fsanitize=address,undefined -fno-sanitize-recover=undefined',
               LIBEV_CFLAGS=f'-I{prefix}/include', LIBEV_LIBS=f'-L{prefix}/lib -lev',
               LD_LIBRARY_PATH=f'{ci}/clang21/usr/lib/aarch64-linux-gnu:{ci}/lib:{prefix}/lib',
               ASAN_OPTIONS='detect_leaks=1:abort_on_error=1',
               UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1')
    return env


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', choices=list(REPOS), required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--jobs', type=int, default=8)
    parser.add_argument('--stage', choices=['archive', 'distcheck', 'autotools', 'cmake', 'no-http3'], required=True)
    args = parser.parse_args()
    repository = ROOT / 'forks/nghttp2'
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(out, 0o700)
    repo = out / 'source'
    if repo.exists():
        head = subprocess.check_output(['git', '-C', str(repository), 'rev-parse', REPOS[args.case]], text=True).strip()
    else:
        head = snapshot(repository, REPOS[args.case], repo)
    env = environment()
    records = []
    result = dict(status='FAIL', case=args.case, stage=args.stage,
                  head=head,
                  profile='ARM64 Linux, Clang21.1.8, libstdc++15.3, Go1.26.10, OpenSSL3.5.7, ASan+UBSan, Werror, mruby',
                  workflow_sha256=sha(repo / '.github/workflows/build.yml'),
                  tool_manifests={name: sha(ROOT / 'tools/nghttp2-ci' / name) for name in ['manifest.json', 'clang-manifest.json']},
                  checks=records)
    def run(cmd, label, cwd):
        log = out / f'{args.stage}-{label}.log'
        start = time.monotonic()
        with log.open('w') as f:
            p = subprocess.run(cmd, cwd=cwd, env=env, stdout=f, stderr=subprocess.STDOUT, timeout=2400)
        text = log.read_text(errors='replace')
        records.append(dict(name=label, command=cmd, exit_code=p.returncode,
                            seconds=round(time.monotonic()-start, 2), log=log.relative_to(ROOT).as_posix(), log_sha256=sha(log)))
        print(args.case, args.stage, label, 'PASS' if p.returncode == 0 else 'FAIL', flush=True)
        assert p.returncode == 0, f'see {log}'
        assert not re.search(r'(?:ERROR: (?:AddressSanitizer|LeakSanitizer)|runtime error:)', text), f'sanitizer diagnostic: {log}'
        return text
    common = ['--disable-dependency-tracking', '--with-mruby', '--without-neverbleed',
              '--with-libev', '--with-libbrotlienc', '--with-libbrotlidec', '--enable-werror']
    try:
        bootstrap = out / 'bootstrap'
        if args.stage == 'archive':
            bootstrap.mkdir(exist_ok=True)
            run(['autoreconf', '-i'], 'autoreconf', repo)
            run([str(repo / 'configure'), *common, '--enable-http3'], 'configure', bootstrap)
            run(['make', f'-j{args.jobs}', 'dist'], 'make-dist', bootstrap)
            archives = list(bootstrap.glob('nghttp2-*.tar.gz'))
            assert len(archives) == 1
            archive = archives[0]
            with tarfile.open(archive) as t:
                names = t.getnames()
                for filename in ['quic_fault_linux_test.go', 'quic_' + ('retry' if args.case == 'retry' else 'truncation') + '_linux_test.go',
                                 'testdata/quic_' + ('retry' if args.case == 'retry' else 'truncation') + '.c']:
                    assert any(n.endswith('/integration-tests/' + filename) for n in names), filename
            result['bootstrap_archive'] = dict(path=archive.relative_to(ROOT).as_posix(), initial_sha256=sha(archive),
                                               note='Transient make dist output; distcheck rebuilds this tarball.')
        elif args.stage == 'distcheck':
            options = common + ['--enable-http3'] + [key+'='+env[key] for key in ['CPPFLAGS','LDFLAGS']]
            text = run(['make', f'-j{args.jobs}', 'distcheck',
                        'DISTCHECK_CONFIGURE_FLAGS=' + shlex.join(options)], 'make-distcheck', bootstrap)
            assert 'archives ready for distribution' in text
            archive = next(bootstrap.glob('nghttp2-*.tar.gz'))
            frozen = out / 'distribution' / archive.name
            frozen.parent.mkdir(exist_ok=True)
            shutil.copy2(archive, frozen)
            result['retained_distribution'] = dict(path=frozen.relative_to(ROOT).as_posix(), sha256=sha(frozen))
        else:
            archive = next((out / 'distribution').glob('nghttp2-*.tar.gz'))
            result['input_distribution_sha256'] = sha(archive)
            dest = out / args.stage
            dest.mkdir(exist_ok=True)
            with tarfile.open(archive) as t:
                t.extractall(dest, filter='data')
            source = next(dest.glob('nghttp2-*'))
            # CI unpacks inside its checkout and inherits its parent Go module.
            for name in ['go.mod', 'go.sum']:
                shutil.copy2(repo / name, dest / name)
            if args.stage in ['autotools', 'no-http3']:
                run(['./configure', *common, '--enable-http3' if args.stage == 'autotools' else '--disable-http3'], 'configure', source)
                run(['make', f'-j{args.jobs}', 'check'], 'check', source)
            else:
                run(['cmake', '-DENABLE_WERROR=1', '-DWITH_MRUBY=1', '-DWITH_NEVERBLEED=0',
                     '-DENABLE_APP=1', '-DENABLE_HTTP3=1', '-DBUILD_STATIC_LIBS=ON', '-DBUILD_TESTING=ON',
                     '-DCMAKE_PREFIX_PATH='+str(ROOT/'tools/nghttp2-ci/deps'),
                     '-DCPPFLAGS='+env['CPPFLAGS'], '-DLDFLAGS='+env['LDFLAGS'],
                     '-DCFLAGS='+env['CFLAGS'],
                     '-DCMAKE_C_FLAGS='+env['CFLAGS']+' '+env['CPPFLAGS'],
                     '-DCMAKE_CXX_FLAGS='+env['CXXFLAGS']+' '+env['CPPFLAGS'],
                     '-DCMAKE_EXE_LINKER_FLAGS='+env['LDFLAGS'],
                     '-DCMAKE_SHARED_LINKER_FLAGS='+env['LDFLAGS'], '.'], 'configure', source)
                run(['make', f'-j{args.jobs}'], 'build', source)
                run(['make', f'-j{args.jobs}', 'check'], 'check', source)
            # Upstream tester uses fixed port3009; serialize integration jobs.
            lock_path = ROOT / 'build/locks/nghttp2-integration.lock'
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            with lock_path.open('w') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                if args.stage != 'no-http3':
                    test = 'TestH3RetryPreservesTerminalState' if args.case == 'retry' else 'TestH3DropsTruncatedDatagrams'
                    focused = run(['sh', 'setenv', 'go', 'test', '-v', '-tags=quic', '-count=1', '-run', '^'+test+'$'], 'focused', source/'integration-tests')
                    assert '--- SKIP:' not in focused
                text = run(['make', 'it'], 'integration', source/'integration-tests')
            assert '--- SKIP:' not in text, 'integration skips require investigation'
            result['integration_root_tests'] = len(re.findall(r'^--- PASS:', text, re.M))
            result['integration_subtests'] = len(re.findall(r'^    --- PASS:', text, re.M))
            assert result['integration_root_tests'] > 0
            result['test_source_overlay'] = False
        result['status'] = 'PASS'
    finally:
        (out / (args.stage + '-results.json')).write_text(json.dumps(result, indent=2) + '\n')

if __name__ == '__main__':
    main()
