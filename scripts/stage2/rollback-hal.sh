#!/bin/sh
# Stage 2 rollback: put the stock audio HAL back and prove it is back.
# Safe to run at any time, including when nothing was deployed. Idempotent.
set -u
HERE=$(cd "$(dirname "$0")" && pwd); . "$HERE/common.sh"

say "=== Stage 2 回退 ==="
say "目标: $HAL 恢复为原版 $STOCK_SHA"

cur=$(hal_sha)
if [ "$cur" = "$STOCK_SHA" ]; then
  ok "现役已是原版，无需回退文件"
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

  sh_ 'mount -o rw,remount /' || die "remount rw 失败"
  if [ "$src" = device ]; then
    sh_ "cp -f $DEV_BACKUP $HAL"
  else
    $ADB -s "$SERIAL" push "$HOST_STOCK" /data/local/tmp/stock.so >/dev/null 2>&1 || die "push 失败"
    [ "$(sh_ 'sha256sum /data/local/tmp/stock.so' | cut -d' ' -f1)" = "$STOCK_SHA" ] || die "push 后 hash 不符"
    sh_ "cp -f /data/local/tmp/stock.so $HAL"
  fi
  sh_ "chown $OWNER:$OWNER $HAL; chmod $MODE $HAL; chcon $CTX $HAL"
  sh_ 'mount -o ro,remount /' || bad "remount ro 失败（不致命，但请人工确认）"
fi

say "-- 落盘核验 --"
postcheck "$STOCK_SHA" || die "回退后文件属性不符——人工介入"

say "-- 重启服务 --"
service_cycle || die "服务未在 30s 内回到 running——人工介入"
ok "audioserver=$(as_pid)  hal_svc=$(hal_pid)"

say "-- 运行期核验 --"
rc=0
need "HAL 已被映射进服务进程" "1" "$(hal_mapped)" || rc=1
need "205 音量基线"           "$VOLUME_BASELINE" "$(volume)" || rc=1
need "lib64 未被动过"         "$HAL64_SIZE" "$(sh_ "stat -c %s $HAL64")" || rc=1
[ $rc -eq 0 ] || die "回退后运行期核验未通过——人工介入"

say
say "=== 回退完成。设备已回到原版 HAL，205 基线保持。 ==="
