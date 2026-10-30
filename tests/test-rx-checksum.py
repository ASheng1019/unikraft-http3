#!/usr/bin/env python3
"""Real adapter red/green: corrupted authenticated control datagrams must drop."""
import argparse,hashlib,json,socket,struct,time
from pathlib import Path
from quic_fixture import WORK,NativeService,certificates

def checksum(data):
 if len(data)%2:data+=b'\0'
 n=sum(struct.unpack('!%dH'%(len(data)//2),data))
 while n>>16:n=(n&65535)+(n>>16)
 return (~n)&65535

def frame(payload,bad=None,zero=False):
 src=socket.inet_aton('198.18.0.1');dst=socket.inet_aton('198.18.0.2')
 udp=struct.pack('!HHHH',45000,4434,8+len(payload),0)+payload
 c=checksum(src+dst+struct.pack('!BBH',0,17,len(udp))+udp) or 65535
 if bad=='udp':c=(c^256) or 1
 udp=udp[:6]+struct.pack('!H',0 if zero else c)+udp[8:]
 ip=struct.pack('!BBHHHBBH4s4s',0x45,0,20+len(udp),1,0,64,17,0,src,dst);c=checksum(ip)
 if bad=='ip':c^=1
 ip=ip[:10]+struct.pack('!H',c)+ip[12:]
 return bytes.fromhex('5254001234565254001234570800')+ip+udp

def trial(root,tag,kind):
 root.mkdir(mode=0o700);certificates(root);a,b=socket.socketpair(socket.AF_UNIX,socket.SOCK_DGRAM);service=None
 try:
  service=NativeService(root,8080,instrumented=False,tag=tag,guest_address='198.18.0.2',static_cidr='198.18.0.2/24',wire=(1,2),network_fd=a.fileno(),file_overrides={'native-runtime.conf':b'control=198.18.0.2,4434\ndrain-seconds=1\npmtud=yes\nmax-udp-payload=1452\n'})
  a.close();before=time.monotonic();b.send(frame(service.token.encode(),kind if kind in ['ip','udp'] else None,kind=='zero'))
  should_stop=kind=='zero'
  if should_stop:
   service.process.wait(timeout=5);assert 'NATIVE_NGHTTPX STOP authenticated' in service.log_path.read_text() and 'main returned 0' in service.log_path.read_text()
  else:
   # Four times the independent ACK deadline; the same exact token then proves
   # socket/address readiness and delivery. No QUIC authentication masks the bug.
   until=time.monotonic()+.5
   while time.monotonic()<until:
    assert service.process.poll() is None,'corrupt packet reached application';time.sleep(.01)
   b.send(frame(service.token.encode()));service.process.wait(timeout=5)
   assert 'NATIVE_NGHTTPX STOP authenticated' in service.log_path.read_text() and 'main returned 0' in service.log_path.read_text()
  return {'kind':kind,'status':'PASS','corrupt_delivered':False,'valid_control_delivered':True,'image_sha256':hashlib.sha256(service.image.read_bytes()).hexdigest(),'seconds':time.monotonic()-before}
 finally:
  if service:service.close()
  a.close();b.close()
def main():
 p=argparse.ArgumentParser();p.add_argument('--tag',default='standard');a=p.parse_args();root=WORK/'build/rx-checksum';root.mkdir(mode=0o700);out={'status':'FAIL','cases':[],'scope':'actual IPv4/UDP netif receive path, authenticated application control delivery oracle; valid IPv4 UDP checksum0 preserved'}
 try:
  for kind in ['ip','udp','zero']:out['cases'].append(trial(root/('rc-'+kind),a.tag,kind))
  out['status']='PASS';print('RX_CHECKSUM PASS corrupt_IPv4_and_UDP_drop valid_UDP_checksum0',flush=True)
 finally:(WORK/'rx-checksum-results.json').write_text(json.dumps(out,indent=2)+'\n')
if __name__=='__main__':main()
