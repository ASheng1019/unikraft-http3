#!/usr/bin/env python3
"""Stage 6A: same-image deployment configurations and bounded shutdown."""
from quic_fixture import result_file
import hashlib, json, socket, subprocess, time, select
from quic_fixture import FIXTURES,WORK, NativeService, Backend, certificates, request, require_body, SMALL


def main():
    root=WORK/'build/expanded-deployment';certificates(root);backend=Backend();service=None
    result={'status':'FAIL','stage':'6A','cases':[],'validation_date':'2026-10-15'}
    def directory(name):
        d=root/name;d.mkdir(exist_ok=True);d.chmod(0o700)
        for p in ['server.pem','server.key','ca.pem']:
            (d/p).write_bytes((root/p).read_bytes());(d/p).chmod(0o600 if p.endswith('.key') else 0o644)
        return d
    def record(name,**details):
        result['cases'].append({'name':name,'status':'PASS',**details});print(f'DEPLOYMENT {name} PASS',flush=True)
    try:
        hashes=set()
        for name,options in [('dhcp-default',{}),('dhcp-other-address',{'guest_address':'10.0.2.25','guest_port':8443,'control_port':9444,'connection_limit':32}),('static-address',{'guest_address':'10.0.2.35','guest_port':9443,'control_port':9445,'connection_limit':8,'static_cidr':'10.0.2.35/24'})]:
            d=directory(name);service=NativeService(d,backend.port,tag='expanded',**options)
            if options.get('static_cidr') and 'DHCP configuration' in service.log_path.read_text():raise RuntimeError('static case used DHCP')
            hashes.add(hashlib.sha256(service.image.read_bytes()).hexdigest())
            require_body(request(d,service.front,label='get'),SMALL)
            service.idle_stats();service.stop();service.close();service=None
            record(name,options=options)
        if len(hashes)!=1:raise RuntimeError('configurations did not use the same image')
        result['image_sha256']=hashes.pop()
        for name,overrides in [('zero-limit',{'nghttpx.conf':None}),('invalid-token',{'native-boot.txt':f'{int(time.time())} '.encode()+b'z'*64+b'\n'}),('trailing-boot-data',{'native-boot.txt':f'{int(time.time())} '.encode()+b'a'*64+b' extra\n'}),('invalid-drain',{'native-runtime.conf':b'drain-seconds=0\n'})]:
            d=directory(name)
            if name=='zero-limit':
                from quic_fixture import config
                overrides={'nghttpx.conf':config(backend.port,extra='worker-frontend-connections=0\n').encode()}
            try:service=NativeService(d,backend.port,tag='expanded',file_overrides=overrides)
            except RuntimeError:
                log=(d/'native-serial.log').read_text()
                if 'NATIVE_NGHTTPX READY' in log or 'main returned 1' not in log:raise
                record('reject-'+name)
            else:raise RuntimeError('invalid deployment accepted')
            finally:
                if service:service.close();service=None
        # A long-lived H3 client stays connected while the VM is asked to stop.
        d=directory('bounded-drain');service=NativeService(d,backend.port,tag='expanded',drain_seconds=1)
        client=subprocess.Popen([__import__('sys').executable,str(FIXTURES/'hold-quic-connection.py'),'--port',str(service.front),'--ca',str(d/'ca.pem')],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        try:
            if not select.select([client.stdout],[],[],5)[0] or client.stdout.readline().strip()!=b'CONNECTED':raise RuntimeError('held connection failed')
            started=time.monotonic()
            with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:sock.sendto(service.token.encode(),('127.0.0.1',service.control))
            service.process.wait(timeout=4)
            elapsed=time.monotonic()-started;log=service.log_path.read_text()
            if 'DRAIN_DEADLINE' not in log or not .9<=elapsed<4:raise RuntimeError('shutdown deadline not enforced')
            record('bounded-drain',elapsed_seconds=elapsed)
        finally:
            client.terminate();client.communicate(timeout=3)
        service.close();service=None;result['status']='PASS'
    except Exception as error:result['error']=str(error);raise
    finally:
        if service:service.close()
        backend.close();result_file('deployment-results.json').write_text(json.dumps(result,indent=2)+'\n')

if __name__=='__main__':main()
