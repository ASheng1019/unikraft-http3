#!/usr/bin/env python3
"""6C native DNS, persistent/failing pools, and verified TLS/H2 backends."""
from quic_fixture import result_file
import json,socket,ssl,struct,threading,time,subprocess,re
from concurrent.futures import ThreadPoolExecutor
from quic_fixture import FIXTURES,WORK,PREFIX,NativeService,Backend,certificates,config,request,require_body,SMALL,PAYLOAD,environment

class DNS:
    def __init__(self):
        self.mode='address';self.address='10.0.2.2';self.queries=[];self.running=True
        self.sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);self.sock.bind(('127.0.0.1',0));self.sock.settimeout(.2);self.port=self.sock.getsockname()[1]
        self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start()
    def run(self):
        while self.running:
            try:data,peer=self.sock.recvfrom(4096)
            except socket.timeout:continue
            except OSError:break
            if len(data)<17:continue
            end=12
            while end<len(data) and data[end]:end+=1+data[end]
            if end+5>len(data):continue
            end+=5;kind=int.from_bytes(data[end-4:end-2],'big');self.queries.append({'type':kind,'mode':self.mode,'address':self.address})
            if self.mode=='drop':continue
            answer=b''
            if kind==1 and self.mode=='address':answer=b'\xc0\x0c'+struct.pack('!HHIH',1,1,0,4)+socket.inet_aton(self.address)
            flags=0x8183 if self.mode=='nxdomain' else 0x8180
            message=data[:2]+struct.pack('!HHHHH',flags,1,int(bool(answer)),0,0)+data[12:end]+answer
            self.sock.sendto(message,peer)
    def close(self):
        self.running=False;self.thread.join(1);self.sock.close()

def main():
    root=WORK/'build/expanded-proxy';certificates(root);service=None;backends=[];dns=DNS();h2=None;h2log=None
    result={'status':'FAIL','stage':'6C','cases':[],'validation_date':'2026-10-15'}
    def directory(name):
        d=root/name;d.mkdir(exist_ok=True);d.chmod(0o700)
        for f in ['ca.pem','server.pem','server.key']:(d/f).write_bytes((root/f).read_bytes());(d/f).chmod(0o600)
        return d
    def start(name,backend,extra='',files=None):
        d=directory(name);c=config(backend.port,extra='backend-read-timeout=1s\nbackend-connect-timeout=300ms\n'+extra)
        overrides={'nghttpx.conf':c.encode(),**(files or {})}
        return NativeService(d,backend.port,tag='expanded',file_overrides=overrides)
    def finish(name,**details):
        nonlocal service
        service.stop();service.close();service=None
        result['cases'].append({'name':name,'status':'PASS',**details});print('PROXY',name,'PASS',flush=True)
    try:
        b=Backend(keepalive=True);backends.append(b);service=start('h1-keepalive',b)
        for i in range(5):require_body(request(service.root,service.front,label=f'reuse-{i}'),SMALL)
        ports={r['peer_port'] for r in b.records}
        if len(ports)!=1:raise RuntimeError(f'backend connection not reused: {ports}')
        finish('h1-keepalive',requests=5,connections=len(ports))
        b2=Backend(response=b'backend-two\n');backends.append(b2)
        service=start('multiple-backends',b,extra=f'backend=10.0.2.2,{b2.port}\n')
        bodies=[request(service.root,service.front,label=f'pool-{i}')['body'] for i in range(8)]
        if set(bodies)!={SMALL,b'backend-two\n'}:raise RuntimeError('both backends not selected')
        b2.close();backends.remove(b2)
        for i in range(8):
            r=request(service.root,service.front,label=f'failover-{i}')
            if r['http_status']==200 and r['body']!=SMALL:raise RuntimeError('unexpected failover body')
        require_body(request(service.root,service.front,label='pool-recovered'),SMALL)
        finish('multiple-backends-and-failure',observed_bodies=2)
        ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);ctx.load_cert_chain(root/'server.pem',root/'server.key');ctx.set_alpn_protocols(['http/1.1'])
        def sni(sock,name,_):sock.test_sni=name
        ctx.set_servername_callback(sni)
        tls=Backend(keepalive=True,tls_context=ctx);backends.append(tls)
        for name,sni_name,ca,expected in [('https-verified','localhost',(root/'ca.pem').read_bytes(),200),('https-wrong-name','wrong.test',(root/'ca.pem').read_bytes(),502),('https-wrong-ca','localhost',None,502)]:
            if ca is None:
                other=directory('other-ca');certificates(other);ca=(other/'ca.pem').read_bytes()
            d=directory(name);conf=config(tls.port,extra='cacert=/backend-ca.pem\nbackend-connect-timeout=500ms\n').replace(f'backend=10.0.2.2,{tls.port}',f'backend=10.0.2.2,{tls.port};;tls;sni={sni_name}')
            service=NativeService(d,tls.port,tag='expanded',file_overrides={'nghttpx.conf':conf.encode(),'backend-ca.pem':ca})
            r=request(d,service.front,label=name)
            if r['exit'] or r['http_status']!=expected:raise RuntimeError(f'{name} status {r}')
            if expected==200:require_body(r,SMALL)
            finish(name,status=expected)
        if not any(r['sni']=='localhost' for r in tls.records):raise RuntimeError('backend SNI not observed')
        # Real nghttpd HTTP/2 TLS origin, with parallel H3 requests translated to h2 streams.
        d=directory('h2-backend');www=d/'www';www.mkdir(exist_ok=True);(www/'get').write_bytes(SMALL);(www/'download').write_bytes(PAYLOAD)
        with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        h2log=(d/'h2.log').open('w');h2=subprocess.Popen([str(PREFIX/'bin/nghttpd'),'-v','-a','127.0.0.1','-d',str(www),str(port),str(root/'server.key'),str(root/'server.pem')],env=environment(),stdout=h2log,stderr=subprocess.STDOUT)
        time.sleep(.2)
        conf=config(port,extra='cacert=/backend-ca.pem\n').replace(f'backend=10.0.2.2,{port}',f'backend=10.0.2.2,{port};;tls;sni=localhost;proto=h2')
        service=NativeService(d,port,tag='expanded',file_overrides={'nghttpx.conf':conf.encode(),'backend-ca.pem':(root/'ca.pem').read_bytes()})
        with ThreadPoolExecutor(max_workers=4) as pool:
            responses=list(pool.map(lambda i:request(d,service.front,'/download',label=f'h2-{i}'),range(8)))
        for r in responses:require_body(r,PAYLOAD)
        h2log.flush();log=(d/'h2.log').read_text()
        if 'recv HEADERS frame' not in log or 'h2' not in log:raise RuntimeError('HTTP/2 origin protocol not evidenced')
        streams=re.findall(r'\[id=(\d+)\].*recv HEADERS frame.*stream_id=(\d+)',log)
        if len({stream for connection,stream in streams if connection=='1'})<8:raise RuntimeError('H2 backend streams did not share one connection')
        finish('https-h2-parallel',requests=8,origin_connections=len({connection for connection,stream in streams}),stream_ids=[int(stream) for _,stream in streams])
        h2.terminate();h2.wait(timeout=3);h2=None;h2log.close();h2log=None
        # c-ares consumes an explicit initrd resolver; no host resolver is used.
        for mode in ['address','drop','nxdomain','address-change','cancel']:
            dns.mode='address' if mode=='address-change' else 'drop' if mode=='cancel' else mode;dns.address='10.0.2.99' if mode=='address-change' else '10.0.2.2'
            name='dns-'+mode;d=directory(name);extra='dns-cache-timeout=100ms\ndns-lookup-timeout=100ms\ndns-max-try=1\nbackend-connect-timeout=200ms\n'
            conf=config(b.port,extra=extra).replace(f'backend=10.0.2.2,{b.port}',f'backend=backend.test,{b.port};;dns')
            service=NativeService(d,b.port,tag='expanded',file_overrides={'nghttpx.conf':conf.encode(),'etc/resolv.conf':f'nameserver 10.0.2.2:{dns.port}\n'.encode()})
            before=len(dns.queries);r=request(d,service.front,label='dns-first',timeout=.05 if mode=='cancel' else 5)
            expected=200 if mode=='address' else 504 if mode=='address-change' else 0 if mode=='cancel' else 502
            if (mode=='cancel' and r['exit']!=28) or (mode!='cancel' and (r['exit'] or r['http_status']!=expected)):raise RuntimeError(f'{name} first request: {r}')
            if mode=='address':require_body(r,SMALL)
            if len(dns.queries)==before:raise RuntimeError('DNS query not observed')
            if mode in ['drop','nxdomain','address-change','cancel']:
                dns.mode='address';dns.address='10.0.2.2';time.sleep(.5)
                # Failed backend recovery backoff is upstream behavior; allow it to expire.
                for attempt in range(8):
                    r=request(d,service.front,label=f'dns-recover-{attempt}',timeout=5)
                    if r['http_status']==200:break
                    time.sleep(.5)
                require_body(r,SMALL)
            finish(name,queries=len(dns.queries)-before,first_status=expected)
        result['status']='PASS'
    except Exception as error:result['error']=str(error);raise
    finally:
        if service:service.close()
        if h2:h2.terminate();h2.wait(timeout=3)
        if h2log:h2log.close()
        for b in backends:b.close()
        dns.close();result['dns_queries']=dns.queries;result_file('proxy-capabilities-results.json').write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':main()
