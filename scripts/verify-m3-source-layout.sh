#!/bin/sh
# verify-m3-source-layout.sh
#
# Offline consistency check for the Leo M3 HiFi patch target.
#
#   usage: scripts/verify-m3-source-layout.sh <hal-source-root> [device-hal.so]
#
# <hal-source-root> must contain hal/msm8974/platform.c and hal/msm8974/platform.h
# (the MoKee mkq-mr1-caf-msm8994 layout).  The optional second argument is the
# 32-bit audio.primary.msm8994.so extracted from the device; when supplied the
# script also compares the source device_table against the table baked into the
# binary.
#
# ASSUMPTIONS -- this is NOT a generic validator:
#   * snd_device enum lives in hal/msm8974/platform.h between
#     "SND_DEVICE_OUT_BEGIN" and "SND_DEVICE_OUT_END,";
#   * device_table / acdb_device_table / snd_device_name_index live in
#     hal/msm8974/platform.c and use designated initialisers
#     ([SND_DEVICE_X] = ...) resp. {TO_NAME_INDEX(SND_DEVICE_X)};
#   * the binary is ELF32 little-endian ARM with the device_table stored as a
#     contiguous array of absolute string pointers.
# If the upstream layout changes, this script must be updated -- it will report
# "cannot parse" rather than silently pass.
#
# Exit status: 0 = all checks passed, 1 = a check failed, 2 = usage/parse error.

set -u

SRC="${1:-}"
BIN="${2:-}"

if [ -z "$SRC" ]; then
    echo "usage: $0 <hal-source-root> [device-hal.so]" >&2
    exit 2
fi

PH="$SRC/hal/msm8974/platform.h"
PC="$SRC/hal/msm8974/platform.c"

for f in "$PH" "$PC"; do
    if [ ! -f "$f" ]; then
        echo "FAIL: missing $f (wrong source root?)" >&2
        exit 2
    fi
done

rc=0
pass() { echo "PASS: $1"; }
fail() { echo "FAIL: $1"; rc=1; }

# ---------------------------------------------------------------- enum shape
out_enum=$(awk '/SND_DEVICE_OUT_BEGIN/{f=1} f{print} /SND_DEVICE_OUT_END,/{if(f)exit}' "$PH" \
           | grep -oE 'SND_DEVICE_OUT_[A-Z0-9_]+' | grep -v 'OUT_BEGIN\|OUT_END' | sort -u)
n_enum=$(printf '%s\n' "$out_enum" | grep -c . )

if [ "$n_enum" -eq 0 ]; then
    fail "cannot parse the OUT enum from platform.h"
else
    pass "parsed $n_enum SND_DEVICE_OUT_* symbols from platform.h"
fi

# ------------------------------------------------- device_table completeness
missing_dev=""
for sym in $out_enum; do
    if ! grep -q "\[$sym\][[:space:]]*=" "$PC"; then
        missing_dev="$missing_dev $sym"
    fi
done
if [ -n "$missing_dev" ]; then
    fail "OUT devices with no table entry at all:$missing_dev"
else
    pass "every SND_DEVICE_OUT_* symbol has at least one designated table entry"
fi

# --------------------------------------------- acdb + name-index for the new device
LEO=SND_DEVICE_OUT_LEO_HIFI_HEADPHONES
if grep -q "$LEO" "$PH"; then
    grep -qE "\[$LEO\][[:space:]]*=[[:space:]]*\"hifi-headphones\"" "$PC" \
        && pass "device_table[$LEO] = \"hifi-headphones\"" \
        || fail "device_table[$LEO] missing or wrong string"

    grep -qE "\[$LEO\][[:space:]]*=[[:space:]]*-1" "$PC" \
        && pass "acdb_device_table[$LEO] = -1 (no borrowed calibration)" \
        || fail "acdb_device_table[$LEO] must be -1; borrowing another device's ACDB id is forbidden"

    grep -q "TO_NAME_INDEX($LEO)" "$PC" \
        && pass "snd_device_name_index contains $LEO" \
        || fail "snd_device_name_index is missing $LEO"

    # the new device must be the LAST OUT entry so no existing index moves
    last=$(awk '/SND_DEVICE_OUT_BEGIN/{f=1} f{print} /SND_DEVICE_OUT_END,/{if(f)exit}' "$PH" \
           | grep -oE 'SND_DEVICE_OUT_[A-Z0-9_]+' | grep -v 'OUT_BEGIN\|OUT_END' | tail -1)
    [ "$last" = "$LEO" ] \
        && pass "$LEO is the last OUT entry (no existing index moves)" \
        || fail "$LEO must be the last OUT entry, found '$last'"

    grep -q "leo_assert_hifi_dev_in_out_range" "$PC" \
        && pass "compile-time range guard present" \
        || fail "compile-time range guard leo_assert_hifi_dev_in_out_range missing"
else
    echo "SKIP: $LEO not present (unpatched baseline)"
fi

# ------------------------------------------------------ binary cross-check
if [ -n "$BIN" ]; then
    if [ ! -f "$BIN" ]; then
        fail "binary $BIN not found"
    else
        python3 - "$PH" "$PC" "$BIN" <<'PYEOF'
import re, struct, sys

ph, pc, binpath = sys.argv[1], sys.argv[2], sys.argv[3]

# ---- 1. enum symbol -> index (C semantics: prev+1 unless "= expr") --------
hdr = open(ph, encoding='utf-8', errors='surrogateescape').read()
m = re.search(r'enum\s*\{\s*\n\s*SND_DEVICE_NONE\s*=\s*0\s*,(.*?)\n\};', hdr, re.S)
if not m:
    print("FAIL: cannot parse the snd_device enum from platform.h"); sys.exit(1)
idx = {"SND_DEVICE_NONE": 0}
cur = 0
for line in m.group(1).splitlines():
    line = re.sub(r'/\*.*?\*/', '', line).strip()
    if not line or line.startswith('*') or line.startswith('/') or line.startswith('#'):
        continue
    for item in [t.strip() for t in line.split(',') if t.strip()]:
        mm = re.match(r'^(SND_DEVICE_[A-Z0-9_]+)\s*(?:=\s*(.+))?$', item)
        if not mm:
            continue
        name, val = mm.group(1), mm.group(2)
        if val is None:
            cur += 1
        elif val.strip().isdigit():
            cur = int(val.strip())
        elif val.strip() in idx:
            cur = idx[val.strip()]
        else:
            print("FAIL: cannot evaluate enum initialiser %r" % item); sys.exit(1)
        idx[name] = cur

# ---- 2. source device_table, mapped through the enum ----------------------
src = open(pc, encoding='utf-8', errors='surrogateescape').read()
m = re.search(r'device_table\[SND_DEVICE_MAX\]\s*=\s*\{(.*?)\n\};', src, re.S)
if not m:
    print("FAIL: cannot locate device_table in source"); sys.exit(1)
src_tab = {}
for sym, name in re.findall(r'\[(SND_DEVICE_[A-Z0-9_]+)\]\s*=\s*"([^"]*)"', m.group(1)):
    if sym not in idx:
        print("FAIL: device_table references unknown symbol %s" % sym); sys.exit(1)
    src_tab[idx[sym]] = name

# ---- 3. binary device_table ----------------------------------------------
d = open(binpath, 'rb').read()
if d[:4] != b'\x7fELF' or d[4] != 1:
    print("FAIL: not an ELF32 image"); sys.exit(1)
e_phoff, = struct.unpack_from('<I', d, 0x1c)
e_phentsize, e_phnum = struct.unpack_from('<HH', d, 0x2a)
segs = []
for i in range(e_phnum):
    o = e_phoff + i * e_phentsize
    p_type, p_off, p_va, _, p_fsz, _, _, _ = struct.unpack_from('<8I', d, o)
    if p_type == 1:
        segs.append((p_off, p_va, p_fsz))

def off(va):
    for p_off, p_va, p_fsz in segs:
        if p_va <= va < p_va + p_fsz:
            return p_off + (va - p_va)
    return None

def cstr(va, maxlen=64):
    o = off(va)
    if o is None:
        return None
    e = d.find(b'\x00', o, o + maxlen)
    return d[o:e].decode('utf8', 'replace') if e >= 0 else None

i = d.find(b'\x00headphones\x00')
if i < 0:
    print("FAIL: cannot find the 'headphones' string in the binary"); sys.exit(1)
va_head = None
for p_off, p_va, p_fsz in segs:
    if p_off <= i + 1 < p_off + p_fsz:
        va_head = p_va + (i + 1 - p_off); break
if va_head is None:
    print("FAIL: cannot map the probe string to a vaddr"); sys.exit(1)

hits = [o for o in range(0, len(d) - 4, 4)
        if struct.unpack_from('<I', d, o)[0] == va_head]
if not hits:
    print("FAIL: cannot locate device_table in the binary"); sys.exit(1)

start = hits[0]
while start > 4:
    pv = struct.unpack_from('<I', d, start - 4)[0]
    s = cstr(pv) if 0x1000 < pv < len(d) else None
    if not s or any(ord(c) < 32 or ord(c) > 126 for c in s):
        break
    start -= 4

bin_tab = []
for k in range(0, 256):
    v = struct.unpack_from('<I', d, start + k * 4)[0]
    s = cstr(v) if 0x1000 < v < len(d) else None
    if s is None or (s and any(ord(c) < 32 or ord(c) > 126 for c in s)):
        break
    bin_tab.append(s)

# ---- 4. compare, accounting for the deliberate insertion -----------------
#
# The Leo device is appended at the end of the OUT range, so every CAPTURE
# device index shifts by exactly one relative to the shipped binary.  That is
# expected.  What must hold is:
#   (a) every index BELOW the new device matches exactly, and
#   (b) every index AT OR ABOVE it is the shipped entry shifted by exactly the
#       number of inserted OUT devices -- i.e. nothing else moved.
LEO = "SND_DEVICE_OUT_LEO_HIFI_HEADPHONES"
shift = 0
cut = len(bin_tab)
if LEO in idx:
    cut = idx[LEO]
    shift = 1

head_bad = [(k, src_tab[k], bin_tab[k])
            for k in range(min(cut, len(bin_tab)))
            if k in src_tab and src_tab[k] != bin_tab[k]]
if head_bad:
    print("FAIL: source/binary device_table diverges below the inserted device "
          "at %d index/indices" % len(head_bad))
    for k, a, b in head_bad[:8]:
        print("        [%3d] src=%-32r bin=%r" % (k, a, b))
    sys.exit(1)
print("PASS: source device_table matches the binary at all %d indices below the "
      "insertion point" % min(cut, len(bin_tab)))

if shift:
    tail_bad = [(k, src_tab.get(k + shift), bin_tab[k])
                for k in range(cut, len(bin_tab))
                if (k + shift) in src_tab and src_tab[k + shift] != bin_tab[k]]
    if tail_bad:
        print("FAIL: entries above the insertion point are not a clean +%d shift "
              "(%d mismatch(es)); something other than the new device moved"
              % (shift, len(tail_bad)))
        for k, a, b in tail_bad[:8]:
            print("        bin[%3d]=%-28r != src[%3d]=%r" % (k, b, k + shift, a))
        sys.exit(1)
    print("PASS: every entry above the insertion point is a clean +%d shift "
          "(only the new device was added)" % shift)
    print("PASS: inserted device is %r at index %d" % (src_tab.get(cut), cut))
sys.exit(0)
PYEOF
        [ $? -eq 0 ] || rc=1
    fi
else
    echo "SKIP: no device binary supplied; source/binary cross-check not run"
fi

echo
if [ $rc -eq 0 ]; then
    echo "verify-m3-source-layout: ALL CHECKS PASSED"
else
    echo "verify-m3-source-layout: FAILURES PRESENT"
fi
exit $rc
