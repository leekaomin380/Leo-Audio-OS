#!/bin/bash
# Gate 3 candidate set: build the three variants the integration ruling rests on
# and assert the relations between them.
#
#   ON       patched tree, LEO_HIFI_ENABLED   -> the M3 HAL candidate
#   OFF      patched tree, feature off        -> what every other board builds
#   STOCK    pristine 7f4cac74, no patches    -> upstream
#
# Asserts: ON links and passes every artefact check; OFF is byte-identical to
# STOCK (the patch series costs nothing when the feature is off); and ON is
# reproducible across two run directories of different path length, which is
# what catches __FILE__ leaking an absolute path into the binary.
#
#   usage: verify-m3-candidate-set.sh <gate2-workspace> <aosp-headers-root> [out-dir]
set -uo pipefail

[ "$#" -ge 2 ] || { echo "usage: $0 <gate2-workspace> <aosp-headers-root> [out-dir]" >&2; exit 2; }
G=$(cd "$1" && pwd)
H=$(cd "$2" && pwd)
OUT=${3:-$G/candidate-set-$(date +%Y%m%d-%H%M%S)}
V=$(cd "$(dirname "$0")" && pwd)/verify-gate2-link.sh
[ -e "$OUT" ] && { echo "FAIL: out dir exists: $OUT" >&2; exit 1; }
mkdir -p "$OUT"
fails=0
h() { shasum -a 256 "$1" | cut -d' ' -f1; }

build() { # build <label> <rundir-name> <env...>
    local label=$1 dir=$2; shift 2
    echo "--- building $label"
    if ! env "$@" bash "$V" "$G" "$H" "$OUT/$dir" > "$OUT/$label.log" 2>&1; then
        echo "  FAIL: $label did not build"; tail -5 "$OUT/$label.log" | sed 's/^/       /'
        fails=$((fails+1)); return 1
    fi
    cp "$OUT/$dir/out/audio.primary.msm8994.so" "$OUT/$label.so"
    echo "  ok   $label  $(h "$OUT/$label.so")"
}

build ON    on    M3_FEATURE=on  M3_PATCHES=1
build OFF   off   M3_FEATURE=off M3_PATCHES=1
build STOCK stock M3_FEATURE=off M3_PATCHES=0
# Deliberately long second run dir: the path length difference is the probe.
build ON2   on-second-run-directory-with-a-much-longer-name M3_FEATURE=on M3_PATCHES=1

echo
echo "=== relations ==="
if [ -f "$OUT/OFF.so" ] && [ -f "$OUT/STOCK.so" ]; then
    if cmp -s "$OUT/OFF.so" "$OUT/STOCK.so"; then
        echo "  ok   feature OFF is byte-identical to stock"
    else
        echo "  FAIL feature OFF differs from stock - the series is not free when disabled"
        fails=$((fails+1))
    fi
fi
if [ -f "$OUT/ON.so" ] && [ -f "$OUT/ON2.so" ]; then
    if cmp -s "$OUT/ON.so" "$OUT/ON2.so"; then
        echo "  ok   ON is reproducible across run directories of different length"
    else
        echo "  FAIL ON is path-dependent (check -ffile-prefix-map and __FILE__ use)"
        fails=$((fails+1))
    fi
fi
if [ -f "$OUT/ON.so" ] && [ -f "$OUT/OFF.so" ] && cmp -s "$OUT/ON.so" "$OUT/OFF.so"; then
    echo "  FAIL ON and OFF are identical - the feature build did nothing"
    fails=$((fails+1))
elif [ -f "$OUT/ON.so" ]; then
    echo "  ok   ON differs from OFF (the feature is actually compiled in)"
fi

{ echo "# M3 candidate set"; echo "generated_from=$G"; echo
  for l in ON OFF STOCK ON2; do [ -f "$OUT/$l.so" ] && echo "$l  $(h "$OUT/$l.so")"; done
} > "$OUT/CANDIDATES.txt"
cat "$OUT/CANDIDATES.txt"

echo
[ "$fails" = 0 ] && { echo "verify-m3-candidate-set: PASS  ($OUT)"; exit 0; }
echo "verify-m3-candidate-set: $fails FAILURE(S)"; exit 1
