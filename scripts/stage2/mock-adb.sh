#!/bin/sh
# Mock adb for the Stage 2 dry run. Models just enough of the device to exercise
# every branch of deploy-hal.sh and rollback-hal.sh without touching hardware.
# State lives under $MOCK_ROOT. Fault injection via $MOCK_FAIL.
set -u
: "${MOCK_ROOT:?MOCK_ROOT unset}"
: "${MOCK_FAIL:=}"
R=$MOCK_ROOT
sha() { shasum -a 256 "$1" | cut -d' ' -f1; }

case "${1:-}" in
  devices) echo "List of devices attached"; echo "$(cat $R/serial)	device"; exit 0;;
esac
# -s SERIAL <verb> ...
shift 2
verb=$1; shift
case "$verb" in
  push)
    src=$1; dst=$2
    [ "$MOCK_FAIL" = push ] && exit 1
    mkdir -p "$R/fs$(dirname "$dst")"; cp "$src" "$R/fs$dst"
    [ "$MOCK_FAIL" = corrupt ] && printf 'X' >> "$R/fs$dst"
    echo "1 file pushed"; exit 0;;
  shell) ;;
  *) exit 0;;
esac
handle() {
  c="$1"
HAL=$R/fs/system/vendor/lib/hw/audio.primary.msm8994.so
HAL64=$R/fs/system/vendor/lib64/hw/audio.primary.msm8994.so
case "$c" in
  "id -u")                 echo 0;;
  *"random/boot_id")       cat "$R/boot_id";;
  "pidof audioserver")     cat "$R/as_pid";;
  "pidof android.hardware.audio@2.0-service") cat "$R/hal_pid";;
  *"tinymix Volume"*)      cat "$R/volume";;
  *"/proc/mounts"*sed*)    cat "$R/mount_ro";;
  *"/proc/mounts"*)        cat "$R/mount_state";;
  *"sha256sum /system/vendor/lib/hw/"*) echo "$(sha "$HAL")  x";;
  *"sha256sum /data/local/tmp/leo-hal-backup"*) [ -f "$R/fs/data/local/tmp/leo-hal-backup" ] && echo "$(sha "$R/fs/data/local/tmp/leo-hal-backup")  x" || echo "";;
  *"sha256sum /data/local/tmp/cand.so"*)  echo "$(sha "$R/fs/data/local/tmp/cand.so")  x";;
  *"sha256sum /data/local/tmp/stock.so"*) echo "$(sha "$R/fs/data/local/tmp/stock.so")  x";;
  *"stat -c %s /system/vendor/lib64"*) stat -f%z "$HAL64";;
  *"stat -c %s"*)  stat -f%z "$HAL";;
  *"stat -c %a"*)  cat "$R/mode";;
  *"stat -c %U"*)  cat "$R/owner";;
  *"ls -Z"*)       echo "-rw-r--r-- 1 root root $(cat $R/ctx) 0 2009-01-01 08:00 x";;
  *"df /system"*awk*) echo 141912;;
  *"df /system"*)  echo "fs 1677160 1535248 141912 92% /";;
  *"mount -o rw,remount"*) [ "$MOCK_FAIL" = remount ] && exit 1; echo rw > "$R/rw"; echo rw > "$R/mount_ro"; echo "/dev/block/mmcblk0p41 / ext4 rw,seclabel 0 0" > "$R/mount_state";;
  *"mount -o ro,remount"*) rm -f "$R/rw"; echo ro > "$R/mount_ro"; echo "/dev/block/mmcblk0p41 / ext4 ro,seclabel,nodev,relatime,discard 0 0" > "$R/mount_state";;
  *"mkdir -p"*)    mkdir -p "$R/fs/data/local/tmp";;
  *"cp -f "*)
    s=$(echo "$c" | awk '{print $3}'); d=$(echo "$c" | awk '{print $4}')
    case "$d" in /system/*) [ -f "$R/rw" ] || { echo "cp: read-only file system" >&2; return 1; };; esac
    mkdir -p "$R/fs$(dirname "$d")"; cp "$R/fs$s" "$R/fs$d";;
  *"chown "*|*"chmod "*|*"chcon "*)
    case "$c" in *chcon*|*chmod*|*chown*) [ -f "$R/rw" ] || return 1;; esac
    echo "$c" | grep -q chcon && echo "$(echo "$c" | sed -E 's/.*chcon ([^ ]+).*/\1/')" > "$R/ctx"
    echo "$c" | grep -q chmod && echo "$(echo "$c" | sed -E 's/.*chmod ([0-9]+).*/\1/')" > "$R/mode";;
  *"setprop ctl.restart audioserver"*)
    [ "$MOCK_FAIL" = service ] && { echo stopped > "$R/svc_as"; exit 0; }
    # dlopen 失败模拟：候选 hash 不在允许加载集合内
    if [ "$MOCK_FAIL" = dlopen ] && [ "$(sha "$HAL")" != "$(cat $R/stock_sha)" ]; then
      echo stopped > "$R/svc_as"; echo stopped > "$R/svc_hal"; echo "" > "$R/hal_pid"; echo 0 > "$R/mapped"
    else
      echo running > "$R/svc_as"; echo running > "$R/svc_hal"
      echo $(( $(cat $R/as_pid) + 100 )) > "$R/as_pid"
      echo $(( $(cat $R/hal_pid 2>/dev/null || echo 6379) + 100 )) > "$R/hal_pid"
      echo 4 > "$R/mapped"
    fi;;
  *"getprop init.svc.audioserver"*)          cat "$R/svc_as";;
  *"getprop init.svc.vendor.audio-hal-2-0"*) cat "$R/svc_hal";;
  *"grep -c"*"maps"*)                        cat "$R/mapped";;
  *"dumpsys media.audio_flinger"*)
    if [ "$(sha "$HAL")" = "$(cat $R/stock_sha)" ]; then echo ""; else echo "  leo_hifi_status: schema=3;supported=1"; fi;;
  *) echo "";;
  esac
}
OLDIFS=$IFS; IFS=";"
for part in $*; do
  p2=$(printf %s "$part" | sed -E 's/^ +//; s/ +$//')
  [ -n "$p2" ] && handle "$p2"
done
IFS=$OLDIFS
exit 0
