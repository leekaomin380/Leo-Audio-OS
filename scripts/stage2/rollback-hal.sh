#!/bin/sh
# Stage 2 rollback: put the stock audio HAL back and prove it is back.
#
# 2026-08-31 修订（Codex 对抗式审查 §5.B）：此前无论文件是否被改动都无条件
# 重启 audioserver，所以它不是"未部署时安全空转"的工具 —— 空跑一次就会打断
# 正在播放的音频。现在只有真正回写了文件才重启；部署中途失败需要强制重启时
# 用 --force-restart 显式要求。
set -u
HERE=$(cd "$(dirname "$0")" && pwd); . "$HERE/common.sh"
FORCE_RESTART=0; [ "${1:-}" = "--force-restart" ] && FORCE_RESTART=1

say "=== Stage 2 回退 ==="
say "目标: $HAL 恢复为原版 $STOCK_SHA"

cur=$(hal_sha); [ $? -eq 0 ] || die "无法读取现役 HAL（adb 调用失败）——人工介入"
CHANGED=0

if [ "$cur" = "$STOCK_SHA" ]; then
  ok "现役已是原版，未回写文件"
else
  say "-- 选择回退源 --"
  src=""
  if [ "$(sh_ "sha256sum $DEV_BACKUP 2>/dev/null" | cut -d' ' -f1)" = "$STOCK_SHA" ]; then
    src=device; ok "设备内备份 $DEV_BACKUP 可用且 hash 正确"
  elif [ -f "$HOST_STOCK" ] && [ "$(shasum -a 256 "$HOST_STOCK" | cut -d' ' -f1)" = "$STOCK_SHA" ]; then
    src=host; ok "主机副本可用且 hash 正确"
  else
    die "两处回退源都不可用或 hash 不符——停止，不要盲目写入"
  fi

  shx_ 'mount -o rw,remount /' >/dev/null || die "remount rw 失败"
  if [ "$src" = device ]; then
    shx_ "cp -f $DEV_BACKUP $HAL" >/dev/null || die "回写失败"
  else
    push_ "$HOST_STOCK" /data/local/tmp/stock.so || die "push 失败"
    [ "$(sh_ 'sha256sum /data/local/tmp/stock.so' | cut -d' ' -f1)" = "$STOCK_SHA" ] || die "push 后 hash 不符"
    shx_ "cp -f /data/local/tmp/stock.so $HAL" >/dev/null || die "回写失败"
  fi
  shx_ "chown $OWNER:$OWNER $HAL" >/dev/null || die "chown 失败"
  shx_ "chmod $MODE $HAL"         >/dev/null || die "chmod 失败"
  shx_ "chcon $CTX $HAL"          >/dev/null || die "chcon 失败"
  shx_ 'mount -o ro,remount /'    >/dev/null || die "remount ro 失败——分区仍可写，人工介入"
  CHANGED=1
fi

say "-- 落盘核验 --"
postcheck "$STOCK_SHA" || die "回退后文件属性或挂载状态不符——人工介入"

if [ $CHANGED -eq 1 ] || [ $FORCE_RESTART -eq 1 ]; then
  say "-- 重启服务 --"
  service_cycle || die "服务身份未变化——重启未真正发生，人工介入"
  ok "audioserver=$(as_pid)  hal_svc=$(hal_pid)"
  say "-- 运行期核验 --"
  rc=0
  need "服务进程映射的正是磁盘上那个 inode" "$(hal_inode)" "$(hal_mapped_inode)" || rc=1
  need "205 音量基线"   "$VOLUME_BASELINE" "$(volume)" || rc=1
  need "lib64 未被动过" "$HAL64_SIZE" "$(sh_ "stat -c %s $HAL64")" || rc=1
  [ $rc -eq 0 ] || die "回退后运行期核验未通过——人工介入"
else
  say "-- 未回写文件，不重启服务（避免打断正在播放的音频）--"
  say "   若部署中途失败需要强制重启，用: $0 --force-restart"
fi

say
say "=== 回退完成。设备已回到原版 HAL，205 基线保持。 ==="
