# Dropbear USD browser-cache pipeline

The dashboard does not vendor the 402 MB source USD. To regenerate the
browser cache, clone `https://github.com/robit-man/dropbear-locomotion` at
`a397be863fed2d328c2e8f62c3db2f1e23575eb1`, install the pinned browser
optimizer with `npm --prefix web install`, then run:

```bash
python3 -m venv /tmp/dropbear-usd-venv
/tmp/dropbear-usd-venv/bin/pip install usd-core numpy trimesh fast-simplification pygltflib
/tmp/dropbear-usd-venv/bin/python tools/export_dropbear_usd.py \
  /path/to/dropbear-locomotion/dropbear_walk/isaaclab_asset/dropbear.usd \
  web/assets/robot/dropbear-usd-browser.glb \
  web/assets/robot/dropbear-articulation.json \
  --ratio 0.003 \
  --meshopt-cli web/node_modules/.bin/gltf-transform \
  --meshopt-ratio 0.2
```

The export replaces the two detailed AGX Orin carrier-board visual meshes
with one occupied-envelope proxy, then welds and simplifies the remaining
visual geometry to the browser budget. The JSON preserves all
physical joints, rigid-body transforms, loop-closure records, Isaac SDK joint
names, masses, inertias, collisions, and the 12 low-level CAN-to-USD bindings.

Source model license: CC-BY-NC-SA-4.0. Attribution:
Hyperspawn Robotics — Priyanshu Pareek and Cole Myers.
