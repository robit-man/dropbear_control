# External reference working copies

## Dropbear

`references/Dropbear/` is an ignored sparse working copy of the upstream robot
repository. The low-level control audit is pinned to:

```text
repository: https://github.com/Hyperspawn/Dropbear.git
branch: main
commit: 13cf5ecaa39b8b89c794fe905dcea0490cfa7726
commit date: 2025-08-07T14:09:15-07:00
sparse path: Control System/Low Level Control
```

Recreate the working copy without downloading the repository's large Git LFS
payloads:

```bash
GIT_LFS_SKIP_SMUDGE=1 git clone --depth=1 --filter=blob:none --sparse \
  https://github.com/Hyperspawn/Dropbear.git references/Dropbear
git -C references/Dropbear sparse-checkout set \
  'Control System/Low Level Control'
git -C references/Dropbear checkout \
  13cf5ecaa39b8b89c794fe905dcea0490cfa7726
```

The working copy is intentionally not vendored or added as a submodule in this
assessment. Decide repository ownership/versioning when the control-stack
rewrite begins.
