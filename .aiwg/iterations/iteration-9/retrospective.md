# Iteration 9 retrospective

## What worked

- Defining calibration evidence before conversion kept prototype offsets and
  synthetic fixtures out of the physical admission path.
- Keeping four limit provenance classes separate made “most restrictive”
  executable without treating vendor maxima or missing data as robot-safe
  bounds.
- One allocation-free observation core plus one Python reference corpus made
  timestamp, source, wrap, preference and denial semantics independently
  reviewable.
- The readiness projection converted a broad cross-layer gap list into 13
  exact checks per actuator without producing placeholder runtime objects.
- Reading selected Git objects allowed the robot-description audit to cover
  sparse, source and committed install trees reproducibly.
- Storing observations once per unique object kept 198 paths and their
  duplicate relations visible without treating duplication as evidence.
- The atomic gate report removed ambiguity about which stage ran, what failed
  and which workspace/config/toolchain produced the result.

## What the work caught

1. The description generator initially used `git ls-tree -l`. In a partial
   checkout that asks Git for sizes of every unrelated large CAD blob and can
   trigger a repository-wide fetch. The run was stopped and replaced with
   size-free tree enumeration plus one selected 96-object `cat-file --batch`.
2. The first inventory schema pass rejected underscore-bearing generated
   question IDs. Stable IDs were normalized to hyphenated tokens before any
   artifact was accepted.
3. Machine-report tests caught an incorrect assumption that the canonical
   config used an `admission` field; the actual reviewed field is
   `safety_admission`.
4. Preflight caught missing executable bits on the three new suite entrypoints
   before the unified run. The full gate therefore never produced a partial
   false pass.
5. A very large patch result was ambiguous at the tool boundary. Explicit
   file inspection and focused regeneration/test became the recovery rule
   before traceability was updated.

## What remains difficult

- There are now 161 well-formed graph questions, but answering them requires
  mechanical and control review. Automation cannot decide active/passive,
  mimic/coupled or simulator-only loop-closure semantics.
- A source-authority choice is still needed among detailed, simplified,
  Gazebo, RViz, CAD-export and committed install surfaces. Exact equality only
  proves duplication.
- Both hip-yaw external feedback roles remain absent, and native drive
  telemetry applicability is unknown for every installed actuator.
- Physical calibration and measured robot limits cannot advance without
  exact serial/topology discovery and controlled movement authority.
- The ESP32 has tested portable cores but no selected physical CAN controller
  implementation, wiring evidence or integration into a single production
  task.
- Real motor plants still need model-specific sourced parameters and
  correlation. STEP geometry alone cannot supply electrical, friction,
  thermal or latency truth.
- Independent CAD review and all physical gates remain external carries.

## Process changes for Iteration 10

1. Treat source-authority selection and graph semantics as signed,
   hash-bound decisions separate from the observation inventory.
2. Partition graph review into bounded cohorts: source family, leg
   cardinality, mimic/coupling edges and simulator-only closures.
3. Generate no canonical graph until every required edge is decided and
   cross-side/cardinality/loop invariants pass transactionally.
4. Keep candidate graph decisions from granting CAD, motor, protocol,
   calibration, limit or motion support.
5. Add a denial-only ROS/hardware/simulator graph consumer before any positive
   generator exists.
6. Extend the machine report with new graph artifacts and preserve one
   exclusive output namespace per generator.
7. Continue independent CAD and physical discovery as explicit parallel
   carries; do not hold safe offline work open or automate their authority.
