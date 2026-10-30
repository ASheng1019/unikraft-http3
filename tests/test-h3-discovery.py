#!/usr/bin/env python3
"""An HTTPS origin advertises native H3; curl discovers it through Alt-Svc."""
from quic_fixture import result_file
import json,ssl,subprocess,threading,time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from quic_fixture import FIXTURES,WORK,PREFIX,Backend,NativeService,certificates,environment,SMALL

def main():
    root=WORK/'build/expanded-discovery';certificates(root);backend=Backend();native=origin=None
    result={'status':'FAIL','stage':'6A','validation_date':time.strftime('%Y-%m-%d')}
    (root/'alt-svc.cache').unlink(missing_ok=True)
    try:
        native=NativeService(root,backend.port,tag='expanded')
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200);self.send_header('Alt-Svc',f'h3=":{native.front}"; ma=60');self.send_header('Content-Length','9');self.end_headers();self.wfile.write(b'bootstrap')
            def log_message(self,*args):pass
        origin=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);ctx.load_cert_chain(root/'server.pem',root/'server.key')
        origin.socket=ctx.wrap_socket(origin.socket,server_side=True);threading.Thread(target=origin.serve_forever,daemon=True).start()
        command=[str(PREFIX/'bin/curl'),'--silent','--show-error','--noproxy','*','--cacert',str(root/'ca.pem'),'--alt-svc',str(root/'alt-svc.cache'),'--max-time','10','--resolve',f'localhost:{origin.server_port}:127.0.0.1','--resolve',f'localhost:{native.front}:127.0.0.1']
        url=f'https://localhost:{origin.server_port}/discovery'
        first=subprocess.run(command+[url],env=environment(),capture_output=True,timeout=12)
        if first.returncode or first.stdout!=b'bootstrap':raise RuntimeError('HTTPS discovery response failed')
        second=subprocess.run(command+['--http3','--write-out','\n%{http_version}',url],env=environment(),capture_output=True,timeout=12)
        (root/'client.log').write_bytes(second.stderr)
        if second.returncode or second.stdout!=SMALL+b'\n3':raise RuntimeError('client did not discover and use native H3')
        result.update(status='PASS',discovery='HTTPS Alt-Svc',http_version='3',native_image=str(native.image))
        native.stop();print('H3_DISCOVERY PASS verified_CA=1 forced_http3_only=0',flush=True)
    except Exception as error:result['error']=str(error);raise
    finally:
        if native:native.close()
        if origin:origin.shutdown();origin.server_close()
        backend.close();result_file('discovery-results.json').write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':main()
