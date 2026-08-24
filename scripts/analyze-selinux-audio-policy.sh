#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
policy="${1:-${repo_root}/resources/private/stock-boot-analysis-v2/ramdisk/sepolicy}"
ramdisk="${2:-${repo_root}/resources/private/stock-boot-analysis-v2/ramdisk}"
timestamp="$(date +%Y%m%d-%H%M%S)"
output_dir="${3:-${repo_root}/resources/private/selinux-policy-analysis/${timestamp}-stock}"
image="leo-audio-os-selinux-audit:bookworm"

for input in "${policy}" "${ramdisk}/file_contexts.bin" \
  "${ramdisk}/service_contexts" "${ramdisk}/property_contexts"; do
  if [[ ! -e "${input}" ]]; then
    echo "required input is missing: ${input}" >&2
    exit 1
  fi
done

policy="$(cd "$(dirname "${policy}")" && pwd)/$(basename "${policy}")"
ramdisk="$(cd "${ramdisk}" && pwd)"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker was not found" >&2
  exit 1
fi

if ! docker image inspect "${image}" >/dev/null 2>&1; then
  echo "analysis image is missing; build it with:" >&2
  echo "  docker build -t ${image} ${repo_root}/tools/selinux-audit" >&2
  exit 1
fi

mkdir -p "${output_dir}"
if [[ -n "$(find "${output_dir}" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
  echo "output directory is not empty: ${output_dir}" >&2
  exit 1
fi

container=(docker run --rm -v "${policy}:/input/sepolicy:ro" "${image}" -c)

"${container[@]}" 'seinfo --version; sesearch --version; seinfo /input/sepolicy' \
  >"${output_dir}/policy-summary.txt"

"${container[@]}" '
  p=/input/sepolicy
  for type in audioserver audiod adsprpcd rfs_access audio_device \
    miui_audio_device audio_data_file audioserver_data_file qdsp_device \
    uio_device firmware_file rfs_file rfs_shared_hlos_file rfs_system_file \
    dts_data_file avtimer_device audio_prop audio_service audioserver_service; do
    echo "[$type]"
    seinfo -t "$type" -x "$p"
  done
  for attr in domain domain_deprecated binderservicedomain appdomain; do
    echo "[attribute:$attr]"
    seinfo -a "$attr" -x "$p"
  done
' >"${output_dir}/types-and-attributes.txt"

"${container[@]}" '
  p=/input/sepolicy
  for source in audioserver audiod adsprpcd rfs_access; do
    echo "[$source effective]"
    sesearch -A -s "$source" "$p"
    echo "[$source direct]"
    sesearch -A -ds -s "$source" "$p"
  done
' >"${output_dir}/domain-rules.txt"

"${container[@]}" '
  p=/input/sepolicy
  printf "domain\teffective_allow\teffective_allowxperm\tdirect_allow\tdirect_allowxperm\n"
  for source in audioserver audiod adsprpcd rfs_access; do
    effective="$(sesearch -A -s "$source" "$p")"
    direct="$(sesearch -A -ds -s "$source" "$p")"
    ea="$(printf "%s\n" "$effective" | awk "/^allow / {n++} END {print n+0}")"
    ex="$(printf "%s\n" "$effective" | awk "/^allowxperm / {n++} END {print n+0}")"
    da="$(printf "%s\n" "$direct" | awk "/^allow / {n++} END {print n+0}")"
    dx="$(printf "%s\n" "$direct" | awk "/^allowxperm / {n++} END {print n+0}")"
    printf "%s\t%s\t%s\t%s\t%s\n" "$source" "$ea" "$ex" "$da" "$dx"
  done
' >"${output_dir}/domain-rule-counts.tsv"

"${container[@]}" '
  p=/input/sepolicy
  query() {
    source=$1
    target=$2
    echo "[$source -> $target]"
    sesearch -A -s "$source" -t "$target" "$p"
  }
  query audioserver audio_device
  query audioserver miui_audio_device
  query audioserver audio_data_file
  query audioserver system_file
  query audioserver ion_device
  query audioserver debugfs_trace_marker
  query audioserver audiod
  query audioserver audioserver_service
  query system_server audio_service
  query untrusted_app audio_service
  query audioserver audio_prop
  query audioserver avtimer_device
  query audiod audio_device
  query audiod audioserver
  query audiod audioserver_service
  query audiod proc_audiod
  query adsprpcd qdsp_device
  query adsprpcd adsprpcd_file
  query rfs_access uio_device
  query rfs_access firmware_file
  query rfs_access rfs_file
  query rfs_access rfs_shared_hlos_file
  query rfs_access rfs_system_file
  query rfs_access persist_file
  query dtsconfigurator audio_pp_data_file
  query dtseagleservice audio_pp_data_file
  query dtsconfigurator dts_data_file
  query dtseagleservice dts_data_file
  query untrusted_app audioserver
  query untrusted_app audioserver_service
  echo "[all -> avtimer_device]"
  sesearch -A -t avtimer_device "$p"
  echo "[all -> audio_pp_data_file]"
  sesearch -A -t audio_pp_data_file "$p"
  echo "[all -> dts_data_file]"
  sesearch -A -t dts_data_file "$p"
' >"${output_dir}/targeted-rules.txt"

"${container[@]}" '
  p=/input/sepolicy
  for pair in "audioserver audioserver_exec" "audiod audiod_exec" \
    "adsprpcd adsprpcd_exec" "rfs_access rfs_access_exec"; do
    set -- $pair
    domain=$1
    executable=$2
    echo "[init -> $executable -> $domain]"
    sesearch -T -s init -t "$executable" -c process "$p"
    sesearch -A -s init -t "$executable" "$p"
    sesearch -A -s "$domain" -t "$executable" "$p"
  done
' >"${output_dir}/domain-transitions.txt"

rg -n '^(audio|media\.audio_flinger|media\.audio_policy|media\.sound_trigger_hw)[[:space:]]' \
  "${ramdisk}/service_contexts" >"${output_dir}/audio-service-contexts.txt"
rg -n '^(persist\.audio\.|dolby\.audio\.|sys\.audio\.init)' \
  "${ramdisk}/property_contexts" >"${output_dir}/audio-property-contexts.txt"
strings -a "${ramdisk}/file_contexts.bin" >"${output_dir}/file-contexts-strings.txt"
rg -n -B 2 -A 2 -i \
  'audio|audioserver|audiod|adsprpc|rfs|qdsp|avtimer|/dev/snd|/data/misc/dts' \
  "${output_dir}/file-contexts-strings.txt" \
  >"${output_dir}/audio-file-context-excerpts.txt"

(
  cd "${output_dir}"
  shasum -a 256 ./*.txt ./*.tsv >SHA256SUMS
)

printf '%s\n' "${output_dir}"
