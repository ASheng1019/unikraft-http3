#!/usr/bin/env python3
"""Same QUIC connection and HTTP/3 session across relay source-port changes."""
from quic_fixture import result_file
import argparse,asyncio,json,ssl
from aioquic.asyncio import connect
from aioquic.quic.configuration import QuicConfiguration
from quic_fixture import FIXTURES,WORK,Backend,NativeService,certificates,load,SMALL,PAYLOAD
Client=load(FIXTURES/'interop-client.py').Client
async def run():
    root=WORK/'build/expanded-rebinding';certificates(root);backend=Backend();service=relay=None
    result={'status':'FAIL','stage':'6B','validation_date':'2026-10-15','changes':[]}
    try:
        service=NativeService(root,backend.port,tag='expanded')
        relay=load(FIXTURES/'udp-fault-relay.py').Relay(('127.0.0.1',service.front))
        config=QuicConfiguration(is_client=True,alpn_protocols=['h3'],server_name='localhost')
        config.load_verify_locations(cafile=str(root/'ca.pem'));config.verify_mode=ssl.CERT_REQUIRED
        async with connect('127.0.0.1',relay.port,configuration=config,create_protocol=Client) as client:
            if await client.request('/first')!=SMALL:raise RuntimeError('initial request mismatch')
            for index in range(3):
                mappings=relay.rebind()
                if not mappings or any(m['before']==m['after'] for m in mappings):raise RuntimeError('source port unchanged')
                if await client.request('/download')!=PAYLOAD:raise RuntimeError('post-rebind transfer mismatch')
                result['changes'].append(mappings)
        service.idle_stats();service.stop();result['status']='PASS';print('REBINDING PASS changes=3 same_connection=1',flush=True)
    except Exception as error:result['error']=str(error);raise
    finally:
        if relay:relay.close()
        if service:service.close()
        backend.close();result_file('rebinding-results.json').write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':asyncio.run(run())
