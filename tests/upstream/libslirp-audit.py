"""Reproduce known TIME_WAIT limitations without modifying the host QA library."""
import argparse,hashlib,json,pathlib,resource,subprocess
from source import snapshot
r=pathlib.Path(__file__).resolve().parents[2]
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=pathlib.Path,required=True)
args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True)
checkout=r/'forks/libslirp';repo=out/'source';head=snapshot(checkout,'HEAD',repo);build=out/'meson'
for command in [['meson','setup',str(build),str(repo),'--buildtype=debug'],['ninja','-C',str(build),'-j4']]:
 subprocess.run(command,check=True)
source=(repo/'test/tcptimewaittest.c').read_text()
objects=sorted(next(build.glob('libslirp.so.*.p')).glob('*.o'));assert objects
flags=subprocess.check_output(['pkg-config','--cflags','--libs','glib-2.0'],text=True).split()
resource.setrlimit(resource.RLIMIT_CORE,(0,0))
checks=[]
for label,body in [('original',None),('in-window-syn-ack','TH_SYN | TH_ACK'),('in-window-syn-fin','TH_SYN | TH_FIN'),('in-window-syn-urg','TH_SYN | TH_URG'),('reopen-local-isn','ISN')]:
 text=source if body is None else source[:source.index('int main(void)')]+f'int main(void) {{ run_case(100000, 100001, {body}, false, false); return 0; }}\n'
 if body=='ISN':
  text=source[:source.index('int main(void)')].replace('assert(tp->rcv_nxt == sequence + 1);', 'assert(tp->rcv_nxt == sequence + 1);\n        assert(SEQ_GT(tp->iss, (tcp_seq)500000));')+'int main(void) { run_case(100000, 110000, TH_SYN, true, false); return 0; }\n'
 p=out/(label+'.c');p.write_text(text);binary=out/label
 command=['cc','-std=gnu99','-O0','-g','-DBUILDING_LIBSLIRP','-I'+str(build),'-I'+str(repo/'src'),str(p),*map(str,objects),*flags,'-o',str(binary)]
 subprocess.run(command,check=True,capture_output=True)
 result=subprocess.run([str(binary)],capture_output=True,text=True);(out/(label+'.log')).write_text(result.stdout+result.stderr)
 assert result.returncode==(0 if body is None else -6)
 checks.append(dict(case=label,command=command,exit_code=result.returncode,expected_failure=body is not None,log=str((out/(label+'.log')).relative_to(r)),log_sha256=hashlib.sha256((result.stdout+result.stderr).encode()).hexdigest(),source_sha256=hashlib.sha256(text.encode()).hexdigest()))
 print(label,result.returncode)
(out/'results.json').write_text(json.dumps(dict(status='PASS',meaning='Original fixture passes; three stronger in-window preservation assertions fail. New local ISN also need not exceed old snd_max. These are inherited behavior, not newly introduced by moving the TIME_WAIT branch.',head=head,checks=checks),indent=2)+'\n')
