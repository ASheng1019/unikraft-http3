#!/usr/bin/env python3
"""Rebuild the isolated, pinned libslirp used by local regression tests."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[2]
URL = 'https://gitlab.freedesktop.org/slirp/libslirp/-/archive/v4.9.5/libslirp-v4.9.5.tar.gz'
SHA256 = 'f43e68b60b580647574ec4a0e2b6c600a56281e6c39f79426510832dc810f483'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='fresh build directory')
    args = parser.parse_args()
    output = args.output.resolve()
    archive = ROOT / 'cache/tools/libslirp-v4.9.5.tar.gz'
    if not archive.is_file() or sha(archive) != SHA256:
        parser.error(f'place {URL} at {archive}, required SHA256 {SHA256}')
    output.mkdir(parents=True, mode=0o700)
    with tarfile.open(archive) as stream:
        stream.extractall(output / 'source', filter='data')
    source = output / 'source/libslirp-v4.9.5'
    patch = Path(__file__).resolve().with_name('time-wait-syn.patch')
    subprocess.run(['patch', '-p1', '--batch', '--fuzz=0', '-i', str(patch)], cwd=source, check=True)
    build = output / 'out'
    env = dict(os.environ, CCACHE_DISABLE='1')
    subprocess.run(['meson', 'setup', str(build), str(source), '--buildtype=release',
                    '-Ddefault_library=shared'], env=env, check=True)
    subprocess.run(['ninja', '-C', str(build), '-j8'], env=env, check=True)
    subprocess.run(['meson', 'test', '-C', str(build), '--print-errorlogs'], env=env, check=True)
    library = (build / 'libslirp.so.0').resolve(strict=True)
    result = dict(status='PASS', source_url=URL, source_sha256=SHA256,
                  patch_sha256=sha(patch), builder_sha256=sha(Path(__file__)),
                  library=str(library), library_sha256=sha(library))
    (output / 'build-results.json').write_text(json.dumps(result, indent=2) + '\n')
    print('PASS; select explicitly with --slirp-dir', build)


if __name__ == '__main__':
    main()
