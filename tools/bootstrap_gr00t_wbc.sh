#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
lock_file="${project_root}/integrations/gr00t_wbc/UPSTREAM_LOCK.json"
checkout_dir="${project_root}/references/GR00T-WholeBodyControl"

readarray -t upstream < <(
  python3 - "${lock_file}" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as stream:
    lock = json.load(stream)
print(lock["repository"])
print(lock["commit"])
print(lock["sourceLicense"]["sha256"])
PY
)

repository="${upstream[0]}"
commit="${upstream[1]}"
license_sha256="${upstream[2]}"

if [[ -e "${checkout_dir}" && ! -d "${checkout_dir}/.git" ]]; then
  echo "Refusing to replace non-Git path: ${checkout_dir}" >&2
  exit 2
fi

fresh_checkout=0
if [[ ! -d "${checkout_dir}/.git" ]]; then
  mkdir -p "${project_root}/references"
  GIT_LFS_SKIP_SMUDGE=1 git clone \
    --filter=blob:none \
    --no-checkout \
    "${repository}" \
    "${checkout_dir}"
  fresh_checkout=1
fi

if [[ "${fresh_checkout}" -eq 0 && -n "$(git -C "${checkout_dir}" status --porcelain)" ]]; then
  echo "Refusing to change a modified upstream checkout: ${checkout_dir}" >&2
  exit 2
fi

configured_origin="$(git -C "${checkout_dir}" remote get-url origin)"
if [[ "${configured_origin}" != "${repository}" ]]; then
  echo "Unexpected upstream origin: ${configured_origin}" >&2
  exit 2
fi

GIT_LFS_SKIP_SMUDGE=1 git -C "${checkout_dir}" fetch \
  --depth=1 \
  origin \
  "${commit}"
GIT_LFS_SKIP_SMUDGE=1 git -C "${checkout_dir}" checkout \
  --detach \
  "${commit}"

resolved_commit="$(git -C "${checkout_dir}" rev-parse HEAD)"
if [[ "${resolved_commit}" != "${commit}" ]]; then
  echo "Resolved ${resolved_commit}; expected ${commit}" >&2
  exit 2
fi

resolved_license_sha256="$(sha256sum "${checkout_dir}/LICENSE" | cut -d' ' -f1)"
if [[ "${resolved_license_sha256}" != "${license_sha256}" ]]; then
  echo "Upstream LICENSE hash mismatch" >&2
  exit 2
fi

echo "Pinned GR00T-WholeBodyControl checkout ready:"
echo "  path: ${checkout_dir}"
echo "  commit: ${resolved_commit}"
echo "  weights: not downloaded"
