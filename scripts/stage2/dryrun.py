#!/usr/bin/env python3
import hashlib,json,os,shutil,subprocess,tempfile
from pathlib import Path
here=Path(__file__).resolve().parent
stock=Path('/Users/km/Desktop/Leo-Audio-OS/resources/private/phase5b-mokee/selected/system/vendor/lib/hw/audio.primary.msm8994.so')
stock_sha=hashlib.sha256(stock.read_bytes()).hexdigest()
cases=[('preflight','',False,True,'stock'),('deploy','',True,True,'candidate')]
cases += [(fault,fault,True,False,'stock') for fault in ['corrupt','remount','transport','hash_bad_rc',
          'restart_error','restart_noop','identity_empty','identity_error','pid_multiple',
          'maps_missing','maps_mixed','volume','service']]
cases += [('remount-ro reboot fallback','remount_ro',True,True,'candidate')]
cases += [('noop rollback','',False,True,'stock')]
cases += [('noop rollback volume','baseline_volume',False,False,'stock')]
failed=[]
with tempfile.TemporaryDirectory(prefix='leo-stage2-') as tmp:
    for i,(label,fault,go,success,end) in enumerate(cases):
        r=Path(tmp)/str(i);hal=r/'fs/system/vendor/lib/hw/audio.primary.msm8994.so'
        hal.parent.mkdir(parents=True);shutil.copyfile(stock,hal)
        lib64=r/'fs/system/vendor/lib64/hw/audio.primary.msm8994.so'
        lib64.parent.mkdir(parents=True);lib64.write_bytes(bytes(187784))
        state=dict(as_pid=6378,hal_pid=6379,cycles=0,mapped_inode=hal.stat().st_ino,
                   mount='ro',mode='644',ctx='u:object_r:vendor_file:s0',stock_sha=stock_sha)
        (r/'state.json').write_text(json.dumps(state))
        env={**os.environ,'MOCK_ROOT':str(r),'LEO_SERIAL':'leo-test-device','MOCK_FAIL':fault,'ADB':str(here/'mock-adb.sh'),
             'LEO_SERVICE_WAIT_STEPS':'2','LEO_SERVICE_WAIT_INTERVAL':'0'}
        script='rollback-hal.sh' if label.startswith('noop rollback') else 'deploy-hal.sh'
        args=['sh',str(here/script)]+(['--i-have-authorization'] if go else [])
        p=subprocess.run(args,env=env,capture_output=True,text=True,errors="replace",timeout=55)
        current=hashlib.sha256(hal.read_bytes()).hexdigest()
        valid=(p.returncode==0)==success and ((current==stock_sha)==(end=='stock'))
        if fault: valid=valid and json.loads((r/'state.json').read_text()).get('fault_seen',False)
        if valid and label=='noop rollback': valid=json.loads((r/'state.json').read_text())['cycles']==0
        print(('PASS' if valid else 'FAIL'),label,'rc='+str(p.returncode),flush=True)
        if not valid:
            print(p.stdout+p.stderr);raise SystemExit(1)
print(f'{len(cases)-len(failed)}/{len(cases)} dry-run scenarios passed')
raise SystemExit(bool(failed))
