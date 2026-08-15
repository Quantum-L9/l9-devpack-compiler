<!-- L9_META
l9_schema: 1
parent: l9-devpack-compiler
layer: reference
role: quality_gates
tags: [dpk, scoring, readiness, red-lines, handoff]
owner: igor_beylin
status: active
version: 2.0.0
updated: 2026-08-15
/L9_META -->

# Quality Gates & Readiness Scoring

## Purpose

Score a compiled dev pack 0–100 for handoff readiness, and enforce the red-line overrides that instantly disqualify it. Implemented deterministically by `scripts/validate_devpack.py`.

## Evidence Scope (DEC-004)

`validate_devpack.py` reports **structural compile-readiness only**. Artifact
presence is never represented as executed proof:

- every report declares `evidence_scope: structural_compile_readiness`;
- every category carries a `category_evidence` entry stating its evidence
  level (`structural_presence`) and a presence-only claim;
- every red line carries a `red_line_evidence` entry with
  `evidence_level: structural_declaration`;
- `executed_proof` (tests executed, rollback dry-run executed, eval executed,
  architecture-alignment verified) is **always false** in this validator.
  Runtime proof requires independent execution by another authority (e.g.,
  the Program Execution Controller).

## Scoring Matrix (weights)

| Category | Weight | Structural metric (presence only) |
|---|---|---|
| Repository Clarity | 10% | verification tokens present in root structural docs |
| Architecture Mapping | 15% | `.ai/repository-map.yaml` present (alignment verification NOT performed) |
| Local Reproducibility | 10% | bootstrap entrypoint present (`scripts/bootstrap` / Makefile) |
| Test & Eval Coverage | 15% | test directory present (+ eval reference resolves); no test execution claimed |
| Security Boundaries | 10% | `.ai/constraints.yaml` present; checks NOT executed |
| Observability Integrity | 15% | every alert statically correlates to a resolving runbook |
| Deployment & Rollback | 10% | rollback target declared; dry-run NOT executed |
| Transition Clarity | 15% | debt ledger present; remediation targets NOT verified |

## Readiness Bands (structural)

```text
[90–100]  compile_ready              — structural envelope complete, no red line
[80–89]   compile_ready_conditional  — structural envelope present with gaps
[0–79]    blocked                    — structural envelope incomplete or red line tripped
```

The legacy `operable` / `conditional` labels are removed: a structural
validator cannot warrant runtime operability, and `compile_ready` does not
claim it. Consumers that need executed proof must obtain it independently.

## 🚨 Red-Line Overrides (score → 0 instantly)

Any one of these zeroes the cumulative score regardless of other categories.
Red-line evidence is **structural declaration only** — `red_line_evidence`
marks every red line `executed: false`.

1. **No production operations owner** in `.ai/manifest.yaml` (`ownership.operational_owner` missing/empty, or no provenanced default — see §Provenance-Backed Defaults).
2. **No machine-executable rollback target declared** (a `rollback.command` or rollback entrypoint must exist; dry-run success is NOT claimed by presence).
3. **No evaluation suite** mapping a non-deterministic AI feature (each `prompts.*` / model role must reference a resolving `eval_suite`/`eval_baseline`).
4. **Broken alert→runbook link** (any `alert.runbook` path does not resolve to a real file).

## Library / SDK Adapter (red-line interpretation)

DPK-1.0 red-lines are service-centric. For a **library/SDK** (`repository.type: library`) map them to the packaging equivalents — the red line still holds, only its evidence changes:

- **Ops owner** → the package **maintainer / owning team** (still required; `Unknown` fails; a provenanced policy default may apply — see §Provenance-Backed Defaults).
- **Rollback** → a **version pin/yank** target (`npm dist-tag` + `npm deprecate`, or a yanked release) that is declared, plus a **golden-parity gate** as the safety net. Declaration is structural; dry-run success is separate, independent evidence.
- **Eval suite** → N/A when the library is deterministic (no non-deterministic AI feature); the parity/golden-vector suite is the equivalent proof.
- **Alert→runbook** → a **CI parity-failure signal** (cross-language vector mismatch) routed to a documented response, in place of a production page.

## Provenance-Backed Defaults (fail-closed)

An authority-affecting default is **derived only from an explicit governing
policy with recorded provenance**. `validate_devpack.py` has no undocumented
fallback: a missing fact stays a red-line failure until a provenanced default
exists.

The canonical policy artifact is **`.ai/policy.yaml`**:

```yaml
policy_derived_defaults:
  operational_owner:
    value: quantum-ai
    source_id: quantum-ai-org-policy   # governing source identity (required)
    source_revision: "2026-07"         # optional revision/version of that source
  library_rollback:
    value: version-pin-yank
    source_id: dpk-1.0-library-adapter
    source_revision: "1.2.0"
```

Rules:

- **Ops owner** — declared `ownership.operational_owner` in `.ai/manifest.yaml`
  always wins. When missing/placeholder, an `operational_owner` policy entry
  applies only if it carries a real `source_id` (a placeholder `source_id` is
  rejected). Alternatively the operator may pass `--owner <team>
  --owner-source <id>[@revision]`; `--owner` alone is rejected.
- **Rollback (library/SDK only)** — a declared rollback target always wins. A
  library without one may default to the version pin/yank target (`npm
  dist-tag` + `npm deprecate`) only from a provenanced `library_rollback`
  policy entry.
- **Machine record** — every applied or rejected derivation is recorded in the
  report under `policy_provenance` (fact, status, derived value, and governing
  source identity). Provenance that exists only in prose and is absent from
  machine output does not count.
- **Fail closed** — no policy entry, an entry without a real `source_id`, or a
  missing `--owner-source` leaves the red line **failing**. `--strict` is
  accepted for DPK-1.0 compatibility but is deprecated: fail-closed is now the
  only mode.

Autofix is removed: a **broken runbook link** and a **missing eval suite for a
real AI feature** fail as before, and unspecified owners/rollback now also fail
unless derivation carries provenance. When the compiler emits a pack (Gate D)
it applies the same rule: it never writes a defaulted `operational_owner` or
library rollback without recording the governing source.

## Verdict

- `compile_ready` — score ≥ 90, no red-line (structural only).
- `compile_ready_conditional` — score 80–89, no red-line.
- `blocked` — score < 80 **or** any red-line tripped. Never present a `blocked` pack as compile-ready; deliver it with the specific failing red-line/category and its remediation target. Never present any structural verdict as runtime operability.

## Output

`scripts/validate_devpack.py` emits a machine-readable report:
`evidence_scope`, per-category scores with `category_evidence` (evidence level
+ presence-only claim), `red_line_evidence` (structural declaration,
`executed: false`), `executed_proof` (always false), total score, band, the
`policy_provenance` record, and the ranked remediation list. Exit codes: `0`
compile_ready/compile_ready_conditional, `1` blocked (red-line or score<80),
`2` unreadable input.
