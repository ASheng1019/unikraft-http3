#!/usr/bin/env python3
"""Native dual-stack H3 across a real Ethernet/IP link to a Linux KVM guest."""
from quic_fixture import result_file
import json,hashlib,time,shlex,argparse
from quic_fixture import FIXTURES,WORK,NativeService,certificates,config
from ethernet_fixture import EthernetLink,ClientVM

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--tx-burst',type=int,choices=range(1,9),default=1);p.add_argument('--name');a=p.parse_args()
    if a.name and not a.name.replace('-','').isalnum():p.error('invalid name')
    root=WORK/'build'/('wire-'+a.name if a.name else 'expanded-wire' if a.tx_burst==1 else 'burst-wire');certificates(root);link=EthernetLink();native=client=None
    result={'status':'FAIL','stage':'6B','cases':[],'validation_date':'2026-10-15','tx_burst':a.tx_burst}
    try:
        client=ClientVM(root,link)
        conf=config(8080,idle='10s',extra='frontend=fd00:1::2,4433;quic\nworker-frontend-connections=64\n')
        conf=conf.replace('log-level=NOTICE','log-level=INFO')
        conf=conf.replace('frontend=10.0.2.15,4433;quic','frontend=198.18.0.2,4433;quic').replace('backend=10.0.2.2,8080','backend=198.18.0.1,8080')
        runtime=b'control=198.18.0.2,4434\ndrain-seconds=10\nipv6-address=fd00:1::2\necn=yes\npmtud=yes\nmax-udp-payload=1452\n'
        if a.tx_burst!=1:runtime+=f'tx-burst={a.tx_burst}\n'.encode()
        native=NativeService(root,8080,tag='expanded',guest_address='198.18.0.2',static_cidr='198.18.0.2/24',wire=(link.native_port,link.to_native),file_overrides={'nghttpx.conf':conf.encode(),'native-runtime.conf':runtime})
        result['image_sha256']=hashlib.sha256(native.image.read_bytes()).hexdigest()
        client.run('mkdir -p /tmp/qlog')
        base='QLOGDIR=/tmp/qlog /curl --verbose --trace-config http/3 --http3-only --fail-with-body --cacert /ca.pem --noproxy "*" --silent --show-error --max-time 15'
        for family,addr in [(4,'198.18.0.2'),(6,'[fd00:1::2]')]:
            command=f'{base} --resolve localhost:4433:{addr} https://localhost:4433/get -o /tmp/get --write-out HTTP3:%{{http_version}}'
            code,out=client.run(command)
            (root/f'ipv{family}-client.log').write_text(out)
            if code or 'HTTP3:3' not in out:raise RuntimeError(f'IPv{family} request failed: {out}')
            body_code,body=client.run('cat /tmp/get')
            if body_code or body!='native-nghttpx-backend-ok\n':raise RuntimeError('small response content mismatch')
            result['cases'].append({'name':f'ipv{family}-h3','status':'PASS'});print(f'WIRE ipv{family}-h3 PASS',flush=True)
        ipv4_data = [r for r in link.records if r['direction'] == 'server'
                     and r['family'] == 4 and r['next'] == 17]
        if not ipv4_data or not all(r['df'] for r in ipv4_data):
            raise RuntimeError('QUIC IPv4 output must retain DF on every datagram')
        result['cases'].append({'name': 'ipv4-quic-df', 'status': 'PASS',
                                'datagrams': len(ipv4_data)})
        for mtu in [1500,1280,1500]:
            link.mtu=mtu;link.mark_ce=True
            start=len(link.records)
            command=f'{base} --resolve localhost:4433:[fd00:1::2] https://localhost:4433/download -o /tmp/download'
            code,out=client.run(command)
            if code:raise RuntimeError(f'IPv6 MTU{mtu} transfer failed: {out}')
            code,out=client.run('sha256sum /tmp/download')
            expected=hashlib.sha256(bytes(range(256))*1024).hexdigest()
            if code or not out.startswith(expected):raise RuntimeError('download content differs')
            packets=link.records[start:]
            result['cases'].append({'name':f'ipv6-mtu-{mtu}','status':'PASS','largest_server_ip_packet':max(x['length'] for x in packets if x['direction']=='server'),'oversize_drops':sum(x['dropped'] for x in packets),'ce_marks':sum(x.get('ce_marked',False) for x in packets)})
            print(f'WIRE ipv6-mtu-{mtu} PASS',flush=True)
        if not any(x.get('ce_marked') for x in link.records):raise RuntimeError('ECN path never exercised')
        if not any(x['dropped'] for x in link.records):raise RuntimeError('MTU path never dropped a probe')
        code,logs=client.run('cat /tmp/qlog/*',timeout=20)
        if code:raise RuntimeError('client qlog unavailable')
        (root/'client-qlog.jsonseq').write_text(logs)
        events=[json.loads(part) for part in logs.split('\x1e') if part.strip()]
        ack_frames=[frame for event in events for frame in event.get('data',{}).get('frames',[]) if frame.get('frame_type')=='ack']
        result['ecn_feedback']=[frame for frame in ack_frames if frame.get('ce',0)>0]
        if not result['ecn_feedback']:raise RuntimeError('no CE feedback in QUIC ACK frames')
        token=shlex.quote(native.token)
        code,out=client.run(f'printf %s {token} | /wire-control 198.18.0.2 4434')
        if code:raise RuntimeError('wire control datagram send failed')
        native.process.wait(timeout=12)
        if 'main returned 0' not in native.log_path.read_text():raise RuntimeError('wire native graceful stop failed')
        native.close();native=None
        (root/'dual-stack-native.log').write_bytes((root/'native-serial.log').read_bytes())
        # Wildcard sockets must reply from the packet's actual destination;
        # exercise ECN bleaching and the conservative 1200-byte fallback too.
        d=root/'wildcard';d.mkdir(exist_ok=True);d.chmod(0o700)
        for f in ['server.pem','server.key','ca.pem']:(d/f).write_bytes((root/f).read_bytes());(d/f).chmod(0o600)
        conf=conf.replace('frontend=198.18.0.2,4433;quic','frontend=0.0.0.0,4433;quic').replace('frontend=fd00:1::2,4433;quic','frontend=::,4433;quic')
        runtime=runtime.replace(b'pmtud=yes',b'pmtud=no').replace(b'max-udp-payload=1452',b'max-udp-payload=1200')
        link.mark_ce=False;link.bleach_ecn=True;link.mtu=1280
        native=NativeService(d,8080,tag='expanded',guest_address='198.18.0.2',static_cidr='198.18.0.2/24',wire=(link.native_port,link.to_native),file_overrides={'nghttpx.conf':conf.encode(),'native-runtime.conf':runtime})
        for family,addr in [(4,'198.18.0.2'),(6,'[fd00:1::2]')]:
            start=len(link.records)
            code,out=client.run(f'{base} --resolve localhost:4433:{addr} https://localhost:4433/download -o /tmp/download')
            if code:raise RuntimeError(f'wildcard IPv{family} request failed: {out}')
            code,out=client.run('sha256sum /tmp/download')
            if code or not out.startswith(expected):raise RuntimeError('wildcard body differs')
            packets=[r for r in link.records[start:] if r['direction']=='server' and r['family']==family and r.get('next')==17]
            if not any(r.get('bleached') for r in packets):raise RuntimeError('ECN bleaching not exercised')
            if not any(r['ecn']==0 and r['length']>1000 for r in packets):raise RuntimeError('ECN did not fall back to Not-ECT data')
            if any(r['dropped'] for r in packets):raise RuntimeError('1200-byte fallback exceeded path MTU')
            result['cases'].append({'name':f'wildcard-ipv{family}-ecn-fallback','status':'PASS','server_payload_limit':1200})
        code,_=client.run(f'printf %s {shlex.quote(native.token)} | /wire-control 198.18.0.2 4434')
        if code:raise RuntimeError('wildcard control send failed')
        native.process.wait(timeout=12)
        if 'main returned 0' not in native.log_path.read_text():raise RuntimeError('wildcard shutdown failed')
        result['status']='PASS';print('WIRE_NETWORK PASS',flush=True)
    except Exception as error:result['error']=str(error);raise
    finally:
        if native:native.close()
        if client:client.close()
        result['ipv6_control_packets']=[r for r in link.records if r['family']==6 and r.get('icmp_type')]
        result['packet_counts']={'total':len(link.records),'server_ecn':sum(x['direction']=='server' and x['ecn']!=0 for x in link.records),'df':sum(x.get('df',False) for x in link.records)}
        link.close();result_file('wire-network-results.json').write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':main()
