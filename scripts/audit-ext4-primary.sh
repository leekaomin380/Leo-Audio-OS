#!/usr/bin/env bash
# Gate 1 primary evidence: no network, no mount, read-only image audit.
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: $0 RAW_SYSTEM_IMAGE EMPTY_REPORT_DIRECTORY" >&2
  exit 64
fi

raw_image=$(cd "$(dirname "$1")" && pwd)/$(basename "$1")
report_dir=$(cd "$(dirname "$2")" && pwd)/$(basename "$2")
image=${LEO_EXT4_AUDIT_IMAGE:-leo-audio-os-selinux-audit:bookworm}
script_dir=$(cd "$(dirname "$0")" && pwd)
repo_root=$(cd "$script_dir/.." && pwd)
profile="$repo_root/manifests/stock-system-ext4-profile-v0.1.json"

if [[ ! -f "$raw_image" ]]; then
  echo "FAIL: raw system image does not exist: $raw_image" >&2
  exit 1
fi
if [[ -e "$report_dir" ]] && [[ -n "$(find "$report_dir" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
  echo "FAIL: report directory must be empty: $report_dir" >&2
  exit 1
fi
mkdir -p "$report_dir"
docker image inspect "$image" >/dev/null
image_id=$(docker image inspect "$image" --format '{{.Id}}')

docker run --rm \
  --network none \
  --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=128m \
  --mount "type=bind,src=$raw_image,dst=/input/system.raw,readonly" \
  --mount "type=bind,src=$report_dir,dst=/output" \
  --env "LEO_EXT4_AUDIT_IMAGE=$image" \
  --env "LEO_EXT4_AUDIT_IMAGE_ID=$image_id" \
  --entrypoint /bin/sh \
  "$image" -ec '
    raw=/input/system.raw
    out=/output
    printf "container_image=%s\n" "${LEO_EXT4_AUDIT_IMAGE:-leo-audio-os-selinux-audit:bookworm}" >"$out/toolchain.txt"
    printf "container_image_id=%s\n" "$LEO_EXT4_AUDIT_IMAGE_ID" >>"$out/toolchain.txt"
    cat /etc/os-release >>"$out/toolchain.txt"
    e2fsck -V >>"$out/toolchain.txt" 2>&1
    sha256sum "$raw" >"$out/raw-system.sha256"
    set +e
    e2fsck -f -n "$raw" >"$out/e2fsck.txt" 2>&1
    e2fsck_status=$?
    set -e
    printf "e2fsck_exit=%s\n" "$e2fsck_status" >"$out/e2fsck-status.txt"
    dumpe2fs -h "$raw" >"$out/superblock.txt" 2>&1
    dumpe2fs -g "$raw" >"$out/group-layout.txt" 2>&1
    debugfs -R stats "$raw" >"$out/debugfs-stats.txt" 2>&1
    debugfs -R "ls -p -l /" "$raw" >"$out/debugfs-root.txt" 2>&1
  '

python3 "$script_dir/verify-stock-ext4-source.py" \
  --raw "$raw_image" \
  --profile "$profile" \
  --e2fsck-report "$report_dir/e2fsck.txt" \
  --e2fsck-status "$report_dir/e2fsck-status.txt" \
  --output "$report_dir/source-verdict.json"

(
  cd "$report_dir"
  shasum -a 256 \
    debugfs-root.txt \
    debugfs-stats.txt \
    e2fsck-status.txt \
    e2fsck.txt \
    group-layout.txt \
    raw-system.sha256 \
    source-verdict.json \
    superblock.txt \
    toolchain.txt >SHA256SUMS
)

echo "OK: locked stock source accepted with documented legacy deviation; filesystem is not labelled clean"
