#!/usr/bin/env python3
"""Read-only source/host audit. No build, download, cleanup, or device action."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import stat
import subprocess
import xml.etree.ElementTree as ET


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_inputs(lock, manifest):
    projects = json.loads(lock.read_text())['projects']
    locked = {}
    for p in projects:
        path = PurePosixPath(p['path'])
        if path.is_absolute() or not path.parts or '..' in path.parts or str(path) != p['path']:
            raise ValueError('unsafe/noncanonical project path')
        if p['path'] in locked or not re.fullmatch(r'[0-9a-f]{40}', p['commit']):
            raise ValueError('duplicate path or invalid commit')
        locked[p['path']] = p
    xml = ET.parse(manifest).getroot()
    if xml.tag != 'manifest': raise ValueError('not a repo manifest')
    if xml.findall('include') or xml.findall('extend-project') or xml.findall('remove-project'):
        raise ValueError('manifest must be fully expanded')
    seen = {}
    for p in xml.findall('project'):
        name = p.get('path', p.get('name'))
        if name in seen: raise ValueError('duplicate manifest path')
        seen[name] = p
    if set(seen) != set(locked): raise ValueError('manifest/lock path sets differ')
    remotes = {r.get('name'): r.get('fetch', '').rstrip('/') for r in xml.findall('remote')}
    if len(remotes) != len(xml.findall('remote')): raise ValueError('duplicate remote')
    defaults = xml.find('default')
    default_remote = defaults.get('remote') if defaults is not None else None
    for name,p in seen.items():
        if p.get('revision') != locked[name]['commit'] or p.get('name') != locked[name]['name']:
            raise ValueError('manifest/lock identity differs: '+name)
        fetch = remotes.get(p.get('remote', default_remote), '')
        if not fetch.startswith('https://') or fetch+'/'+p.get('name') != locked[name]['url']:
            raise ValueError('manifest/lock source URL differs: '+name)
    if not projects: raise ValueError('empty source lock')
    return projects


def load_daily_overlay(here, projects):
    overlay = json.loads((here/'hal-overlay.json').read_text())
    expected_path = 'hardware/qcom-caf/msm8994/audio'
    if overlay['path'] != expected_path:
        raise ValueError('overlay is not the daily HAL')
    matches = [p for p in projects if p['path'] == expected_path]
    if len(matches) != 1 or matches[0]['commit'] != overlay['base_commit']:
        raise ValueError('overlay base differs from source lock')
    repo = here.parents[1]
    if len(overlay['patches']) != 8 or len(overlay['files']) != 7:
        raise ValueError('unexpected daily patch or file count')
    for patch in overlay['patches']:
        path = (repo/patch['path']).resolve(strict=True)
        if not path.is_relative_to(repo) or digest(path) != patch['sha256']:
            raise ValueError('reviewed patch changed: '+patch['path'])
    for name, entry in overlay['files'].items():
        path = PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts or str(path) != name:
            raise ValueError('unsafe overlay path')
        if entry['mode'] != '100644' or entry['kind'] not in {'tracked','untracked'}:
            raise ValueError('unsupported overlay entry')
    return overlay


def verify_overlay(path, overlay, git):
    # Staging is not part of this build recipe. Other projects remain strictly clean.
    if git('diff','--cached','--name-only'):
        raise ValueError('overlay has staged changes')
    tracked = set(filter(None,git('diff','--no-ext-diff','HEAD','--name-only','-z').split('\0')))
    untracked = set(filter(None,git('ls-files','--others','--exclude-standard','-z').split('\0')))
    for kind, actual in [('tracked',tracked),('untracked',untracked)]:
        expected = {n for n,e in overlay['files'].items() if e['kind'] == kind}
        if actual != expected:
            raise ValueError('overlay '+kind+' file set differs')
    # Reject index flags that could hide an additional tracked change.
    if any(line and not line.startswith('H ') for line in git('ls-files','-v').splitlines()):
        raise ValueError('overlay checkout has hidden index flags')
    for name, entry in overlay['files'].items():
        target = path/name
        mode = target.lstat().st_mode
        if (not stat.S_ISREG(mode) or mode & 0o111 or
                not target.resolve().is_relative_to(path) or digest(target) != entry['sha256']):
            raise ValueError('overlay content or mode differs: '+name)


def audit_project(root, project, overlay=None):
    name = project['path']
    path = (root/name).resolve()
    result = {'path':name, 'expected':project['commit'], 'valid':False}
    if not path.is_relative_to(root) or not path.is_dir():
        return {**result, 'error':'missing project or path outside source root'}
    # git -C may silently discover an ancestor repo: require the exact top level.
    def git(*args):
        p = subprocess.run(['git','-C',str(path),*args], capture_output=True,
                           text=True, timeout=30, env={**os.environ,'GIT_OPTIONAL_LOCKS':'0'})
        if p.returncode: raise ValueError('git read failed: '+args[0])
        return p.stdout.strip()
    try:
        top = Path(git('rev-parse','--show-toplevel')).resolve()
        if top != path: raise ValueError('not an independent project checkout')
        result['actual'] = git('rev-parse','HEAD')
        result['tracked_or_untracked_changes'] = bool(git('status','--porcelain','--untracked-files=all'))
        if result['actual'] != result['expected']: raise ValueError('wrong commit')
        if overlay is not None and name == overlay['path']:
            if result['actual'] != overlay['base_commit']:
                raise ValueError('wrong overlay base')
            verify_overlay(path,overlay,git)
            result['reviewed_daily_overlay'] = True
        elif result['tracked_or_untracked_changes']:
            raise ValueError('source checkout is not clean')
        result['valid'] = True
    except (ValueError, OSError, subprocess.TimeoutExpired) as e:
        result['error'] = str(e)
    return result


def host_info(root):
    data = {'system':platform.system(), 'machine':platform.machine(),
            'cpu_count':os.cpu_count(), 'disk_free_bytes':shutil.disk_usage(root).free}
    data['supported_build_host'] = data['system']=='Linux' and data['machine'] in {'x86_64','amd64'}
    if Path('/proc/meminfo').is_file():
        for line in Path('/proc/meminfo').read_text().splitlines():
            key,_,value = line.partition(':')
            if key in {'MemTotal','MemAvailable','SwapTotal'}:
                data[key+'_bytes'] = int(value.split()[0])*1024
    # These are planning warnings, not invented Android minimum requirements.
    data['planning_warnings'] = []
    if data['disk_free_bytes'] < 350*1024**3:
        data['planning_warnings'].append('less than the planned 350 GiB free disk')
    if data.get('MemTotal_bytes',0) < 64*1024**3:
        data['planning_warnings'].append('less than the planned 64 GiB RAM, or not measured')
    return data


def main():
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--lock',type=Path,default=here/'source-lock.json')
    parser.add_argument('--manifest',type=Path,default=here/'manifest.xml')
    parser.add_argument('--daily-hal-overlay',action='store_true',
                        help='require the exact reviewed eight-patch HAL; all other projects stay clean')
    args = parser.parse_args()
    root = args.source.resolve(strict=True)
    if args.report.resolve().is_relative_to(root):
        parser.error('report must be outside the audited source tree')
    projects = load_inputs(args.lock,args.manifest)
    overlay = load_daily_overlay(here,projects) if args.daily_hal_overlay else None
    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(lambda p:audit_project(root,p,overlay),projects))
    host = host_info(root)
    good = all(p['valid'] for p in rows) and host['supported_build_host']
    report = {'status':('PATCHED_INPUTS_RECORDED' if overlay else 'CLEAN_INPUTS_RECORDED')
                        if good else 'INPUT_AUDIT_FAILED',
              'build_verified':False, 'target_module_verified':False,
              'source_root':str(root), 'lock_sha256':digest(args.lock),
              'manifest_sha256':digest(args.manifest), 'host':host, 'projects':rows}
    if overlay:
        report['reviewed_overlay'] = overlay
        report['overlay_sha256'] = digest(here/'hal-overlay.json')
    args.report.parent.mkdir(parents=True,exist_ok=True)
    # Do not overwrite an earlier audit or build evidence.
    with args.report.open('x') as output: json.dump(report,output,indent=2)
    print(f"{report['status']}: {sum(p['valid'] for p in rows)}/{len(rows)} verified project inputs")
    print('No build or target/device compatibility has been verified.')
    return 0 if good else 1


if __name__ == '__main__':
    raise SystemExit(main())
