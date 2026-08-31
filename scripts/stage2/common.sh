# Shared constants and assertions for the Stage 2 HAL swap.
# Every constant below was measured on the device, not assumed. See
# docs/verification/2026-08-31-hal-abi-gate.md for the evidence.
#
# 2026-08-31 修订（Codex 对抗式审查 §5.B）：此前 sh_() 把 adb 放在管道里，
# 退出码取自管道末端的 tr，恒为 0 —— adb 与远端命令的失败被完全吞掉。
# 实测：包装后退出码 0，直接调用 127。修法见下。同批修正的还有
# service_cycle() 的假成功、postcheck() 不查 remount-ro、以及
# 映射断言只比对文件名不比对 inode。

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

# ---- adb 调用：退出码必须穿透 -------------------------------------------
# 现代 adb 会把远端命令的退出码带回来，所以这层同时捕获传输失败与远端失败。
# 输出走变量而非管道，避免管道末端覆盖退出码。
LAST_ADB_RC=0
sh_() {
  _out=$($ADB -s "$SERIAL" shell "$@" 2>/dev/null); LAST_ADB_RC=$?
  printf '%s' "$_out" | tr -d '\r'
  return $LAST_ADB_RC
}

# 必须成功的远端命令用这个：失败即中止，不给后续断言机会掩盖。
shx_() {
  _out=$(sh_ "$@"); _rc=$?
  printf '%s' "$_out"
  if [ $_rc -ne 0 ]; then
    bad "远端命令失败 (rc=$_rc): $*"
    return $_rc
  fi
  return 0
}

push_() {
  $ADB -s "$SERIAL" push "$1" "$2" >/dev/null 2>&1
}

say()  { printf '%s\n' "$*"; }
ok()   { printf '  [OK]   %s\n' "$*"; }
bad()  { printf '  [FAIL] %s\n' "$*" >&2; }
die()  { bad "$*"; exit 1; }

need() { # need <description> <expected> <actual>
  if [ "$2" = "$3" ]; then ok "$1"
  else bad "$1"; printf '         期望: %s\n         实际: %s\n' "$2" "$3" >&2; return 1; fi
}

# 一个已 dlopen 的 .so 在 /proc/<pid>/maps 里占多行（r--/r-x/rw-/r--，实测 4 行），
# 行数随段布局而变。语义是"已被映射"，不是"恰好一行"。
need_ge() { # need_ge <description> <min> <actual>
  if [ "${3:-0}" -ge "$2" ] 2>/dev/null; then ok "$1 (映射 $3 行)"
  else bad "$1"; printf '         期望 >= %s，实际: %s\n' "$2" "$3" >&2; return 1; fi
}

hal_sha()   { sh_ "sha256sum $HAL" | cut -d' ' -f1; }
hal_ctx()   { sh_ "ls -Z $HAL" | grep -oE 'u:object_r:[a-zA-Z0-9_]+:s0' | head -1; }
hal_size()  { sh_ "stat -c %s $HAL"; }
hal_mode()  { sh_ "stat -c %a $HAL"; }
hal_owner() { sh_ "stat -c %U $HAL"; }
hal_inode() { sh_ "stat -c %i $HAL"; }
volume()    { sh_ 'tinymix Volume' | tr -d '\n'; }
boot_id()   { sh_ 'cat /proc/sys/kernel/random/boot_id'; }
hal_pid()   { sh_ 'pidof android.hardware.audio@2.0-service'; }
as_pid()    { sh_ 'pidof audioserver'; }
root_mount(){ sh_ "grep -m1 ' / ext4 ' /proc/mounts | sed -E 's/.* ext4 ([^,]+),.*/\\1/'"; }

# 映射行数（宽松判据，仅证明有同名映射）
hal_mapped(){ sh_ "grep -c 'audio.primary.msm8994' /proc/\$(pidof android.hardware.audio@2.0-service)/maps"; }

# 严格判据：证明服务进程映射的正是磁盘上那个 inode，而不是同名的别的东西，
# 也不是重启前那个进程遗留的旧映射。Codex §5.B 指出 >=1 只证明"有同名映射"。
hal_mapped_inode() {
  sh_ "grep -m1 'audio.primary.msm8994' /proc/\$(pidof android.hardware.audio@2.0-service)/maps | awk '{print \$5}'"
}

# 进程身份：pid + starttime（/proc/<pid>/stat 第 22 字段）。
# 只比 pid 会被 pid 复用骗过；starttime 一起比才能证明确实是新进程。
proc_ident() { # proc_ident <pid>
  [ -n "$1" ] || { printf 'none'; return 1; }
  sh_ "cat /proc/$1/stat 2>/dev/null | awk '{print \$1\":\"\$22}'"
}

preflight() {
  say "== 前置断言 =="
  rc=0
  need "设备在线且序列号匹配" "$SERIAL" "$($ADB devices | awk -v s=$SERIAL '$1==s{print $1}')" || rc=1
  uid=$(sh_ 'id -u'); [ $? -eq 0 ] || { bad "adb shell 调用本身失败"; return 1; }
  need "adb 具备 root"        "0"       "$uid" || rc=1
  need "/ 当前为只读"          "ro"      "$(root_mount)" || rc=1
  need "现役 HAL 是原版"       "$STOCK_SHA" "$(hal_sha)" || rc=1
  need "现役 HAL 尺寸"         "$STOCK_SIZE" "$(hal_size)" || rc=1
  need "SELinux 上下文"        "$CTX"    "$(hal_ctx)" || rc=1
  need "权限位"                "$MODE"   "$(hal_mode)" || rc=1
  need "属主"                  "$OWNER"  "$(hal_owner)" || rc=1
  need "205 音量基线"          "$VOLUME_BASELINE" "$(volume)" || rc=1
  need "lib64 版本未被动过"    "$HAL64_SIZE" "$(sh_ "stat -c %s $HAL64")" || rc=1
  need "服务进程映射的正是磁盘上那个 inode" "$(hal_inode)" "$(hal_mapped_inode)" || rc=1
  [ -f "$HOST_STOCK" ] && need "主机原版副本 hash" "$STOCK_SHA" "$(shasum -a 256 "$HOST_STOCK" | cut -d' ' -f1)" || { bad "主机原版副本缺失"; rc=1; }
  [ -f "$CANDIDATE" ]  && need "候选 schema3 hash" "$CAND_SHA"  "$(shasum -a 256 "$CANDIDATE" | cut -d' ' -f1)"  || { bad "候选缺失"; rc=1; }
  avail=$(sh_ "df /system | tail -1 | awk '{print \$4}'")
  [ "${avail:-0}" -gt 10240 ] && ok "system 分区剩余 ${avail}K" || { bad "system 分区空间不足: ${avail}K"; rc=1; }
  return $rc
}

# 每次写入后都必须过这一关，否则立即回退。
# 2026-08-31 增补：必须独立回读挂载状态。此前 remount-ro 失败会被静默放过。
postcheck() { # postcheck <expected_sha>
  rc=0
  need "落盘 hash"        "$1"     "$(hal_sha)" || rc=1
  need "SELinux 上下文"   "$CTX"   "$(hal_ctx)" || rc=1
  need "权限位"           "$MODE"  "$(hal_mode)" || rc=1
  need "属主"             "$OWNER" "$(hal_owner)" || rc=1
  need "/ 已恢复只读"      "ro"     "$(root_mount)" || rc=1
  return $rc
}

# 重启服务并证明确实换了进程。
# 2026-08-31 修订：此前只看 init.svc.* 是否 running 且 pid 非空，
# 于是"重启请求失败但旧进程仍在跑"会被判成功（Codex §5.B 实测复现）。
# 现在强制要求 pid+starttime 组成的身份发生变化。
service_cycle() {
  before_as=$(as_pid); before_hal=$(hal_pid)
  before_as_id=$(proc_ident "$before_as"); before_hal_id=$(proc_ident "$before_hal")
  say "  重启 audioserver（其 init 规则含 onrestart restart vendor.audio-hal-2-0，会级联）"
  say "  重启前身份: audioserver=$before_as_id  hal=$before_hal_id"
  sh_ 'setprop ctl.restart audioserver' >/dev/null
  if [ $LAST_ADB_RC -ne 0 ]; then bad "setprop ctl.restart 调用失败 (rc=$LAST_ADB_RC)"; return 1; fi
  i=0
  while [ $i -lt 30 ]; do
    sleep 1; i=$((i+1))
    now_as=$(as_pid); now_hal=$(hal_pid)
    [ -n "$now_as" ] && [ -n "$now_hal" ] || continue
    [ "$(sh_ 'getprop init.svc.audioserver')" = running ] || continue
    [ "$(sh_ 'getprop init.svc.vendor.audio-hal-2-0')" = running ] || continue
    now_as_id=$(proc_ident "$now_as"); now_hal_id=$(proc_ident "$now_hal")
    # 身份必须变化，否则说明重启根本没发生，只是旧进程还活着。
    if [ "$now_as_id" != "$before_as_id" ] && [ "$now_hal_id" != "$before_hal_id" ]; then
      say "  重启后身份: audioserver=$now_as_id  hal=$now_hal_id"
      return 0
    fi
  done
  bad "30s 内服务身份未发生变化（旧进程可能仍在跑，重启并未真正发生）"
  say "  当前身份: audioserver=$(proc_ident "$(as_pid)")  hal=$(proc_ident "$(hal_pid)")"
  return 1
}
