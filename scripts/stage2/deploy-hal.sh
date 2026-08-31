#!/bin/sh
# Stage 2 deploy: swap in the schema3 audio HAL.
#
# Refuses to do anything without --i-have-authorization. Without it this is a
# preflight report only. Any failure after the first write triggers rollback
# automatically; the script never leaves the device in an unknown state.
#
# The candidate is a DEGRADED build (ARMv7 baseline vs stock ARMv8-A, no
# BIND_NOW, sound_trigger compiled out). It loads -- all 133 undefined symbols
# resolve inside the strict NEEDED closure and the float ABI matches exactly --
# but it is a functional probe, not a shippable artifact. See
# docs/verification/2026-08-31-hal-abi-gate.md.
set -u
HERE=$(cd "$(dirname "$0")" && pwd); . "$HERE/common.sh"
GO=0; [ "${1:-}" = "--i-have-authorization" ] && GO=1

say "=== Stage 2 部署 schema3 HAL ==="
[ $GO -eq 1 ] || say "*** 预检模式：不会写入任何东西。加 --i-have-authorization 才真正部署。***"
say

preflight || die "前置断言未全过——拒绝部署"
say
BOOT_BEFORE=$(boot_id); AS_BEFORE=$(as_pid); HAL_BEFORE=$(hal_pid)
say "  基线: boot_id=$BOOT_BEFORE audioserver=$AS_BEFORE hal_svc=$HAL_BEFORE"

[ $GO -eq 1 ] || { say; say "预检全过。确认后加 --i-have-authorization 重跑。"; exit 0; }

trap 'bad "异常中断——执行回退"; sh "$HERE/rollback-hal.sh"; exit 1' INT TERM

say
say "== 1. 双份备份 =="
sh_ "mkdir -p $(dirname $DEV_BACKUP); cp -f $HAL $DEV_BACKUP"
need "设备内备份 hash" "$STOCK_SHA" "$(sh_ "sha256sum $DEV_BACKUP" | cut -d' ' -f1)" || die "设备内备份失败"
ok "主机副本已在 $HOST_STOCK（前置已验 hash）"

say
say "== 2. 推入候选并在设备上验 hash =="
$ADB -s "$SERIAL" push "$CANDIDATE" /data/local/tmp/cand.so >/dev/null 2>&1 || die "push 失败"
need "推入后设备侧 hash" "$CAND_SHA" "$(sh_ 'sha256sum /data/local/tmp/cand.so' | cut -d' ' -f1)" || die "传输损坏"

say
say "== 3. 写入 system 分区 =="
sh_ 'mount -o rw,remount /' || die "remount rw 失败"
sh_ "cp -f /data/local/tmp/cand.so $HAL; chown $OWNER:$OWNER $HAL; chmod $MODE $HAL; chcon $CTX $HAL"
sh_ 'mount -o ro,remount /'
postcheck "$CAND_SHA" || { bad "落盘核验失败"; sh "$HERE/rollback-hal.sh"; exit 1; }

say
say "== 4. 重启服务 =="
if ! service_cycle; then bad "服务未回到 running"; sh "$HERE/rollback-hal.sh"; exit 1; fi
ok "audioserver=$(as_pid)  hal_svc=$(hal_pid)"

say
say "== 5. 运行期核验 =="
rc=0
need_ge "新 HAL 已被映射（dlopen 成功）" 1 "$(hal_mapped)" || rc=1
need "未发生重启"  "$BOOT_BEFORE" "$(boot_id)" || rc=1
need "205 音量基线未被改动" "$VOLUME_BASELINE" "$(volume)" || rc=1
need "lib64 未被动过" "$HAL64_SIZE" "$(sh_ "stat -c %s $HAL64")" || rc=1
if [ $rc -ne 0 ]; then bad "运行期核验失败"; sh "$HERE/rollback-hal.sh"; exit 1; fi

say
say "== 6. schema3 可达性探针（只读） =="
st=$(sh_ 'dumpsys media.audio_flinger 2>/dev/null | grep -m1 leo_hifi')
if [ -n "$st" ]; then ok "AudioFlinger 侧出现 leo_hifi 参数: $st"
else say "  [注意] AudioFlinger 转储中未见 leo_hifi。需用 Stage 1 应用读 leo_hifi_status 才能定论。"; fi

say
say "=== 部署完成。设备现运行 schema3 HAL（降级构建，仅供功能验证）。 ==="
say "    回退随时可用: sh $HERE/rollback-hal.sh"
