#!/usr/bin/env python3
import argparse,asyncio,ssl
from aioquic.asyncio import connect
from aioquic.quic.configuration import QuicConfiguration
from quic_fixture import FIXTURES,WORK,load
Client=load(FIXTURES/"interop-client.py").Client
async def main(args):
    config=QuicConfiguration(is_client=True,alpn_protocols=['h3'],server_name='localhost')
    config.load_verify_locations(cafile=args.ca);config.verify_mode=ssl.CERT_REQUIRED
    async with connect('127.0.0.1',args.port,configuration=config,create_protocol=Client) as client:
        task=asyncio.create_task(client.request('/hold'))
        await asyncio.sleep(.2)
        print('CONNECTED',flush=True)
        try:await asyncio.sleep(30)
        finally:
            task.cancel();await asyncio.gather(task,return_exceptions=True)
p=argparse.ArgumentParser();p.add_argument('--port',type=int,required=True);p.add_argument('--ca',required=True)
asyncio.run(main(p.parse_args()))
