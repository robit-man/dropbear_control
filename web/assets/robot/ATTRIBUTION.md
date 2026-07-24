# Dropbear USD browser cache

`dropbear-usd-browser.glb` is an adapted, decimated browser-rendering cache of:

- Source: `Hyperspawn/dropbear_rl`
- Revision: `3c37aedce6d445205671d5714d05ae28b8c90e2c`
- Source path: `dropbear_model/Dropbear/usd/dropbear.usd`
- Source SHA-256: `ef4434e0adb5a74cb0fe8e779c49aac4ebdcba48998ed519cf17ab16d822e073`
- Attribution: Hyperspawn Robotics — Priyanshu Pareek and Cole Myers
- License: [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/)

Changes: visual meshes were decoded from the binary USD crate, grouped by
rigid body/material, decimated, welded, quantized, and translated to glTF 2.0.
The sibling articulation manifest retains the USD rigid-body transforms,
physical joints, loop-closure records, SDK action joints, and low-level
CAN-to-USD bindings.

The browser cache does not replace the source USD or Isaac/PhysX simulation.
