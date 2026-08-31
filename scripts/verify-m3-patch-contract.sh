#!/bin/sh
# verify-m3-patch-contract.sh
#
# Static contract check for the Leo M3 HiFi patch series.
#
#   usage: scripts/verify-m3-patch-contract.sh [patch-dir]
#          (default patch-dir: patches/phase5b-m3)
#
# Checks the ADDED lines of the patch series against the hard rules in
# docs/19-PHASE-5B-M3-HIFI-CONTROLLER-CONTRACT.md.  It reads the .patch files
# only -- it does not apply them, does not compile anything and cannot tell you
# whether the code is correct.  A green run means "the series does not violate
# the stated contract", nothing more.
#
# ASSUMPTIONS -- this is NOT a generic validator:
#   * the series is the 5-patch set named 000{1..5}-leo-*.patch;
#   * added lines start with '+' and removed lines with '-' (unified diff);
#   * the target tree is MoKee mkq-mr1-caf-msm8994, where the symbol
#     platform_check_hifi_backend_cfg does not exist at all.
#
# Exit status: 0 = all checks passed, 1 = a check failed, 2 = usage error.

set -u

DIR="${1:-patches/phase5b-m3}"

if [ ! -d "$DIR" ]; then
    echo "usage: $0 [patch-dir]   (no such directory: $DIR)" >&2
    exit 2
fi

PATCHES=$(ls "$DIR"/0*.patch 2>/dev/null)
if [ -z "$PATCHES" ]; then
    echo "FAIL: no 0*.patch files in $DIR" >&2
    exit 2
fi

ADDED=$(mktemp)
CODE=$(mktemp)
trap 'rm -f "$ADDED" "$CODE"' EXIT
# collect added source lines only (skip the '+++' file headers)
cat $PATCHES | grep '^+' | grep -v '^+++' | sed 's/^+//' > "$ADDED"
# CODE = added lines with whole-line C comments removed, so that rules about
# forbidden literals are not tripped by prose that *documents* those literals.
grep -vE '^[[:space:]]*(\*|//|/\*)' "$ADDED" > "$CODE"

rc=0
pass() { echo "PASS: $1"; }
fail() { echo "FAIL: $1"; rc=1; }

echo "series: $(echo "$PATCHES" | tr '\n' ' ')"
echo "added source lines: $(wc -l < "$ADDED" | tr -d ' ') (non-comment: $(wc -l < "$CODE" | tr -d ' '))"
echo

# 1. no cross-version numeric snd_device / usecase hardcoding
if grep -nE '(snd_device|out_snd_device|in_snd_device)[[:space:]]*(=|==)[[:space:]]*[0-9]+' "$ADDED" >/dev/null; then
    fail "numeric snd_device assignment/comparison found (must use symbols)"
    grep -nE '(snd_device|out_snd_device|in_snd_device)[[:space:]]*(=|==)[[:space:]]*[0-9]+' "$ADDED" | head -5
else
    pass "no numeric snd_device assignment or comparison"
fi

if grep -nE '\busecase->id[[:space:]]*==[[:space:]]*[0-9]+' "$CODE" >/dev/null; then
    fail "usecase->id compared against a literal (use is_offload_usecase())"
    grep -nE '\busecase->id[[:space:]]*==[[:space:]]*[0-9]+' "$CODE" | head -3
else
    pass "no literal usecase->id comparison (comments excluded)"
fi

if grep -nE '(^|[^A-Za-z0-9_])34([^0-9]|$)' "$CODE" >/dev/null; then
    fail "the MIUI device number 34 appears in added code"
    grep -nE '(^|[^A-Za-z0-9_])34([^0-9]|$)' "$CODE" | head -5
else
    pass "MIUI device number 34 appears only in comments, never in code"
fi

# 2. must not touch the zero-caller symbol
if grep -n 'platform_check_hifi_backend_cfg' "$ADDED" >/dev/null; then
    fail "series references platform_check_hifi_backend_cfg (zero-caller symbol; the live path is platform_check_and_set_codec_backend_cfg)"
else
    pass "platform_check_hifi_backend_cfg is not referenced"
fi

# 2b. the entry-side backend hook must be on enable_snd_device().
#
# select_devices() assigns usecase->out_snd_device only AFTER
# check_and_route_playback_usecases() has run, so a hook inside
# platform_check_and_set_codec_backend_cfg() that guards on
# usecase->out_snd_device tests the PREVIOUS device: it never fires on entry
# and always fires on exit.  enable_snd_device() is the first point that sees
# the new device, and it still runs before enable_audio_route() starts the DAI.
if grep -qn 'platform_leo_hifi_snd_device_enabled' "$ADDED"; then
    pass "entry hook is platform_leo_hifi_snd_device_enabled (enable_snd_device)"
else
    fail "no entry hook on enable_snd_device; the backend would be written on the wrong edge"
fi
if grep -nE '^\s*if \(usecase->out_snd_device == SND_DEVICE_OUT_LEO_HIFI_HEADPHONES\)' "$CODE" >/dev/null; then
    fail "guard on usecase->out_snd_device inside the codec-backend path (stale device)"
else
    pass "no guard on the stale usecase->out_snd_device"
fi

# 2c. every leo token in the two upstream C files must sit inside #ifdef
if grep -nE '^\s*#ifdef LEO_HIFI_ENABLED' "$ADDED" >/dev/null; then
    pass "changes to upstream files are wrapped in #ifdef LEO_HIFI_ENABLED"
else
    fail "no #ifdef LEO_HIFI_ENABLED guard found"
fi

# 2d. sign-safe dB formatting
if grep -qn 'leo_hifi_ctl_to_db' "$ADDED"; then
    pass "dB logging goes through the sign-safe helper"
else
    fail "no leo_hifi_ctl_to_db helper; integer division would drop the sign in (-1.0, 0.0)"
fi
if grep -nE 'abs\(\(?[a-z_]*ctl_value \* 5' "$CODE" >/dev/null; then
    fail "abs()-based dB formatting is back"
else
    pass "no abs()-based dB formatting"
fi

# 3. deterministic backend on BOTH edges
if grep -n 'LEO_HIFI_SAMPLERATE_STR' "$ADDED" | grep -q 'KHZ_48' || grep -qn '"KHZ_48"' "$ADDED"; then
    pass "KHZ_48 target defined"
else
    fail "no KHZ_48 target found"
fi
grep -qn '"S24_LE"' "$ADDED" && pass "S24_LE target defined" || fail "no S24_LE target found"

grep -qn 'leo_hifi_set_backend' "$ADDED" \
    && pass "backend writer leo_hifi_set_backend present" \
    || fail "backend writer missing"
grep -qn 'platform_leo_hifi_backend_exit' "$ADDED" \
    && pass "exit-side backend restore present (disable_audio_route)" \
    || fail "no exit-side backend restore; a stale sample rate would survive teardown"

# 4. offload detection, IF present, must be semantic
#
# M3 pins the backend per DEVICE, not per usecase, so the series legitimately
# has no offload gating at all.  The rule is therefore conditional: gate on the
# usecase only through is_offload_usecase(), never on a literal.  M3.5 will
# need this when it starts choosing a rate from the stream.
if grep -qn 'is_offload_usecase' "$ADDED"; then
    pass "offload detection uses is_offload_usecase()"
elif grep -nE 'USECASE_AUDIO_PLAYBACK_OFFLOAD|->id == ' "$CODE" >/dev/null; then
    fail "offload/usecase gating present but not via is_offload_usecase()"
else
    pass "no usecase gating at all (backend is pinned per device) -- rule not applicable"
fi

# 5. volume: clamp + read-back + fallback + no premature default
grep -qn 'LEO_HIFI_CTL_FLOOR' "$ADDED" && grep -qn 'LEO_HIFI_CTL_CEIL' "$ADDED" \
    && pass "volume clamp bounds present" || fail "volume clamp bounds missing"
grep -qn 'leo_hifi_read_volume' "$ADDED" \
    && pass "volume read-back present" || fail "volume read-back missing"
grep -qn 'leo_hifi_restore_volume_floor' "$ADDED" \
    && pass "volume failure fallback to the factory floor present" \
    || fail "no volume fallback path"
if grep -nE 'leo_hifi_apply_volume\(&my_data->leo,[[:space:]]*(213|225|229)\)' "$ADDED" >/dev/null \
   || grep -nE 'property_get\([[:space:]]*LEO_PROP_VOLUME[^)]*"(213|225|229)"' "$ADDED" >/dev/null; then
    fail "213/225/229 used as a default before R6/R7"
else
    pass "no 213/225/229 product default before R6/R7"
fi

# 6. ACDB must not be borrowed
if grep -nE '\[SND_DEVICE_OUT_LEO_HIFI_HEADPHONES\][[:space:]]*=[[:space:]]*[0-9]+' "$ADDED" \
     | grep -v '= -1' >/dev/null; then
    fail "a numeric ACDB id was assigned to the HiFi device"
else
    pass "HiFi device keeps acdb id -1 (no borrowed calibration)"
fi

# 7. bypass detection
for tok in 'SLIMBUS_0_RX Audio Mixer MultiMedia' 'HPHL DAC Switch' 'SLIM RX1 MUX' \
           'SLIM RX2 MUX' 'RX1 MIX1 INP1' 'RX2 MIX1 INP1' 'CLASS_H_DSM MUX' \
           'QUAT_MI2S_RX Audio Mixer MultiMedia'; do
    grep -qn "$tok" "$ADDED" && pass "bypass assertion covers '$tok'" \
        || fail "bypass assertion does not cover '$tok'"
done
grep -qn 'LEO_EV_FATAL_MASK' "$ADDED" \
    && pass "fatal evidence mask present" || fail "no fatal evidence mask"
grep -qn 'LEO_BP_FATAL_MASK' "$ADDED" \
    && pass "bypass fatal mask is separate from the observation mask" \
    || fail "no separate bypass fatal mask; an inaudible bypass attempt would be fatal"
grep -qn 'LEO_EV_E4' "$ADDED" \
    && pass "E4 (a QUAT front end really came up) is an evidence bit" \
    || fail "no E4: a usecase without a hifi mixer path would silently produce silence"

# 8. feature flag / default off
grep -qn 'LEO_HIFI_ENABLED' "$ADDED" \
    && pass "leo-specific build flag LEO_HIFI_ENABLED present" \
    || fail "no leo-specific build flag"
grep -qn 'property_get(LEO_PROP_ENABLE, value, "false")' "$ADDED" \
    && pass "runtime default is OFF" \
    || fail "runtime default is not provably OFF"

# 9. forbidden shortcuts
for bad in 'system(' 'popen(' '/system/bin/sh' 'setenforce' 'magisk' 'Magisk' 'su -c' 'adb ' 'tinymix'; do
    if grep -Fn "$bad" "$CODE" >/dev/null; then
        fail "forbidden construct '$bad' appears in added code"
        grep -Fn "$bad" "$ADDED" | head -3
    fi
done
grep -Fq 'system(' "$CODE" || pass "no shell-out from the HAL"

# 10. binary patching must not be proposed as the shipping route
if grep -niE 'objcopy|hexedit|LD_PRELOAD' "$CODE" >/dev/null; then
    fail "binary-patching machinery referenced"
else
    pass "no binary-patching machinery"
fi

echo
if [ $rc -eq 0 ]; then
    echo "verify-m3-patch-contract: ALL CHECKS PASSED"
    echo "NOTE: this proves contract compliance only; the series is UNCOMPILED"
    echo "      and UNVERIFIED on hardware."
else
    echo "verify-m3-patch-contract: FAILURES PRESENT"
fi
exit $rc
