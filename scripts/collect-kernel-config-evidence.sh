#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
timestamp="$(date +%Y%m%d-%H%M%S)"
output_dir="${1:-${repo_root}/resources/private/kernel-config-evidence/${timestamp}-leo}"

if ! command -v adb >/dev/null 2>&1; then
  echo "adb was not found" >&2
  exit 1
fi

connected_devices=()
while IFS= read -r device_serial; do
  connected_devices+=("${device_serial}")
done < <(adb devices | awk '$2 == "device" {print $1}')

if [[ "${#connected_devices[@]}" -ne 1 ]]; then
  echo "expected exactly one authorized Android device; found ${#connected_devices[@]}" >&2
  adb devices -l >&2
  exit 1
fi

device_serial="${connected_devices[0]}"
adb_cmd=(adb -s "${device_serial}")
device_code="$(${adb_cmd[@]} shell getprop ro.product.device | tr -d '\r')"

if [[ "${device_code}" != "leo" ]]; then
  echo "refusing to collect: expected device code leo, found ${device_code}" >&2
  exit 1
fi

if ! ${adb_cmd[@]} shell su -c id | grep -q 'uid=0(root)'; then
  echo "root access was not granted" >&2
  exit 1
fi

mkdir -p "${output_dir}"

capture_root() {
  local filename="$1"
  shift
  printf '%s\n' "$*" | "${adb_cmd[@]}" shell su -c sh >"${output_dir}/${filename}" 2>&1 || true
}

capture_root live-kernel-config-evidence.txt '
  echo "[identity]"
  printf "device="; getprop ro.product.device
  printf "build="; getprop ro.build.display.id
  printf "kernel="; uname -a
  printf "selinux="; getenforce

  echo "[config-export]"
  ls -lZ /proc/config.gz 2>/dev/null || echo "/proc/config.gz absent"
  if [ -r /proc/config.gz ]; then
    printf "config_gz_bytes="; wc -c < /proc/config.gz
  fi

  echo "[modules]"
  cat /proc/modules 2>/dev/null || echo "/proc/modules unavailable"

  echo "[cpu-topology]"
  for node in possible present online offline; do
    printf "%s=" "$node"
    cat "/sys/devices/system/cpu/$node" 2>/dev/null || echo unavailable
  done
  printf "cpuidle_driver="
  cat /sys/devices/system/cpu/cpu0/cpuidle/driver/name 2>/dev/null || echo unavailable
  for state in /sys/devices/system/cpu/cpu0/cpuidle/state*; do
    [ -d "$state" ] || continue
    printf "%s|" "${state##*/}"
    cat "$state/name" "$state/desc" "$state/disable" "$state/usage" "$state/time" 2>/dev/null |
      tr "\n" ","
    echo
  done

  echo "[lpm-runtime]"
  for node in \
    /sys/module/lpm_levels/parameters/sleep_disabled \
    /sys/module/lpm_levels/system/a53/cpu0/pc/idle_enabled \
    /sys/module/lpm_levels/system/a53/a53-l2-pc/idle_enabled \
    /sys/module/lpm_levels/system/a57/cpu4/pc/idle_enabled \
    /sys/module/lpm_levels/system/a57/a57-l2-pc/idle_enabled \
    /sys/module/lpm_levels/system/system-cci-pc/idle_enabled \
    /sys/module/lpm_levels/system/system-cci-pc/suspend_enabled; do
    printf "%s=" "$node"
    cat "$node" 2>/dev/null || echo unavailable
  done

  echo "[power-and-debug]"
  ls -lZ /sys/power 2>/dev/null
  grep debugfs /proc/mounts 2>/dev/null || true
  ls -lZ /proc/kallsyms /dev/mem 2>/dev/null || true

  echo "[audio-registration]"
  cat /proc/asound/cards 2>/dev/null
  ls -lZ /dev/snd/compr* 2>/dev/null || true
  ls -lZ /dev/adsprpc-smd /sys/kernel/boot_adsp/boot 2>/dev/null || true

  echo "[performance-and-thermal]"
  find /sys/module/msm_performance -maxdepth 2 -type f 2>/dev/null | sort
  find /sys/class/thermal -maxdepth 1 -name "thermal_zone*" 2>/dev/null | sort
'

(
  cd "${output_dir}"
  shasum -a 256 ./*.txt >SHA256SUMS
)

printf '%s\n' "${output_dir}"
