#!/usr/bin/env python3
"""Compile a normal C++ consumer with real build flags and a negative config control."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compile-commands', type=Path, required=True)
    parser.add_argument('--baseline-port', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(mode=0o700)
    database = json.loads(args.compile_commands.read_text())
    entry = next(row for row in database if row['file'].endswith('/lib-nghttpx/entry.cc'))
    tokens = shlex.split(entry['command'])
    command = []
    skip = False
    for value in tokens:
        if skip:
            skip = False
            continue
        if value in ('-c', '-o'):
            skip = True
            continue
        if value.startswith('-Wp,-MD,'):
            continue
        command.append(value)
    source = args.output / 'consumer.cc'
    source.write_text('''#include <__config_site>
#ifdef _LIBCPP_BUILDING_LIBRARY
#error CONSUMER_BUILD_MACRO_LEAK
#endif
#include <cmath>
#include <cstdlib>
#include <string_view>
static_assert(std::string_view("h3").starts_with("h"));
int consumer(double value) { return std::isfinite(value) ? std::abs(-1) : 0; }
''')
    baseline = args.output / 'baseline'
    baseline.mkdir()
    original = subprocess.check_output(['git', '-C', str(args.baseline_port), 'show',
                                       'b7d939f50cdd4ab19967858084f4a33fb62b6c0e:include/21.1.8/__config_site'])
    (baseline / '__config_site').write_bytes(original)
    results = []
    for name, prefix, success in [('current', [], True),
                                  ('baseline-config', ['-I' + str(baseline.resolve())], False)]:
        run = subprocess.run(command[:1] + prefix + command[1:] +
                             ['-fsyntax-only', '-H', str(source.resolve())],
                             cwd=entry['directory'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        (args.output / (name + '.log')).write_bytes(run.stdout)
        assert (run.returncode == 0) == success, name
        if not success:
            assert b'CONSUMER_BUILD_MACRO_LEAK' in run.stdout
        results.append(dict(name=name, expected_success=success, exit_code=run.returncode,
                            log_sha256=hashlib.sha256(run.stdout).hexdigest()))
    (args.output / 'results.json').write_text(json.dumps(dict(status='PASS', checks=results), indent=2) + '\n')
    print('CXX_CONSUMER PASS positive_and_baseline_macro_control', flush=True)


if __name__ == '__main__':
    main()
