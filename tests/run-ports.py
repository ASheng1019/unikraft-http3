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
    a=p.parse_args()
    core=a.core.resolve(strict=True);root=a.output.resolve();root.mkdir(mode=0o700)
    libs=Path(__file__).resolve().parent.parent/'libs'
    results=dict(status='FAIL',suites=[])
    try:
        for name,count in [('ngtcp2',297),('nghttp3',61)]:
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
            assert re.search(rf'{count} of {count} \(100%\) tests successful, 0 \(0%\) test skipped',text)
            assert f'UPSTREAM_TESTS {name} PASS' in text
            results['suites'].append(dict(name=name,passed=count,skipped=0,image_sha256=hashlib.sha256(image.read_bytes()).hexdigest()))
            print('STANDARD_PORT',name,count,'PASS',flush=True)
        results['status']='PASS'
    finally:(root/'results.json').write_text(json.dumps(results,indent=2)+'\n')

if __name__=='__main__':main()
