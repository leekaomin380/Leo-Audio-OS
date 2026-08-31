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


def audit_project(root, project):
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
        if result['tracked_or_untracked_changes']: raise ValueError('source checkout is not clean')
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
    args = parser.parse_args()
    root = args.source.resolve(strict=True)
    if args.report.resolve().is_relative_to(root):
        parser.error('report must be outside the audited source tree')
    projects = load_inputs(args.lock,args.manifest)
    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(lambda p:audit_project(root,p),projects))
    host = host_info(root)
    good = all(p['valid'] for p in rows) and host['supported_build_host']
    report = {'status':'CLEAN_INPUTS_RECORDED' if good else 'INPUT_AUDIT_FAILED',
              'build_verified':False, 'target_module_verified':False,
              'source_root':str(root), 'lock_sha256':digest(args.lock),
              'manifest_sha256':digest(args.manifest), 'host':host, 'projects':rows}
    args.report.parent.mkdir(parents=True,exist_ok=True)
    # Do not overwrite an earlier audit or build evidence.
    with args.report.open('x') as output: json.dump(report,output,indent=2)
    print(f"{report['status']}: {sum(p['valid'] for p in rows)}/{len(rows)} clean pinned projects")
    print('No build or target/device compatibility has been verified.')
    return 0 if good else 1


if __name__ == '__main__':
    raise SystemExit(main())
