# Iteration 13 all-configuration CAD campaign verification

Status: `PASS / G13.2 SOFTWARE CAMPAIGN CLOSED`

## Outcome

One local-only campaign now covers all 53 exact CAD configurations and source
variants:

- 26 assembly semantic-member review lanes;
- 15 disconnected-solid manual-partition lanes;
- 2 single-solid face-partition/re-source lanes;
- 5 high-component-count specialized-partition/re-source lanes;
- 5 shell healing/re-source lanes;
- 41 packet-reviewable configurations;
- 12 configurations blocked for better source/healing/specialized work;
- 5 duplicate-byte groups retaining 10 independent configurations;
- 13 questions per configuration / 689 unanswered total;
- 1 candidate export;
- 0 accepted configurations;
- 0 browser-releasable configurations; and
- 0 support or physical authority.

The generated local HTML index contains no network requests and links each
configuration to its exact assembly-member or flattened-component packet.
Packet images remain local vendor-derived review material and are not granted
redistribution rights.

## Canonical verification

- full-gate run: `55ef4fd05aa84247d7f649e5`
- result: `PASS`
- stages: 62/62
- critical artifacts: 26
- requirements/test catalog: 77 / 127
- source files: 573
- source manifest SHA-256:
  `1c47f0371f139101c77c8bad7fcf14f152ec360e1ddb2afb44eb3992f3af323c`
- physical work: false
- accepted CAD: 0
- motion enable: false

## Bound hashes

| Artifact | SHA-256 |
|---|---|
| Campaign schema | `72757cb0cc8c54e4115bffd066a20b3e7825f0084b82d8fbbd481ae6d2d76b8f` |
| Campaign JSON | `96f6cfaf273dae35649fc824a7d15c761cd3010cb236a5e0a18a0665468d5052` |
| Local HTML index | `f96822b49d2c1da3a6b6c10e38480ed836f95db17c58cba0f7b719bd84add99d` |
| Generator | `8cc3a954f36e719d2c0160bc4d57aa79c7674e5d2cd43c1437f0d6ace29bdfba` |

## Human and source work still required

The software campaign does not complete CAD semantics. Independent competent
reviewers must answer and evidence each configuration. Twelve configurations
first need a better source or additional partition/healing tooling. Accepted
geometry must then be rebuilt, topology/articulation-regressed, licensed,
ingested into the runtime registry, and separately bound to an accepted
Dropbear graph.
