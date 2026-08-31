#!/bin/bash
# Reproducible Gate 2: link a real audio.primary.msm8994.so and compare it to
# the module the device actually ships. Fail-closed on every input.
#
# usage: verify-gate2-link.sh <gate2-workspace> <aosp-headers-root> [run-dir]
#
# The workspace must contain: lib/ (12 device libraries), src/hal-tree (the HAL
# git tree at the pinned commit, CLEAN), kheaders/sound (real kernel uapi
# headers), patches/ (the five M3 patches), evidence/reference-*.so, elfinfo.py
# and SHA256SUMS.
#
# NOT a deployment gate. A module that links is not a module that loads.
set -euo pipefail

BASE_COMMIT=7f4cac748b6f62897294cdaece9d1aec27e1e927
LD=${M3_ELF_LD:-/opt/homebrew/bin/ld.lld}

[ "$#" -ge 2 ] || { echo "usage: $0 <gate2-workspace> <aosp-headers-root> [run-dir]" >&2; exit 2; }
G=$(cd "$1" && pwd)
H=$(cd "$2" && pwd)
RUN=${3:-$G/run-$(date +%Y%m%d-%H%M%S)}
[ -e "$RUN" ] && { echo "FAIL: run dir already exists: $RUN" >&2; exit 1; }
mkdir -p "$RUN/out"
echo "RUN=$RUN"

fail() { echo "FAIL: $*" >&2; exit 1; }
[ -x "$LD" ] || fail "no ELF linker at $LD (set M3_ELF_LD)"

# ---- 1. input identity -------------------------------------------------
commit=$(git -C "$G/src/hal-tree" rev-parse HEAD)
[ "$commit" = "$BASE_COMMIT" ] || fail "hal-tree is at $commit, expected $BASE_COMMIT"
[ -z "$(git -C "$G/src/hal-tree" status --porcelain)" ] || fail "hal-tree is not clean"
( cd "$G" && shasum -a 256 -c SHA256SUMS >/dev/null ) || fail "input SHA256 mismatch"
n=$(ls "$G"/patches/000*.patch 2>/dev/null | wc -l | tr -d ' ')
[ "$n" = 5 ] || fail "expected five M3 patches, found $n"

# ---- 2. isolated tree + patches ---------------------------------------
cp -R "$G/src/hal-tree" "$RUN/hal-tree"
for p in "$G"/patches/000*.patch; do
    git -C "$RUN/hal-tree" apply --check "$p" || fail "patch does not apply: $(basename "$p")"
    git -C "$RUN/hal-tree" apply "$p"
done

# ---- 3. compile --------------------------------------------------------
# HW_VARIANTS_ENABLED is NOT a device-tree switch: hal/Android.mk sets
# MULTIPLE_HW_VARIANTS_ENABLED unconditionally for the msm8974 B-family block
# that msm8994 belongs to. Omitting it makes hw_info_init() expand to (0),
# which kills the platform_init() branch holding audio_route_init().
DEFS=(-DPLATFORM_MSM8994 -DUSE_VENDOR_EXTN -DLEO_HIFI_ENABLED -DHW_VARIANTS_ENABLED
  -DPCM_OFFLOAD_ENABLED -DPCM_OFFLOAD_ENABLED_24 -DFLUENCE_ENABLED
  -DAFE_PROXY_ENABLED -DKPI_OPTIMIZE_ENABLED -DHFP_ENABLED
  -DMULTI_VOICE_SESSION_ENABLED -DCOMPRESS_VOIP_ENABLED
  -DAUDIO_EXTN_FORMATS_ENABLED -DENABLE_EXTENDED_COMPRESS_FORMAT
  -DFLAC_OFFLOAD_ENABLED -DCOMPRESS_METADATA_NEEDED -DDOLBY_ACDB_LICENSE)
CFLAGS=(-target armv7a-linux-androideabi -nostdlibinc -D__ANDROID__ -D_GNU_SOURCE
  -Werror=implicit-function-declaration -Werror=int-conversion
  -Werror=incompatible-pointer-types -Werror=return-type
  -Wno-unused-variable -Wno-macro-redefined -fPIC -Os -fcommon
  -D_FORTIFY_SOURCE=2 -fstack-protector-strong)
INC=(-I"$G/kheaders")
for d in system/core/include system/core/libcutils/include system/core/libprocessgroup/include \
  hardware/libhardware/include system/media/audio/include system/media/audio_effects/include \
  system/media/audio_route/include system/media/audio_utils/include external/tinyalsa/include \
  external/expat/lib external/tinycompress/include bionic/libc/include bionic/libc/kernel/uapi \
  bionic/libc/kernel/android/uapi bionic/libc/kernel/uapi/asm-arm; do
    [ -d "$H/$d" ] || fail "header dir missing: $d"
    INC+=(-I"$H/$d")
done
T=$RUN/hal-tree
INC+=(-I"$T/hal" -I"$T/hal/msm8974" -I"$T/hal/audio_extn" -I"$T/hal/voice_extn")

SRCS=(hal/audio_hw.c hal/voice.c hal/platform_info.c hal/msm8974/platform.c
  hal/audio_extn/audio_extn.c hal/audio_extn/utils.c hal/msm8974/leo_hifi.c
  hal/edid.c hal/audio_extn/hfp.c hal/voice_extn/voice_extn.c
  hal/voice_extn/compress_voip.c hal/msm8974/hw_info.c)

B=$H/bionic/libc/arch-common/bionic
# --gc-sections at link time reclaims the unused atexit/pthread_atfork paths,
# so only __cxa_finalize joins the undefined set - matching the factory module,
# which has __cxa_finalize but not __cxa_atexit.
clang -target armv7a-linux-androideabi -mthumb -fPIC -ffunction-sections -fdata-sections \
  -I"$H/bionic/libc/include" -I"$B" -c "$B/crtbegin_so.c" -o "$RUN/out/crtbegin_so.o" || fail "CC crtbegin_so.c"
clang -target armv7a-linux-androideabi -mthumb -fPIC \
  -c "$B/crtend_so.S" -o "$RUN/out/crtend_so.o" || fail "CC crtend_so.S"

OBJS=()
for f in "${SRCS[@]}"; do
    o=$RUN/out/$(echo "$f" | tr '/' '_' | sed 's/\.c$/.o/')
    clang "${CFLAGS[@]}" "${DEFS[@]}" "${INC[@]}" -c "$T/$f" -o "$o" || fail "CC $f"
    OBJS+=("$o")
done
echo "compiled ${#OBJS[@]} objects"

# ---- 4. link -----------------------------------------------------------
NEW=$RUN/out/audio.primary.msm8994.so
"$LD" -shared --gc-sections -soname audio.primary.msm8994.so -o "$NEW" \
  "$RUN/out/crtbegin_so.o" "${OBJS[@]}" "$RUN/out/crtend_so.o" \
  -L"$G/lib" -lc -lcutils -ldl -lexpat -lhardware -llog -lm \
  -lprocessgroup -ltinyalsa -laudioroute -ltinycompress || fail "link failed"

{
  echo "base_commit=$BASE_COMMIT"
  clang --version | head -1
  "$LD" --version | head -1
  echo "cflags=${CFLAGS[*]}"
  echo "defs=${DEFS[*]}"
  echo "sources=${SRCS[*]}"
  echo "--- input hashes ---"
  cat "$G/SHA256SUMS"
} > "$RUN/provenance.txt"

# ---- 5. verify the artefact -------------------------------------------
REF=$(ls "$G"/evidence/reference-*.so | head -1)
python3 - "$NEW" "$REF" "$G" <<'PY' || exit 1
import sys, glob, struct
new, ref, G = sys.argv[1], sys.argv[2], sys.argv[3]
exec(open(G + '/elfinfo.py').read().split('a=parse')[0])
n, r = parse(new), parse(ref)
bad = []
if n['soname'] != 'audio.primary.msm8994.so': bad.append('SONAME=%s' % n['soname'])
if 'HMI' not in n['defined']: bad.append('HMI not exported')

# Symbol closure is a DANGEROUS proxy on its own: dead-code elimination removes
# calls silently, so missing code produces no undefined symbol. Assert that the
# symbols a working platform_init must reference are actually referenced.
REQUIRED = ['audio_route_init', 'mixer_open', 'dlopen', 'dlsym', 'dlerror',
            'malloc', '__android_log_print', '__cxa_finalize']
missing = [s for s in REQUIRED if s not in n['undef']]
if missing: bad.append('required references absent (dead code?): %s' % missing)

for s in ('leo_hifi_init', 'leo_hifi_on_route'):
    if s not in n['defined']: bad.append('M3 symbol not exported: %s' % s)

pool = set()
for p in glob.glob(G + '/lib/*.so'): pool |= set(parse(p)['defined'])
unmet = sorted(set(n['undef']) - pool)
if unmet: bad.append('undefined symbols no device library provides: %s' % unmet)

d = open(new,'rb').read()
sh,=struct.unpack_from('<I',d,0x20); es,=struct.unpack_from('<H',d,0x2E)
cnt,=struct.unpack_from('<H',d,0x30); si,=struct.unpack_from('<H',d,0x32)
secs=[struct.unpack_from('<10I',d,sh+i*es) for i in range(cnt)]
so=secs[si][4]
names=[d[so+s[0]:].split(b'\0')[0].decode() for s in secs]
if '.fini_array' not in names: bad.append('.fini_array missing (crt not linked?)')

print('undefined=%d (factory %d)  exported=%d (factory %d)  shared=%d'
      % (len(n['undef']), len(r['undef']), len(n['defined']), len(r['defined']),
         len(set(n['defined']) & set(r['defined']))))
if bad:
    for b in bad: print('FAIL: ' + b)
    sys.exit(1)
print('artefact checks OK')
PY

echo "PASS  ($NEW)"
