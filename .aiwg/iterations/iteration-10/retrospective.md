# Iteration 10 retrospective

## What changed

The largest ambiguity was not a missing parser or simulator feature; it was
authority. Dropbear contains multiple source, expanded and install
descriptions, 161 unresolved mechanical/mapping questions and a six-actuator
versus five-ROS-joint cardinality mismatch per leg. Treating any runnable
description as canonical would have propagated guesses into ROS, simulation
and physical control.

The iteration therefore built a steel thread from exact source selection to a
reviewed graph and then deliberately stopped every consumer at the missing
human decision. This made the current absence measurable: zero accepted
sources, zero graph, zero mappings and zero handles, rather than an informal
TODO hidden behind a working visualization.

## What worked

- Hash-bound subjects made repository/tree/config drift a hard failure.
- Review cohorts and a local workbench made 161 questions tractable without
  allowing automation to answer or approve them.
- Positive synthetic graph fixtures were essential: denials alone would not
  prove tree, mimic, physical closed-chain and simulator-only semantics can
  actually be represented.
- Four narrow consumer views exposed parity mistakes early and kept candidate
  file paths out of browser/runtime outputs.
- The hardware API made backend substitution, signal provenance, lease timing
  and lifecycle cancellation explicit before runtime integration.
- Planning Iteration 11 one iteration ahead produced an actionable unpowered
  package while retaining zero physical authority.
- The dual-track iteration structure from the SDLC flow skill helped separate
  current delivery from next-iteration discovery and prevented hardware work
  from leaking into offline implementation.

## What remains difficult

- Human review is now the critical path for source, graph and CAD authority.
- The 112 mimic/coupling and 35 Gazebo-loop candidates require real mechanical
  expertise and likely source-model simplification before efficient review.
- The exact installed CAN controller/transceiver and all twelve
  model/hardware/firmware identities are still unknown.
- Real plant correlation and whole-robot simulation cannot be recovered from
  STEP shape or protocol documents.
- Three legacy host command object graphs and the preserved ESP32 runtime still
  need a separately reviewed migration to the common API.

## Next iteration guidance

Begin with one explicitly authorized, de-energized installed-inventory
campaign. Do not connect a CAN adapter during that authorization. Use its
observations to decide TWAI versus MCP2515 and design a separately authorized
isolated listen-only campaign. In parallel, seek independent source/graph/CAD
review so physical identity work and robot-model authority converge without
either being guessed from the other.
