#!/bin/sh
# Local dry run of deploy + rollback against mock-adb.sh. No device involved.
# Exercises the happy path and four injected failures.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
STOCK=/Users/km/Desktop/Leo-Audio-OS/resources/private/phase5b-mokee/selected/system/vendor/lib/hw/audio.primary.msm8994.so
CAND=/Users/km/Documents/Codex/2026-08-31/users-km-documents-codex-leo-audio/outputs/hifi-eight-way-20260831/diagnostic-candidates/final-hal-on/audio.primary.msm8994.so

setup() {
  R=$1; rm -rf "$R"; mkdir -p "$R/fs/system/vendor/lib/hw" "$R/fs/system/vendor/lib64/hw" "$R/fs/data/local/tmp"
  cp "$STOCK" "$R/fs/system/vendor/lib/hw/audio.primary.msm8994.so"
  # lib64 只需尺寸正确
  mkfile_size=187784; dd if=/dev/zero of="$R/fs/system/vendor/lib64/hw/audio.primary.msm8994.so" bs=1 count=$mkfile_size 2>/dev/null
  echo 68f5f468 > "$R/serial"
  echo "245a2267-e200-4484-81f8-1b0b7ba2f0e1" > "$R/boot_id"
  echo 6378 > "$R/as_pid"; echo 6379 > "$R/hal_pid"
  echo "Volume: 205 205 (dsrange 0->255)" > "$R/volume"
  echo "/dev/block/mmcblk0p41 / ext4 ro,seclabel,nodev,relatime,discard 0 0" > "$R/mount_state"; echo ro > "$R/mount_ro"
  echo "u:object_r:vendor_file:s0" > "$R/ctx"; echo 644 > "$R/mode"; echo root > "$R/owner"
  echo running > "$R/svc_as"; echo running > "$R/svc_hal"; echo 1 > "$R/mapped"
  shasum -a 256 "$STOCK" | cut -d' ' -f1 > "$R/stock_sha"
}
run() { # run <label> <MOCK_FAIL> <args...>
  label=$1; fail=$2; shift 2
  R=/private/tmp/claude-501/-Users-km-Desktop-Leo-Audio-OS/12edf412-1f36-4e20-9e88-56cf1f28dbcf/scratchpad/mockdev
  setup "$R"
  printf '\n############ %s (MOCK_FAIL=%s) ############\n' "$label" "${fail:-none}"
  MOCK_ROOT=$R MOCK_FAIL=$fail ADB="$HERE/mock-adb.sh" sh "$@" ; rc=$?
  final=$(shasum -a 256 "$R/fs/system/vendor/lib/hw/audio.primary.msm8994.so" | cut -d' ' -f1)
  stock=$(cat "$R/stock_sha")
  printf -- '---- 退出码 %s ；结束时设备上的 HAL = %s ----\n' "$rc" \
    "$([ "$final" = "$stock" ] && echo '原版（已回退或未部署）' || echo '候选 schema3')"
}

run "A 预检模式（不写入）"        ""        "$HERE/deploy-hal.sh"
run "B 正常部署"                  ""        "$HERE/deploy-hal.sh" --i-have-authorization
run "C 传输损坏 → 应中止"         corrupt   "$HERE/deploy-hal.sh" --i-have-authorization
run "D remount 失败 → 应中止"     remount   "$HERE/deploy-hal.sh" --i-have-authorization
run "E dlopen 失败 → 应自动回退"  dlopen    "$HERE/deploy-hal.sh" --i-have-authorization
run "F 服务起不来 → 应自动回退"   service   "$HERE/deploy-hal.sh" --i-have-authorization
run "G 空跑回退（本来就是原版）"  ""        "$HERE/rollback-hal.sh"
