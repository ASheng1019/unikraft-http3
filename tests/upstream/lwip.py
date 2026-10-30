#!/usr/bin/env python3
"""Native red/green regressions and strict lwIP sanitizer/CI validation.

Builds only git-archive snapshots. No downloads, pushes or PR creation.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import tarfile
import time

ROOT = Path(__file__).resolve().parents[2]
BASE = '339df98f6967fbc0f5e8f87ec345b1365bb542b2'
CASES = {
    'arm64': ('dev/detect-unit-test-pointer-width', 'test/unit/lwipopts.h', None, 139),
    'loopback': ('dev/fix-loopback-callback-type', 'src/core/netif.c', 'NETIF', 4),
    'mqtt': ('dev/reject-overlong-mqtt-length', 'src/apps/mqtt/mqtt.c', 'MQTT', 4),
    'combined': ('dev/lwip-correctness-validation', None, None, 144),
    'recvmsg': ('dev/lwip-correctness-validation', 'src/api/sockets.c', 'SOCKETS', 7),
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', choices=CASES, required=True)
    parser.add_argument('--compiler', choices=['gcc', 'clang'], required=True)
    parser.add_argument('--output', type=Path, required=True, help='fresh workspace directory')
    parser.add_argument('--ci', action='store_true', help='combined upstream Linux CI')
    parser.add_argument('--release', action='store_true', help='test 2.2.1 plus the port correctness backports')
    parser.add_argument('--jobs', type=int, default=8)
    args = parser.parse_args()
    if args.case == 'loopback' and args.compiler != 'clang':
        parser.error('the callback type regression requires Clang function sanitizer')
    if args.case == 'arm64' and args.compiler != 'gcc':
        parser.error('isolate ARM64 configuration with GCC; combined mode tests Clang strictly')
    if args.ci and args.case != 'combined':
        parser.error('--ci requires --case combined')
    repo_name, production, suite, count = CASES[args.case]
    repo = ROOT/'forks/lwip'
    base = '77dcd25a72509eb83f72b033d219b1d40cd8eb95' if args.release else BASE
    ref = base if args.release else repo_name
    if args.release:
        count = {'arm64': 137, 'loopback': 4, 'mqtt': 3, 'recvmsg': 7, 'combined': 142}[args.case]
    head = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', ref], text=True).strip()
    out = args.output.resolve()
    out.mkdir(parents=True, mode=0o700)
    source = out/'source'
    source.mkdir()
    data = subprocess.check_output(['git', '-C', str(repo), 'archive', head])
    (out/'source.tar').write_bytes(data)
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        tar.extractall(source, filter='data')
    applied = []
    if args.release:
        for patch in sorted((ROOT/'libs/lib-lwip/patches/2.2.1/fixes').glob('*.patch')):
            # Isolate the pointer-width fix for its baseline comparison.
            if args.case == 'arm64' and not patch.name.startswith('0001-'):
                continue
            subprocess.run(['patch', '--batch', '--fuzz=0', '-p1', '-i', str(patch)], cwd=source, check=True)
            applied.append(patch.relative_to(ROOT).as_posix())
    check = ROOT/'tools/check/usr'
    docs = ROOT/'tools/lwip-ci/usr'
    compiler = '/usr/bin/gcc' if args.compiler == 'gcc' else '/usr/bin/clang-18'
    env = dict(os.environ, CC=compiler, CCACHE_DISABLE='1',
               PATH=str(docs/'bin')+':'+os.environ['PATH'],
               LD_LIBRARY_PATH=f'{docs}/lib/aarch64-linux-gnu:{check}/lib/aarch64-linux-gnu',
               ASAN_OPTIONS='detect_leaks=1:abort_on_error=1',
               UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1')
    for key in ['CK_RUN_SUITE','CK_RUN_CASE','CK_INCLUDE_TAGS','CK_EXCLUDE_TAGS',
                'CFLAGS','CPPFLAGS','CXXFLAGS','LDFLAGS']:
        env.pop(key, None)
    if suite:
        env['CK_RUN_SUITE'] = suite
    # Preserve the upstream alignment exclusion for protocol wire structures.
    sanitizer = '' if args.case == 'arm64' else '-fsanitize=address,undefined -fno-sanitize=alignment -fno-sanitize-recover=undefined'
    warning = ' -Wno-error=unused-but-set-variable' if args.release and args.compiler == 'clang' else ''
    make = ['make','-C',str(source/'contrib/ports/unix/check'),
            f'CC={compiler}{warning} -isystem {check}/include {sanitizer}',
            f'LDFLAGS=-L{check}/lib/aarch64-linux-gnu -lcheck -lsubunit -lm -pthread',f'-j{args.jobs}']
    names = subprocess.check_output(['git','-C',str(repo),'diff','--name-only',base,head],text=True).splitlines()
    result = dict(status='FAIL',case=args.case,compiler=args.compiler,head=head,
                  base_commit=base,release_backports=applied,source_archive_sha256=sha(out/'source.tar'),
                  source_inputs={name:sha(source/name) for name in names},
                  compiler_version=subprocess.check_output([compiler,'--version'],text=True).splitlines()[0],
                  strict_sanitizer=args.case != 'arm64',
                  sanitizer_flags=sanitizer, forced_ipv6_configuration=False,
                  recovery=False, diagnostic_allowlist=False, suite=suite, expected_tests=count,
                  checks=[], options=[], pushes=False, PR_created=False)

    def run(command,label,cwd=None,fail=False,expected=None):
        log = out/(label+'.log')
        start=time.monotonic()
        with log.open('x') as f:
            p=subprocess.run(command,cwd=cwd,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=1800)
        text=log.read_text(errors='replace')
        result['checks'].append(dict(name=label,command=command,exit_code=p.returncode,
                                     expected_failure=fail,expected_diagnostic=expected,
                                     seconds=round(time.monotonic()-start,2),
                                     log=log.relative_to(ROOT).as_posix(),log_sha256=sha(log)))
        print(args.case,args.compiler,label,'EXPECTED_FAIL' if fail else ('PASS' if p.returncode==0 else 'FAIL'),flush=True)
        assert bool(p.returncode)==fail,str(log)
        diagnostics=re.search(r'runtime error:|ERROR: (?:AddressSanitizer|LeakSanitizer)|SUMMARY: .*Sanitizer',text)
        if fail:
            assert expected in text,str(log)
        else:
            assert not diagnostics,str(log)
        return text

    def green(label):
        text=run(make+['check'],label)
        assert f'100%: Checks: {count}, Failures: 0, Errors: 0' in text
        return text

    try:
        run(make,'unit-build')
        green('unit-check')
        if production:
            path=source/production
            original=path.read_bytes()
            try:
                path.write_bytes(subprocess.check_output(['git','-C',str(repo),'show',base+':'+production]))
                run(make,'baseline-build')
                marker={'arm64':'sizeof(struct ip6_reass_helper)',
                        'loopback':'call to function netif_poll through pointer to incorrect function type',
                        'mqtt':'state.disconnected == 1 && client->conn == NULL',
                        'recvmsg':'got 4, expected 1'}[args.case]
                text=run(make+['check'],'baseline-fails',fail=True,expected=marker)
                if args.case=='mqtt' and args.compiler=='clang' and not args.release:
                    assert 'shift exponent 35 is too large' in text
                if args.case=='recvmsg':
                    assert 'Checks: 7, Failures: 2, Errors: 0' in text
                    fixed=b'(ssize_t)LWIP_MIN((size_t)datagram_len, (size_t)buflen)'
                    assert original.count(fixed)==1
                    path.write_bytes(original.replace(fixed,
                        b'(ssize_t)LWIP_MIN((size_t)datagram_len, message->msg_iov[0].iov_len)'))
                    run(make,'first-iovec-build')
                    text=run(make+['check'],'first-iovec-fails',fail=True,expected='iovecs=2 capacity=2')
                    assert 'Checks: 7, Failures: 3, Errors: 0' in text
            finally:
                path.write_bytes(original)
                run(make,'restored-build')
            green('restored-check')
        if args.case=='recvmsg':
            observations=[]
            for family,address in [(socket.AF_INET,('127.0.0.1',0)),(socket.AF_INET6,('::1',0))]:
                for capacities in [[1],[1,2]]:
                    with socket.socket(family,socket.SOCK_DGRAM) as sock:
                        sock.settimeout(2)
                        sock.bind(address)
                        sock.sendto(b'abcd',sock.getsockname())
                        for flags in [socket.MSG_PEEK,0]:
                            n,_,output_flags,_=sock.recvmsg_into([bytearray(n) for n in capacities],0,flags)
                            assert n==sum(capacities) and output_flags & socket.MSG_TRUNC
                            observations.append(dict(family=int(family),capacities=capacities,peek=bool(flags),returned=n))
            result['linux_reference']=observations
        if args.ci:
            example=source/'contrib/examples/example_app'
            shutil.copy2(example/'lwipcfg.h.ci',example/'lwipcfg.h')
            build=out/'cmake'
            run(['cmake','-S',str(source),'-B',str(build),'-G','Ninja',
                 '-DCMAKE_C_COMPILER='+compiler],'cmake-configure')
            run(['cmake','--build',str(build),'--parallel',str(args.jobs)],'cmake-build')
            run(['cmake','--build',str(build),'--target','lwipdocs'],'cmake-docs')
            run(['./iteropts.sh'],'iteropts',source/'contrib/ports/unix/example_app')
            configs=sorted((example/'test_configs').glob('*.h'))
            assert len(configs)==14
            for config in configs:
                log=source/'contrib/ports/unix/example_app'/(config.stem+'.log')
                result['options'].append(dict(name=config.stem,log=log.relative_to(ROOT).as_posix(),sha256=sha(log)))
            shutil.copy2(example/'lwipcfg.h.example',example/'lwipcfg.h')
            run(['make','-C',str(source/'contrib/ports/unix/example_app'),'TESTFLAGS=-Wno-documentation','-j4'],'default-example')
            if args.compiler=='gcc':
                build=out/'unit-cmake'
                run(['cmake','-S',str(source/'contrib/ports/unix/check'),'-B',str(build),'-G','Ninja',
                     '-DCMAKE_C_COMPILER='+compiler,'-DCMAKE_BUILD_TYPE=Debug',
                     f'-DCMAKE_C_FLAGS=-isystem {check}/include -Wno-error=format-extra-args -fno-stack-clash-protection -fno-sanitize-recover=undefined',
                     '-DCMAKE_LIBRARY_PATH='+str(check/'lib/aarch64-linux-gnu')],'unit-cmake-configure')
                run(['cmake','--build',str(build),'--parallel',str(args.jobs)],'unit-cmake-build')
                text=run([str(build/'lwip_unittests')],'unit-cmake-check',build)
                assert f'100%: Checks: {count}, Failures: 0, Errors: 0' in text
        if args.case=='arm64':
            result['configuration_probes']=[]
            for target,size,flag in [('aarch64-linux-gnu','8','PTR64'),('armv7-none-eabi','4','PTR32'),
                                     ('x86_64-linux-gnu','8','PTR64'),('i686-linux-gnu','4','PTR32')]:
                command=['/usr/bin/clang-18','--target='+target,'-E','-dM','-include',
                         str(source/'test/unit/lwipopts.h'),'-x','c','/dev/null']
                text=run(command,'configuration-'+target)
                defines={l.split()[1]:' '.join(l.split()[2:]) for l in text.splitlines() if l.startswith('#define ')}
                assert defines['__SIZEOF_POINTER__']==size and flag in defines
                assert ('IPV6_FRAG_COPYHEADER' in defines)==(size=='8')
                result['configuration_probes'].append(dict(target=target,pointer_bytes=int(size),
                    classification=flag,copy_header=defines.get('IPV6_FRAG_COPYHEADER','default')))
        assert all(sha(source/n)==h for n,h in result['source_inputs'].items())
        result['status']='PASS'
    finally:
        (out/'results.json').write_text(json.dumps(result,indent=2)+'\n')

if __name__=='__main__':
    main()
