#!/bin/sh
# verify-m3-flag-off-equivalence.sh
#
#   usage: scripts/verify-m3-flag-off-equivalence.sh <patched-root> <pristine-root>
#
# Proves the strongest form of "feature OFF == stock": with LEO_HIFI_ENABLED
# undefined, every upstream file the series touches produces an IDENTICAL
# preprocessor token stream to the unpatched baseline.  Comments and whitespace
# are removed before comparison because they never reach the compiler.
#
# Not covered (by construction):
#   * hal/Android.mk -- a make file, not C.  Its change is a self-contained
#     ifeq block that only fires on AUDIO_FEATURE_ENABLED_LEO_HIFI := true.
#   * hal/msm8974/leo_hifi.{c,h} -- new files, not compiled with the flag off.
#
# ASSUMPTIONS: the only conditional introduced by the series is
# "#ifdef LEO_HIFI_ENABLED"; nested #if inside such a block is skipped with it.
#
# Exit status: 0 = token-identical, 1 = differs, 2 = usage error.

set -u
A="${1:-}"; B="${2:-}"
if [ -z "$A" ] || [ -z "$B" ]; then
    echo "usage: $0 <patched-root> <pristine-root>" >&2
    exit 2
fi

rc=0
for f in hal/msm8974/platform.h hal/msm8974/platform.c hal/audio_hw.c; do
    if [ ! -f "$A/$f" ] || [ ! -f "$B/$f" ]; then
        echo "FAIL: missing $f in one of the trees" >&2
        rc=1; continue
    fi
    printf "%-30s " "$(basename "$f")"
    python3 - "$A/$f" "$B/$f" <<'PYEOF'
import sys, re, difflib

def strip_ifdef(path):
    out = []; depth = 0
    for line in open(path, encoding='utf-8', errors='surrogateescape'):
        st = line.strip()
        if st.startswith('#ifdef LEO_HIFI_ENABLED'):
            depth += 1; continue
        if depth:
            if st.startswith('#if'):
                depth += 1; continue
            if st.startswith('#endif'):
                depth -= 1; continue
            continue
        out.append(line)
    if depth:
        print("FAIL: unbalanced #ifdef LEO_HIFI_ENABLED"); sys.exit(1)
    return "".join(out)

def toks(txt):
    txt = re.sub(r'/\*.*?\*/', ' ', txt, flags=re.S)
    txt = re.sub(r'//[^\n]*', ' ', txt)
    txt = re.sub(r'\n\s*#', '\n@HASH@ ', txt)   # keep directives distinguishable
    return txt.split()

a = toks(strip_ifdef(sys.argv[1]))
b = toks(open(sys.argv[2], encoding='utf-8', errors='surrogateescape').read())
if a == b:
    print("TOKEN-IDENTICAL (%d tokens)" % len(a)); sys.exit(0)
d = list(difflib.unified_diff(b, a, 'upstream', 'patched(flag off)', lineterm='', n=3))
print("DIFFERS"); print("\n".join("   " + x for x in d[:40])); sys.exit(1)
PYEOF
    [ $? -eq 0 ] || rc=1
done

echo
if [ $rc -eq 0 ]; then
    echo "verify-m3-flag-off-equivalence: FEATURE OFF IS TOKEN-IDENTICAL TO STOCK"
else
    echo "verify-m3-flag-off-equivalence: DIVERGENCE PRESENT"
fi
exit $rc
