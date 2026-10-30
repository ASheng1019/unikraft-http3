"""Materialize a Git ref and its cached submodules without changing a checkout."""
import io
import subprocess
import tarfile
from pathlib import Path


def snapshot(repo, ref, destination):
    repo = Path(repo)
    destination = Path(destination)
    destination.mkdir()
    head = subprocess.check_output(
        ['git', '-C', str(repo), 'rev-parse', ref], text=True).strip()

    def extract(git_dir, commit, target):
        data = subprocess.check_output(['git', '--git-dir', str(git_dir), 'archive', commit])
        with tarfile.open(fileobj=io.BytesIO(data)) as archive:
            archive.extractall(target, filter='data')
        tree = subprocess.check_output(
            ['git', '--git-dir', str(git_dir), 'ls-tree', '-r', commit], text=True)
        for line in tree.splitlines():
            metadata, name = line.split('\t', 1)
            mode, _, oid = metadata.split()
            if mode == '160000':
                # nghttp2 uses submodule names identical to their paths.
                module = git_dir / 'modules' / name
                if not module.is_dir():
                    if git_dir == Path(common):
                        raise RuntimeError(f'Initialize cached submodule {name} in {repo} first')
                    # Match the checkout: optional nested test dependencies may
                    # be uninitialized (e.g. urlparse's own test submodules).
                    continue
                extract(module, oid, target / name)

    common = subprocess.check_output(
        ['git', '-C', str(repo), 'rev-parse', '--path-format=absolute', '--git-common-dir'],
        text=True).strip()
    extract(Path(common), head, destination)
    return head
