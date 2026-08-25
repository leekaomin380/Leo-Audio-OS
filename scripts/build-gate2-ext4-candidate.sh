#!/usr/bin/env bash
# Build one development-unverified raw ext4 candidate from verified private inputs.
set -euo pipefail

if [[ $# -ne 3 ]]; then
  echo "usage: $0 <staging-tree> <metadata-dir> <new-output-dir>" >&2
  exit 64
fi

staging=$1
metadata=$2
output_dir=$3
root_dir=$(cd "$(dirname "$0")/.." && pwd)
builder_image=leo-audio-os-gate2-builder:bookworm
config="$root_dir/tools/gate2-builder/mke2fs.conf"

for path in "$staging" "$metadata" "$config"; do
  [[ -e "$path" ]] || { echo "FAIL: required input missing: $path" >&2; exit 1; }
done
[[ -d "$staging" && -d "$metadata" ]] || { echo "FAIL: staging and metadata must be directories" >&2; exit 1; }
[[ ! -e "$output_dir" ]] || { echo "FAIL: output path already exists: $output_dir" >&2; exit 1; }

staging=$(cd "$staging" && pwd)
metadata=$(cd "$metadata" && pwd)
config=$(cd "$(dirname "$config")" && pwd)/$(basename "$config")
mkdir -p "$output_dir"
output_dir=$(cd "$output_dir" && pwd)

for required in fs_config.canned file_contexts.closed-world metadata-summary.json; do
  [[ -s "$metadata/$required" ]] || { echo "FAIL: metadata missing: $required" >&2; exit 1; }
done

docker image inspect "$builder_image" >/dev/null
docker run --rm --network none --entrypoint /bin/sh \
  -e E2FSPROGS_FAKE_TIME=1 \
  -v "$config:/input/mke2fs.conf:ro" \
  -v "$staging:/staging:ro" \
  -v "$metadata:/metadata:ro" \
  -v "$output_dir:/output:rw" \
  "$builder_image" -lc '
    set -eu
    export MKE2FS_CONFIG=/input/mke2fs.conf
    /opt/e2fsprogs/sbin/mke2fs -F -t ext4 -b 4096 -I 256 -N 104832 -g 32768 -m 0 \
      -U da594c53-9beb-f85c-85c5-cedf76546f7a -L system -J size=25 \
      -E hash_seed=da594c53-9beb-f85c-85c5-cedf76546f7a,resize=432046080 \
      /output/system.ext4.raw 419329 > /output/mke2fs.txt 2>&1
    e2fsdroid -e -f /staging -a /system -C /metadata/fs_config.canned \
      -S /metadata/file_contexts.closed-world /output/system.ext4.raw \
      > /output/e2fsdroid.txt 2>&1
  '

"$root_dir/scripts/normalize-gate2-ext4.sh" \
  "$output_dir/system.ext4.raw" "$output_dir/normalization"
(
  cd "$output_dir"
  sha256sum system.ext4.raw > system.ext4.raw.sha256
)
printf 'candidate_build_valid=true\nclassification=development-unverified\n' > "$output_dir/verification.txt"
