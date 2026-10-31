#!/usr/bin/env python3
"""Native HTTP/3: two real MTU blackholes separated by a full cooldown/reprobe."""
import argparse
import base64
import concurrent.futures
import gzip
import re
import shlex
import sys
import time

import hashlib, json, datetime, os
from pathlib import Path
from quic_fixture import NativeService, certificates, config, PAYLOAD, PREFIX, WORK
from ethernet_fixture import EthernetLink, ClientVM
ROOT = WORK
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
utc = lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
def write(path, obj): path.write_text(json.dumps(obj, indent=2)+'\n')


def packets(events, lower, upper):
    return [e['data']['raw']['length'] for e in events
            if e.get('name') == 'transport:packet_received'
            and any(f.get('frame_type') == 'stream' and
                    4 * lower <= int(f.get('stream_id', -1)) < 4 * upper
                    for f in e.get('data', {}).get('frames', []))]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag', required=True)
    parser.add_argument('--family', choices=[4, 6], type=int, required=True)
    parser.add_argument('--attempt', required=True)
    args = parser.parse_args()
    assert args.tag.isalnum() and args.attempt.isalnum()
    image = Path(os.environ['QUIC_TEST_IMAGE'])
    root = ROOT / 'network' / f'{args.tag}-ipv{args.family}-{args.attempt}'
    assert not root.exists(), 'preserve prior attempts'
    root.mkdir(parents=True, mode=0o700)
    result = dict(status='FAIL', started_utc=utc(), settings=vars(args), transitions=[],
                  image_sha256=sha(image), 
                  server='Unikraft/KVM nghttpx; U03 v2 release patches',
                  client='unchanged pinned Linux curl/ngtcp2 in KVM',
                  payload_bytes=len(PAYLOAD), payload_sha256=sha_bytes(PAYLOAD),
                  client_sha256=sha(PREFIX / 'bin/curl'),
                  fixture_version='standard')
    client = native = link = pool = future = None
    qlog_done = False

    def capture():
        nonlocal qlog_done
        code, encoded = client.run('cat /tmp/mtu-qlog/* | gzip -c | base64', timeout=30)
        assert code == 0, 'qlog export failed'
        qlog = gzip.decompress(base64.b64decode(''.join(encoded.split()), validate=True))
        path = root / 'client-qlog.jsonseq'
        path.write_bytes(qlog)
        qlog_done = True
        events = [__import__('json').loads(e) for e in qlog.decode().split('\x1e') if e.strip()]
        result['qlog_connections'] = sum('qlog_format' in e for e in events)
        result['qlog_sha256'] = sha(path)
        return events

    try:
        certificates(root)
        link = EthernetLink()
        cgi = b'#!/busybox sh\nsleep 1\nprintf "Content-Type: application/octet-stream\\r\\nContent-Length: 262144\\r\\n\\r\\n"\ncat /www/download\n'
        requests = ''.join(f'url = "https://localhost:4433/cgi-bin/paced-download?phase={i}"\noutput = "/tmp/mtu-{i}"\n' for i in range(80))
        files = {'www/cgi-bin/paced-download': (cgi, 0o100755),
                 'curl-requests.conf': (requests.encode(), 0o100600)}
        client = ClientVM(root, link, files=files)
        host = '198.18.0.2' if args.family == 4 else 'fd00:1::2'
        conf = config(8080, idle='45s').replace('frontend=10.0.2.15,4433;quic', f'frontend={host},4433;quic').replace('backend=10.0.2.2,8080', 'backend=198.18.0.1,8080')
        runtime = (b'control=198.18.0.2,4434\ndrain-seconds=5\nipv6-interface=en1\nipv6-multicast-rx=yes\nipv6-address=fd00:1::2\n'
                   + (Path(__file__).parent.parent / 'app-nghttpx/recommended-runtime.conf').read_bytes())
        offloads = ('csum', 'guest_csum', 'gso', 'host_tso4', 'host_tso6', 'host_ecn', 'host_ufo')
        options = [v for prop in offloads for v in ['-global', f'virtio-net-device.{prop}=off']]
        native = NativeService(root, 8080, tag=args.tag, instrumented=False,
                               guest_address='198.18.0.2', static_cidr='198.18.0.2/24',
                               wire=(link.native_port, link.to_native), qemu_options=options,
                               file_overrides={'nghttpx.conf': conf.encode(), 'native-runtime.conf': runtime})
        assert native.image == image
        result['runtime_sha256'] = sha_bytes(runtime)
        result['offloads_disabled'] = list(offloads)
        result['resources'] = dict(server_vcpus=1, client_vcpus=1, memory_mib_per_guest=768)
        assert client.run('mkdir -p /tmp/mtu-qlog')[0] == 0
        address = host if args.family == 4 else f'[{host}]'
        command = ('QLOGDIR=/tmp/mtu-qlog /curl --http3-only --fail-early --fail-with-body '
                   '--cacert /ca.pem --noproxy "*" --silent --show-error --max-time 15 '
                   f'--resolve localhost:4433:{address} '
                   '--write-out "PHASE=%{urlnum} CODE=%{http_code} CONNECTS=%{num_connects} BYTES=%{size_download}\\n" '
                   '--config /curl-requests.conf')
        offset = client.log_path.stat().st_size
        started = time.monotonic()
        pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        future = pool.submit(client.run, command, 200)
        for phase, mtu in [(0, 1280), (1, 1500), (75, 1280), (76, 1500)]:
            deadline = time.monotonic() + 115
            marker = f'PHASE={phase} CODE=200 CONNECTS={1 if phase == 0 else 0} BYTES={len(PAYLOAD)}'
            while marker not in client.log_path.read_bytes()[offset:].decode(errors='replace'):
                assert not future.done(), f'transfer ended before phase {phase}'
                assert time.monotonic() < deadline, f'phase {phase} timeout'
                time.sleep(.005)
            result['transitions'].append(dict(after_phase=phase, new_mtu=mtu,
                                               packet_index=len(link.records), elapsed_s=time.monotonic()-started))
            link.mtu = mtu
            print(f'U03_NATIVE IPv{args.family} phase={phase} MTU={mtu}', flush=True)
        code, output = future.result(timeout=25)
        (root / 'client-transfer.log').write_text(output)
        assert code == 0, f'curl exit {code}'
        phases = [dict(phase=int(m[0]), code=int(m[1]), connects=int(m[2]), bytes=int(m[3]))
                  for m in re.findall(r'PHASE=(\d+) CODE=(\d+) CONNECTS=(\d+) BYTES=(\d+)', output)]
        assert len(phases) == 80
        for i, phase in enumerate(phases):
            assert phase == dict(phase=i, code=200, connects=int(i == 0), bytes=len(PAYLOAD)), phase
        result['responses'] = phases
        code, output = client.run('sha256sum ' + ' '.join(f'/tmp/mtu-{i}' for i in range(80)))
        (root / 'body-hashes.log').write_text(output)
        hashes = re.findall(r'([0-9a-f]{64})\s+/tmp/mtu-(\d+)', output)
        assert code == 0 and len(hashes) == 80 and {int(i) for _, i in hashes} == set(range(80))
        assert all(digest == result['payload_sha256'] for digest, _ in hashes)
        result['body_hashes_verified'] = 80
        events = capture()
        assert result['qlog_connections'] == 1, 'connection was replaced'
        baseline = packets(events, 0, 1)
        cooldown = packets(events, 5, 50)
        recovered = packets(events, 65, 75)
        assert max(baseline, default=0) > 1280, 'no baseline large STREAM data'
        assert cooldown and max(cooldown) <= 1200, 'fallback/cooldown not observed'
        assert max(recovered, default=0) > 1280, 'no recovered large STREAM data before second shrink'
        result['stream_evidence'] = dict(baseline_max_udp=max(baseline), cooldown_phase_range=[5, 50],
                                         cooldown_max_udp=max(cooldown), cooldown_packets=len(cooldown),
                                         recovered_phase_range=[65, 75], recovered_max_udp=max(recovered),
                                         recovered_large_packets=sum(n > 1280 for n in recovered))
        windows = []
        for i in [0, 2]:
            start, end = result['transitions'][i:i+2]
            frames = [r for r in link.records[start['packet_index']:end['packet_index']]
                      if r['direction'] == 'server' and r['family'] == args.family and r.get('next') == 17]
            drops = sum(r['dropped'] for r in frames)
            largest = max((r['length'] for r in frames if not r['dropped']), default=0)
            assert drops > 0 and 1000 < largest <= 1280, 'shrink was not exercised'
            windows.append(dict(after_phase=start['after_phase'], oversize_drops=drops,
                                largest_delivered_ip=largest, completion_s=end['elapsed_s']-start['elapsed_s']))
        result['shrink_windows'] = windows
        assert result['transitions'][2]['elapsed_s'] - result['transitions'][1]['elapsed_s'] >= 60
        # This helper sends the control token on stdin; neither token nor
        # control command is persisted in the public result or transcript.
        code, _ = client.run(f'printf %s {shlex.quote(native.token)} | /wire-control 198.18.0.2 4434')
        exitcode = native.process.wait(timeout=10)
        assert code == exitcode == 0 and 'main returned 0' in native.log_path.read_text(), 'unclean shutdown'
        result.update(status='PASS', same_connection_transfers=80, graceful_shutdown=True,
                      fixture_finished=True)
    except Exception as error:
        result['error'] = str(error)
        raise
    finally:
        if future and not future.done() and client:
            client.process.terminate()
        if pool:
            pool.shutdown(wait=True, cancel_futures=True)
        if client and client.process.poll() is None and not qlog_done:
            try:
                capture()
            except Exception as error:
                result['qlog_error'] = str(error)
        if native:
            native.close()
        if client:
            client.close()
        if link:
            link.close()
            # IP metadata only: no payload, key or control token.
            write(root / 'wire-records.json', link.records)
        result.update(finished_utc=utc(), fixture_sha256=sha(__file__))
        result['evidence'] = {name: sha(root / name) for name in
                              ['client-transfer.log', 'body-hashes.log', 'client-qlog.jsonseq', 'wire-records.json']
                              if (root / name).exists()}
        write(root / 'results.json', result)
    print(f'U03_NATIVE IPv{args.family} PASS transfers=80', flush=True)


def sha_bytes(data):
    import hashlib
    return hashlib.sha256(data).hexdigest()


if __name__ == '__main__':
    main()
