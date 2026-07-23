# Dropbear CAD binding and real-plant intake plan

Status: `EVIDENCE-INTAKE-ONLY`

## CAD output-member cohorts

Prioritize review by installation relevance and recoverability:

1. exact X12-320 assembly/archive variants that can expose housing, rotor and
   output members separately;
2. exact installed motor model once unpowered inventory identifies it;
3. flattened variants whose archive has a traceable source assembly and can be
   re-exported with stable occurrence lineage;
4. shell-only or inseparable variants requiring vendor re-source; and
5. families not observed on Dropbear, retained as catalog coverage only.

Each accepted binding needs exact CAD asset/hash, configuration identity,
occurrence/output member, housing member, output frame, axis, sign, zero
reference, assembly transform and independent reviewer. Mesh similarity and
filename tokens are hypotheses only. Healing or re-export produces a new
derived artifact with tool/version/arguments/source hashes; it cannot rewrite
the vendor source or silently inherit support.

## Real actuator-plant intake

A real plant parameter set is separate from STEP geometry and protocol
emulation. For every electrical, mechanical, friction, backlash, thermal,
sensor and delay parameter, record:

- parameter definition, frame and unit;
- exact motor/hardware/firmware/control-mode applicability;
- source type (official value, independent measurement or reviewed fit);
- raw evidence path/hash and acquisition setup;
- estimate, uncertainty/distribution and covariance/correlation;
- voltage, temperature, load, speed and time envelope;
- fit/validation split, residual metric and acceptance threshold;
- solver/time-step/numerical-stability evidence; and
- owner, independent reviewer and invalidation conditions.

No nominal or convenient value fills a missing real parameter. A fitted model
must be validated on held-out trajectories and compared against the current
synthetic baseline without relabeling either as physical truth.

## Exit gates

CAD review can admit one exact mechanical binding but grants no drive support.
Plant review can admit one exact model tuple and envelope but grants no
hardware command authority. Simulator integration needs both plus canonical
graph, calibration and limit references; physical motion additionally needs
route, safe-power and HIL gates.
