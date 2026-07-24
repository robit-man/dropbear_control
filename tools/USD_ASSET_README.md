# Dropbear USD browser-cache pipeline

The dashboard does not vendor the 402 MB source USD. To regenerate the
browser cache, clone `https://github.com/Hyperspawn/dropbear_rl` at
`3c37aedce6d445205671d5714d05ae28b8c90e2c`, then run:

```bash
python3 -m venv /tmp/dropbear-usd-venv
/tmp/dropbear-usd-venv/bin/pip install usd-core numpy trimesh fast-simplification pygltflib
/tmp/dropbear-usd-venv/bin/python tools/export_dropbear_usd.py \
  /path/to/dropbear_rl/dropbear_model/Dropbear/usd/dropbear.usd \
  /tmp/dropbear-usd-preview.glb \
  web/assets/robot/dropbear-articulation.json
npx @gltf-transform/cli weld \
  /tmp/dropbear-usd-preview.glb /tmp/dropbear-usd-welded.glb
npx @gltf-transform/cli simplify \
  /tmp/dropbear-usd-welded.glb /tmp/dropbear-usd-simplified.glb \
  --ratio 0.22 --error 0.015
npx @gltf-transform/cli quantize \
  /tmp/dropbear-usd-simplified.glb \
  web/assets/robot/dropbear-usd-browser.glb \
  --quantize-position 14 --quantize-normal 10 \
  --quantize-texcoord 12 --quantize-color 8
```

The output GLB is an adapted, decimated visual cache. The JSON preserves all
physical joints, rigid-body transforms, loop-closure records, Isaac SDK joint
names, and the 12 low-level CAN-to-USD bindings.

Source model license: CC-BY-NC-SA-4.0. Attribution:
Hyperspawn Robotics — Priyanshu Pareek and Cole Myers.
