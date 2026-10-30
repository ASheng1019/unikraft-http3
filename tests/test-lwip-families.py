#!/usr/bin/env python3
"""Syntax-check pinned lwIP socket adaptations across IP/metadata selections.

Requires a completed ordinary application build for target compile commands.
Pristine archives are extracted and patched independently; no source tree is
modified. This is compile coverage, not a claim of single-family runtime QA.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import zipfile


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build-dir', type=Path, required=True)
    p.add_argument('--cache-dir', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    root = Path(__file__).resolve().parents[1]
    out = a.output.resolve()
    out.mkdir()
    db = json.loads((a.build_dir/'compile_commands.json').read_text())
    lock = json.loads((root/'sources.lock.json').read_text())['lwip']
    cases = []
    for version, record, groups in [
        ('2.2.1', lock, ['2.2.1/common', '2.2.1/fixes', '2.2.1/native']),
        ('2.1', lock['previous_compatibility_source'], ['common', 'pinned-2.1']),
    ]:
        archive = a.cache_dir/'liblwip'/record['url'].rsplit('/', 1)[-1]
        assert hashlib.sha256(archive.read_bytes()).hexdigest() == record['sha256']
        target = out/version
        with zipfile.ZipFile(archive) as z:
            z.extractall(target)
        source = next(target.iterdir())
        for group in groups:
            for patch in sorted((root/'libs/lib-lwip/patches'/group).glob('*')):
                if patch.is_file():
                    subprocess.run(['patch', '--batch', '--fuzz=0', '-p1', '-i', str(patch)],
                                   cwd=source, check=True, stdout=subprocess.DEVNULL)
        for family in ['4', '6', '46']:
            for metadata in [False, True]:
                name = f'{version}-ipv{family}-metadata{int(metadata)}'
                override = out/(name+'.h')
                override.write_text('#include <uk/config.h>\n' + ''.join(
                    f'#undef CONFIG_LWIP_IPV{x}\n' for x in '46' if x not in family) +
                    '#undef CONFIG_LWIP_NETBUF_RECVINFO\n' +
                    ('#define CONFIG_LWIP_NETBUF_RECVINFO 1\n' if metadata else ''))
                for filename in ['api/api_msg.c', 'api/sockets.c', 'core/udp.c']:
                    entry = next(e for e in db if e['file'].endswith('/src/'+filename))
                    old_source = str(Path(entry['file']).parents[2])
                    command = shlex.split(entry['command'])
                    index = command.index('-o')
                    del command[index:index+2]
                    command = [str(source)+arg[len(old_source):] if arg.startswith(old_source)
                               else '-I'+str(source)+arg[len('-I'+old_source):]
                               if arg.startswith('-I'+old_source) else arg for arg in command]
                    command += ['-fsyntax-only', '-include', str(override)]
                    run = subprocess.run(command, cwd=entry['directory'], capture_output=True, text=True)
                    (out/(name+'-'+Path(filename).stem+'.log')).write_text(run.stdout+run.stderr)
                    assert run.returncode == 0, name+' '+filename
                cases.append(dict(name=name, status='PASS'))
                print('LWIP_FAMILIES', name, 'PASS', flush=True)
    (out/'results.json').write_text(json.dumps(dict(status='PASS', cases=cases), indent=2)+'\n')


if __name__ == '__main__':
    main()
