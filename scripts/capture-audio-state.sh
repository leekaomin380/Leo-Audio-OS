#!/usr/bin/env bash

set -euo pipefail

if [[ "$#" -ne 1 || ! "$1" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]]; then
  echo "usage: $0 LABEL" >&2
  exit 1
fi

label="$1"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
timestamp="$(date +%Y%m%d-%H%M%S)"
output_dir="${repo_root}/resources/private/runtime-states/${timestamp}-${label}"

connected_devices=()
while IFS= read -r device_serial; do
  connected_devices+=("${device_serial}")
done < <(adb devices | awk '$2 == "device" {print $1}')

if [[ "${#connected_devices[@]}" -ne 1 ]]; then
  echo "expected exactly one authorized Android device; found ${#connected_devices[@]}" >&2
  exit 1
fi

adb_cmd=(adb -s "${connected_devices[0]}")
device_code="$("${adb_cmd[@]}" shell getprop ro.product.device | tr -d '\r')"

if [[ "${device_code}" != "leo" ]]; then
  echo "refusing to collect: expected device code leo, found ${device_code}" >&2
  exit 1
fi

if ! "${adb_cmd[@]}" shell su -c id | grep -q 'uid=0(root)'; then
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

capture_shell state.txt '
  printf "captured_at="; date +%s
  printf "hifi="; getprop persist.audio.hifi
  printf "hifi_volume="; getprop persist.audio.hifi.volume
  printf "wired_state="; dumpsys audio | grep -Ei "wired|headset|headphone|device"
'

capture_shell dumpsys-audio.txt 'dumpsys audio'
capture_shell dumpsys-audio-flinger.txt 'dumpsys media.audio_flinger'
capture_shell dumpsys-audio-policy.txt 'dumpsys media.audio_policy'
capture_shell audio-logcat.txt '
  logcat -d -v threadtime -b main -b system -b crash |
    grep -Ei "AudioFlinger|AudioPolicy|audio_hw|audio.primary|audioserver|AudioTrack|ACDB|hifi|QUAT_MI2S|offload|tinycompress|q6asm|q6afe|WiredAccessoryManager|MusicFX|Dirac"
'
capture_root processes.txt 'ps -A 2>/dev/null || ps'
capture_root process-maps.txt '
  for process_name in audioserver audiod adsprpcd com.spotify.music; do
    for pid in $(pidof "$process_name" 2>/dev/null); do
      echo "[$process_name pid=$pid maps]"
      cat "/proc/$pid/maps"
      echo "[$process_name pid=$pid file-descriptors]"
      ls -l "/proc/$pid/fd"
    done
  done
'
capture_root proc-asound.txt '
  cat /proc/asound/cards
  cat /proc/asound/pcm
  for file in /proc/asound/card*/pcm*/sub*/hw_params; do
    echo "[$file]"
    cat "$file"
  done
'
capture_root tinymix.txt 'tinymix'
capture_root kernel-audio-log.txt \
  'dmesg | grep -Ei "audio|sound|alsa|asoc|adsp|es9018|ess9018|hifi|i2s|slim|wcd|headset|headphone|mbhc|tomtom|scontext=u:r:(audioserver|audiod|adsprpcd)"'
capture_root clocks-and-interrupts.txt '
  echo "[clock summary]"
  cat /sys/kernel/debug/clk/clk_summary 2>/dev/null |
    grep -Ei "audio|adsp|lpass|i2s|mi2s|quat|codec"
  echo "[interrupts]"
  cat /proc/interrupts |
    grep -Ei "audio|adsp|lpass|i2s|mi2s|quat|codec|sound"
'

(
  cd "${output_dir}"
  shasum -a 256 ./*.txt >SHA256SUMS
)

printf '%s\n' "${output_dir}"
