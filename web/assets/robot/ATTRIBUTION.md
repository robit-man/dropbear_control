# Dropbear USD browser cache

`dropbear-usd-browser.glb` is an adapted, decimated browser-rendering cache of:

- Source: `robit-man/dropbear-locomotion`
- Revision: `a397be863fed2d328c2e8f62c3db2f1e23575eb1`
- Source path: `dropbear_walk/isaaclab_asset/dropbear.usd`
- Source SHA-256: `45586414b065cd982d487cbd868fe982108b3b8ccec64d3dfcf629652ed8db0f`
- Attribution: Hyperspawn Robotics — Priyanshu Pareek and Cole Myers
- License: [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/)

Changes: visual meshes were decoded from the binary USD crate, grouped by
rigid body/material, welded, simplified, and translated to glTF 2.0. The two
detailed AGX Orin carrier-board meshes were replaced by one visual bounds
proxy; their rigid-body physics records and collision contract remain intact.
The sibling articulation manifest retains the USD rigid-body transforms,
physical joints, loop-closure records, SDK action joints, and low-level
CAN-to-USD bindings.

The browser cache does not replace the source USD or Isaac/PhysX simulation.
