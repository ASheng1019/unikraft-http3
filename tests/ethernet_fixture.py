"""Isolated Ethernet link between two actual KVM guests, carried by QEMU UDP."""
import os,json,subprocess,threading,time,socket,selectors,struct,hashlib
from pathlib import Path
from quic_fixture import WORK,PREFIX,environment,filesystem_cpio,free_udp

class EthernetLink:
    def __init__(self):
        self.native_port,self.client_port=free_udp(),free_udp()
        self.to_native,self.to_client=free_udp(),free_udp()
        self.sockets=[];self.selector=selectors.DefaultSelector();self.records=[];self.running=True
        self.mtu=1500;self.mark_ce=False;self.bleach_ecn=False
        for port,target,direction in [(self.to_native,self.client_port,'server'),(self.to_client,self.native_port,'client')]:
            s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.bind(('127.0.0.1',port));s.setblocking(False)
            self.sockets.append(s);self.selector.register(s,selectors.EVENT_READ,(target,direction))
        self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start()
    def run(self):
        while self.running:
            for key,_ in self.selector.select(.01):
                frame=bytearray(key.fileobj.recv(65536));target,direction=key.data
                if len(frame)<14:continue
                kind=int.from_bytes(frame[12:14],'big');record=None
                if kind==0x0800 and len(frame)>=34:
                    iplen=int.from_bytes(frame[16:18],'big');ecn=frame[15]&3
                    record={'direction':direction,'family':4,'length':iplen,'ecn':ecn,'df':bool(frame[20]&0x40),'next':frame[23]}
                    if direction=='server' and ((self.mark_ce and ecn in (1,2)) or (self.bleach_ecn and ecn)):
                        frame[15]=(frame[15]&0xfc)|(0 if self.bleach_ecn else 3);frame[24:26]=b'\0\0'
                        header=frame[14:14+(frame[14]&15)*4];words=struct.unpack('!%dH'%(len(header)//2),header)
                        c=sum(words)
                        while c>>16:c=(c&0xffff)+(c>>16)
                        frame[24:26]=struct.pack('!H',(~c)&0xffff);record['ce_marked']=not self.bleach_ecn;record['bleached']=self.bleach_ecn
                elif kind==0x86dd and len(frame)>=54:
                    iplen=int.from_bytes(frame[18:20],'big')+40;ecn=(frame[15]>>4)&3
                    record={'direction':direction,'family':6,'length':iplen,'ecn':ecn,'next':frame[20],'src':socket.inet_ntop(socket.AF_INET6,frame[22:38]),'dst':socket.inet_ntop(socket.AF_INET6,frame[38:54])}
                    if frame[20]==58 and len(frame)>54:record['icmp_type']=frame[54]
                    if direction=='server' and ((self.mark_ce and ecn in (1,2)) or (self.bleach_ecn and ecn)):
                        frame[15]=(frame[15]&0xcf)|(0 if self.bleach_ecn else 0x30);record['ce_marked']=not self.bleach_ecn;record['bleached']=self.bleach_ecn
                if record:
                    # Only the QUIC UDP path crosses the emulated bottleneck; the
                    # TCP origin is a separate logical network path.
                    record['path_mtu']=self.mtu
                    record['dropped']=record['next']==17 and record['length']>record['path_mtu']
                    self.records.append(record)
                    if record['dropped']:continue
                key.fileobj.sendto(frame,('127.0.0.1',target))
    def close(self):
        self.running=False;self.thread.join(timeout=1)
        for s in self.sockets:s.close()
        self.selector.close()

class ClientVM:
    def __init__(self,root,link,files=None,*,cpu=None,vcpus=1,qemu_options=(),network_fd=None):
        self.root=root;self.log_path=root/'client-serial.log';self.log=self.log_path.open('w')
        entries={'epoch':(str(int(time.time())).encode(),0o100600),'busybox':(Path('/usr/bin/busybox').read_bytes(),0o100755),'ca.pem':((root/'ca.pem').read_bytes(),0o100644),
                 'www/download':((bytes(range(256))*1024),0o100644),'www/get':(b'native-nghttpx-backend-ok\n',0o100644)}
        for program in ['curl','openssl']:
            binary=PREFIX/'bin'/program;entries[program]=(binary.read_bytes(),0o100755)
            for line in subprocess.check_output(['ldd',str(binary)],env=environment(),text=True).splitlines():
                row=line.split();p=row[2] if '=>' in row and len(row)>2 else row[0]
                if p.startswith('/'):
                    dest=p.lstrip('/') if 'ld-linux' in p else 'lib/'+Path(p).name
                    entries[dest]=(Path(p).read_bytes(),0o100755)
        helper=root/'wire-control'
        subprocess.run(['cc','-static','-O2',str(Path(__file__).with_name('wire-control.c')),'-o',str(helper)],check=True)
        entries['wire-control']=(helper.read_bytes(),0o100755)
        entries.update(files or {})
        init='''#!/busybox sh
/busybox mkdir -p /proc /sys /dev /bin /tmp
/busybox mount -t proc proc /proc
/busybox mount -t sysfs sysfs /sys
/busybox mount -t devtmpfs devtmpfs /dev
/busybox --install -s /bin
export PATH=/bin
export LD_LIBRARY_PATH=/lib
export OPENSSL_CONF=/dev/null
stty -echo
date -u -s @$(cat /epoch)
ip link set lo up
ip link set eth0 up
ip addr add 198.18.0.1/24 dev eth0
ip -6 addr add fd00:1::1/64 dev eth0
httpd -p 8080 -h /www
sleep 2
echo CLIENT_VM_READY
while IFS= read -r command; do
 eval "$command"
 echo COMMAND_DONE=$?
done
poweroff -f
'''
        entries['init']=(init.encode(),0o100755)
        initrd=root/'client.cpio';initrd.write_bytes(filesystem_cpio(entries));initrd.chmod(0o600)
        self.command=['qemu-system-aarch64','-machine','virt,gic-version=host','-cpu','host','-accel','kvm','-m','768M','-smp','1','-display','none','-monitor','none','-serial','stdio','-no-reboot','-kernel',os.environ['QUIC_TEST_LINUX_IMAGE'],'-initrd',str(initrd),'-append','console=ttyAMA0 rdinit=/init loglevel=3','-netdev',f'socket,id=n0,udp=127.0.0.1:{link.to_client},localaddr=127.0.0.1:{link.client_port}','-device','virtio-net-device,netdev=n0,mac=52:54:00:12:34:57,csum=off,guest_csum=off,gso=off,host_tso4=off,host_tso6=off,host_ecn=off,host_ufo=off']
        self.command[self.command.index('-smp')+1]=str(vcpus)
        self.command+=list(qemu_options)
        if network_fd is not None:
            self.command[self.command.index('-netdev')+1]=f'socket,id=n0,fd={network_fd}'
        if cpu is not None:self.command=['taskset','-c',str(cpu)]+self.command
        self.process=subprocess.Popen(self.command,stdin=subprocess.PIPE,stdout=self.log,stderr=subprocess.STDOUT,
                                      pass_fds=() if network_fd is None else (network_fd,))
        for _ in range(150):
            if 'CLIENT_VM_READY' in self.log_path.read_text():return
            if self.process.poll() is not None:break
            time.sleep(.1)
        self.close();raise RuntimeError('client VM startup failed')
    def run(self,command,timeout=20):
        offset=self.log_path.stat().st_size
        self.process.stdin.write(command.encode()+b'\n');self.process.stdin.flush()
        until=time.monotonic()+timeout
        while time.monotonic()<until:
            data=self.log_path.read_bytes()[offset:].decode(errors='replace').replace('\r','')
            if 'COMMAND_DONE=' in data:
                output,code=data.rsplit('COMMAND_DONE=',1)
                return int(code.split()[0]),output
            if self.process.poll() is not None:raise RuntimeError('client VM exited')
            time.sleep(.05)
        raise RuntimeError('client VM command timed out')
    def close(self):
        if self.process.poll() is None:
            self.process.terminate()
            try:self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:self.process.kill();self.process.wait()
        self.process.stdin.close();self.log.close()
