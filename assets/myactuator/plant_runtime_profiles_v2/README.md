# Plant runtime execution profiles V2

This is the controlled human-input namespace for exact
`myactuator-plant-runtime-profile/2` submissions.

The tracked baseline intentionally contains no JSON profile. A V2 profile
does not create motor facts or motor support. It selects the deterministic
torque regime, delay-jitter interpretation, operating point, scenario bounds,
transmission damping, current-controller gain, and separate winding/case
derate thresholds for one exact generated plant parameter set.

Every submission must be prepared and independently accepted by two distinct
humans, bind the exact parameter-set and assembly-generation hashes, and keep
support, physical validation, physical I/O, and motion authority false.
`tools/generate_plant_runtime_adapters_v2.py` owns the derived registry and
contracts; unknown files, duplicate subjects, hash drift, unreviewed choices,
or engine-incompatible source semantics fail closed.
