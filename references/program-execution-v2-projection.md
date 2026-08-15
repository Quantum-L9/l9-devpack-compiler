<!-- L9_META
l9_schema: 1
parent: l9-devpack-compiler
layer: reference
role: program_execution_v2_projection
tags: [dpk, program-execution, blueprint-v2, projection, emitter, provenance]
owner: igor_beylin
status: active
version: 1.0.0
updated: 2026-08-15
/L9_META -->

# Program Execution Blueprint v2 Projection (compile target)

## Purpose

The versioned **program-execution-v2** compile target: `scripts/emit_program_execution_v2.py` maps a DPK pack's IR into the complete Program Execution Blueprint v2 indexed authority source set — **definitions only**. The Blueprint owns design-time execution authority; the Controller owns runtime state; the program owner owns the terminal verdict. DPK never becomes a runtime authority (DEC-001).

## Role boundary

| Layer | Owns |
|---|---|
| DPK compiler | evidence extraction, DPK IR, structural compile-readiness, versioned Blueprint generation |
| Program Execution Blueprint | accepted design-time authority (this emitted set) |
| Program Execution Controller | runtime state, exact repo bindings, attempts, verification, recovery, gates, receipts |
| Program owner | terminal verdict |

The emitter produces no runtime state, gate results, attempts, leases, or receipts (DNB-001, DNB-005).

## Input model

The pack root provides:

- `.ai/manifest.yaml` — identity, ownership (provenanced `operational_owner` required), deployment rollback declaration;
- `.ai/execution-package.yaml` — `work_queue` phases (each phase: `phase`, `entry_criteria`, `exit_criteria`, `validation` commands); a phase may carry `read_only: true`;
- `.ai/program-execution-v2.yaml` — the versioned target overlay config (schema: [schemas/program-execution-v2-target.schema.json](../schemas/program-execution-v2-target.schema.json)): `program_version`, `snapshot_at`, and `open_decisions` (blocking entries become **scoped** UNKNOWN_REGISTER records via `blocks_tasks`; non-blocking entries become pending DECISION_REGISTER records);
- `.ai/policy.yaml`, `.ai/constraints.yaml`, `.ai/alerts*`, `.ai/debt.yaml`, `AGENTS.md` — provenance facts;
- `scripts/validate_devpack.py` — the structural compile-readiness report, recorded honestly in CURRENT_STATE_DELTA (executed proof is never claimed, DEC-004).

Fail-closed: a missing manifest, an unprovenanced owner, an empty work queue, or a phase without validation commands aborts emission with exit 2 — the emitter never invents authority facts (DEC-003).

## Mapping (DPK IR → Blueprint v2 sources)

| Blueprint source | Populated from |
|---|---|
| PROGRAM.yaml | manifest identity + ownership (provenanced) + overlay `program_version`/`snapshot_at`; canonical authority order |
| EXECUTION_TARGETS.yaml | `repository.id` → TARGET-001 (git_repository, repo_local) |
| AUTHORITY_REGISTRY.yaml | DPK role boundary (AUTH-001…AUTH-005) with source_of_truth paths |
| DECISION_REGISTER.yaml | non-blocking `open_decisions` (pending) |
| UNKNOWN_REGISTER.yaml | blocking `open_decisions`; each blocks **only** its `blocks_tasks` (DEC-005) |
| RISK_REGISTER.yaml | `.ai/debt.yaml` ledger entries |
| EVIDENCE_CATALOG.yaml | sha256 provenance anchors per source file + per-phase planned test evidence + EVID-GOV-001 (governing template tree digest) |
| DO_NOT_BUILD.yaml | DPK red lines + runtime-ownership prohibitions |
| CURRENT_STATE_DELTA.yaml | `validate_devpack` structural report (honest semantics) |
| WORKSTREAMS / WAVES / TASK_CARDS / GATES / DEPENDENCY_GRAPH | one workstream, wave, task, gate, and graph node per execution-package phase (serial order) |
| OBSERVABILITY_PLAN.yaml | pack alerts (static correlation signals) |
| CUTOVER_AND_ROLLBACK.yaml | manifest `deployment.rollback` (declaration only) |
| SOURCE_TRACEABILITY.yaml | provenance edges: every source file → claims → tasks/gates/workstreams |

Every emitted Task Card carries the **exact canonical ten-action authorization ceiling** — `inspect: true`, `local_write: true` (false when the phase is `read_only`), and the eight remote/destructive actions `false`. Nothing is granted by omission (AC-011).

## Governing contract

The emitter copies the governing Blueprint template's boilerplate docs, `TEMPLATE_VARIABLES.yaml`, and `schemas/` from the EVID-006-bound core distribution (flag `--blueprint-template-dir`) and records its tree digest as EVID-GOV-001. Validate the emitted set with the official `validate_blueprint.py --mode instantiated` at that exact revision.

## Usage

```bash
python3 scripts/emit_program_execution_v2.py <pack-root> \
  --out <empty-output-dir> \
  --blueprint-template-dir <governing-core>/program-execution-blueprint-template
```

## Non-negotiable

- No runtime state, gate results, or receipts are ever emitted.
- No owner, repository, branch, or rollback fact is invented; missing authority fails closed.
- Structural compile-readiness is never presented as runtime proof.
- Unknowns block only named dependents.
- Emission is deterministic: identical inputs produce byte-identical outputs.
