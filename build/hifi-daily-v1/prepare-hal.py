#!/usr/bin/env python3
"""Apply only to a clean, exact upstream HAL checkout inside an Android tree."""
import argparse
from pathlib import Path
import subprocess

p=argparse.ArgumentParser();p.add_argument('source',type=Path);a=p.parse_args()
repo=Path(__file__).resolve().parents[2]
hal=a.source.resolve()/'hardware/qcom-caf/msm8994/audio'
def git(*args):return subprocess.check_output(['git',*args],cwd=hal,text=True).strip()
if git('rev-parse','HEAD')!='7f4cac748b6f62897294cdaece9d1aec27e1e927':
    raise SystemExit('Refusing: wrong HAL HEAD')
if git('status','--porcelain','--untracked-files=all'):
    raise SystemExit('Refusing: HAL checkout has existing changes; nothing reset')
patches=sorted((repo/'patches/phase5b-m3').glob('*.patch'))+[
    repo/'patches/phase5b-hifi-ui/0006-hal-schema2.patch',
    repo/'patches/phase5b-hifi-ui/0007-hal-schema3-guard.patch',
    repo/'patches/phase5b-hifi-daily/0008-schema4-volume-recovery.patch']
if len(patches)!=8:raise SystemExit('Refusing: unexpected patch sequence')
for patch in patches:
    subprocess.run(['git','apply','--check',str(patch)],cwd=hal,check=True)
    subprocess.run(['git','apply',str(patch)],cwd=hal,check=True)
    print(patch.name)
print('8 patches applied. No build or device operation was performed.')
