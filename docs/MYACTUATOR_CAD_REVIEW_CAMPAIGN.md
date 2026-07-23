# MYACTUATOR all-configuration CAD review campaign

Status: `LOCAL REVIEW NAVIGATION / ZERO ACCEPTED GEOMETRY`

Open the local campaign at
[`generated/myactuator/cad/campaign/index.html`](../generated/myactuator/cad/campaign/index.html).
Its canonical machine-readable form is
[`campaign.json`](../generated/myactuator/cad/campaign/campaign.json).

## Exact coverage

| Campaign state | Count |
|---|---:|
| Exact models | 44 |
| Exact configurations/STEP variants | 53 |
| Assembly member-review lane | 26 |
| Flattened disconnected-component lane | 15 |
| Flattened single-solid face-partition/re-source lane | 2 |
| Flattened high-component specialized-partition/re-source lane | 5 |
| Shell healing/re-source lane | 5 |
| Packet-reviewable with current evidence | 41 |
| Blocked for better source/healing/specialized partition | 12 |
| Candidate export available | 1 |
| Duplicate-byte groups / independent configurations | 5 / 10 |
| Questions per configuration / total unanswered | 13 / 689 |
| Accepted / browser releasable / supported | 0 / 0 / 0 |

The 41 “packet-reviewable” rows are ready for a human to investigate member
or stable-component semantics. They are not ready for automatic acceptance.
The 12 blocked rows still have useful triage packets, but they require a
better source assembly, reviewed solid healing, a reproducible face partition,
or a specialized high-component partition tool before housing/output
acceptance is possible.

## Required questions

Every configuration independently asks for evidence of:

1. fixed housing membership;
2. rotating output membership;
3. every residual member’s disposition;
4. source units and exact scale to metres;
5. source-to-canonical rigid transform;
6. physical output axis and expression frame;
7. physical origin/reference plane;
8. zero pose;
9. positive direction and motor/encoder sign;
10. housing immobility and output-only articulation;
11. visual/collision topology, healing and simplification;
12. qualified mass, center-of-mass and inertia provenance; and
13. local/redistribution license authority.

All 689 responses are structurally `unanswered` with no evidence refs.
Automation cannot fill or sign them.

## Evidence lanes

Assembly packets provide bounded member inventories and ranked names.
Name scoring is a visual-review aid only. Flattened packets provide stable
solid/shell component IDs and topology metrics. Stable IDs do not identify
semantics.

Five STEP sources are shell-only and cannot become collision geometry without
reviewed healing/solidification:

- the two exact X6-8 source occurrences;
- CEM-25;
- CEM-45; and
- FL-85-23.

Five duplicate geometry hashes each retain two separate variant,
configuration, source-package, and decision identities. An answer for one
does not transfer to the other.

## Rebuild and verify

```bash
python3 tools/generate_cad_review_campaign.py --check
tests/cad_review_campaign/run_tests.sh
```

Intentional regeneration:

```bash
python3 tools/generate_cad_review_campaign.py --write
```

The local HTML makes no network requests. Packet images are vendor-derived
local review material and are not redistributable without separate approval.
The campaign itself cannot grant CAD, simulator, motor, plant, HIL, Dropbear,
browser-release, or motion authority.
