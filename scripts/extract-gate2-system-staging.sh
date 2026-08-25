#!/usr/bin/env bash
# Extract only the ext4 content tree from the private stock system partition.
# It never writes the source image or any connected Android device.
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: $0 <stock-system.partition.raw> <new-staging-dir>" >&2
  exit 64
fi

source_image=$1
staging_dir=$2
builder_image=leo-audio-os-gate2-builder:bookworm

if [[ ! -f "$source_image" ]]; then
  echo "FAIL: source image is not a regular file: $source_image" >&2
  exit 1
fi
if [[ -e "$staging_dir" ]]; then
  echo "FAIL: staging destination already exists: $staging_dir" >&2
  exit 1
fi

source_dir=$(cd "$(dirname "$source_image")" && pwd)
source_name=$(basename "$source_image")
mkdir -p "$staging_dir"
staging_dir=$(cd "$staging_dir" && pwd)

docker image inspect "$builder_image" >/dev/null
docker run --rm --network none --read-only --entrypoint /bin/sh \
  -v "$source_dir:/input:ro" \
  -v "$staging_dir:/output:rw" \
  "$builder_image" -lc '
    set -eu
    mkdir /output/tree
    # Read inode data directly. Kernel-mounted extraction can be blocked by
    # deliberately restrictive Android DAC modes even though the raw inode is valid.
    /opt/e2fsprogs/sbin/debugfs -R "rdump / /output/tree" /input/'"$source_name"' \
      > /output/debugfs-rdump.txt 2>&1
    if grep -Eqi "while (opening|reading|dumping|making)|short read|error" /output/debugfs-rdump.txt; then
      cat /output/debugfs-rdump.txt >&2
      exit 1
    fi
    find /output/tree -xdev -printf "%y\\t%p\\n" | LC_ALL=C sort > /output/tree-index.tsv
    find /output/tree -xdev -printf "%y\\n" | LC_ALL=C sort | uniq -c > /output/type-counts.txt
    # The staging directory itself represents the source root, so its index
    # contains the same 3923 entries as the Gate 1 semantic manifest.
    test "$(wc -l < /output/tree-index.tsv)" -eq 3923
  '

[[ -d "$staging_dir/tree" ]]
[[ -s "$staging_dir/tree-index.tsv" ]]
printf 'staging_extract_valid=true\n' > "$staging_dir/verification.txt"
