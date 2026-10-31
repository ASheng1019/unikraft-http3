"""Shared local fixtures for native regression and Linux VM measurements."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

FIXTURES = Path(__file__).resolve().parent
WORK = Path(os.environ["QUIC_TEST_OUTPUT"])
PREFIX = Path(os.environ["QUIC_TEST_CLIENT_PREFIX"])


def qemu_environment(root):
    """Select an isolated usernet runtime without changing host libraries."""
    selected = os.environ.get('QUIC_QEMU_SLIRP_DIR')
    if not selected:
        return None
    library = (Path(selected).resolve() / 'libslirp.so.0').resolve(strict=True)
    environment = os.environ.copy()
    environment['LD_PRELOAD'] = str(library) + (' ' + environment['LD_PRELOAD'] if environment.get('LD_PRELOAD') else '')
    (root / 'qemu-slirp.json').write_text(json.dumps({
        'path': str(library), 'sha256': hashlib.sha256(library.read_bytes()).hexdigest(),
        'scope': 'QEMU process only; explicit QUIC_QEMU_SLIRP_DIR override',
    }, indent=2) + '\n')
    return environment


def verify_qemu_environment(process, root):
    manifest = root / 'qemu-slirp.json'
    if not os.environ.get('QUIC_QEMU_SLIRP_DIR'):
        return
    runtime = json.loads(manifest.read_text())
    for _ in range(100):
        try:
            maps = Path(f'/proc/{process.pid}/maps').read_text()
        except FileNotFoundError:
            break
        if any(line.split()[-1] == runtime['path'] for line in maps.splitlines() if line.split()):
            runtime['loaded_verified'] = True
            manifest.write_text(json.dumps(runtime, indent=2) + '\n')
            return
        if process.poll() is not None:
            break
        time.sleep(.01)
    raise RuntimeError('selected libslirp was not observed in QEMU memory maps')


def result_file(name):
    """Keep later validation stages from overwriting the first-edition evidence."""
    directory=WORK / os.environ.get('QUIC_REPORT_DIR','.')
    if not directory.resolve().is_relative_to(WORK):raise ValueError('report directory outside workspace')
    directory.mkdir(parents=True,exist_ok=True)
    return directory / name

PAYLOAD = bytes(range(256)) * 1024
UPLOAD = bytes(range(256)) * 256
SMALL = b"native-nghttpx-backend-ok\n"


def load(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def free_udp():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def environment():
    return dict(os.environ, LD_LIBRARY_PATH=str(PREFIX / "lib"), OPENSSL_CONF="/dev/null")


def certificates(root):
    root.mkdir(parents=True, exist_ok=True)
    root.chmod(0o700)
    openssl = str(PREFIX / "bin/openssl")
    commands = [
        [openssl, "req", "-x509", "-newkey", "rsa:2048", "-noenc", "-days", "2",
         "-subj", "/CN=regression CA", "-addext", "basicConstraints=critical,CA:TRUE",
         "-keyout", str(root / "ca.key"), "-out", str(root / "ca.pem")],
        [openssl, "req", "-new", "-newkey", "rsa:2048", "-noenc", "-subj", "/CN=localhost",
         "-keyout", str(root / "server.key"), "-out", str(root / "server.csr")],
        [openssl, "x509", "-req", "-in", str(root / "server.csr"), "-CA", str(root / "ca.pem"),
         "-CAkey", str(root / "ca.key"), "-CAcreateserial", "-days", "2", "-sha256",
         "-extfile", str(root / "server.ext"), "-out", str(root / "server.pem")]]
    (root / "server.ext").write_text("subjectAltName=DNS:localhost\nbasicConstraints=critical,CA:FALSE\n"
                                   "keyUsage=critical,digitalSignature,keyEncipherment\n"
                                   "extendedKeyUsage=serverAuth\n")
    with (root / "cert.log").open("w") as log:
        for command in commands:
            subprocess.run(command, env=environment(), stdout=log, stderr=log, check=True)
    for path in root.glob("*.key"):
        path.chmod(0o600)


class Backend:
    def __init__(self, *, keepalive=False, tls_context=None, response=SMALL, tcp_nodelay=False):
        self.records = []
        records = self.records

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def setup(self):
                super().setup()
                if tcp_nodelay:
                    self.connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

            def respond(self):
                body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                records.append({"method": self.command, "path": self.path,
                                "version": self.request_version, "peer_port": self.client_address[1], "sni": getattr(self.connection,"test_sni",None), "bytes": len(body),
                                "sha256": hashlib.sha256(body).hexdigest()})
                if self.path == "/backend-reset":
                    self.close_connection = True
                    self.connection.shutdown(socket.SHUT_RDWR)
                    return
                if self.path == "/backend-timeout":
                    time.sleep(7)
                result = body if self.command == "POST" else PAYLOAD if self.path == "/download" else response
                self.send_response(200)
                self.send_header("Content-Length", str(len(result) + (100 if self.path == "/backend-truncated" else 0)))
                self.send_header("Connection", "keep-alive" if keepalive else "close")
                self.end_headers()
                if self.path in ("/slow", "/hold"):
                    time.sleep(10 if self.path == "/hold" else .8)
                try:
                    self.wfile.write(result)
                except (BrokenPipeError, ConnectionResetError):
                    pass
                self.close_connection = not keepalive

            do_GET = do_POST = respond

            def log_message(self, *args):
                pass

        class Server(ThreadingHTTPServer):
            # Sixteen simultaneous upstream streams must not overflow the
            # stdlib default backlog of five and confound VM measurements.
            request_queue_size = 128

        self.server = Server(("127.0.0.1", 0), Handler)
        if tls_context:
            self.server.socket = tls_context.wrap_socket(self.server.socket,server_side=True)
        self.server.daemon_threads = True
        self.port = self.server.server_port
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def config(backend_port, idle="2s", extra=""):
    return (f"frontend=10.0.2.15,4433;quic\nbackend=10.0.2.2,{backend_port}\n"
            "private-key-file=/server.key\ncertificate-file=/server.pem\nworkers=1\n"
            "single-process=yes\nsingle-thread=yes\nno-quic-bpf=yes\n"
            "errorlog-file=/dev/stderr\nlog-level=NOTICE\n"
            f"frontend-quic-idle-timeout={idle}\n" + extra)


class NativeService:
    def __init__(self, root, backend_port, *, instrumented=False, cpu=None, file_overrides=None,
                 tag="", guest_address="10.0.2.15", guest_port=4433, control_port=None,
                 connection_limit=16, static_cidr=None, drain_seconds=15, extra_config="", wire=None,
                 qemu_options=(), startup_timeout=15, network_fd=None, managed=True):
        self.root = root
        self.managed = managed
        self.front, self.control = free_udp(), free_udp()
        self.token = secrets.token_hex(32)
        select_fresh=tag=="expanded" and os.environ.get("QUIC_EXPANDED_FRESH")=="1"
        if tag=="expanded":tag=os.environ.get("QUIC_EXPANDED_TAG",tag)
        output = "arm64-nghttpx" + ("-" + tag if tag else "") + ("-instrumented" if instrumented else "")
        if select_fresh:output+="-fresh"
        self.image = Path(os.environ["QUIC_TEST_IMAGE"])
        self.log_path = root / "native-serial.log"
        self.log = self.log_path.open("w")
        control_port = control_port or (guest_port + 1)
        self.config = config(backend_port, extra=f"backend-read-timeout=5s\nbackend-connect-timeout=500ms\nworker-frontend-connections={connection_limit}\n" + extra_config)
        self.config = self.config.replace("frontend=10.0.2.15,4433;quic", f"frontend={guest_address},{guest_port};quic")
        files = {"nghttpx.conf": self.config.encode(), "server.pem": (root / "server.pem").read_bytes(),
                 "server.key": (root / "server.key").read_bytes(),
                 "native-epoch.txt": f"{int(time.time())}\n".encode()}
        if managed:
            files["native-control.token"] = (self.token+"\n").encode()
        if tag and managed:
            files["native-runtime.conf"] = f"control={guest_address},{control_port}\ndrain-seconds={drain_seconds}\n".encode()
        profile = os.environ.get('QUIC_NATIVE_RUNTIME_PROFILE')
        if profile is not None:
            if profile not in ['throughput', 'burst']:
                raise ValueError('unknown native runtime profile')
            profile_path = FIXTURES / 'profiles' / (profile + '-runtime.conf')
            # An explicit per-test runtime file retains precedence (e.g. an
            # ECN-only contract or MTU fault test). Record whether it won.
            files['native-runtime.conf'] = files.get('native-runtime.conf', b'') + profile_path.read_bytes()
        for name, data in (file_overrides or {}).items():
            if data is None:
                files.pop(name, None)
            else:
                files[name] = data
        if profile is not None:
            effective = files.get('native-runtime.conf', b'')
            (root / 'runtime-profile.json').write_text(json.dumps({
                'profile': profile,
                'profile_sha256': hashlib.sha256(profile_path.read_bytes()).hexdigest(),
                'applied': 'native-runtime.conf' not in (file_overrides or {}),
                'effective_runtime_sha256': hashlib.sha256(effective).hexdigest(),
                'network_options': [line for line in effective.decode().splitlines()
                    if line.startswith(('pmtud=', 'max-udp-payload=', 'ecn=', 'tx-burst='))]}, indent=2) + '\n')
        initrd = root / "native.cpio"
        initrd.write_bytes(filesystem_cpio({name:(data,0o100600) for name,data in files.items()}))
        initrd.chmod(0o600)
        self.command = ["qemu-system-aarch64", "-machine", "virt,gic-version=host", "-cpu", "host", "-accel", "kvm",
                        "-m", "768M", "-smp", "1", "-display", "none", "-monitor", "none", "-serial", "stdio",
                        "-no-reboot", "-kernel", str(self.image), "-initrd", str(initrd), "-netdev",
                        f"user,id=n0,host={guest_address.rsplit('.',1)[0]}.2,dhcpstart={guest_address},hostfwd=udp:127.0.0.1:{self.front}-{guest_address}:{guest_port},hostfwd=udp:127.0.0.1:{self.control}-{guest_address}:{control_port}",
                        "-device", "virtio-net-device,netdev=n0,csum=off,guest_csum=off,gso=off,host_tso4=off,host_tso6=off,host_ecn=off,host_ufo=off"]
        if wire:
            # QEMU transports complete Ethernet frames over local UDP. No TAP or host routes.
            index=self.command.index('-netdev')
            self.command[index+1]=f'socket,id=n0,udp=127.0.0.1:{wire[1]},localaddr=127.0.0.1:{wire[0]}'
        if static_cidr:
            self.command += ["-append", f"nghttpx netdev.ip={static_cidr}:{guest_address.rsplit('.',1)[0]}.{1 if wire else 2} --"]
        self.command += list(qemu_options)
        if network_fd is not None:
            if not wire: raise ValueError('inherited Ethernet socket requires wire configuration')
            self.command[self.command.index('-netdev')+1] = f'socket,id=n0,fd={network_fd}'
        crypto_mask=os.environ.get('QUIC_GUEST_OPENSSL_ARMCAP')
        if crypto_mask is not None:
            mask=int(crypto_mask,0)
            if not 0<=mask<=0xffffffff:raise ValueError('guest OpenSSL deny mask outside uint32')
            parameter=f'env.vars=[OPENSSL_armcap={mask}]'
            if '-append' in self.command:
                index=self.command.index('-append')+1
                self.command[index]=self.command[index].replace(' --',f' {parameter} --',1)
            else:self.command+=['-append',f'nghttpx {parameter} --']
            (root/'guest-crypto-mask.json').write_text(json.dumps({'deny_mask':mask})+'\n')
        if cpu is not None:
            self.command = ["taskset", "-c", str(cpu)] + self.command
        self.started = time.monotonic()
        self.process = subprocess.Popen(self.command, stdout=self.log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                        pass_fds=() if network_fd is None else (network_fd,),
                                        env=qemu_environment(root))
        try:
            verify_qemu_environment(self.process, root)
        except Exception:
            self.close()
            raise
        for _ in range(int(startup_timeout*10)):
            if "NATIVE_NGHTTPX READY" in self.log_path.read_text():
                return
            if self.process.poll() is not None:
                self.close()
                raise RuntimeError("native service failed during startup")
            time.sleep(.1)
        self.close()
        raise RuntimeError("native readiness timed out")

    def stats(self):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(2)
            sock.sendto(b"STATS " + self.token.encode(), ("127.0.0.1", self.control))
            return json.loads(sock.recv(1024))

    def idle_stats(self, timeout=20):
        until = time.monotonic() + timeout
        while time.monotonic() < until:
            result = self.stats()
            if result["connections"] == result["close_waits"] == 0:
                time.sleep(.1)
                return self.stats()
            time.sleep(.25)
        raise RuntimeError("native connections did not drain")

    def stop(self):
        if not self.managed:
            raise RuntimeError("unmanaged guests require host-side teardown")
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.sendto(self.token.encode(), ("127.0.0.1", self.control))
        code = self.process.wait(timeout=25)
        if code or "main returned 0" not in self.log_path.read_text():
            raise RuntimeError("native graceful stop failed")

    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        self.log.close()


def request(root, port, path="/get", *, body=None, timeout=15, extra=(), label="request", client_cpu=None):
    destination = root / (label + ".body")
    headers = root / (label + ".headers")
    destination.unlink(missing_ok=True)
    headers.unlink(missing_ok=True)
    command = [str(PREFIX / "bin/curl"), "--http3-only", "--silent", "--show-error", "--noproxy", "*",
               "--cacert", str(root / "ca.pem"), "--resolve", f"localhost:{port}:127.0.0.1",
               "--max-time", str(timeout), "--output", str(destination), "--dump-header", str(headers),
               "--write-out", "%{http_code} %{time_total}", *extra]
    if body is not None:
        source = root / (label + ".upload")
        source.write_bytes(body)
        command += ["--data-binary", "@" + str(source)]
    command += [f"https://localhost:{port}{path}"]
    if client_cpu is not None:
        command = ["taskset", "-c", str(client_cpu)] + command
    result = subprocess.run(command, env=environment(), capture_output=True, timeout=timeout + 3)
    (root / (label + ".client.log")).write_bytes(result.stderr)
    metadata = result.stdout.decode().split()
    return {"exit": result.returncode, "http_status": int(metadata[0]) if metadata else 0,
            "seconds": float(metadata[1]) if len(metadata) > 1 else 0,
            "body": destination.read_bytes() if destination.exists() else b""}


def require_body(result, expected):
    if result["exit"] or result["http_status"] != 200 or result["body"] != expected:
        raise RuntimeError(f"H3 request failed exit={result['exit']} HTTP={result['http_status']} bytes={len(result['body'])}")


def filesystem_cpio(files):
    """Minimal newc writer with explicit directories and regular-file permissions."""
    entries = {}
    for name, (data, mode) in files.items():
        for parent in Path(name).parents:
            if str(parent) != '.':
                entries.setdefault(str(parent), (b'', 0o40755))
        entries[name] = (data, mode)
    entries['TRAILER!!!'] = (b'', 0)
    output = bytearray()
    for inode, (name, (data, mode)) in enumerate(entries.items(), 1):
        encoded = name.encode() + b'\0'
        fields = [inode, mode, 0, 0, 1, 0, len(data), 0, 0, 0, 0, len(encoded), 0]
        output += b'070701' + ''.join(f'{n:08x}' for n in fields).encode() + encoded
        output += b'\0' * (-len(output) % 4)
        output += data
        output += b'\0' * (-len(output) % 4)
    return bytes(output)

