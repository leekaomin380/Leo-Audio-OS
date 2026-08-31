#!/bin/bash
# Deliberately break each Gate 2 input and require verify-gate2-link.sh to
# reject it FOR THE RIGHT REASON. A non-zero exit alone proves nothing: a
# script can fail for an unrelated reason and still look like a working gate.
#
# usage: negative-gates-gate2.sh <gate2-workspace> <aosp-headers-root>
set -uo pipefail

[ "$#" -ge 2 ] || { echo "usage: $0 <gate2-workspace> <aosp-headers-root>" >&2; exit 2; }
G=$(cd "$1" && pwd)
H=$(cd "$2" && pwd)
VERIFY=$(cd "$(dirname "$0")" && pwd)/verify-gate2-link.sh
TMP=$(mktemp -d "${TMPDIR:-/tmp}/gate2-neg.XXXXXX")
pass=0; fail=0

# expect_fail <label> <regex the failure output must match> <verify script>
expect_fail() {
    local label=$1 want=$2 script=${3:-$VERIFY} out rc
    out=$(bash "$script" "$G" "$H" "$TMP/run-$RANDOM$RANDOM" 2>&1); rc=$?
    if [ "$rc" = 0 ]; then
        echo "  FAIL [$label]: verify PASSED but should have been rejected"; fail=$((fail+1)); return
    fi
    if printf '%s' "$out" | grep -qE "$want"; then
        echo "  ok   [$label]: rejected, reason matches /$want/"; pass=$((pass+1))
    else
        echo "  FAIL [$label]: rejected but for the WRONG reason"; fail=$((fail+1))
        printf '%s\n' "$out" | grep -E '^FAIL' | head -3 | sed 's/^/         /'
    fi
}

echo "=== negative gates ==="

echo "1. corrupted device library"
cp "$G/lib/libcutils.so" "$TMP/libcutils.bak"
printf '\x00' | dd of="$G/lib/libcutils.so" bs=1 seek=4096 count=1 conv=notrunc status=none
expect_fail "corrupt-lib" "input SHA256 mismatch"
cp "$TMP/libcutils.bak" "$G/lib/libcutils.so"

echo "2. dirty source tree"
echo "/* dirty */" >> "$G/src/hal-tree/hal/audio_hw.c"
expect_fail "dirty-tree" "hal-tree is not clean"
git -C "$G/src/hal-tree" checkout -- hal/audio_hw.c

echo "3. missing patch"
mv "$G/patches/0005-leo-add-status-and-fallback.patch" "$TMP/p5.bak"
expect_fail "missing-patch" "expected five M3 patches|input SHA256 mismatch"
mv "$TMP/p5.bak" "$G/patches/0005-leo-add-status-and-fallback.patch"

echo "4. surrogate kernel header instead of the device kernel's"
cp "$G/kheaders/sound/compress_params.h" "$TMP/cp.bak"
cp "$H/bionic/libc/kernel/uapi/sound/compress_params.h" "$G/kheaders/sound/compress_params.h"
expect_fail "surrogate-header" "input SHA256 mismatch"
cp "$TMP/cp.bak" "$G/kheaders/sound/compress_params.h"

# The regression this whole gate exists for. Dropping HW_VARIANTS_ENABLED still
# compiles and still links; hw_info_init() collapses to (0) and the branch
# holding audio_route_init() is eliminated. Symbol closure stays "clean"
# because absent code raises no undefined symbol. Only the required-reference
# assertion catches it.
echo "5. HW_VARIANTS_ENABLED dropped (silent dead-code elimination)"
sed -e "s/ -DHW_VARIANTS_ENABLED//" -e "s|hal/msm8974/hw_info.c||" "$VERIFY" > "$TMP/verify-nohw.sh"
expect_fail "no-hw-variants" "required references absent" "$TMP/verify-nohw.sh"

rm -rf "$TMP"
echo "=== $pass passed, $fail failed ==="
[ "$fail" = 0 ]
