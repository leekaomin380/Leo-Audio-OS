#!/usr/bin/env bash
# Normalize the few mke2fs 1.46.6 fields whose stock leo values cannot be
# expressed at creation time. This is a Gate 2 development-only operation.
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: $0 <candidate.ext4.raw> <empty-report-dir>" >&2
  exit 64
fi

image=$1
report_dir=$2
root_dir=$(cd "$(dirname "$0")/.." && pwd)
builder_image=leo-audio-os-gate2-builder:bookworm

if [[ ! -f "$image" ]]; then
  echo "FAIL: image is not a regular file: $image" >&2
  exit 1
fi
if [[ $(basename "$image") != *.ext4.raw ]]; then
  echo "FAIL: refuses a non-.ext4.raw target: $image" >&2
  exit 1
fi
if [[ -e "$report_dir" ]]; then
  echo "FAIL: report path already exists: $report_dir" >&2
  exit 1
fi

image_dir=$(cd "$(dirname "$image")" && pwd)
image_name=$(basename "$image")
mkdir -p "$report_dir"
report_dir=$(cd "$report_dir" && pwd)

docker image inspect "$builder_image" >/dev/null
docker run --rm --network none --read-only --entrypoint /bin/sh \
  -v "$image_dir:/image:rw" \
  -v "$report_dir:/report:rw" \
  "$builder_image" -lc '
    set -eu
    image=/image/'"$image_name"'
    for command in \
      "set_super_value min_extra_isize 28" \
      "set_super_value want_extra_isize 28" \
      "set_inode_field <11> atime 0" \
      "set_inode_field <11> ctime 0" \
      "set_inode_field <11> mtime 0"; do
      /opt/e2fsprogs/sbin/debugfs -w -R "$command" "$image"
    done > /report/debugfs-normalize.txt 2>&1
    /opt/e2fsprogs/sbin/dumpe2fs -h "$image" > /report/superblock.txt 2>&1
    /opt/e2fsprogs/sbin/debugfs -R "stat <11>" "$image" > /report/lost-found.txt 2>&1
    /opt/e2fsprogs/sbin/e2fsck -f -n "$image" > /report/e2fsck.txt 2>&1
  '

rg -q 'Required extra isize:[[:space:]]+28' "$report_dir/superblock.txt"
rg -q 'Desired extra isize:[[:space:]]+28' "$report_dir/superblock.txt"
rg -q 'mtime: 0x00000000:00000000' "$report_dir/lost-found.txt"
printf 'normalization_valid=true\n' > "$report_dir/verification.txt"
