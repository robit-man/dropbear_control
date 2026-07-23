# Plant runtime execution profiles

This directory is the controlled human-input namespace for exact
`myactuator-plant-runtime-profile/1` submissions.

The tracked baseline intentionally contains no JSON profile. A profile is not
a motor specification: it selects an operating point and records solver,
scenario, damping, controller and thermal-policy choices for one exact
generated plant parameter set. It must be prepared and independently reviewed
by two distinct humans, is hash-bound to that set and its assembly generation,
and cannot grant hardware support, physical validation or motion authority.

`tools/generate_plant_runtime_adapters.py` owns the generated registry and
runtime contracts. Unknown files, duplicate subjects, source drift and any
unrepresentable source semantics fail closed.
