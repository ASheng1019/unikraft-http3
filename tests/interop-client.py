#!/usr/bin/env python3
"""Independent aioquic HTTP/3 client; certificate validation is mandatory."""
import argparse
import asyncio
import hashlib
import json
import ssl
from aioquic.asyncio import QuicConnectionProtocol, connect
from aioquic.h3.connection import H3_ALPN, H3Connection
from aioquic.h3.events import DataReceived, HeadersReceived
from aioquic.quic.configuration import QuicConfiguration
from aioquic.quic.events import ConnectionTerminated, HandshakeCompleted
from aioquic.quic.packet import QuicProtocolVersion


class Client(QuicConnectionProtocol):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.http = H3Connection(self._quic)
        self.pending = {}
        self.alpn = None
        self.session_resumed = False

    def quic_event_received(self, event):
        if isinstance(event, HandshakeCompleted):
            self.alpn = event.alpn_protocol
            self.session_resumed = event.session_resumed
        if isinstance(event, ConnectionTerminated):
            for future, _, _ in self.pending.values():
                if not future.done():
                    future.set_exception(ConnectionError(event.reason_phrase))
        for item in self.http.handle_event(event):
            if isinstance(item, (HeadersReceived, DataReceived)) and item.stream_id in self.pending:
                future, headers, body = self.pending[item.stream_id]
                if isinstance(item, HeadersReceived):
                    headers.update(item.headers)
                else:
                    body.extend(item.data)
                if item.stream_ended and not future.done():
                    future.set_result((headers, bytes(body)))

    async def request(self, path, body=None):
        stream_id = self._quic.get_next_available_stream_id()
        future = asyncio.get_running_loop().create_future()
        self.pending[stream_id] = (future, {}, bytearray())
        headers = [(b":method", b"POST" if body is not None else b"GET"),
                   (b":scheme", b"https"), (b":authority", b"localhost"),
                   (b":path", path.encode())]
        if body is not None:
            headers.append((b"content-length", str(len(body)).encode()))
        self.http.send_headers(stream_id, headers, end_stream=body is None)
        if body is not None:
            self.http.send_data(stream_id, body, end_stream=True)
        self.transmit()
        try:
            result = await asyncio.wait_for(future, timeout=15)
            if result[0].get(b":status") != b"200":
                raise RuntimeError(f"HTTP error: {result[0]}")
            return result[1]
        finally:
            self.pending.pop(stream_id, None)


async def run(args):
    config = QuicConfiguration(is_client=True, alpn_protocols=H3_ALPN,
                               server_name=args.server_name, max_datagram_size=1200,
                               supported_versions=[QuicProtocolVersion.VERSION_1])
    config.verify_mode = ssl.CERT_REQUIRED
    config.load_verify_locations(cafile=args.ca)
    async with connect("127.0.0.1", args.port, configuration=config,
                       create_protocol=Client) as client:
        upload = bytes(range(256)) * 256
        responses = await asyncio.gather(client.request("/download"),
                                         client.request("/upload", upload),
                                         *(client.request(f"/interop/{i}") for i in range(4)))
        expected = [bytes(range(256)) * 1024, upload] + [b"native-nghttpx-backend-ok\n"] * 4
        if responses != expected or client.alpn != "h3":
            raise RuntimeError("HTTP/3 content or ALPN mismatch")
        return {"status": "PASS", "implementation": "aioquic", "version": "1.3.0",
                "alpn": client.alpn, "quic_version": "v1", "certificate_verification": "required",
                "connection_count": 1, "streams": len(responses),
                "body_bytes": list(map(len, responses)),
                "body_sha256": [hashlib.sha256(body).hexdigest() for body in responses]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--ca", required=True)
    parser.add_argument("--server-name", default="localhost")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run(args))))


if __name__ == "__main__":
    main()
