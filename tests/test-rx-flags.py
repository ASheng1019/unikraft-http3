#!/usr/bin/env python3
"""Inject real recvmsg truncation flags; ensure no flagged input reaches QUIC."""
import hashlib
import json
from quic_fixture import WORK, NativeService, Backend, certificates, request, require_body, SMALL, PAYLOAD


def main():
    root = WORK / 'build/rx-flags'
    root.mkdir(mode=0o700)
    certificates(root)
    backend = Backend(keepalive=True, tcp_nodelay=True)
    native = None
    result = dict(status='FAIL', scope='test-only recvmsg flags/parser guard; production libraries')
    try:
        native = NativeService(root, backend.port, tag='standard')
        result['image_sha256'] = hashlib.sha256(native.image.read_bytes()).hexdigest()
        require_body(request(root, native.front, '/download', label='large'), PAYLOAD)
        require_body(request(root, native.front, label='next'), SMALL)
        native.stop()
        assert 'TEST_RX_FLAGS PASS skipped=2 parser_calls=0' in native.log_path.read_text()
        result.update(status='PASS', flags=['MSG_TRUNC', 'MSG_CTRUNC'],
                      flagged_input_delivered_to_parser=False, large_and_next_response=True,
                      graceful_shutdown=True)
        print('STANDARD_RX_FLAGS PASS skipped=2 parser_calls=0', flush=True)
    finally:
        if native:
            native.close()
        backend.close()
        (WORK / 'rx-flags-results.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
