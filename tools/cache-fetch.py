#!/usr/bin/env python3
"""Optional WGET override for offline builds from the locked workspace cache."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('-O', dest='output', type=Path, required=True)
parser.add_argument('url')
args = parser.parse_args()
lock = json.loads((root / 'sources.lock.json').read_text())
records = lock['sources'] + lock['runtime_archives'] + [lock['musl'], lock['lwip'], lock['lwip']['previous_compatibility_source']]
record = next((r for r in records if r['url'] == args.url), None)
if record is None:
    parser.error('URL is not in sources.lock.json')
for source in (root / 'cache').rglob(args.url.rsplit('/', 1)[-1]):
    if source.is_file() and hashlib.sha256(source.read_bytes()).hexdigest() == record['sha256']:
        shutil.copyfile(source, args.output)
        break
else:
    parser.error('no verified cached archive for this URL')
