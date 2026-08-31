#!/bin/sh
# Stage 2 deploy: swap in the schema3 audio HAL.
#
# Refuses to do anything without --i-have-authorization. Without it this is a
# preflight report only.
#
# 2026-08-31 修订（Codex 对抗式审查 §5.B）。此前的三处假成功路径已修：
#   - sh_() 把 adb 放在管道里，退出码恒为 0 —— 所有远端失败被吞掉
#   - service_cycle() 只看 init.svc 是否 running，"重启失败但旧进程仍在跑"判成功
#   - 映射断言只比对文件名，不证明映射的是新写入的那个 inode
# 关键写入改用 shx_（失败即中止），重启要求 pid:starttime 身份变化，
# 运行期核验比对 inode。
#
# 诚实边界：INT/TERM trap 覆盖不了 USB 断线、主机进程被强杀、断电。
# 本脚本不承诺"绝不留下未知状态"，只承诺"失败时不谎报成功"。
# 中断后请手动运行 rollback-hal.sh 并核对其输出。
set -u
HERE=$(cd "$(dirname "$0")" && pwd); . "$HERE/common.sh"
GO=0; [ "${1:-}" = "--i-have-authorization" ] && GO=1

say "=== Stage 2 部署 schema3 HAL ==="
[ $GO -eq 1 ] || say "*** 预检模式：不会写入任何东西。加 --i-have-authorization 才真正部署。***"
say

preflight || die "前置断言未全过——拒绝部署"
say
BOOT_BEFORE=$(boot_id)
say "  基线: boot_id=$BOOT_BEFORE audioserver=$(proc_ident "$(as_pid)") hal=$(proc_ident "$(hal_pid)")"

[ $GO -eq 1 ] || { say; say "预检全过。确认后加 --i-have-authorization 重跑。"; exit 0; }

trap 'bad "异常中断——尝试回退，之后请人工核对 rollback 输出"; sh "$HERE/rollback-hal.sh" --force-restart; exit 1' INT TERM

say
say "== 1. 双份备份 =="
shx_ "mkdir -p /data/local/tmp" >/dev/null || die "mkdir 失败"
shx_ "cp -f $HAL $DEV_BACKUP"   >/dev/null || die "设备内备份写入失败"
need "设备内备份 hash" "$STOCK_SHA" "$(sh_ "sha256sum $DEV_BACKUP" | cut -d' ' -f1)" || die "设备内备份校验失败"
ok "主机副本已在 $HOST_STOCK（前置已验 hash）"

say
say "== 2. 推入候选并在设备上验 hash =="
push_ "$CANDIDATE" /data/local/tmp/cand.so || die "push 失败"
need "推入后设备侧 hash" "$CAND_SHA" "$(sh_ 'sha256sum /data/local/tmp/cand.so' | cut -d' ' -f1)" || die "传输损坏"

say
say "== 3. 写入 system 分区 =="
shx_ 'mount -o rw,remount /' >/dev/null || die "remount rw 失败"
shx_ "cp -f /data/local/tmp/cand.so $HAL" >/dev/null || { bad "写入失败"; sh "$HERE/rollback-hal.sh" --force-restart; exit 1; }
shx_ "chown $OWNER:$OWNER $HAL" >/dev/null || { bad "chown 失败"; sh "$HERE/rollback-hal.sh" --force-restart; exit 1; }
shx_ "chmod $MODE $HAL"         >/dev/null || { bad "chmod 失败"; sh "$HERE/rollback-hal.sh" --force-restart; exit 1; }
shx_ "chcon $CTX $HAL"          >/dev/null || { bad "chcon 失败"; sh "$HERE/rollback-hal.sh" --force-restart; exit 1; }
shx_ 'mount -o ro,remount /'    >/dev/null || { bad "remount ro 失败——分区仍可写"; sh "$HERE/rollback-hal.sh" --force-restart; exit 1; }
postcheck "$CAND_SHA" || { bad "落盘核验失败"; sh "$HERE/rollback-hal.sh" --force-restart; exit 1; }

say
say "== 4. 重启服务（要求身份变化，不接受旧进程仍在跑）=="
if ! service_cycle; then bad "重启未真正发生"; sh "$HERE/rollback-hal.sh" --force-restart; exit 1; fi
ok "audioserver=$(as_pid)  hal_svc=$(hal_pid)"

say
say "== 5. 运行期核验 =="
rc=0
need "服务进程映射的正是新写入的 inode" "$(hal_inode)" "$(hal_mapped_inode)" || rc=1
need "未发生重启"  "$BOOT_BEFORE" "$(boot_id)" || rc=1
need "205 音量基线未被改动" "$VOLUME_BASELINE" "$(volume)" || rc=1
need "lib64 未被动过" "$HAL64_SIZE" "$(sh_ "stat -c %s $HAL64")" || rc=1
if [ $rc -ne 0 ]; then bad "运行期核验失败"; sh "$HERE/rollback-hal.sh" --force-restart; exit 1; fi

say
say "== 6. schema3 可达性探针（只读） =="
st=$(sh_ 'dumpsys media.audio_flinger 2>/dev/null | grep -m1 leo_hifi')
if [ -n "$st" ]; then ok "AudioFlinger 侧出现 leo_hifi 参数"
else say "  [注意] AudioFlinger 转储中未见 leo_hifi。需用 Stage 1 应用读 leo_hifi_status 才能定论。"; fi

say
say "=== 部署完成。设备现运行 schema3 HAL（降级构建，仅供功能验证）。 ==="
say "    回退: sh $HERE/rollback-hal.sh"
