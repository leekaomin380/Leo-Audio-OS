# Shared constants and assertions for the Stage 2 HAL swap.
# Every fact below was measured on the device, not assumed. See
# docs/verification/2026-08-31-hal-abi-gate.md for the evidence.

SERIAL=${LEO_SERIAL:-68f5f468}
HAL=/system/vendor/lib/hw/audio.primary.msm8994.so
HAL64=/system/vendor/lib64/hw/audio.primary.msm8994.so   # dead code: no process maps it
STOCK_SHA=701019bd222052051b89e00fbe0aca1a0aee4aad1fd0959a259a9f013e69af47
STOCK_SIZE=175296
CAND_SHA=bfd4c93471c78fc24cd4e9d4a862b69119bf734caec13595fcc4eeaeafa01c3d
HAL64_SIZE=187784
CTX=u:object_r:vendor_file:s0
MODE=644
OWNER=root
VOLUME_BASELINE="Volume: 205 205 (dsrange 0->255)"
DEV_BACKUP=/data/local/tmp/leo-hal-backup
HOST_STOCK=/Users/km/Desktop/Leo-Audio-OS/resources/private/phase5b-mokee/selected/system/vendor/lib/hw/audio.primary.msm8994.so
CANDIDATE=/Users/km/Documents/Codex/2026-08-31/users-km-documents-codex-leo-audio/outputs/hifi-eight-way-20260831/diagnostic-candidates/final-hal-on/audio.primary.msm8994.so

: "${ADB:=adb}"
sh_()  { $ADB -s "$SERIAL" shell "$@" 2>/dev/null | tr -d '\r'; }
say()  { printf '%s\n' "$*"; }
ok()   { printf '  [OK]   %s\n' "$*"; }
bad()  { printf '  [FAIL] %s\n' "$*" >&2; }
die()  { bad "$*"; exit 1; }

# 一个已 dlopen 的 .so 在 /proc/<pid>/maps 里占多行（r--/r-x/rw-/r--，实测 4 行），
# 行数随段布局而变。语义是"已被映射"，不是"恰好一行"。
need_ge() { # need_ge <description> <min> <actual>
  if [ "${3:-0}" -ge "$2" ] 2>/dev/null; then ok "$1 (映射 $3 行)"
  else bad "$1"; printf '         期望 >= %s，实际: %s\n' "$2" "$3" >&2; return 1; fi
}

need() { # need <description> <expected> <actual>
  if [ "$2" = "$3" ]; then ok "$1"
  else bad "$1"; printf '         期望: %s\n         实际: %s\n' "$2" "$3" >&2; return 1; fi
}

hal_sha()   { sh_ "sha256sum $HAL" | cut -d' ' -f1; }
hal_ctx()   { sh_ "ls -Z $HAL" | grep -oE 'u:object_r:[a-zA-Z0-9_]+:s0' | head -1; }
hal_size()  { sh_ "stat -c %s $HAL"; }
hal_mode()  { sh_ "stat -c %a $HAL"; }
hal_owner() { sh_ "stat -c %U $HAL"; }
volume()    { sh_ 'tinymix Volume' | tr -d '\n'; }
boot_id()   { sh_ 'cat /proc/sys/kernel/random/boot_id'; }
hal_pid()   { sh_ 'pidof android.hardware.audio@2.0-service'; }
as_pid()    { sh_ 'pidof audioserver'; }
hal_mapped(){ sh_ "grep -c 'audio.primary.msm8994' /proc/\$(pidof android.hardware.audio@2.0-service)/maps"; }
hifi_probe(){ sh_ 'dumpsys media.audio_flinger 2>/dev/null | grep -c leo_hifi'; }

preflight() {
  say "== 前置断言 =="
  rc=0
  need "设备在线且序列号匹配" "$SERIAL" "$($ADB devices | awk -v s=$SERIAL '$1==s{print $1}')" || rc=1
  need "adb 具备 root"        "0"       "$(sh_ 'id -u')" || rc=1
  need "/ 当前为只读"          "ro"      "$(sh_ "grep -m1 ' / ext4 ' /proc/mounts | sed -E 's/.* ext4 ([^,]+),.*/\\1/'")" || rc=1
  need "现役 HAL 是原版"       "$STOCK_SHA" "$(hal_sha)" || rc=1
  need "现役 HAL 尺寸"         "$STOCK_SIZE" "$(hal_size)" || rc=1
  need "SELinux 上下文"        "$CTX"    "$(hal_ctx)" || rc=1
  need "权限位"                "$MODE"   "$(hal_mode)" || rc=1
  need "属主"                  "$OWNER"  "$(hal_owner)" || rc=1
  need "205 音量基线"          "$VOLUME_BASELINE" "$(volume)" || rc=1
  need "lib64 版本未被动过"    "$HAL64_SIZE" "$(sh_ "stat -c %s $HAL64")" || rc=1
  [ -f "$HOST_STOCK" ] && need "主机原版副本 hash" "$STOCK_SHA" "$(shasum -a 256 "$HOST_STOCK" | cut -d' ' -f1)" || { bad "主机原版副本缺失"; rc=1; }
  [ -f "$CANDIDATE" ]  && need "候选 schema3 hash" "$CAND_SHA"  "$(shasum -a 256 "$CANDIDATE" | cut -d' ' -f1)"  || { bad "候选缺失"; rc=1; }
  avail=$(sh_ "df /system | tail -1 | awk '{print \$4}'")
  [ "${avail:-0}" -gt 10240 ] && ok "system 分区剩余 ${avail}K" || { bad "system 分区空间不足: ${avail}K"; rc=1; }
  return $rc
}

# 每次写入后都必须过这一关，否则立即回退
postcheck() { # postcheck <expected_sha>
  rc=0
  need "落盘 hash"        "$1"     "$(hal_sha)" || rc=1
  need "SELinux 上下文"   "$CTX"   "$(hal_ctx)" || rc=1
  need "权限位"           "$MODE"  "$(hal_mode)" || rc=1
  need "属主"             "$OWNER" "$(hal_owner)" || rc=1
  return $rc
}

service_cycle() {
  say "  重启 audioserver（其 init 规则含 onrestart restart vendor.audio-hal-2-0，会级联）"
  sh_ 'setprop ctl.restart audioserver'
  i=0
  while [ $i -lt 30 ]; do
    sleep 1; i=$((i+1))
    [ "$(sh_ 'getprop init.svc.audioserver')" = running ] \
      && [ "$(sh_ 'getprop init.svc.vendor.audio-hal-2-0')" = running ] \
      && [ -n "$(hal_pid)" ] && return 0
  done
  return 1
}
