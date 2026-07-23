# Dropbear source-authority registry V2

The V2 registry is a positive-capable lifecycle boundary for selecting one
canonical Dropbear description source. The tracked project state contains no
submission, no event and no active source authority.

Source selection is narrower than motor support, hardware readiness or motion
authorization. Every V2 submission, event and generated registry is required
to keep both `support_granted` and `physical_motion_authority` false.

## Artifacts and ownership

- `schemas/dropbear-source-authority-submission-v2.schema.json` defines a
  submission envelope around one exact V1 decision.
- `schemas/dropbear-source-authority-event-v2.schema.json` defines the closed
  accept, reject, revoke and supersede event vocabulary.
- `schemas/dropbear-source-authority-registry-v2.schema.json` defines the
  replayed runtime projection.
- `assets/dropbear/source_authority_registry/decisions/` is the human-owned
  submission namespace.
- `assets/dropbear/source_authority_registry/events/` is the human-owned,
  globally sequenced event namespace.
- `generated/dropbear_source_registry_v2/registry.json` is generated output.
- `tools/manage_dropbear_source_registry_v2.py` validates and replays
  governance evidence transactionally.
- `host/myactuator_lib/dropbear_source_registry_v2.py` independently validates
  the materialized evidence before a host consumer can use it.

The V1 decision remains the exact source-content review: current repository
commit/tree, inventory, configuration, seven roles and all divergent logical
groups. V2 adds identity, submission custody and lifecycle; it does not weaken
V1.

## Lifecycle

Every submission starts in `submitted`. Its only direct transitions are:

| Event | Prior | Next | Effect |
|---|---|---|---|
| `accept` | submitted | accepted | Makes one runtime-complete decision active |
| `reject` | submitted | rejected | Terminates the submission without authority |
| `revoke` | accepted | revoked | Immediately removes active authority |
| `supersede` | accepted | superseded | Atomically accepts one exact eligible replacement |

Event sequences start at one, are contiguous, and use strictly increasing UTC
approval times. At most one submission can be accepted after any replay step.
A superseding submission must name the old submission and the event binds both
canonical submission hashes.

The lifecycle approver must attest human identity, governance authority and
independence. The approver cannot be automation, the source reviewer or either
affected submitter. These records are evidence envelopes, not a substitute for
organizational signature verification; signed release policy remains open.

## Runtime admission and revocation

The host consumer rechecks:

1. strict schemas and registry generation/record digests;
2. current inventory and denial-only V1 baseline hashes and identities;
3. every materialized submission and event hash, ID and record digest;
4. lifecycle sequence, time order, transitions, approval separation and
   atomic supersession;
5. replayed final states, counts, blockers and active identity; and
6. exact seven-role coverage before returning selected paths.

Consumers may bind a handle to `registry_generation_sha256`. A different
generation is stale and denied. Revocation therefore removes the active item,
while supersession changes the generation and exact submission identity.

No "latest", family, filename, build/install derivative or first-match
fallback exists.

## Commands

```sh
python3 tools/manage_dropbear_source_registry_v2.py --generate
python3 tools/manage_dropbear_source_registry_v2.py --check
tests/dropbear_source_registry_v2/run_tests.sh
```

`--generate` builds the complete value before an atomic replace. Invalid
input preserves the prior generated registry. Synthetic positive fixtures use
temporary directories and never enter project evidence.

## Current baseline

As of Iteration 11:

- submissions: 0;
- lifecycle events: 0;
- active source authorities: 0;
- revoked/superseded authorities: 0;
- support granted: false; and
- physical motion authority: false.

The next dependent authority is structured graph V2. It must bind this
registry generation and cannot become canonical while the source registry has
no active accepted submission.
