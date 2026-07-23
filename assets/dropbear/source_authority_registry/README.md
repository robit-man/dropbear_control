# Source-authority registry intake

This directory is reserved for independently reviewed source-authority
decisions and lifecycle events. The tracked baseline contains no submissions.

- `decisions/`: V2 submission envelopes containing exact validated V1
  source-authority decisions.
- `events/`: exact V2 accept/reject/revoke/supersede event JSON files.

Do not place drafts, generated templates, build/install derivatives or
synthetic test fixtures here. Adding a file cannot grant support or motion;
the V2 registry validator must replay the complete lifecycle transactionally.
