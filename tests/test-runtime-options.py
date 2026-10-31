#!/usr/bin/env python3
"""Exercise deployment ownership through real HTTP/3 and isolated build profiles."""
import argparse
import hashlib
import errno
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import time
from quic_fixture import (WORK, PREFIX, NativeService, Backend, certificates,
                          request, require_body, SMALL, PAYLOAD, config, environment)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--variants', type=Path, required=True)
    a = p.parse_args()
    root = WORK/'build/runtime-options'
    certificates(root)
    backend = Backend(keepalive=True, tcp_nodelay=True)
    services = []
    children = []
    result = dict(status='FAIL', cases=[])
    original_image = os.environ['QUIC_TEST_IMAGE']

    def directory(name):
        d = root/name
        d.mkdir(mode=0o700)
        for f in ['ca.pem', 'server.pem', 'server.key']:
            (d/f).write_bytes((root/f).read_bytes())
            (d/f).chmod(0o600)
        return d

    def record(name, **kw):
        result['cases'].append(dict(name=name, status='PASS', **kw))
        print('RUNTIME_OPTIONS', name, 'PASS', flush=True)

    def start(name, variant='unmanaged', managed=False, overrides=None, port=None):
        app = 'platform-clock-app' if variant == 'platform-clock' else 'app-nghttpx'
        os.environ['QUIC_TEST_IMAGE'] = str(a.variants/variant/'out'/(app+'_qemu-arm64'))
        d = directory(name)
        if variant == 'platform-clock':
            overrides = {'native-epoch.txt': None,
                         'test-platform-epoch.txt': f'{int(time.time())}\n'.encode(),
                         **(overrides or {})}
        s = NativeService(d, port or backend.port, tag='standard', managed=managed,
                          file_overrides=overrides)
        services.append(s)
        return s

    def finish(s, graceful=True):
        # No guest stop mechanism exists in unmanaged profiles. Host teardown
        # is intentional and must not be reported as a graceful guest exit.
        if s.managed and graceful:
            s.stop()
        s.close()
        services.remove(s)

    def no_reply(s, message):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(.25)
            sock.sendto(message, ('127.0.0.1', s.control))
            try:
                sock.recv(1024)
            except socket.timeout:
                return
            raise AssertionError('unexpected management response')

    def rejection(name, variant, overrides, marker=None):
        try:
            s = start(name, variant=variant, overrides=overrides)
        except RuntimeError:
            log = (root/name/'native-serial.log').read_text()
            assert 'NATIVE_NGHTTPX READY' not in log and 'main returned 1' in log
            if marker:
                assert marker in log, marker
            record(name)
        else:
            finish(s)
            raise AssertionError(name+' unexpectedly accepted')

    try:
        # Build-time absence, in addition to network behavior. Inspect target
        # artifacts; a silent UDP timeout alone cannot establish code exclusion.
        result['images'] = {}
        for variant in ['unmanaged', 'shutdown-only', 'stats-only', 'fd-stats', 'platform-clock']:
            app = 'platform-clock-app' if variant == 'platform-clock' else 'app-nghttpx'
            out = a.variants/variant/'out'
            image = out/(app+'_qemu-arm64')
            symbols = subprocess.check_output(['nm', str(image)+'.dbg'], text=True)
            result['images'][variant] = hashlib.sha256(image.read_bytes()).hexdigest()
            if variant in ['unmanaged', 'platform-clock']:
                assert 'app_control_ready' not in symbols
                assert 'reply_stats' not in symbols
            if variant == 'platform-clock':
                for symbol in ['__wrap_clock_gettime', '__wrap_gettimeofday', '__wrap_time', 'app_clock_anchor']:
                    assert symbol not in symbols, symbol
            else:
                assert '__wrap_clock_gettime' in symbols
            if variant in ['shutdown-only', 'stats-only', 'fd-stats']:
                unresolved = subprocess.check_output(['nm', '-u', str(out/'appnghttpx/control.o')], text=True)
                assert (' fcntl\n' in unresolved) == (variant == 'fd-stats')
                assert (' uk_nghttpx_get_stats\n' in unresolved) == (variant != 'shutdown-only')
                assert (' uk_nghttpx_shutdown\n' in unresolved) == (variant != 'stats-only')
        record('disabled-code-absent')
        # No token file and no control config; requests still complete.
        s = start('unmanaged-h1')
        require_body(request(s.root, s.front, label='small'), SMALL)
        require_body(request(s.root, s.front, '/download', label='large'), PAYLOAD)
        upload = bytes(range(256))*4096
        require_body(request(s.root, s.front, '/post', body=upload, label='post'), upload)
        for message in [b'0'*64, s.token.encode(), b'STATS '+s.token.encode()]:
            no_reply(s, message)
        require_body(request(s.root, s.front, label='after-control'), SMALL)
        assert 'READY management=disabled' in s.log_path.read_text()
        assert 'CONTROL port=' not in s.log_path.read_text()
        finish(s)
        record('unmanaged-h1-large-post', token_required=False, guest_shutdown=False)

        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(root/'server.pem', root/'server.key')
        ctx.set_alpn_protocols(['http/1.1'])
        tls = Backend(keepalive=True, tls_context=ctx)
        children.append(tls)
        conf = config(tls.port, extra='cacert=/backend-ca.pem\n').replace(
            f'backend=10.0.2.2,{tls.port}',
            f'backend=10.0.2.2,{tls.port};;tls;sni=localhost')
        s = start('unmanaged-tls-origin', port=tls.port,
                  overrides={'nghttpx.conf': conf.encode(), 'backend-ca.pem': (root/'ca.pem').read_bytes()})
        require_body(request(s.root, s.front, label='verified-origin'), SMALL)
        finish(s)
        record('unmanaged-verified-tls-origin')

        d = directory('h2-origin')
        www = d/'www'
        www.mkdir()
        (www/'download').write_bytes(PAYLOAD)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        with (d/'origin.log').open('x') as log:
            h2 = subprocess.Popen([str(PREFIX/'bin/nghttpd'), '-v', '-a', '127.0.0.1',
                                   '-d', str(www), str(port), str(root/'server.key'), str(root/'server.pem')],
                                  env=environment(), stdout=log, stderr=subprocess.STDOUT)
        try:
            time.sleep(.2)
            conf = config(port, extra='cacert=/backend-ca.pem\n').replace(
                f'backend=10.0.2.2,{port}', f'backend=10.0.2.2,{port};;tls;sni=localhost;proto=h2')
            s = start('unmanaged-h2-origin', port=port,
                      overrides={'nghttpx.conf': conf.encode(), 'backend-ca.pem': (root/'ca.pem').read_bytes()})
            with ThreadPoolExecutor(max_workers=4) as pool:
                replies = list(pool.map(lambda n: request(s.root, s.front, '/download', label=f'h2-{n}'), range(8)))
            for reply in replies:
                require_body(reply, PAYLOAD)
            finish(s)
            record('unmanaged-concurrent-h2-origin', requests=8)
        finally:
            h2.terminate()
            h2.wait(timeout=5)

        rejection('unmanaged-reject-control', 'unmanaged', {'native-runtime.conf': b'control=10.0.2.15,4434\n'})
        rejection('missing-epoch', 'unmanaged', {'native-epoch.txt': None})
        rejection('no-clock-provider', 'platform-clock', {'test-platform-epoch.txt': None}, 'TIME unavailable')
        s = start('platform-clock-provider', variant='platform-clock')
        require_body(request(s.root, s.front, '/download', label='platform-time'), PAYLOAD)
        finish(s)
        record('platform-clock-without-app-wrappers', test_provider=True)
        conf = config(tls.port, extra='cacert=/backend-ca.pem\n').replace(
            f'backend=10.0.2.2,{tls.port}', f'backend=10.0.2.2,{tls.port};;tls;sni=localhost')
        s = start('platform-clock-tls-origin', variant='platform-clock', port=tls.port,
                  overrides={'nghttpx.conf': conf.encode(), 'backend-ca.pem': (root/'ca.pem').read_bytes()})
        require_body(request(s.root, s.front, label='platform-verified-origin'), SMALL)
        finish(s)
        record('platform-clock-verified-tls-origin')

        s = start('shutdown-only', variant='shutdown-only', managed=True)
        no_reply(s, b'STATS '+s.token.encode())
        no_reply(s, b'0'*64)
        require_body(request(s.root, s.front, label='still-running'), SMALL)
        finish(s)
        record('shutdown-without-stats', graceful_shutdown=True)
        s = start('stats-only', variant='stats-only', managed=True,
                  overrides={'native-runtime.conf': b'control=10.0.2.15,4434\n'})
        no_reply(s, s.token.encode())
        assert s.stats()['fd_scan_limit'] == 0
        require_body(request(s.root, s.front, label='read-only-management'), SMALL)
        finish(s, graceful=False)
        record('stats-without-shutdown', guest_shutdown=False)
        s = start('fd-stats', variant='fd-stats', managed=True)
        stat = s.stats()
        assert stat['fd_scan_limit'] == 4096 and stat['fds'] > 0
        finish(s)
        record('explicit-fd-stats')

        os.environ['QUIC_TEST_IMAGE'] = original_image
        d = directory('normal-stats')
        s = NativeService(d, backend.port, tag='standard')
        services.append(s)
        no_reply(s, b'STATS '+b'0'*64)
        stat = s.stats()
        assert stat['fds'] == -1 and stat['fd_scan_limit'] == 0
        finish(s)
        record('stats-without-fd-scan')

        for name, runtime, code in [
            ('unknown-interface', 'ipv6-interface=en99\nipv6-multicast-rx=yes\n', -errno.ENODEV),
            ('missing-interface', 'ipv6-address=fd00:1::2\n', None),
            ('missing-multicast-contract', 'ipv6-interface=en1\nipv6-address=fd00:1::2\n', -errno.EOPNOTSUPP),
            ('multicast-address', 'ipv6-interface=en1\nipv6-multicast-rx=yes\nipv6-address=ff02::1\n', -errno.EINVAL),
            ('dad-timeout', 'ipv6-interface=en1\nipv6-multicast-rx=yes\nipv6-dad-timeout-ms=1\n', -errno.ETIMEDOUT),
        ]:
            rejection(name, 'unmanaged', {'native-runtime.conf': runtime.encode()},
                      None if code is None else f'IPV6 failed status={code}')
        s = start('explicit-slaac', overrides={'native-runtime.conf': b'ipv6-interface=en1\nipv6-multicast-rx=yes\nipv6-slaac=yes\n'})
        require_body(request(s.root, s.front, label='named-interface'), SMALL)
        finish(s)
        record('explicit-linklocal-slaac', global_slaac_address_qualification=False)
        result['status'] = 'PASS'
    finally:
        os.environ['QUIC_TEST_IMAGE'] = original_image
        for s in services:
            s.close()
        for child in children:
            child.close()
        backend.close()
        (WORK/'runtime-options-results.json').write_text(json.dumps(result, indent=2)+'\n')


if __name__ == '__main__':
    main()
