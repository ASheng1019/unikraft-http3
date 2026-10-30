#!/usr/bin/env python3
"""Build standalone upstream protocol suites with native Unikraft make rules."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--core',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--cache-dir',type=Path,help='optional prior output containing pristine archives only')
    p.add_argument('--compiler',help='optional native compiler executable')
    p.add_argument('--libs-root',type=Path,help='optional alternate port directory for submission-branch qualification')
    a=p.parse_args()
    core=a.core.resolve(strict=True);root=a.output.resolve();root.mkdir(mode=0o700)
    libs=(a.libs_root or Path(__file__).resolve().parent.parent/'libs').resolve()
    results=dict(status='FAIL',suites=[])
    try:
        for name in ['ngtcp2','nghttp3']:
            case=root/name;case.mkdir();out=case/'out';out.mkdir()
            if a.cache_dir:
                for lib in ['libmusl','lib'+name]:
                    for src in (a.cache_dir/lib).iterdir():
                        if src.is_file() and src.name.endswith(('.gz','.xz','.zip')):
                            (out/lib).mkdir(exist_ok=True);shutil.copyfile(src,out/lib/src.name)
            app=libs/('lib-'+name)/'tests/upstream'
            make=['make','-C',str(core),f'A={app}',f'O={out}',f'C={case}/config',
                  f'L={libs}/lib-musl:{libs}/lib-{name}',f'UK_DEFCONFIG={app}/defconfig']
            if a.compiler:make.append('COMPILER='+a.compiler)
            def run(command,log,timeout=900):
                with log.open('x') as f:subprocess.run(command,stdout=f,stderr=subprocess.STDOUT,check=True,timeout=timeout)
            run(make+['defconfig'],case/'configure.log')
            run(make+['-j4'],case/'build.log')
            image=out/'upstream_qemu-arm64'
            run(['qemu-system-aarch64','-machine','virt,gic-version=host','-cpu','host','-accel','kvm',
                 '-m','512M','-smp','1','-display','none','-monitor','none','-serial','stdio','-no-reboot',
                 '-kernel',str(image)],case/'serial.log',120)
            text=(case/'serial.log').read_text()
            summary=re.search(r'(\d+) of (\d+) \(100%\) tests successful, 0 \(0%\) test skipped',text)
            assert summary and int(summary[1])>0 and summary[1]==summary[2]
            count=int(summary[1])
            # The pinned ngtcp2 release has 266 tests; the policy adds 31.
            assert count in ({266,297} if name=='ngtcp2' else {61}), (name,count)
            assert f'UPSTREAM_TESTS {name} PASS' in text
            results['suites'].append(dict(name=name,passed=count,skipped=0,image_sha256=hashlib.sha256(image.read_bytes()).hexdigest()))
            print('STANDARD_PORT',name,count,'PASS',flush=True)
        results['status']='PASS'
    finally:(root/'results.json').write_text(json.dumps(results,indent=2)+'\n')

if __name__=='__main__':main()
