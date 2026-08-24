#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
timestamp="$(date +%Y%m%d-%H%M%S)"
output_dir="${1:-${repo_root}/resources/private/selinux-runtime/${timestamp}-leo}"

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
if [[ -n "$(find "${output_dir}" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
  echo "output directory is not empty: ${output_dir}" >&2
  exit 1
fi

capture_root() {
  local filename="$1"
  shift
  printf '%s\n' "$*" | "${adb_cmd[@]}" shell su -c sh >"${output_dir}/${filename}" 2>&1 || true
}

capture_root runtime-domains.txt '
  printf "device="; getprop ro.product.device
  printf "build="; getprop ro.build.display.id
  printf "selinux="; getenforce
  for process in audioserver audiod adsprpcd rfs_access; do
    pid="$(pidof "$process")"
    printf "%s|pid=%s|context=" "$process" "$pid"
    if [ -n "$pid" ]; then
      tr -d "\000" < "/proc/$pid/attr/current"
    else
      printf "not-running"
    fi
    echo
  done
'

capture_root runtime-labels.txt '
  for path in \
    /system/bin/audioserver /system/bin/audiod /system/bin/adsprpcd \
    /system/bin/rfs_access /dev/snd/controlC0 /dev/snd/pcmC0D0p \
    /dev/snd/hwC0D1000 /dev/msm_audio_cal /dev/msm_rtac \
    /dev/msm_hweffects /dev/adsprpc-smd /dev/ion /dev/uio1 /dev/uio2 \
    /dev/uio3 /sys/kernel/debug/tracing/trace_marker /data/misc/audio \
    /data/misc/audio/acdbdata /data/misc/audioserver /data/misc/dts \
    /persist/rfs /persist/hlos_rfs /system/rfs /firmware/image/adsp.mdt \
    /system/etc/acdbdata/Forte/Forte_Headset_cal.acdb \
    /system/etc/aanc_tuning_mixer.txt; do
    if [ -e "$path" ]; then
      ls -ldZ "$path"
    else
      printf "missing %s\n" "$path"
    fi
  done
'

capture_root runtime-file-descriptors.txt '
  for process in audioserver audiod adsprpcd rfs_access; do
    pid="$(pidof "$process")"
    echo "[$process pid=$pid]"
    if [ -n "$pid" ]; then
      ls -l "/proc/$pid/fd" 2>/dev/null |
        grep -Ei "snd|audio|dsp|firmware|rfs|uio|ion|trace_marker|system/etc|socket"
    fi
  done
'

capture_root init-service-state.txt '
  for service in audioserver audiod adsprpcd rfs_access dts_configurator dtseagleservice; do
    printf "%s=" "$service"
    getprop "init.svc.$service"
  done
  for path in /system/bin/dts_configurator /system/bin/dts_eagle_service \
    /data/misc/audio_pp; do
    if [ -e "$path" ]; then ls -ldZ "$path"; else printf "missing %s\n" "$path"; fi
  done
'

(
  cd "${output_dir}"
  shasum -a 256 ./*.txt >SHA256SUMS
)

printf '%s\n' "${output_dir}"
