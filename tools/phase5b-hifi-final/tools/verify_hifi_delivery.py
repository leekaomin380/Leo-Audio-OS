"""Read-only SHA256SUMS verification. Skipped private files are not verified."""
import argparse
import hashlib
import re
from pathlib import Path, PurePosixPath

def verify_delivery(manifest_path, exclude_private=False, chunk_size=65536):
    manifest = Path(manifest_path)
    if not isinstance(chunk_size, int) or chunk_size < 1:
        return False
    if manifest.is_symlink() or not manifest.is_file():
        return False
    base = manifest.parent.resolve()
    success, seen, verified, skipped = True, set(), 0, 0
    try:
        lines = manifest.read_text(encoding='utf-8').splitlines()
    except (OSError, UnicodeError):
        return False
    for number, line in enumerate(lines, 1):
        if not line or line.startswith('#'):
            continue
        match = re.fullmatch(r'([0-9a-fA-F]{64})[ \t]+\*?([^\r\n]+)', line)
        if not match:
            print('ERROR invalid SHA256 record at line', number); success = False; continue
        digest, name = match.groups()
        rel = PurePosixPath(name)
        if (not name or rel.is_absolute() or '..' in rel.parts or '\\' in name
                or '\0' in name or str(rel) != name or name in seen):
            print('ERROR unsafe/duplicate path at line', number); success = False; continue
        seen.add(name)
        path = base / name
        if any(p.is_symlink() for p in [path, *path.parents] if p != base and base in p.parents):
            print('ERROR symlink:', name); success = False; continue
        private = rel.parts[0] in {'private', 'private-diagnostic-image'}
        if exclude_private and private:
            skipped += 1; print('SKIP UNVERIFIED:', name); continue
        if not path.is_file():
            print('ERROR missing/nonregular:', name); success = False; continue
        h = hashlib.sha256()
        try:
            with path.open('rb') as f:
                for chunk in iter(lambda: f.read(chunk_size), b''):
                    h.update(chunk)
        except OSError:
            success = False; continue
        if h.hexdigest() != digest.lower():
            print('ERROR hash mismatch:', name); success = False
        else:
            verified += 1
    if not seen:
        print('ERROR empty manifest'); success = False
    print('verified=%d skipped_unverified=%d result=%s' % (verified, skipped, 'PASS' if success else 'FAIL'))
    return success

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('manifest')
    p.add_argument('--exclude-private', action='store_true', help='Skip only private/ and private-diagnostic-image/ entries; report them as unverified')
    a = p.parse_args()
    return 0 if verify_delivery(a.manifest, a.exclude_private) else 1

if __name__ == '__main__':
    raise SystemExit(main())
