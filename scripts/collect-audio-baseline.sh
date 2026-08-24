#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
timestamp="$(date +%Y%m%d-%H%M%S)"
output_dir="${1:-${repo_root}/resources/private/device-baselines/${timestamp}-leo}"

if ! command -v adb >/dev/null 2>&1; then
  echo "adb was not found" >&2
  exit 1
fi

mapfile_cmd="$(command -v mapfile || true)"
if [[ -n "${mapfile_cmd}" ]]; then
  mapfile -t connected_devices < <(adb devices | awk '$2 == "device" {print $1}')
else
  connected_devices=()
  while IFS= read -r device_serial; do
    connected_devices+=("${device_serial}")
  done < <(adb devices | awk '$2 == "device" {print $1}')
fi

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

capture_shell() {
  local filename="$1"
  shift
  printf '%s\n' "$*" | "${adb_cmd[@]}" shell sh >"${output_dir}/${filename}" 2>&1 || true
}

capture_root() {
  local filename="$1"
  shift
  printf '%s\n' "$*" | "${adb_cmd[@]}" shell su -c sh >"${output_dir}/${filename}" 2>&1 || true
}

capture_shell system-identity.txt '
  printf "product_device="; getprop ro.product.device
  printf "product_model="; getprop ro.product.model
  printf "android_release="; getprop ro.build.version.release
  printf "sdk="; getprop ro.build.version.sdk
  printf "display_id="; getprop ro.build.display.id
  printf "fingerprint="; getprop ro.build.fingerprint
  printf "security_patch="; getprop ro.build.version.security_patch
  printf "build_date_utc="; getprop ro.build.date.utc
  printf "verified_boot_state="; getprop ro.boot.verifiedbootstate
  printf "selinux="; getenforce
  printf "kernel="; uname -a
  printf "adb_identity="; id
  printf "root_identity="; su -c id
'

capture_root partitions-and-mounts.txt '
  echo "[mount]"
  mount
  echo "[df]"
  df
  echo "[/proc/partitions]"
  cat /proc/partitions
  echo "[by-name]"
  for directory in /dev/block/platform/*/by-name /dev/block/bootdevice/by-name; do
    if [ -d "$directory" ]; then
      ls -lZ "$directory"
    fi
  done
'

capture_root audio-properties.txt '
  getprop | grep -Ei "audio|sound|voice|media|dsp|hifi|ess|msm8994" | sort
'

capture_root audio-processes-and-services.txt '
  echo "[processes]"
  ps -A 2>/dev/null || ps
  echo "[binder services]"
  service list
  echo "[audio-related binder services]"
  service list | grep -Ei "audio|media|sound|dsp"
'

capture_root audio-file-index.txt '
  find /system/etc /system/lib /system/lib64 /system/bin /system/xbin /vendor /firmware/image -type f 2>/dev/null |
    grep -Ei "audio|mixer|acdb|sound|adsp|adsprpc|es9018|ess9018|hifi|tinyalsa|tinycompress" |
    sort |
    while IFS= read -r file; do ls -lZ "$file"; done
'

capture_root audio-file-hashes.txt '
  find /system/etc /system/lib /system/lib64 /system/bin /system/xbin /vendor /firmware/image -type f 2>/dev/null |
    grep -Ei "audio|mixer|acdb|sound|adsp|adsprpc|es9018|ess9018|hifi|tinyalsa|tinycompress" |
    sort |
    while IFS= read -r file; do busybox sha256sum "$file"; done
'

capture_root init-audio-references.txt '
  grep -RniE "audio|mixer|acdb|sound|dsp|hifi|ess|adsprpc|msm8994" \
    /init*.rc /system/etc/init /vendor/etc/init 2>/dev/null
'

capture_root proc-asound.txt '
  for file in /proc/asound/version /proc/asound/cards /proc/asound/devices /proc/asound/pcm; do
    echo "[$file]"
    if [ -r "$file" ]; then cat "$file"; else echo "unavailable"; fi
  done
  echo "[/dev/snd]"
  ls -lZ /dev/snd 2>/dev/null
  echo "[audio-like device nodes]"
  ls -lZ /dev/*dsp* /dev/*audio* /dev/*sound* 2>/dev/null
'

capture_root tinymix-idle.txt '
  if command -v tinymix >/dev/null 2>&1; then
    tinymix
  else
    echo "tinymix unavailable"
  fi
'

capture_shell dumpsys-audio.txt dumpsys audio
capture_shell dumpsys-audio-flinger.txt dumpsys media.audio_flinger
capture_shell dumpsys-audio-policy.txt dumpsys media.audio_policy
capture_root kernel-audio-log.txt 'dmesg | grep -Ei "audio|sound|alsa|asoc|adsp|es9018|ess9018|hifi|i2s|slim|wcd|headset|headphone|mbhc|tomtom"'

(
  cd "${output_dir}"
  shasum -a 256 ./*.txt >SHA256SUMS
)

printf '%s\n' "${output_dir}"
