# Definition of Done: {{PROGRAM_NAME}}

The Execution Program is complete only when every applicable blocking condition is proven with evidence.

## Definition integrity

- The Blueprint validates with no unresolved placeholders or cross-reference errors.
- Every execution target, authority, decision, Unknown, risk, waiver, task, gate, and evidence record has one stable ID.
- No definition state is confused with runtime state or evidence result.

## Authority and contracts

- Every persistent fact and executable behavior has one authoritative owner.
- Competing or superseded authority paths are removed, disabled, or explicitly bounded.
- Cross-surface contracts name producer, consumer, version, compatibility, failure, replay, and ownership behavior.

## Execution and validation

- Every required task is `COMPLETED` or explicitly cancelled by accepted decision.
- Every blocking convergence gate has a valid Controller Gate Evaluation of `PASS`.
- Worker claims exactly match Controller-observed changed files and validations.
- Failure, timeout, retry, duplicate delivery, replay, malformed input, authorization, rollback, and recovery paths are proven where applicable.

## Operations and closure

- Observability signals, alert routing, support ownership, and recovery are operational.
- Cutover or destructive actions occurred only under exact approval.
- The Controller Handoff Receipt is accepted by the program owner.
- Residual risks are accepted by named owners.
- The final verdict is one of the canonical program verdicts.
