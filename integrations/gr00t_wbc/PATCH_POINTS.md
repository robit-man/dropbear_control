# Applying the overlay to the pinned upstream

Use only a checkout matching `UPSTREAM_LOCK.json`. Do not copy released G1
weights into a Dropbear deployment bundle: the G1 decoder is 29-DoF and is not
compatible with Dropbear's 22-motor action surface.

The upstream new-embodiment registration requires these additions:

1. Place or reference the authoritative `dropbear.usd` beneath
   `gear_sonic/data/assets/robot_description/`. A derived `dropbear.xml` is
   also required by the motion library, but must first pass parity checks
   against the USD.
2. Add `gear_sonic/envs/manager_env/robots/dropbear.py`. Select the 22 USD
   joints from `config/dropbear_embodiment.json` in that exact order. Preserve
   all passive linkage joints and all 27 closure constraints in PhysX.
3. Import the robot module in
   `gear_sonic/envs/manager_env/robots/__init__.py` and register
   `type: dropbear` in `modular_tracking_env_cfg.py`.
4. Add a Dropbear converter to `gear_sonic/trl/utils/order_converter.py`.
   `DropbearOrderConverter` in this overlay is the dependency-free golden
   implementation and round-trip oracle.
5. Install `config/sonic_dropbear.yaml` in the upstream Hydra experiment
   tree. Replace G1-named encoder/decoder keys only when a new checkpoint is
   exported; their names are internal upstream identifiers in the seed config.
   Preserve `action_clip_value: 1.0`, and apply the same `[-1, 1]` clamp in the
   Dropbear deployment decoder before center/scale conversion. The pinned G1
   reference deployment does not add that clamp for Dropbear.
6. Export encoder and decoder ONNX files together with
   `config/observation_config.yaml`. The decoder must have 784 observation
   inputs and 22 action outputs. Reject any different shape at bundle admission.
7. Generalize the C++ robot transport away from Unitree G1. The Dropbear
   backend must consume the 22-state ROS 2 snapshot and emit only the 22
   commanded motor targets. Passive linkage joints are never command outputs.

## Closed-loop boundary

`closure_adapter.py` exposes the exact topology and validates reduced knee and
elbow projections. It intentionally does not synthesize the remaining passive
body transforms. Full passive poses, contact and constraint impulses come from
the source USD in Isaac/PhysX. A derived MJCF must be validated as sim-to-sim;
it is not allowed to become the source of truth.

## CUDA admission

Training and deployment configurations are CUDA-first and fail closed:

- Training: Isaac Lab 2.3.2 and a CUDA PyTorch build.
- Deployment: the CUDA/TensorRT versions required by the selected upstream
  target, with an engine built from the matching Dropbear ONNX bundle.
- CPU is allowed only for contract tests, reference conversion, and offline
  validation.

Hardware deployment remains denied until motor effort/velocity limits, PD
gains, latency, encoder signs and thermal/current guards are sourced and
validated. Those fields are deliberately marked unverified in the embodiment
contract.
