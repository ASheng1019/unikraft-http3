#!/usr/bin/env python3
"""Test-only image: a blocked 1-RTT datagram survives three EAGAIN returns."""
import hashlib
import json
from quic_fixture import WORK, NativeService, Backend, certificates, request, require_body, SMALL, PAYLOAD

def main():
    root=WORK/'build/udp-eagain';root.mkdir(mode=0o700);certificates(root)
    backend=Backend(keepalive=True,tcp_nodelay=True);native=None
    result=dict(status='FAIL',scope='test-only --wrap=sendmsg; ordinary protocol/service libraries')
    try:
        native=NativeService(root,backend.port,tag='standard')
        result['image_sha256']=hashlib.sha256(native.image.read_bytes()).hexdigest()
        require_body(request(root,native.front,'/download',label='large'),PAYLOAD)
        require_body(request(root,native.front,label='next'),SMALL)
        native.idle_stats();native.stop()
        marker='TEST_UDP_EAGAIN PASS failures=3 identical_datagram_and_metadata=1'
        assert marker in native.log_path.read_text(), 'identical pending datagram was not replayed through all injected failures'
        result.update(status='PASS',injected_eagain=3,identical_datagram_and_metadata=True,
                      large_body_sha256=hashlib.sha256(PAYLOAD).hexdigest(),subsequent_request=True,
                      graceful_shutdown=True)
        print('STANDARD_EAGAIN PASS failures=3 identical_datagram_and_metadata=1',flush=True)
    finally:
        if native:native.close()
        backend.close();(WORK/'eagain-results.json').write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':main()
