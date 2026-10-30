#!/usr/bin/env python3
"""Large-body HTTP/HTTPS closure, truncation, reset and timeout recovery.
Ordinary image: validates content, failure propagation and subsequent recovery;
internal buffer occupancy requires a separate instrumented build.
"""
import os,hashlib,json,re,socket,ssl,struct,threading,time
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from quic_fixture import FIXTURES,WORK,NativeService,certificates,config,request,require_body,PAYLOAD,SMALL
class Origin(ThreadingHTTPServer):
 request_queue_size=128;daemon_threads=True
class Handler(BaseHTTPRequestHandler):
 protocol_version='HTTP/1.1'
 def do_GET(self):
  kind=self.path.strip('/')
  if kind=='get':body=SMALL;declared=len(body)
  else:body=PAYLOAD;declared=len(body)*(2 if kind in ['truncated','timeout','reset'] else 1)
  self.send_response(200);self.send_header('Content-Length',str(declared));self.send_header('Connection','close');self.end_headers()
  try:self.wfile.write(body);self.wfile.flush()
  except (BrokenPipeError,ConnectionResetError):self.close_connection=True;return
  if kind in ['truncated','reset']:time.sleep(.2)
  if kind=='timeout':time.sleep(1)
  if kind=='reset':self.connection.setsockopt(socket.SOL_SOCKET,socket.SO_LINGER,struct.pack('ii',1,0))
  self.close_connection=True
 def log_message(self,*args):pass

def main():
 root=WORK/'build/backend-faults';assert not root.exists();certificates(root);out={'status':'FAIL','cases':[]};services=[];origins=[]
 try:
  for tls in [False,True]:
   b=Origin(('127.0.0.1',0),Handler);origins.append(b)
   if tls:
    ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);ctx.load_cert_chain(root/'server.pem',root/'server.key');ctx.set_alpn_protocols(['http/1.1']);b.socket=ctx.wrap_socket(b.socket,server_side=True)
   t=threading.Thread(target=b.serve_forever,daemon=True);t.start()
   for kind in ['large-close-churn','truncated','reset','timeout']:
    name=('tls-' if tls else 'clear-')+kind;p=root/name;certificates(p)
    conf=config(b.server_port,extra='backend-read-timeout=300ms\nbackend-connect-timeout=500ms\n')
    files={}
    if tls:conf=conf.replace(f'backend=10.0.2.2,{b.server_port}',f'backend=10.0.2.2,{b.server_port};;tls;sni=localhost')+'cacert=/backend-ca.pem\n';files['backend-ca.pem']=(root/'ca.pem').read_bytes()
    files['nghttpx.conf']=conf.encode();s=NativeService(p,b.server_port,tag='m4c1',file_overrides=files);services.append(s);response_info=[]
    if kind=='large-close-churn':
     with ThreadPoolExecutor(max_workers=4) as pool:
      for r in pool.map(lambda i:request(p,s.front,'/normal',label=f'close-{i}',timeout=8),range(128)):require_body(r,PAYLOAD)
    else:
     for i in range(3):
      r=request(p,s.front,'/'+kind,label=f'fault-{i}',timeout=4)
      assert r['exit'] not in [0,28] and r['http_status']==200 and r['body']==PAYLOAD,(name,r['exit'],r['http_status'],len(r['body']))
      response_info.append({'exit':r['exit'],'http_status':r['http_status'],'body_bytes':len(r['body']),'body_sha256':hashlib.sha256(r['body']).hexdigest()})
      require_body(request(p,s.front,label=f'recovery-{i}',timeout=5),SMALL)
    stat=s.idle_stats();assert not stat['connections'] and not stat['close_waits'];assert stat['enomem'] in (-1,0);s.stop();s.close();services.remove(s)
    out['cases'].append({'name':name,'status':'PASS','large_close_requests':128 if kind=='large-close-churn' else 0,'faults':response_info,'highwater_checks':'not instrumented; functional recovery only','idle':stat});print('BACKEND_FAULTS',name,'PASS',flush=True)
  out['status']='PASS'
 except Exception as e:out['error']=str(e);raise
 finally:
  for s in services:s.close()
  for b in origins:b.shutdown();b.server_close()
  out['image_sha256']=hashlib.sha256(__import__('pathlib').Path(os.environ['QUIC_TEST_IMAGE']).read_bytes()).hexdigest();(WORK/'backend-fault-results.json').write_text(json.dumps(out,indent=2)+'\n')
if __name__=='__main__':main()
