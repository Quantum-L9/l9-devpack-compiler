---
name: l9-devpack-compiler
description: compile a source repository into a dpk-1.0 developer pack — the six-layer machine-parseable envelope (.ai/manifest, repository-map, constraints, task contracts, verification/eval reports, alert-to-runbook mapping, technical-debt ledger) plus an execution package (repository access, environment access, scoped credentials, authoritative contracts, a phased work queue, validation commands, and stop conditions), and emit a versioned Program Execution Blueprint v2 design-time authority set. use when the user asks to produce, build, analyze, score, or harden a developer pack / dpk / agent handoff pack, make a repo agent-operable or handoff-ready, or generate the design-time envelope that lets a human or ai agent discover, change, validate, and operate a system with zero tribal knowledge.
skill_schema: 1
layer: compiler
role: skill_entrypoint
tags: [l9, devpack, dpk, handoff, agent-operable, compiler, execution-package, exemplary]
owner: igor_beylin
status: active
version: 1.2.0
updated: 2026-08-15
sources:
  - Developer Pack Kernel (DPK-1.0)
---

# Developer Pack Compiler (DPK-1.0)

## Purpose

Turn an ambiguous source repository into a **provenance-safe, machine-parseable, self-documenting developer pack**. Compile the DPK-1.0 six-layer machine envelope **and** the execution package that makes the work reproducible. The prompt explains *what* to build; the execution package supplies the infrastructure decisions (access, credentials, contracts, work queue, validation, stop conditions) so the agent **never invents missing infrastructure**.

**Role boundary (DEC-001).** DPK is an upstream **compiler and intermediate representation**, not a runtime authority. It owns: evidence extraction, the DPK IR, structural compile-readiness scoring, and versioned **Program Execution Blueprint v2** generation. It does **not** own runtime task state, gate evaluation, attempts, approvals, leases, or receipts — the **Program Execution Controller** owns runtime state and gate results; the program owner owns the terminal verdict. DPK emits **design-time authority only**.

**Spec-first input.** The optimal input is a machine-readable **build spec** ([`schemas/spec.schema.json`](schemas/spec.schema.json)) — declarative facts (interfaces, invariants, commands, contracts, file plan, work queue, stop conditions) plus first-class `open_decisions`, and **no code bodies or pseudo-code**. A spec legitimately carries unbuilt work as `file_plan.status` + `open_decisions` (that is not a stub — see [references/spec-schema.md](references/spec-schema.md)); zero-stub governs the *built* artifact, not the spec. Each spec block maps 1:1 to a DPK layer / execution-package component.

The output must let any qualified human engineer or autonomous agent answer, with trace evidence:

> "What does this repo own, how does it work, what must never be broken, how do I change it safely, how do I prove the change is correct, how is it operated in production, and what risk or unfinished work am I inheriting?"

## Core Contract

| Mode | Output | Load |
|------|--------|------|
| analyze | Gap report: repo vs DPK-1.0 six layers + red-lines | [references/quality-gates.md](references/quality-gates.md) |
| build | The six-layer machine envelope, emitted as complete files | [references/dpk-layer-contract.md](references/dpk-layer-contract.md) |
| execution-package | Repo/env/creds/contracts/work-queue/validation/stop envelope | [references/execution-package-contract.md](references/execution-package-contract.md) |
| score | 0–100 structural readiness score + red-line verdict | [references/quality-gates.md](references/quality-gates.md) + `scripts/validate_devpack.py` |
| program-execution-v2 | Complete Program Execution Blueprint v2 design-time authority source set (definitions only; no runtime state) | [references/program-execution-v2-projection.md](references/program-execution-v2-projection.md) + `scripts/emit_program_execution_v2.py` |
| package | Full pack + execution package + score + zip | all references + [references/enforcement-gates.md](references/enforcement-gates.md) |

## The Six Layers (machine envelope)

| Layer | Artifact | Proves |
|-------|----------|--------|
| 1 Identity & Capabilities | `.ai/manifest.yaml`, `.ai/repository-map.yaml`, `.ai/constraints.yaml` | ownership, boundaries, interfaces, tiers |
| 2 Architectural Truth | verification block on every structural doc (`last_verified`, `commit`, `environment`, `confidence`) | claims map to real invariants — zero hallucination |
| 3 Change Control | `AGENTS.md` + Task Contracts (`allowed`/`prohibited` + constraints) | every mutation is bounded before it starts |
| 4 Verification & Evidence | validation-class table → commands (lint/unit/contract/integration/eval/perf/resilience) | what each test *proves* to the gatekeeper |
| 5 Operational Ownership | alert → runbook 1:1 routing (`alert.runbook` resolves) | every page has an operator path |
| 6 Transition State | signed technical-debt & risk ledger with remediation targets | inherited debt is disclosed, not greenfield |

Full artifact schemas + copy-ready templates: [references/dpk-layer-contract.md](references/dpk-layer-contract.md).

## Authority Order

When constraints conflict, apply this cascade (compiled from the DPK AGENTS.md contract; Program Execution v2 compatible):

1. Security, safety, and legal constraints.
2. Accepted architecture and contracts (system architecture invariants, public interface schemas).
3. Approved Task Contract — a **narrowing** scope projection: it may restrict but **never override** accepted architecture or public contracts.
4. Architecture Decision Records (ADRs).
5. Automated test assertions.
6. Local file stylistic conventions.
7. `Unknown` — **fail closed**: never fabricate owners, contracts, commands, or credentials; label `Unknown` and stop.

## Non-Negotiable Rules (red lines)

The cumulative structural readiness score is **instantly zero** if any hold — enforce these as hard gates:

1. **Production operations owner** must be declared in `.ai/manifest.yaml` (`ownership.operational_owner`) or derived from a provenanced policy default.
2. A **machine-executable rollback target** must be declared (presence is declaration; dry-run success is separate, independent evidence).
3. Every **non-deterministic AI feature** must map to a dedicated **evaluation suite**.
4. Every **alert links 1:1 to a runbook** that resolves to a real repo file.

**Defaults require provenance (fail closed).** An authority-affecting default (owner, library rollback) is applied only from an explicit governing policy (`.ai/policy.yaml` `policy_derived_defaults` with a real `source_id`) or an operator-supplied `--owner <team> --owner-source <id>[@rev]` — recorded in the machine report under `policy_provenance`. There is no undocumented fallback; `--strict` is accepted for compatibility but deprecated. See [references/quality-gates.md](references/quality-gates.md) §Provenance-Backed Defaults.

Plus: DO NOT weaken/delete tests to pass gates; DO NOT log prohibited fields (`raw_prompt`, `access_token`, `customer_email`); DO NOT edit generated assets directly; DO NOT invent infrastructure the execution package must supply — stop and ask.

## Compact Workflow

Each step produces a required gate artifact (see [references/enforcement-gates.md](references/enforcement-gates.md)); do not advance without it.

1. **Parse the repo** — languages, entrypoints, services, interfaces, tests, CI, owners-if-declared. Label everything unverifiable `Unknown`. → **Gate A.**
2. **Extract expertise** — run `extract_expertise` over the repo + DPK-1.0 to build the intelligence model (experts, doctrine, invariants, activation/reject signals, adapters, failure modes, leverage points); then `compress_expertise` into the smallest behavior-changing form. → **Gate B** (exemplary builds).
3. **Design the layer set** — map repo evidence to the six layers; select adapters (non-AI service, monorepo, greenfield). Only emit artifacts that carry real evidence. → **Gate C.**
4. **Emit the machine envelope** — complete `.ai/*` + AGENTS.md + verification blocks + validation-class table + alert→runbook + debt ledger, using the templates in `references/dpk-layer-contract.md`. No stubs. → **Gate D.**
5. **Emit the execution package** — the seven components in [references/execution-package-contract.md](references/execution-package-contract.md). A missing component is a **STOP**, not an invention. → **Gate E.**
6. **Score & red-line** — run `python3 scripts/validate_devpack.py <repo>`: compute the structural readiness score and the four red-line verdicts. Below 80 or any red-line tripped → `blocked`. → **Gate F.**
7. **Package & deliver** — pack + execution package + score report (+ zip on request), plus the single highest-leverage next action. → **Gate G.**

### Mandatory Exemplary Pipeline

```text
parse_repo → extract_expertise → compress_expertise → design_layers → emit_envelope → emit_execution_package → run_exemplary_gate → package
```

`extract_expertise` is required for any claimed exemplary tier; fail closed when the model is missing or incomplete.

## Multi-Agent Role Matrix (mutation control)

No model instance validates its own mutations. Split roles: **Architect** (strategy, constraints — never writes impl) → **Implementer** (minimal code — never grades itself) → **Reviewer/Test** (independent assertions, scope-creep analysis — never writes features) → **Specialist Security/Perf** (triggered on auth/prompt/hot-path changes). Detail: [references/dpk-layer-contract.md](references/dpk-layer-contract.md) §Role Matrix.

## Resource Map

- [references/dpk-layer-contract.md](references/dpk-layer-contract.md) — the six-layer artifact schemas, AI model/prompt registries, role matrix, and copy-ready templates.
- [references/execution-package-contract.md](references/execution-package-contract.md) — the reproducibility envelope: repository access, environment access, scoped credentials, authoritative contracts, phased work queue, validation commands, stop conditions.
- [references/quality-gates.md](references/quality-gates.md) — the 0–100 structural scoring matrix (weights per category), readiness bands (`compile_ready` / `compile_ready_conditional` / `blocked`), red-line overrides, and provenanced defaults.
- [references/enforcement-gates.md](references/enforcement-gates.md) — **runtime enforcement layer**: the required proof-of-compliance artifact at each workflow step; protocol-violation detection.
- [references/spec-schema.md](references/spec-schema.md) — the spec-first doctrine, the full fact set, and the field → DPK-layer mapping.
- [references/program-execution-v2-projection.md](references/program-execution-v2-projection.md) — the versioned Program Execution Blueprint v2 compile target: provenance edges, scoped Unknowns, canonical authorization ceilings.
- [schemas/spec.schema.json](schemas/spec.schema.json) — canonical machine-readable **build spec** schema (the optimal compiler input); worked example in [schemas/spec.example.json](schemas/spec.example.json).
- [scripts/validate_devpack.py](scripts/validate_devpack.py) — deterministic structural compile-readiness check: layer presence, the four red-lines, and a coarse readiness score. `python3 scripts/validate_devpack.py <repo-root>` (`--json` for machine output; `--owner` requires `--owner-source`).
- [scripts/emit_program_execution_v2.py](scripts/emit_program_execution_v2.py) — emits the complete Program Execution Blueprint v2 authority source set (definitions only; no Controller runtime state).
- [scripts/validate_exemplary_skill.py](scripts/validate_exemplary_skill.py) — deterministic exemplary-tier gate for this skill itself.

## Exemplary Provenance & Self-Improvement

Compiled through the L9 exemplary pipeline: `parse_source → extract_expertise → compress_expertise → design_skill → run_exemplary_gate → package`. The compressed intelligence layer ships as auditable artifacts, not prose:

- [expertise_model.yaml](expertise_model.yaml) — experts, doctrine, invariants, authority hierarchy, activation/reject signals, adapters, failure modes, leverage points (the `extract_expertise` / `compress_expertise` output).
- [skill_intelligence_report.yaml](skill_intelligence_report.yaml) — activation model (measured specificity + false-positive-risk), authority model, expert heuristics, evidence hierarchy, `exemplary_gate` results, tier decision.
- Deterministic gate: [scripts/validate_exemplary_skill.py](scripts/validate_exemplary_skill.py) — `tier: exemplary` is claimed only because this validator passes. Reference to `enforcement-gates` is mandatory and lives in [references/enforcement-gates.md](references/enforcement-gates.md).

**After-use improvement hook** — capture ONLY when the user reports a bad pack or asks to iterate: `missed_layer`, `hallucinated_contract`, `red_line_missed`, or `output_that_required_manual_rework`. Feed captures back into the layer contract and the red-line checks in `scripts/validate_devpack.py`.

## Validation

Before delivery: every required layer file exists and is complete (no stubs); every structural doc carries a verification block or a labeled `Unknown`; the execution package has all seven components; `scripts/validate_devpack.py` reports score ≥ 80 with **no red-line tripped** (bands are structural: `compile_ready` / `compile_ready_conditional` / `blocked` — never runtime operability); the Program Execution v2 projection validates against the official Blueprint validator in instantiated mode; and for this skill itself, `scripts/validate_exemplary_skill.py` passes.

## Failure Handling

State the exact blocker; label missing/unverifiable facts `Unknown`; never fabricate a layer, owner, contract, command, or credential; provide the smallest safe next action; if a red-line cannot be satisfied, deliver the pack as `blocked` with the specific red-line and remediation target — do not present it as compile-ready. DPK never reports runtime proof (tests executed, dry-runs, gate results) from structural inspection — that evidence belongs to the runtime authority (Program Execution Controller) and is recorded there.
