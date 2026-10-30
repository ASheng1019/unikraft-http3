#!/usr/bin/env python3
"""Check the default build still serves H3 and rejects experimental TX options."""
import hashlib
import json
import shutil
import argparse
from quic_fixture import FIXTURES,WORK, Backend, NativeService, certificates, request, require_body, SMALL, PAYLOAD


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--tag',default='txdefault');p.add_argument('--name')
    a=p.parse_args()
    if not a.tag.isalnum() or (a.name and not a.name.replace('-','').isalnum()):p.error('invalid name/tag')
    root=WORK/'build'/('default-tx-'+a.name if a.name else 'default-tx-contract')
    if root.exists():raise RuntimeError('default TX output already exists')
    root.mkdir(mode=0o700);certificates(root)
    backend=Backend(keepalive=True,tcp_nodelay=True);service=None
    result={'status':'FAIL'}
    try:
        overrides={'native-runtime.conf':b'control=10.0.2.15,4434\n'} if a.name else None
        service=NativeService(root,backend.port,tag=a.tag,instrumented=False,file_overrides=overrides)
        result['image_sha256']=hashlib.sha256(service.image.read_bytes()).hexdigest()
        require_body(request(root,service.front,label='small'),SMALL)
        require_body(request(root,service.front,'/download',label='large'),PAYLOAD)
        service.stop();service.close();service=None
        rejected=root/'rejected';rejected.mkdir(mode=0o700)
        for name in ['ca.pem','server.pem','server.key']:shutil.copyfile(root/name,rejected/name)
        try:
            service=NativeService(rejected,backend.port,tag=a.tag,instrumented=False,
                file_overrides={'native-runtime.conf':b'control=10.0.2.15,4434\ntx-burst=8\n'})
        except RuntimeError:
            log=(rejected/'native-serial.log').read_text()
            expected=('FAIL boot time/control configuration' in log and 'main returned 1' in log) if a.name else 'RUNTIME rejected key=tx-burst' in log
            if not expected:raise
        else:raise RuntimeError('default build enabled the experimental TX option')
        result['default_rejects_experimental_option']=True
        result['status']='PASS';print('DEFAULT_TX_CONTRACT PASS',flush=True)
    except Exception as e:result['error']=repr(e);raise
    finally:
        if service:service.close()
        backend.close();(WORK/('default-tx-'+a.name+'-results.json' if a.name else 'default-tx-contract-results.json')).write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':main()
