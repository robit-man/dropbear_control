# MYACTUATOR and Dropbear evidence review queue

Status: `EXECUTABLE-REVIEW-INBOX / ALL HUMAN ASSIGNMENTS OPEN`

The unified queue at
[`generated/myactuator/evidence_review/queue.json`](../generated/myactuator/evidence_review/queue.json)
turns the scattered evidence gaps into 145 exact review subjects:

| Workstream | Subjects | Current state |
|---|---:|---|
| Protocol applicability | 44 models | 34 need installed-tuple/capture evidence; 10 need an exact protocol source |
| CAD articulation/output member | 53 configurations | 41 packet-reviewable; 12 require re-source, partition or healing |
| Plant evidence | 44 models | 1,496 parameter and 176 envelope observations remain missing |
| Dropbear source authority | 1 | Reviewer/approver assignment required |
| Dropbear graph authority | 1 | Blocked by source authority plus 161 unanswered questions |
| Installed inventory | 1 | Bounded U0 authorization and named humans required |
| CAN adapter | 1 | Blocked by installed controller identity and reviewed TX-disable evidence |

The companion local HTML view is
[`generated/myactuator/evidence_review/index.html`](../generated/myactuator/evidence_review/index.html).
It makes no network request and contains no vendor geometry.

The next handoff layer is
[`MYACTUATOR_EVIDENCE_INTAKE_HANDOFF.md`](MYACTUATOR_EVIDENCE_INTAKE_HANDOFF.md).
It materializes all 53 CAD and 44 plant subjects into 97 source-bound drafts
covering the queue's 2,361 CAD questions and plant requirements. Draft
materialization is not assignment, review or acceptance.

## Assignment boundary

The controlled input
[`assets/myactuator/reviewer_assignments.json`](../assets/myactuator/reviewer_assignments.json)
defines 17 non-automatable roles and their required independence edges. It is
currently a digest-bound draft with 0/17 assigned.

A submitted assignment register requires an exact human identity, team,
competence evidence, acknowledgement and UTC due time for every role.
Conflicting identities across independence edges fail validation. Assignment
is scheduling, not approval, and cannot authorize a physical action.

## Dependency order

1. Source and CAD/plant review can begin from pinned offline evidence.
2. Installed-unit identity is required before a real protocol decision.
3. Dropbear source authority must precede graph authority.
4. Installed controller/transceiver identity must precede adapter selection.
5. A reviewed listen-only adapter still needs a separate bounded physical
   authorization before observation.
6. Protocol, CAD, plant, graph and adapter acceptances remain separate inputs
   to later simulator, ROS, HIL and robot gates.

No queue state grants complete motor support, physical fidelity or motion
authority. Every item contains `support_granted=false`,
`physical_motion_authority=false` and
`physical_action_permitted=false`.

## Rebuild and verify

```bash
python3 tools/generate_evidence_review_queue.py --check
tests/evidence_review_queue/run_tests.sh
```

Regeneration is intentional:

```bash
python3 tools/generate_evidence_review_queue.py --write
```

Any source or assignment hash drift invalidates the queue. Failed generation
does not replace the last valid JSON or HTML outputs.
