#!/usr/bin/env bash
# Validate every closed-world Gate 2 file_contexts lookup with libselinux.
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: $0 METADATA_DIRECTORY EMPTY_REPORT_DIRECTORY" >&2
  exit 64
fi

metadata_dir=$(cd "$1" && pwd)
report_dir=$(cd "$(dirname "$2")" && pwd)/$(basename "$2")
image=${LEO_GATE2_BUILDER_IMAGE:-leo-audio-os-gate2-builder:bookworm}

for required in "$metadata_dir/file_contexts.closed-world" "$metadata_dir/selinux-lookups.tsv"; do
  [[ -f "$required" ]] || { echo "FAIL: metadata input missing: $required" >&2; exit 1; }
done
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
  --tmpfs /tmp:rw,noexec,nosuid,size=16m \
  --mount "type=bind,src=$metadata_dir,dst=/input,readonly" \
  --mount "type=bind,src=$report_dir,dst=/output" \
  --env "LEO_GATE2_BUILDER_IMAGE=$image" \
  --env "LEO_GATE2_BUILDER_IMAGE_ID=$image_id" \
  --entrypoint /bin/sh \
  "$image" -ec '
    printf "builder_image=%s\nbuilder_image_id=%s\n" \
      "$LEO_GATE2_BUILDER_IMAGE" "$LEO_GATE2_BUILDER_IMAGE_ID" > /output/toolchain.txt
    count=0
    exec 3< /input/selinux-lookups.tsv
    IFS= read -r _header <&3
    while IFS="$(printf "\t")" read -r path type expected source_path <&3; do
      actual=$(matchpathcon -n -f /input/file_contexts.closed-world -m "$type" "$path")
      if [ "$actual" != "$expected" ]; then
        printf "FAIL: lookup mismatch source=%s path=%s type=%s expected=%s actual=%s\n" \
          "$source_path" "$path" "$type" "$expected" "$actual" >&2
        exit 1
      fi
      count=$((count + 1))
    done
    printf "lookups_valid=true\nlookup_count=%s\n" "$count" > /output/verification.txt
  '

echo "OK: all closed-world SELinux lookups match Gate 1 labels"
