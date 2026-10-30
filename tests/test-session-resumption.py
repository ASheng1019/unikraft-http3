#!/usr/bin/env python3
"""Certificate-verified H3 ticket reuse, overlap rotation and stale-key fallback."""
from quic_fixture import result_file
import asyncio,json,secrets,ssl
from aioquic.asyncio import connect
from aioquic.quic.configuration import QuicConfiguration
from quic_fixture import FIXTURES,WORK,Backend,NativeService,certificates,config,load,SMALL
Client=load(FIXTURES/'interop-client.py').Client
async def main():
    root=WORK/'build/expanded-resumption';certificates(root);backend=Backend();service=None
    result={'status':'FAIL','stage':'6C','cases':[],'validation_date':'2026-10-15'}
    keys=[secrets.token_bytes(48),secrets.token_bytes(48)]
    def start(name,indices):
        d=root/name;d.mkdir(exist_ok=True);d.chmod(0o700)
        for f in ['server.pem','server.key','ca.pem']:(d/f).write_bytes((root/f).read_bytes());(d/f).chmod(0o600)
        extra=''.join(f'tls-ticket-key-file=/ticket-{i}.key\n' for i in indices)
        files={f'ticket-{i}.key':keys[i] for i in indices};files['nghttpx.conf']=config(backend.port,extra=extra).encode()
        return NativeService(d,backend.port,tag='expanded',file_overrides=files)
    async def exchange(ticket=None):
        tickets=[];c=QuicConfiguration(is_client=True,alpn_protocols=['h3'],server_name='localhost');c.load_verify_locations(cafile=str(root/'ca.pem'));c.verify_mode=ssl.CERT_REQUIRED;c.session_ticket=ticket
        async with connect('127.0.0.1',service.front,configuration=c,create_protocol=Client,session_ticket_handler=tickets.append) as client:
            if await client.request('/get')!=SMALL:raise RuntimeError('resumption body mismatch')
            for _ in range(20):
                if tickets:break
                await asyncio.sleep(.05)
            return client.session_resumed,tickets
    def record(name,resumed):
        result['cases'].append({'name':name,'status':'PASS','session_resumed':resumed});print('SESSION',name,'PASS',flush=True)
    try:
        service=start('initial',[0]);resumed,tickets=await exchange()
        if resumed or not tickets:raise RuntimeError('fresh handshake or ticket issuance failed')
        old=tickets[-1];record('fresh-ticket',resumed)
        resumed,_=await exchange(old)
        if not resumed:raise RuntimeError('same-key ticket not resumed')
        record('same-key-resume',resumed);service.stop();service.close();service=None
        service=start('rotation-overlap',[1,0]);resumed,tickets=await exchange(old)
        if not resumed or not tickets:raise RuntimeError('overlapping-key rotation did not resume')
        new=tickets[-1];record('rotation-overlap',resumed);service.stop();service.close();service=None
        service=start('rotation-new-only',[1]);resumed,_=await exchange(new)
        if not resumed:raise RuntimeError('new ticket did not survive rotation')
        record('new-key-resume',resumed)
        resumed,_=await exchange(old)
        if resumed:raise RuntimeError('removed ticket key still accepted')
        record('stale-ticket-full-handshake',resumed);service.stop();result['status']='PASS'
    except Exception as e:result['error']=str(e);raise
    finally:
        if service:service.close()
        backend.close();result_file('session-resumption-results.json').write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':asyncio.run(main())
