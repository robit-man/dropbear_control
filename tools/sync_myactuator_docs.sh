#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
catalog="$root/assets/myactuator/documents.tsv"
target="${1:-$root/assets/vendor/myactuator/docs}"
cache="$target/.downloads"

for command in curl unzip sha256sum find awk; do
  command -v "$command" >/dev/null || {
    printf 'Missing required command: %s\n' "$command" >&2
    exit 2
  }
done

mkdir -p "$cache"

while IFS=$'\t' read -r series document_set revision archive_url; do
  [[ "$series" == "series" || -z "$series" ]] && continue

  archive="$cache/${series}--${document_set}--${revision}.zip"
  document_dir="$target/$series/$document_set"
  vendor_dir="$document_dir/vendor"

  if [[ ! -s "$archive" ]]; then
    printf 'Downloading %s/%s (%s)\n' "$series" "$document_set" "$revision"
    curl --fail --location --retry 3 --output "$archive.part" "$archive_url"
    mv "$archive.part" "$archive"
  else
    printf 'Using cached %s/%s (%s)\n' "$series" "$document_set" "$revision"
  fi

  mkdir -p "$vendor_dir"
  unzip -q -o "$archive" -d "$vendor_dir" || {
    rc=$?
    [[ "$rc" == "1" ]] || exit "$rc"
  }

  printf '%s\n' "$archive_url" > "$document_dir/source.url"
  digest="$(sha256sum "$archive" | awk '{print $1}')"
  printf '%s  %s\n' "$digest" "$(basename "$archive")" > "$document_dir/source.zip.sha256"
done < "$catalog"

sets="$(awk -F '\t' 'NR > 1 && NF == 4 {count++} END {print count + 0}' "$catalog")"
archives="$(find "$cache" -maxdepth 1 -type f -name '*.zip' | wc -l | tr -d ' ')"

if [[ "$sets" != "9" || "$archives" != "9" ]]; then
  printf 'Unexpected document result: %s sets, %s archives (expected 9 and 9)\n' "$sets" "$archives" >&2
  exit 4
fi

printf 'Documentation cache ready: %s source sets at %s\n' "$sets" "$target"
