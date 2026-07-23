# Iteration 14 discovery plan

Status: `ACTIVE / DEFINITION-OF-READY NOT MET`

The executable review queue is the discovery backlog. Human work is ready
only when required roles are assigned, competence and independence are
acknowledged, evidence inputs are accessible, and the decision format is
known. Physical work additionally requires signed action-specific authority.

## Immediate handoff cohorts

| Cohort | Scope | Ready | Blocked | Required roles |
|---|---:|---:|---:|---|
| CAD packet review | 53 configurations | 41 | 12 | geometry reviewer, license owner |
| Plant manual extraction | 44 models | 44 | 0 | source extractor, fact reviewer |
| Protocol exact tuples | 44 models | 0 | 44 | submitter, source reviewer, decision reviewer, inventory |
| Dropbear source authority | 7 roles + 29 divergences | 1 template | assignments | source reviewer, source approver |
| Dropbear graph authority | 161 questions | 0 | source authority | graph reviewer |
| U0 inventory | 12 slots | 0 | authorization | owner, safety, operator, reviewer, custodian |
| Adapter selection | one installed controller | 0 | inventory/TX-disable | adapter reviewer |

## Definition of Ready

- Exact subject and source hashes match the queue.
- Candidate, reviewed, accepted, correlated and physical evidence remain
  distinct.
- Owner and independent reviewer are named in the submitted assignment
  register.
- Evidence location, custody and redistribution constraints are known.
- Decision schema/tool and rejection path are available.
- Due date and escalation path are acknowledged.
- Physical scope, if any, has bounded authorization, stop criteria,
  restoration and expiration.

Until those conditions hold, a row remains preparation work and cannot enter
Delivery as accepted evidence.
