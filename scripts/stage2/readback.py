#!/usr/bin/env python3
"""Strict parsing of successful adb readbacks; empty output is never evidence."""
import re
import sys

def parse(kind, text):
    text = text.strip()
    if not text:
        raise ValueError('empty readback')
    if kind == 'sha':
        m = re.fullmatch(r'([0-9a-f]{64})\s+\S+', text)
        if not m: raise ValueError('invalid sha256sum readback')
        return m[1]
    if kind == 'positive':
        if not re.fullmatch(r'[1-9][0-9]*', text): raise ValueError('invalid positive integer')
        return text
    if kind == 'identity':
        # comm can contain spaces and ')'; only the last ') ' ends it.
        m = re.fullmatch(r'([1-9][0-9]*) \(.*\) (.+)', text)
        if not m: raise ValueError('invalid proc stat')
        fields = m[2].split()
        if len(fields) < 20 or not re.fullmatch(r'[1-9][0-9]*', fields[19]):
            raise ValueError('invalid starttime')
        return m[1] + ':' + fields[19]
    if kind == 'inode':
        if not re.fullmatch(r'[0-9]+:[1-9][0-9]*', text): raise ValueError('invalid stat dev:ino')
        dev, ino = map(int, text.split(':'))
        # Linux dev_t encoding, independent of the host (macOS) os.major ABI.
        major = ((dev >> 8) & 0xfff) | ((dev >> 32) & ~0xfff)
        minor = (dev & 0xff) | ((dev >> 12) & ~0xff)
        return f'{major}:{minor}:{ino}'
    if kind == 'maps':
        identities = set()
        for line in text.splitlines():
            if 'audio.primary.msm8994.so' not in line: continue
            fields = line.split(None, 5)
            if len(fields) != 6 or fields[5] != '/system/vendor/lib/hw/audio.primary.msm8994.so':
                raise ValueError('unexpected/deleted HAL mapping')
            if not re.fullmatch(r'[0-9a-fA-F]+:[0-9a-fA-F]+', fields[3]):
                raise ValueError('invalid mapping device')
            if not re.fullmatch(r'[1-9][0-9]*', fields[4]): raise ValueError('invalid mapping inode')
            major, minor = (int(x,16) for x in fields[3].split(':'))
            identities.add(f'{major}:{minor}:{int(fields[4])}')
        if len(identities) != 1: raise ValueError('missing/conflicting HAL mappings')
        return identities.pop()
    if kind == 'mount':
        rows = [x.split() for x in text.splitlines() if len(x.split()) >= 4 and x.split()[1] == '/']
        # Android system-as-root also lists the covered initial rootfs mount.
        if any(row[2] not in {'rootfs','ext4'} for row in rows):
            raise ValueError('unexpected root mount overlay')
        rows = [row for row in rows if row[2] == 'ext4']
        if len(rows) != 1: raise ValueError('unexpected root mount')
        flags = set(rows[0][3].split(',')) & {'ro','rw'}
        if len(flags) != 1: raise ValueError('invalid mount flags')
        return flags.pop()
    if kind == 'context':
        matches = re.findall(r'u:object_r:[A-Za-z0-9_]+:s0', text)
        if len(matches) != 1: raise ValueError('invalid SELinux readback')
        return matches[0]
    raise ValueError('unknown parser')

if __name__ == '__main__':
    try: print(parse(sys.argv[1], sys.stdin.read()))
    except (ValueError, IndexError) as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
