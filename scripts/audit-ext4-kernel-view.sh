#!/usr/bin/env bash
# Gate 1 cross evidence: isolated Linux ro,noload mount and semantic comparison.
set -euo pipefail

if [[ $# -ne 3 ]]; then
  echo "usage: $0 RAW_SYSTEM_IMAGE PRIMARY_SEMANTIC_DIRECTORY EMPTY_REPORT_DIRECTORY" >&2
  exit 64
fi

raw_image=$(cd "$(dirname "$1")" && pwd)/$(basename "$1")
primary_dir=$(cd "$2" && pwd)
report_dir=$(cd "$(dirname "$3")" && pwd)/$(basename "$3")
image=${LEO_EXT4_AUDIT_IMAGE:-leo-audio-os-selinux-audit:bookworm}
script_dir=$(cd "$(dirname "$0")" && pwd)
repo_root=$(cd "$script_dir/.." && pwd)

for required in "$raw_image" "$primary_dir/entries.jsonl" "$primary_dir/hardlinks.json"; do
  [[ -f "$required" ]] || { echo "FAIL: required evidence missing: $required" >&2; exit 1; }
done
if [[ -e "$report_dir" ]] && [[ -n "$(find "$report_dir" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
  echo "FAIL: report directory must be empty: $report_dir" >&2
  exit 1
fi
mkdir -p "$report_dir"
docker image inspect "$image" >/dev/null
image_id=$(docker image inspect "$image" --format '{{.Id}}')

docker run --rm \
  --privileged \
  --network none \
  --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=128m \
  --tmpfs /mnt:rw,noexec,nosuid,size=64m \
  --mount "type=bind,src=$raw_image,dst=/input/system.raw,readonly" \
  --mount "type=bind,src=$report_dir,dst=/output" \
  --mount "type=bind,src=$script_dir/collect-mounted-semantic.py,dst=/collector.py,readonly" \
  --env "LEO_EXT4_AUDIT_IMAGE=$image" \
  --env "LEO_EXT4_AUDIT_IMAGE_ID=$image_id" \
  --entrypoint /bin/sh \
  "$image" -ec '
    printf "container_image=%s\ncontainer_image_id=%s\nmount=ro,noload,loop\n" \
      "$LEO_EXT4_AUDIT_IMAGE" "$LEO_EXT4_AUDIT_IMAGE_ID" > /output/toolchain.txt
    mount -o ro,noload,loop /input/system.raw /mnt
    trap "umount /mnt" EXIT
    mount | grep " on /mnt " > /output/mount-info.txt
    grep -Eq "/input/system.raw on /mnt type ext4 \(ro,.*norecovery" /output/mount-info.txt
    PYTHONDONTWRITEBYTECODE=1 python3 /collector.py --system-root /mnt --output /output/semantic
  '

python3 "$script_dir/verify-ext4-semantic-manifest.py" \
  --entries "$report_dir/semantic/entries.jsonl" \
  --summary "$report_dir/semantic/audit-summary.json" \
  --audio-manifest "$repo_root/manifests/audio-compatibility-v0.1.tsv" \
  --output "$report_dir/semantic/validation.json" \
  --audio-output "$report_dir/semantic/audio-compatibility-check.json"
python3 "$script_dir/derive-android-metadata.py" \
  --entries "$report_dir/semantic/entries.jsonl" \
  --fs-config-output "$report_dir/semantic/fs-config-derived.tsv" \
  --selinux-output "$report_dir/semantic/selinux-labels.tsv"
python3 "$script_dir/compare-ext4-semantic-manifests.py" \
  --primary "$primary_dir" \
  --kernel "$report_dir/semantic" \
  --output "$report_dir/comparison.json"

(
  cd "$report_dir"
  shasum -a 256 \
    comparison.json \
    mount-info.txt \
    semantic/audit-summary.json \
    semantic/audio-compatibility-check.json \
    semantic/entries.jsonl \
    semantic/fs-config-derived.tsv \
    semantic/hardlinks.json \
    semantic/selinux-labels.tsv \
    semantic/validation.json \
    toolchain.txt >SHA256SUMS
)

echo "OK: kernel ro,noload evidence matches the primary semantic manifest exactly"
