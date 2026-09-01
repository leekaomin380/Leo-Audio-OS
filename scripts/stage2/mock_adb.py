#!/usr/bin/env python3
"""Strict mock: never evaluates a shell or accepts unknown commands."""
import hashlib, json, os, shlex, shutil, sys
from pathlib import Path
root=Path(os.environ['MOCK_ROOT']); state=json.loads((root/'state.json').read_text())
state.setdefault('boot_seq',0)
fault=os.environ.get('MOCK_FAIL',''); hal='/system/vendor/lib/hw/audio.primary.msm8994.so'
def path(p):
    dest=(root/'fs'/p.lstrip('/')).resolve()
    if not dest.is_relative_to((root/'fs').resolve()): raise ValueError('unsafe path')
    return dest
def sha(p): return hashlib.sha256(path(p).read_bytes()).hexdigest()
def save(): (root/'state.json').write_text(json.dumps(state))
def fail(code=23): save(); sys.exit(code)
def hit(name):
    if fault != name: return False
    state['fault_seen']=True;save();return True
args=sys.argv[1:]
if hit('transport'): sys.exit(23)
if args==['devices']:
    print('List of devices attached\nleo-test-device\tdevice');sys.exit(0)
if args[:2]!=['-s','leo-test-device']: sys.exit(127)
verb=args[2];args=args[3:]
if verb=='wait-for-device': sys.exit(0)
if verb=='reboot':
    state['boot_seq']+=1;state['mount']='ro';state['cycles']+=1
    state['as_pid']=(state['as_pid'] or 6378)+100;state['hal_pid']=(state['hal_pid'] or 6379)+100
    state['mapped_inode']=path(hal).stat().st_ino
    save();sys.exit(0)
if verb=='push':
    if hit('push'): fail()
    dst=path(args[1]);dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(args[0],dst)
    if hit('corrupt'): dst.write_bytes(dst.read_bytes()+b'X')
    sys.exit(0)
if verb!='shell': sys.exit(127)
c=' '.join(args);t=shlex.split(c)
if t==['id','-u']: print('0')
elif c=='cat /proc/sys/kernel/random/boot_id': print(f'11111111-2222-3333-4444-{state["boot_seq"]:012d}')
elif t==['getprop','sys.boot_completed']: print('1')
elif t[:1]==['sha256sum']:
    try: print(sha(t[1])+'  '+t[1])
    except OSError: fail(1)
    if hit('hash_bad_rc'): fail()
elif t[:2]==['stat','-c']:
    p=path(t[3]);fmt=t[2]
    if not p.exists(): fail(1)
    values={'%d:%i':'45865:'+str(p.stat().st_ino),'%s':p.stat().st_size,'%a':state['mode'],'%U':'root'}
    if fmt not in values: fail(127)
    print(values[fmt])
elif t[:2]==['ls','-Z']: print(state['ctx']+' '+t[2])
elif t==['tinymix','Volume']:
    v=225 if (state['cycles'] and hit('volume')) or hit('baseline_volume') else 205
    print(f'Volume: {v} {v} (dsrange 0->255)')
elif t==['cat','/proc/mounts']:
    print('rootfs / rootfs rw,seclabel 0 0\n/dev/block/system / ext4 '+state['mount']+',seclabel 0 0')
elif t[:1]==['pidof']:
    pid=state['as_pid'] if t[1]=='audioserver' else state['hal_pid']
    if pid is None: fail(1)
    print(f'{pid} {pid+1}' if state['cycles'] and hit('pid_multiple') else pid)
elif t[:1]==['cat'] and t[1].startswith('/proc/'):
    pid=int(t[1].split('/')[2])
    if pid not in [state['as_pid'],state['hal_pid']]: fail(1)
    if t[1].endswith('/stat'):
        if state['cycles'] and hit('identity_empty'): sys.exit(0)
        if state['cycles'] and hit('identity_error'): fail()
        print(f'{pid} (comm with ) space) S '+' '.join(['0']*18)+f' {100+state["cycles"]} 0 0')
    elif t[1].endswith('/maps'):
        if state['cycles'] and hit('maps_missing'): sys.exit(0)
        for i in range(4):
            ino=state['mapped_inode']+(1 if state['cycles'] and i==3 and hit('maps_mixed') else 0)
            print(f'1000-2000 r-xp 00000000 b3:29 {ino} {hal}')
    else: fail(127)
elif t[:2]==['getprop','init.svc.audioserver']: print('running' if state['as_pid'] else 'stopped')
elif t[:2]==['getprop','init.svc.vendor.audio-hal-2-0']: print('running' if state['hal_pid'] else 'stopped')
elif c=="df /system | tail -1 | awk '{print $4}'": print(141912)
elif t[:2]==['mkdir','-p']: path(t[2]).mkdir(parents=True,exist_ok=True)
elif t[:3]==['test','!','-e']:
    if path(t[3]).exists(): fail(1)
elif t[:2]==['rm','-f']: path(t[2]).unlink(missing_ok=True)
elif t==['sync']: pass
elif t[:2]==['mount','-o']:
    rw=t[2].startswith('rw')
    if (rw and hit('remount')) or (not rw and hit('remount_ro')): fail()
    state['mount']='rw' if rw else 'ro'
elif t[:2] in (['cp','-f'],['mv','-f']):
    src,dst=t[2:4]
    if dst.startswith('/system/') and state['mount']!='rw': fail(1)
    path(dst).parent.mkdir(parents=True,exist_ok=True)
    if t[0]=='cp': shutil.copyfile(path(src),path(dst))
    else: path(src).replace(path(dst))
elif t[0] in ['chmod','chown','chcon']:
    if state['mount']!='rw': fail(1)
    if t[0]=='chmod': state['mode']=t[1]
    if t[0]=='chcon': state['ctx']=t[1]
elif t==['setprop','ctl.restart','audioserver']:
    if hit('restart_error'): fail()
    if hit('restart_noop'): sys.exit(0)
    state['cycles']+=1;state['as_pid']=(state['as_pid'] or 6378)+100;state['hal_pid']=(state['hal_pid'] or 6379)+100
    state['mapped_inode']=path(hal).stat().st_ino
    if sha(hal)!=state['stock_sha'] and hit('service'): state['hal_pid']=None
elif c.startswith('dumpsys media.audio_flinger'): print('')
else:
    print('Unmodeled command: '+c,file=sys.stderr);fail(127)
save()
