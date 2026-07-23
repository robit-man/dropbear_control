#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
catalog="$root/assets/myactuator/catalog.tsv"
target="${1:-$root/assets/vendor/myactuator}"
cache="$target/.downloads"

for command in curl unzip sha256sum find awk; do
  command -v "$command" >/dev/null || {
    printf 'Missing required command: %s\n' "$command" >&2
    exit 2
  }
done

mkdir -p "$cache"

while IFS=$'\t' read -r series model revision archive_url; do
  [[ "$series" == "series" || -z "$series" ]] && continue

  archive="$cache/${series}--${model}--${revision}.zip"
  model_dir="$target/$series/$model"
  vendor_dir="$model_dir/vendor"

  if [[ ! -s "$archive" ]]; then
    printf 'Downloading %s/%s (%s)\n' "$series" "$model" "$revision"
    curl --fail --location --retry 3 --output "$archive.part" "$archive_url"
    mv "$archive.part" "$archive"
  else
    printf 'Using cached %s/%s (%s)\n' "$series" "$model" "$revision"
  fi

  mkdir -p "$vendor_dir"
  unzip -q -o "$archive" '*.[Ss][Tt][Ee][Pp]' -d "$vendor_dir" || {
    rc=$?
    # Info-ZIP returns 1 for non-fatal Unicode filename normalization warnings.
    [[ "$rc" == "1" ]] || exit "$rc"
  }

  printf '%s\n' "$archive_url" > "$model_dir/source.url"
  digest="$(sha256sum "$archive" | awk '{print $1}')"
  printf '%s  %s\n' "$digest" "$(basename "$archive")" > "$model_dir/source.zip.sha256"

  if ! find "$vendor_dir" -type f \( -iname '*.step' -o -iname '*.stp' \) -print -quit | grep -q .; then
    printf 'Archive for %s/%s did not contain STEP geometry\n' "$series" "$model" >&2
    exit 3
  fi
done < "$catalog"

models="$(awk -F '\t' 'NR > 1 && NF == 4 {count++} END {print count + 0}' "$catalog")"
steps="$(find "$target" -type f \( -iname '*.step' -o -iname '*.stp' \) | wc -l | tr -d ' ')"

if [[ "$models" != "44" || "$steps" != "53" ]]; then
  printf 'Unexpected catalog result: %s models, %s STEP files (expected 44 and 53)\n' "$models" "$steps" >&2
  exit 4
fi

printf 'CAD cache ready: %s models, %s STEP files at %s\n' "$models" "$steps" "$target"
