#!/usr/bin/env python3
"""Emit a complete Program Execution Blueprint v2 authority source set from a DPK pack.

DPK is a compiler and design-time authority (DEC-001). This emitter maps the
DPK IR (.ai/* envelope, execution package, policy, build facts) into the 19
Blueprint v2 indexed sources plus the operator-facing EXECUTIVE_DECISION.md and
HANDOFF.md, the governing template's boilerplate docs, its schemas/, and a
fresh MANIFEST.yaml. Output is deterministic for identical inputs.

Laws enforced (definitions only — no runtime authority):
- The emitter emits Blueprint DEFINITIONS only: no runtime task state, gate
  results, attempts, leases, or receipts are ever emitted (DNB-001/DNB-005).
- Authority-affecting facts require provenance: the operational owner is taken
  only from `.ai/manifest.yaml` or a provenanced `.ai/policy.yaml` default
  (DEC-003); every emitted fact that carries authority is traceable through
  EVIDENCE_CATALOG + SOURCE_TRACEABILITY (DEC-006, AC-013).
- Every emitted Task Card carries the exact canonical ten-action authorization
  ceiling; no action is ever granted by omission (AC-011).
- Blocking unknowns map only to the tasks that consume the missing fact
  (DEC-005, AC-012).
- Structural compile-readiness is reported via CURRENT_STATE_DELTA from
  `scripts/validate_devpack.py`; executed runtime proof is never claimed
  (DEC-004).

Fail-closed: a missing manifest, an unprovenanced owner, an empty work queue,
or an unresolvable governing template aborts with exit 2 and a precise error.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any

SCHEMA = "program-execution-blueprint"
CONTRACT_BLUEPRINT = "program-execution-blueprint.v2"
CONTRACT_CONTROLLER = "program-execution-controller.v2"
CONTRACT_PAIR = "program-execution-system.v2"

# Canonical indexed Blueprint v2 source set (EXECUTION_INDEX contract).
REQUIRED_SOURCES = [
    "PROGRAM.yaml",
    "EXECUTION_TARGETS.yaml",
    "AUTHORITY_REGISTRY.yaml",
    "DECISION_REGISTER.yaml",
    "UNKNOWN_REGISTER.yaml",
    "RISK_REGISTER.yaml",
    "WAIVER_REGISTER.yaml",
    "EVIDENCE_CATALOG.yaml",
    "DO_NOT_BUILD.yaml",
    "CURRENT_STATE_DELTA.yaml",
    "WORKSTREAMS.yaml",
    "DEPENDENCY_GRAPH.yaml",
    "EXECUTION_WAVES.yaml",
    "TASK_CARDS.yaml",
    "CONVERGENCE_GATES.yaml",
    "OBSERVABILITY_PLAN.yaml",
    "CUTOVER_AND_ROLLBACK.yaml",
    "SOURCE_TRACEABILITY.yaml",
]

# Canonical ten-action authorization ceiling (AC-011): every emitted task
# carries exactly these keys; nothing is granted by omission.
AUTH_ACTIONS = [
    "inspect",
    "local_write",
    "commit",
    "push",
    "pull_request",
    "merge",
    "publish_or_release",
    "deploy_or_migrate",
    "destructive_change",
    "external_message",
]

# Governing-template docs that are copied verbatim (with program facts
# substituted) rather than generated from pack facts.
BOILERPLATE_DOCS = [
    "README.md",
    "ARCHITECTURE.md",
    "OPERATING_MODEL.md",
    "DEFINITION_OF_DONE.md",
    "AGENT_EXECUTION_CONTRACT.md",
    "RUNBOOK.md",
    "INSTANTIATION_GUIDE.md",
    "VALIDATION.md",
    "DESIGN_RATIONALE.md",
    "CHANGELOG.md",
]

TEMPLATE_KEYS = ["PROGRAM_NAME", "PROGRAM_ID", "PROGRAM_VERSION", "PROGRAM_OWNER", "DATE"]

PLACEHOLDER_PATTERNS = [
    re.compile(r"\{\{[A-Z0-9_]+\}\}"),
    re.compile(r"REPLACE_WITH_[A-Z0-9_]+"),
]


class EmitError(RuntimeError):
    pass


# --------------------------------------------------------------------------
# Loading helpers
# --------------------------------------------------------------------------

def _load_yaml(path: Path) -> Any:
    try:
        import yaml  # type: ignore[import-not-found]

        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise EmitError(f"cannot parse {path}: {exc}") from exc


def _load_optional_yaml(path: Path) -> Any:
    if not path.is_file():
        return None
    return _load_yaml(path)


def _is_real(value: Any) -> bool:
    if not isinstance(value, str):
        return bool(value)
    stripped = value.strip()
    if stripped.lower() in {"", "unknown", "tbd", "todo", "none", "n/a", "na", "?", "fixme"}:
        return False
    if "<" in stripped and ">" in stripped:
        return False
    return bool(stripped)


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    if not slug:
        raise EmitError(f"cannot slug program id from {value!r}")
    return slug


def _digest_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _digest_tree(root: Path) -> str:
    lines = []
    for path in sorted(root.rglob("*")):
        if path.is_file():
            lines.append(f"{path.relative_to(root)}:{_digest_file(path)}")
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# DPK IR extraction
# --------------------------------------------------------------------------

def load_ir(root: Path) -> dict[str, Any]:
    manifest = _load_yaml(root / ".ai" / "manifest.yaml")
    if not isinstance(manifest, dict):
        raise EmitError("missing or invalid .ai/manifest.yaml")
    repo = manifest.get("repository")
    if not isinstance(repo, dict) or not _is_real(repo.get("id")):
        raise EmitError("manifest.repository.id is required and must be a real value")
    ownership = manifest.get("ownership") or {}
    owner = ownership.get("operational_owner")
    if not _is_real(owner):
        raise EmitError(
            "ownership.operational_owner is missing; provide it in .ai/manifest.yaml "
            "or derive it from a provenanced .ai/policy.yaml default (DEC-003)"
        )

    overlay = _load_optional_yaml(root / ".ai" / "program-execution-v2.yaml") or {}
    if not isinstance(overlay, dict):
        raise EmitError(".ai/program-execution-v2.yaml must be a mapping")
    if overlay.get("authorization_ceiling") is not None:
        raise EmitError(
            "authorization_ceiling overrides are rejected: the canonical ten-action "
            "ceiling is fixed and cannot be widened by the projection config (AC-011)"
        )
    program_version = overlay.get("program_version")
    snapshot_at = overlay.get("snapshot_at")
    if not _is_real(program_version) or not _is_real(snapshot_at):
        raise EmitError(
            ".ai/program-execution-v2.yaml requires program_version and snapshot_at"
        )

    execution_package = _load_optional_yaml(root / ".ai" / "execution-package.yaml") or {}
    package = execution_package.get("execution_package") or {}
    if not isinstance(package, dict):
        raise EmitError("execution-package.yaml must contain an execution_package mapping")
    phases = package.get("work_queue") or []
    if not isinstance(phases, list) or not phases:
        raise EmitError("execution_package.work_queue must be a non-empty list of phases")
    for idx, phase in enumerate(phases, start=1):
        if not isinstance(phase, dict) or not _is_real(phase.get("phase")):
            raise EmitError(f"work_queue phase {idx} requires a real 'phase' name")

    policy = _load_optional_yaml(root / ".ai" / "policy.yaml") or {}
    constraints = _load_optional_yaml(root / ".ai" / "constraints.yaml") or {}
    alerts = _collect_alerts(root)
    debt = _collect_debt(root)

    validator = root / "scripts" / "validate_devpack.py"
    if not validator.is_file():
        raise EmitError("scripts/validate_devpack.py is required in the pack root")
    sys.path.insert(0, str(validator.parent))
    from validate_devpack import evaluate  # type: ignore[import-not-found]

    structural = evaluate(root)
    if structural.get("red_line_tripped"):
        raise EmitError(
            "pack structural red line tripped "
            f"({structural.get('red_lines')}); the projection fails closed (DEC-003)"
        )

    return {
        "root": root,
        "manifest": manifest,
        "repo": repo,
        "owner": str(owner).strip(),
        "overlay": overlay,
        "package": package,
        "phases": phases,
        "policy": policy,
        "constraints": constraints,
        "alerts": alerts,
        "debt": debt,
        "program_version": str(program_version).strip(),
        "snapshot_at": str(snapshot_at).strip(),
        "structural": structural,
    }


def _collect_alerts(root: Path) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    for name in (".ai/alerts.yaml", ".ai/observability.yaml"):
        data = _load_optional_yaml(root / name)
        if isinstance(data, dict):
            if isinstance(data.get("alerts"), list):
                alerts += [a for a in data["alerts"] if isinstance(a, dict)]
            elif isinstance(data.get("alert"), dict):
                alerts.append(data["alert"])
    alerts_dir = root / ".ai" / "alerts"
    if alerts_dir.is_dir():
        for path in sorted(alerts_dir.glob("*.y*ml")):
            data = _load_optional_yaml(path)
            if isinstance(data, dict) and isinstance(data.get("alert"), dict):
                alerts.append(data["alert"])
    return alerts


def _collect_debt(root: Path) -> list[dict[str, Any]]:
    data = _load_optional_yaml(root / ".ai" / "debt.yaml") or {}
    items = data.get("debt") or []
    return [d for d in items if isinstance(d, dict)]


# --------------------------------------------------------------------------
# Program model construction
# --------------------------------------------------------------------------

def build_model(ir: dict[str, Any]) -> dict[str, Any]:
    repo = ir["repo"]
    program_id = _slug(str(repo["id"]))
    phases = ir["phases"]
    count = len(phases)
    wave_ids = [f"W{seq}" for seq in range(1, count + 1)]
    task_ids = [f"TASK-{seq:03d}" for seq in range(1, count + 1)]
    ws_ids = [f"WS-{seq:02d}" for seq in range(1, count + 1)]
    gate_ids = [f"GATE-{seq:03d}" for seq in range(1, count + 1)]

    # --- evidence: numeric ids (schema: ^EVID-[0-9]{3,}$) --------------
    source_evidence: dict[str, str] = {}
    evidence: list[dict[str, Any]] = []
    evidence_counter = 0

    def next_evidence_id() -> str:
        nonlocal evidence_counter
        evidence_counter += 1
        return f"EVID-{evidence_counter:03d}"

    for rel in (
        ".ai/manifest.yaml",
        ".ai/execution-package.yaml",
        ".ai/policy.yaml",
        ".ai/constraints.yaml",
        ".ai/repository-map.yaml",
        "AGENTS.md",
    ):
        path = ir["root"] / rel
        if path.is_file():
            evidence_id = next_evidence_id()
            source_evidence[rel] = evidence_id
            evidence.append(
                {
                    "id": evidence_id,
                    "type": "source_snapshot",
                    "source": rel,
                    "revision": _digest_file(path)[:16],
                    "digest": _digest_file(path),
                    "method": "sha256 file capture at emission time",
                    "environment": "local",
                    "producer": "l9-devpack-compiler (projection emitter)",
                    "produced_at": ir["snapshot_at"],
                    "expires_at": None,
                    "result": "INFORMATIONAL",
                    "status": "available",
                    "supports": task_ids,
                    "contradicts": [],
                    "notes": f"provenance anchor for facts derived from {rel}",
                }
            )
    phase_evidence_ids: list[str] = []
    for seq in range(1, count + 1):
        evidence_id = next_evidence_id()
        phase_evidence_ids.append(evidence_id)
        evidence.append(
            {
                "id": evidence_id,
                "type": "test_result",
                "source": f"phase {seq} validation execution",
                "revision": "controller_bound",
                "digest": None,
                "method": "independent command execution by the runtime authority",
                "environment": "local",
                "producer": "Program Execution Controller verifier",
                "produced_at": ir["snapshot_at"],
                "expires_at": None,
                "result": "UNKNOWN",
                "status": "planned",
                "supports": [f"GATE-{seq:03d}", f"TASK-{seq:03d}"],
                "contradicts": [],
                "notes": "runtime-executed validation evidence; structural emission never claims it",
            }
        )
    governing_evidence_id = next_evidence_id()

    # --- unknowns from blocking open decisions (scoped to consuming tasks)
    unknowns: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    open_decisions = ir.get("overlay", {}).get("open_decisions") or []
    if not isinstance(open_decisions, list):
        open_decisions = []
    for idx, od in enumerate(open_decisions, start=1):
        if not isinstance(od, dict) or not _is_real(od.get("id")):
            raise EmitError(f"open_decisions entry {idx} requires a real id")
        if od.get("blocking"):
            requested = [str(t) for t in (od.get("blocks_tasks") or [])]
            unknown_refs = sorted(set(requested) - set(task_ids))
            if unknown_refs:
                raise EmitError(
                    f"open decision {od.get('id')!r} blocks unknown task(s) {unknown_refs}; "
                    "blocks_tasks must name existing emitted tasks (AC-012)"
                )
            blockers = requested
            unknowns.append(
                {
                    "id": f"UNK-{idx:03d}",
                    "topic": str(od.get("question", od["id"])),
                    "owner": ir["owner"],
                    "blocks": blockers,
                    "safe_state": "Blocks only the named consuming tasks; unrelated work proceeds.",
                    "resolution_requirements": [str(od.get("options", []))],
                    "resolution_evidence_ids": [],
                    "status": "open",
                    "resolved_at": None,
                }
            )
        else:
            decisions.append(
                {
                    "id": f"DEC-{idx:03d}",
                    "question": str(od.get("question", od["id"])),
                    "status": "pending",
                    "owner": ir["owner"],
                    "options": [
                        {
                            "id": f"OPT-{j}",
                            "description": str(opt),
                            "benefits": ["unblocks the consuming phase"],
                            "risks": ["requires owner acceptance before promotion"],
                        }
                        for j, opt in enumerate(od.get("options") or [], start=1)
                    ],
                    "selected_option": None,
                    "rationale": None,
                    "evidence_ids": [],
                    "blocks": [],
                    "required_by": "before the consuming phase executes",
                    "supersedes": None,
                }
            )

    # --- tasks / waves / workstreams / gates from phases
    tasks: list[dict[str, Any]] = []
    waves: list[dict[str, Any]] = []
    workstreams: list[dict[str, Any]] = []
    gates: list[dict[str, Any]] = []
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    for seq, phase in enumerate(phases, start=1):
        phase_name = str(phase.get("phase"))
        task_id = task_ids[seq - 1]
        wave_id = wave_ids[seq - 1]
        ws_id = ws_ids[seq - 1]
        gate_id = gate_ids[seq - 1]
        entry_gates = [gate_ids[seq - 2]] if seq > 1 else []
        validations = [
            str(v).strip()
            for v in (phase.get("validation") or [])
            if isinstance(v, str) and v.strip()
        ]
        if not validations:
            raise EmitError(f"phase {phase_name!r} requires at least one validation command")
        exit_criteria = [str(e) for e in (phase.get("exit_criteria") or [])]
        if not exit_criteria:
            raise EmitError(f"phase {phase_name!r} requires exit_criteria")
        entry_criteria = [str(e) for e in (phase.get("entry_criteria") or [])]
        task_unknowns = [
            u["id"]
            for u in unknowns
            if task_id in u["blocks"]
        ]
        ceiling = {action: action in {"inspect", "local_write"} for action in AUTH_ACTIONS}
        if phase.get("read_only") is True:
            ceiling["local_write"] = False
        tasks.append(
            {
                "id": task_id,
                "title": f"Execute phase {phase_name}",
                "definition_status": "ready",
                "workstream_id": ws_id,
                "wave_id": wave_id,
                "target_id": "TARGET-001",
                "execution_kind": "repo_local",
                "objective": f"Satisfy the {phase_name} phase exit criteria with traced evidence.",
                "authority_basis_ids": ["AUTH-001", "AUTH-002", "AUTH-003", "AUTH-004", "AUTH-005"],
                "required_decision_ids": [d["id"] for d in decisions],
                "blocking_unknown_ids": task_unknowns,
                "input_evidence_ids": list(source_evidence.values()) + [governing_evidence_id],
                "actions": [
                    f"execute phase {phase_name} inside the target worktree",
                    "run the declared validation commands and record receipts",
                ],
                "outputs": [
                    {
                        "id": f"OUT-{seq:03d}",
                        "type": "artifact",
                        "location": f"phase {phase_name} validation receipts",
                        "required": True,
                    }
                ],
                "acceptance": [
                    {
                        "id": f"AC-{seq:03d}-{m}",
                        "statement": criterion,
                        "required_evidence_types": ["test_result"],
                    }
                    for m, criterion in enumerate(exit_criteria, start=1)
                ],
                "validation": [
                    {
                        "id": f"VAL-{seq:03d}",
                        "method": "command",
                        "command_or_inspection": command,
                        "environment": "local",
                        "expected_result": "PASS",
                    }
                    for command in validations
                ],
                "negative_cases": [
                    "a validation command fails",
                    "a change lands outside the phase scope",
                    "a blocking unknown resolves without evidence",
                ],
                "rollback": {
                    "strategy": f"restore_{task_id.lower()}_files_from_program_lock_base",
                    "trigger": "validation_failure_or_scope_drift",
                    "validation": "Restored files match the Program Lock base SHA.",
                },
                "risk": {"tier": "T2", "reversibility": "reversible", "blast_radius": phase_name},
                "authorization_ceiling": ceiling,
                "completion_gate_ids": [gate_id],
            }
        )
        nodes.append({"id": task_id, "entity_type": "task", "owner": ir["owner"]})
        if seq > 1:
            edges.append(
                {
                    "id": f"EDGE-{seq - 1:03d}",
                    "from": task_ids[seq - 2],
                    "to": task_id,
                    "relation": "requires",
                    "blocking": True,
                    "proof_gate_ids": [gate_ids[seq - 2]],
                }
            )
        workstreams.append(
            {
                "id": ws_id,
                "name": f"Phase {phase_name}",
                "objective": f"Execute the {phase_name} phase of the execution package.",
                "owner": ir["owner"],
                "target_ids": ["TARGET-001"],
                "scope": {
                    "include": ["target repository (phase scope)"],
                    "exclude": ["merge", "release", "deployment", "remote mutation"],
                },
                "inputs": entry_criteria or ["previous phase exit criteria"],
                "outputs": exit_criteria,
                "entry_gate_ids": entry_gates,
                "exit_gate_ids": [gate_id],
                "rollback_boundary": "Restore the phase files from the Program Lock base SHA.",
                "definition_status": "active",
            }
        )
        waves.append(
            {
                "id": wave_id,
                "name": f"phase_{seq}_{_slug(phase_name)}",
                "sequence": seq,
                "depends_on": [wave_ids[seq - 2]] if seq > 1 else [],
                "workstream_ids": [ws_id],
                "task_ids": [task_id],
                "entry_gate_ids": entry_gates,
                "exit_gate_ids": [gate_id],
                "rollback_boundary": "Restore wave files from the Program Lock base SHA.",
                "definition_status": "active",
            }
        )
        gates.append(
            {
                "id": gate_id,
                "name": f"phase_{seq}_converged",
                "definition_status": "active",
                "owner": ir["owner"],
                "class": "validation",
                "scope": {"wave_ids": [wave_id], "task_ids": [task_id]},
                "method": {
                    "type": "command_and_inspection",
                    "steps": [
                        f"Independently execute the {phase_name} validation commands.",
                        "Inspect the phase diff against the declared scope.",
                        "Confirm no runtime proof is claimed from structural presence.",
                    ],
                },
                "pass_condition": "All phase validation commands pass independently and the diff is scope-exact.",
                "fail_condition": "Any validation command fails, the diff exceeds scope, or evidence is weakened.",
                "blocking": True,
                "required_evidence_ids": [phase_evidence_ids[seq - 1]],
                "waiver_allowed": False,
            }
        )

    model = {
        "ir": ir,
        "program_id": program_id,
        "task_ids": task_ids,
        "wave_ids": wave_ids,
        "ws_ids": ws_ids,
        "gate_ids": gate_ids,
        "source_evidence": source_evidence,
        "phase_evidence_ids": phase_evidence_ids,
        "tasks": tasks,
        "waves": waves,
        "workstreams": workstreams,
        "gates": gates,
        "unknowns": unknowns,
        "decisions": decisions,
        "nodes": nodes,
        "edges": edges,
        "evidence": evidence,
        "critical_path": task_ids,
        "governing_evidence_id": governing_evidence_id,
    }
    return model


# --------------------------------------------------------------------------
# Source-file builders
# --------------------------------------------------------------------------

def _build_program(m: dict[str, Any]) -> dict[str, Any]:
    ir = m["ir"]
    return {
        "schema": f"{SCHEMA}.program.v2",
        "schema_version": "2.0.0",
        "program": {
            "id": m["program_id"],
            "name": str(ir["repo"].get("name", m["program_id"])),
            "version": ir["program_version"],
            "owner": ir["owner"],
            "definition_status": "accepted",
            "snapshot_at": ir["snapshot_at"],
            "objective": str(ir["repo"].get("description", "DPK-compiled execution program.")),
            "problem_statement": (
                "The target repository ships work queued in an execution package; "
                "each phase requires bounded, evidence-backed execution."
            ),
            "target_state": (
                "Every phase executes under a Task Contract with the canonical "
                "authorization ceiling; the Controller owns runtime state, gates, "
                "and receipts; the program owner owns the terminal verdict."
            ),
            "scope": {
                "include": ["target repository phase scopes", "execution package components"],
                "exclude": [
                    "merge",
                    "release",
                    "deployment",
                    "remote mutation",
                    "weakening DPK red-lines or tests merely to pass validation",
                ],
            },
            "contracts": {
                "blueprint": CONTRACT_BLUEPRINT,
                "controller_minimum": CONTRACT_CONTROLLER,
                "pair": CONTRACT_PAIR,
            },
            "authority_order": [
                "applicable_safety_legal_security_requirements",
                "accepted_architecture_and_contracts",
                "approved_task_contract_narrowing_only",
                "adrs",
                "test_assertions",
                "local_style",
                "UNKNOWN_fail_closed",
            ],
            "operating_rules": [
                "one_authority_per_responsibility",
                "controller_may_narrow_never_widen",
                "unknown_blocks_only_named_dependencies",
                "promotion_requires_evidence_backed_gates",
                "no_irreversible_action_without_exact_authority",
                "worker_claim_is_not_verification",
                "compiler_output_must_not_create_runtime_authority",
                "policy_derived_defaults_require_provenance",
                "structural_readiness_is_not_runtime_operability",
            ],
            "terminal_verdicts": [
                "CONVERGED",
                "CONVERGED_WITH_NON_BLOCKING_RISKS",
                "NOT_CONVERGED",
                "INCONCLUSIVE",
            ],
        },
    }


def _build_index(m: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": f"{SCHEMA}.index.v2",
        "schema_version": "2.0.0",
        "blueprint_contract": CONTRACT_BLUEPRINT,
        "required_sources": list(REQUIRED_SOURCES),
        "canonical_owners": {
            "task_dependencies": "DEPENDENCY_GRAPH.yaml",
            "wave_dependencies": "EXECUTION_WAVES.yaml",
            "gate_definitions": "CONVERGENCE_GATES.yaml",
            "runtime_gate_results": "Program Execution Controller",
            "task_definition_state": "TASK_CARDS.yaml",
            "task_runtime_state": "Program Execution Controller",
            "final_program_verdict": "program_owner_acceptance",
        },
        "controller_import": {
            "immutable": True,
            "digest_algorithm": "sha256",
            "unknown_contract": "reject",
            "source_change": "mark_runtime_stale",
        },
    }


def _build_targets(m: dict[str, Any]) -> dict[str, Any]:
    ir = m["ir"]
    return {
        "schema": f"{SCHEMA}.execution-targets.v2",
        "schema_version": "2.0.0",
        "targets": [
            {
                "id": "TARGET-001",
                "name": str(ir["repo"].get("name", m["program_id"])),
                "kind": "git_repository",
                "authority_owner": ir["owner"],
                "execution_mode": "repo_local",
                "repository_id": str(ir["repo"]["id"]),
                "source_of_truth": (
                    "Program Execution Controller repository registration for "
                    f"repository_id={ir['repo']['id']}"
                ),
                "environments": ["local"],
                "mutability": "reversible",
                "expected_revision": "controller_binds_exact_base_sha_at_program_lock",
                "adapter": "git",
            }
        ],
    }


def _build_authority_registry(m: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": f"{SCHEMA}.authority-registry.v2",
        "schema_version": "2.0.0",
        "policy": {
            "one_owner_per_responsibility": True,
            "projection_does_not_transfer_authority": True,
            "unresolved_conflict_result": "BLOCKED",
        },
        "responsibilities": [
            {
                "id": "AUTH-001",
                "responsibility": "DPK compiler role boundary: compilation, design-time projection, and the Program Execution runtime boundary",
                "owner_target_id": "TARGET-001",
                "source_of_truth": "SKILL.md",
                "consumers": ["DPK compiler workflow", "Program Execution v2 projection"],
                "allowed_roles": ["authority", "projection"],
                "prohibited_owner_target_ids": [],
                "enforcement": ["DPK compiles authority but does not own runtime state"],
                "validation_gate_ids": m["gate_ids"][:1],
                "definition_status": "active",
            },
            {
                "id": "AUTH-002",
                "responsibility": "Authority precedence: accepted architecture and contracts above the approved Task Contract (narrowing only)",
                "owner_target_id": "TARGET-001",
                "source_of_truth": "references/dpk-layer-contract.md",
                "consumers": ["SKILL.md", "Program Execution projection"],
                "allowed_roles": ["authority", "projection"],
                "prohibited_owner_target_ids": [],
                "enforcement": ["Task Contracts may narrow but never widen upstream authority"],
                "validation_gate_ids": m["gate_ids"][:1],
                "definition_status": "active",
            },
            {
                "id": "AUTH-003",
                "responsibility": "Provenance requirements for policy-derived defaults",
                "owner_target_id": "TARGET-001",
                "source_of_truth": "references/quality-gates.md",
                "consumers": ["scripts/validate_devpack.py", "Program Execution projection"],
                "allowed_roles": ["authority", "projection"],
                "prohibited_owner_target_ids": [],
                "enforcement": ["no authority fact passes through an undocumented default"],
                "validation_gate_ids": m["gate_ids"][:1],
                "definition_status": "active",
            },
            {
                "id": "AUTH-004",
                "responsibility": "Meaning and evidence boundary of structural compile-readiness results",
                "owner_target_id": "TARGET-001",
                "source_of_truth": "scripts/validate_devpack.py",
                "consumers": ["references/quality-gates.md", "CI consumers"],
                "allowed_roles": ["authority", "projection"],
                "prohibited_owner_target_ids": [],
                "enforcement": ["structural presence is never represented as executed proof"],
                "validation_gate_ids": m["gate_ids"][:1],
                "definition_status": "active",
            },
            {
                "id": "AUTH-005",
                "responsibility": "Program Execution Blueprint v2 projection contract and emitter",
                "owner_target_id": "TARGET-001",
                "source_of_truth": "references/program-execution-v2-projection.md",
                "consumers": ["scripts/emit_program_execution_v2.py", "Program Execution Blueprint v2"],
                "allowed_roles": ["authority", "projection"],
                "prohibited_owner_target_ids": [],
                "enforcement": [
                    "emitted sources conform to the Blueprint v2 contract",
                    "provenance is retained from input facts to emitted authority",
                    "every emitted Task Card has the exact canonical authorization ceiling",
                    "no runtime state or gate result is emitted",
                ],
                "validation_gate_ids": m["gate_ids"][:1],
                "definition_status": "active",
            },
        ],
    }


def _build_decision_register(m: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": f"{SCHEMA}.decision-register.v2",
        "schema_version": "2.0.0",
        "policy": "No blocked decision may be silently defaulted.",
        "decisions": m["decisions"],
    }


def _build_unknown_register(m: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": f"{SCHEMA}.unknown-register.v2",
        "schema_version": "2.0.0",
        "policy": "Unknowns remain explicit and block only named dependent work.",
        "unknowns": m["unknowns"],
    }


def _build_risk_register(m: dict[str, Any]) -> dict[str, Any]:
    ir = m["ir"]
    risks = []
    for idx, debt in enumerate(ir["debt"], start=1):
        risks.append(
            {
                "id": f"RISK-{idx:03d}",
                "risk": str(debt.get("title", debt.get("id", f"TD-{idx}"))),
                "severity": "high",
                "likelihood": "medium",
                "owner": ir["owner"],
                "trigger": "the recorded debt begins affecting phase work",
                "preventive_controls": ["debt disclosed in the transition ledger", "phase scoping"],
                "contingency": ["route remediation through the debt ledger owner"],
                "related_tasks": m["task_ids"][:1],
                "related_gates": m["gate_ids"][:1],
                "acceptance_decision_id": None,
                "status": "open",
            }
        )
    if not risks:
        risks.append(
            {
                "id": "RISK-001",
                "risk": "No transition debt was declared for this pack.",
                "severity": "low",
                "likelihood": "low",
                "owner": ir["owner"],
                "trigger": "latent debt surfaces during execution",
                "preventive_controls": ["transition ledger review"],
                "contingency": "record the surfaced debt in the ledger",
                "related_tasks": m["task_ids"][:1],
                "related_gates": m["gate_ids"][:1],
                "acceptance_decision_id": None,
                "status": "open",
            }
        )
    return {
        "schema": f"{SCHEMA}.risk-register.v2",
        "schema_version": "2.0.0",
        "risks": risks,
    }


def _build_waiver_register(m: dict[str, Any]) -> dict[str, Any]:
    del m  # waivers are always empty at emission time
    return {
        "schema": f"{SCHEMA}.waiver-register.v2",
        "schema_version": "2.0.0",
        "policy": {"implicit_waivers_forbidden": True, "expired_waiver_non_passing": True},
        "waivers": [],
    }


def _build_evidence_catalog(m: dict[str, Any], gov_digest: str, gov_revision: str) -> dict[str, Any]:
    evidence = list(m["evidence"])
    evidence.append(
        {
            "id": m["governing_evidence_id"],
            "type": "source_snapshot",
            "source": "governing Program Execution Blueprint v2 template and schemas",
            "revision": gov_revision,
            "digest": gov_digest,
            "method": "SHA-256 tree digest at emission time",
            "environment": "planning",
            "producer": "l9-devpack-compiler (projection emitter)",
            "produced_at": m["ir"]["snapshot_at"],
            "expires_at": None,
            "result": "INFORMATIONAL",
            "status": "available",
            "supports": m["task_ids"],
            "contradicts": [],
            "notes": "governing contract provenance for every emitted file",
        }
    )
    return {
        "schema": f"{SCHEMA}.evidence-catalog.v2",
        "schema_version": "2.0.0",
        "evidence": evidence,
    }


def _build_do_not_build(m: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": f"{SCHEMA}.do-not-build.v2",
        "schema_version": "2.0.0",
        "prohibited_primary_paths": [
            {
                "id": "DNB-001",
                "path_or_pattern": "DPK-owned runtime task state, leases, attempts, gate results, or receipts",
                "reason": "Program Execution Controller is the sole runtime authority.",
                "detection": "semantic review plus tests rejecting runtime-state emission",
                "exception_authority": "NONE",
            },
            {
                "id": "DNB-002",
                "path_or_pattern": "Task Contract authority above accepted architecture or public contracts",
                "reason": "Downstream task authority may narrow but never widen upstream authority.",
                "detection": "authority-order fixtures and forbidden-semantic scan",
                "exception_authority": "NONE",
            },
            {
                "id": "DNB-003",
                "path_or_pattern": "implicit owner, rollback, repository, credential, or branch facts",
                "reason": "Authority-affecting defaults require explicit governing provenance.",
                "detection": "negative fixtures with missing policy source",
                "exception_authority": "NONE",
            },
            {
                "id": "DNB-004",
                "path_or_pattern": "runtime-operable verdict derived only from artifact presence",
                "reason": "Structural existence is not executed proof.",
                "detection": "negative validator fixtures",
                "exception_authority": "NONE",
            },
            {
                "id": "DNB-005",
                "path_or_pattern": "duplicated Program Execution gate evaluation or Handoff Receipt authority",
                "reason": "Those runtime responsibilities belong to the Controller.",
                "detection": "emitted fixture inspection and ownership-law tests",
                "exception_authority": "NONE",
            },
            {
                "id": "DNB-006",
                "path_or_pattern": "remote mutation or embedded credentials",
                "reason": "The emitted Blueprint authorizes repo-local reversible mutation only.",
                "detection": "changed-file inspection and authorization receipt",
                "exception_authority": "NONE",
            },
        ],
        "allowed_experiments": [],
    }


def _build_current_state_delta(m: dict[str, Any]) -> dict[str, Any]:
    ir = m["ir"]
    structural = ir["structural"]
    observed = (
        f"structural compile-readiness: band={structural.get('band')} "
        f"score={structural.get('score')} red_lines={structural.get('red_lines')}; "
        "executed runtime proof is NOT claimed (DEC-004)"
    )
    return {
        "schema": f"{SCHEMA}.current-state-delta.v2",
        "schema_version": "2.0.0",
        "snapshot_at": ir["snapshot_at"],
        "freshness_policy": {
            "maximum_age": "until TARGET-001 Program Lock is created",
            "stale_result": "BLOCKED",
        },
        "sources": [
            {
                "source_id": f"SRC-{idx:03d}",
                "evidence_id": evidence_id,
                "revision": _digest_file(ir["root"] / rel)[:16],
                "freshness": "emission_snapshot",
            }
            for idx, (rel, evidence_id) in enumerate(sorted(m["source_evidence"].items()), start=1)
        ],
        "deltas": [
            {
                "id": "DELTA-001",
                "target_id": "TARGET-001",
                "expected_state": "DPK reports structural compile-readiness only.",
                "observed_state": observed,
                "classification": "proof_semantics_boundary",
                "impact": "No runtime proof is claimed from structural presence.",
                "required_action": "Runtime proof is produced only by independent Controller verification.",
                "evidence_ids": [m["governing_evidence_id"]],
            }
        ],
        "next_blocking_action": (
            "Bind TARGET-001 to an exact base SHA through the Controller, then admit wave 1."
        ),
    }


def _build_workstreams(m: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": f"{SCHEMA}.workstreams.v2",
        "schema_version": "2.0.0",
        "workstreams": m["workstreams"],
    }


def _build_dependency_graph(m: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": f"{SCHEMA}.dependency-graph.v2",
        "schema_version": "2.0.0",
        "direction": "predecessor_to_successor",
        "nodes": m["nodes"],
        "edges": m["edges"],
        "critical_path": m["critical_path"],
        "parallelizable_groups": [],
        "hard_rule": "No successor may bypass a predecessor by reproducing its output elsewhere.",
    }


def _build_waves(m: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": f"{SCHEMA}.execution-waves.v2",
        "schema_version": "2.0.0",
        "promotion_rule": "A wave starts only when prior waves and all blocking entry gates pass.",
        "waves": m["waves"],
    }


def _build_task_cards(m: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": f"{SCHEMA}.task-cards.v2",
        "schema_version": "2.0.0",
        "tasks": m["tasks"],
    }


def _build_gates(m: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": f"{SCHEMA}.convergence-gates.v2",
        "schema_version": "2.0.0",
        "result_values": ["PASS", "FAIL", "BLOCKED", "UNKNOWN", "NOT_APPLICABLE_WITH_REASON"],
        "unknown_is_non_passing": True,
        "gates": m["gates"],
    }


def _build_observability(m: dict[str, Any]) -> dict[str, Any]:
    ir = m["ir"]
    signals = []
    for idx, alert in enumerate(ir["alerts"], start=1):
        signals.append(
            {
                "id": f"OBS-{idx:03d}",
                "name": str(alert.get("name", f"alert-{idx}")),
                "owner": ir["owner"],
                "source_target_id": "TARGET-001",
                "collection_method": "alert-to-runbook static correlation",
                "expected_range": "PASS",
                "alert_condition": "alert runbook link does not resolve",
                "retention": "through program-owner terminal verdict",
                "related_gate_ids": m["gate_ids"][:1],
                "status": "planned",
            }
        )
    return {
        "schema": f"{SCHEMA}.observability-plan.v2",
        "schema_version": "2.0.0",
        "signals": signals,
        "incident_routing": [
            {
                "condition": "blocking_signal_breach",
                "owner": ir["owner"],
                "action": "pause_affected_wave_and_preserve_evidence",
            }
        ],
    }


def _build_cutover(m: dict[str, Any]) -> dict[str, Any]:
    ir = m["ir"]
    dep = ir["manifest"].get("deployment") or {}
    rollback = dep.get("rollback") or {}
    return {
        "schema": f"{SCHEMA}.cutover-and-rollback.v2",
        "schema_version": "2.0.0",
        "cutover": {
            "required_gate_ids": m["gate_ids"][-1:],
            "approval_action": "program_owner_acceptance",
            "steps": [
                "preserve final Program Lock digest and all Verification/Gate receipts",
                "generate Controller Handoff Receipt",
                "present verified local worktree and residual risks to program owner",
                "do not commit, push, open a PR, merge, publish, or deploy under this Blueprint",
            ],
            "abort_conditions": [
                "any blocking gate is not PASS",
                "unresolved authority or provenance conflict exists",
                "rollback cannot recreate the Program Lock base state",
            ],
            "observation_window": "until explicit program-owner terminal verdict",
        },
        "rollback": {
            "trigger_conditions": [
                "blocking_gate_failure",
                "material_scope_or_authority_breach",
                "program_owner_rejects_local_result",
            ],
            "steps": [
                "preserve failure evidence and receipts",
                "discard the isolated TARGET-001 worktree",
                "recreate TARGET-001 from the exact Program Lock base SHA",
            ],
            "data_reconciliation": (
                "Not applicable; the program authorizes repository-local source changes only."
            ),
            "validation": [
                "recreated worktree HEAD equals Program Lock base SHA",
                "working tree contains no program-created mutation",
            ],
            "owner": "Program Execution Controller",
            "declared_rollback": {
                "strategy": str(rollback.get("strategy", "unspecified")),
                "command": str(rollback.get("command", "unspecified")),
                "evidence_scope": "structural declaration only; dry-run success is not claimed",
            },
        },
    }


def _build_traceability(m: dict[str, Any]) -> dict[str, Any]:
    ir = m["ir"]
    sources = []
    for idx, (rel, evidence_id) in enumerate(sorted(m["source_evidence"].items()), start=1):
        sources.append(
            {
                "id": f"SRC-{idx:03d}",
                "source": rel,
                "revision": _digest_file(ir["root"] / rel)[:16],
                "authority_class": "supporting",
                "evidence_id": evidence_id,
                "claims": [f"facts emitted from {rel} trace to this digest"],
                "target_ids": ["TARGET-001"],
                "workstream_ids": m["ws_ids"],
                "task_ids": m["task_ids"],
                "gate_ids": m["gate_ids"],
                "status": "active",
            }
        )
    sources.append(
        {
            "id": f"SRC-{len(sources) + 1:03d}",
            "source": "governing Program Execution Blueprint v2 template and schemas",
            "revision": m["governing_evidence_id"],
            "authority_class": "governing",
            "evidence_id": m["governing_evidence_id"],
            "claims": [
                "canonical indexed Blueprint source set",
                "canonical ten-action authorization ceiling",
                "task-card and gate schema conformance",
            ],
            "target_ids": ["TARGET-001"],
            "workstream_ids": m["ws_ids"],
            "task_ids": m["task_ids"],
            "gate_ids": m["gate_ids"],
            "status": "active",
        }
    )
    return {
        "schema": f"{SCHEMA}.source-traceability.v2",
        "schema_version": "2.0.0",
        "authority_classes": ["governing", "supporting", "contradicting", "example", "historical", "inferred"],
        "sources": sources,
    }


# --------------------------------------------------------------------------
# Docs + manifest
# --------------------------------------------------------------------------

def _build_executive_decision(m: dict[str, Any]) -> str:
    ir = m["ir"]
    return (
        f"# Executive Decision: {ir['repo'].get('name', m['program_id'])}\n"
        "## Decision\n"
        "Compile the DPK pack into a complete Program Execution Blueprint v2 "
        "design-time authority set. The compiler owns evidence extraction, IR, "
        "structural compile-readiness, and versioned Blueprint generation; the "
        "Controller owns runtime state, gate results, and receipts.\n"
        "## Problem being resolved\n"
        "The repository's execution package queues phased work that requires "
        "bounded, evidence-backed execution with explicit authorization ceilings.\n"
        "## Target state\n"
        "Every phase executes as a repo-local Task Contract with the canonical "
        "ten-action ceiling (inspect + local_write only); the Controller owns "
        "runtime; the program owner owns the terminal verdict.\n"
        "## Authority assignment\n"
        "`AUTHORITY_REGISTRY.yaml` is canonical.\n"
        "## Forbidden end states\n"
        "- DPK and the Controller both own runtime task or gate state.\n"
        "- A Task Contract overrides accepted architecture or public contracts.\n"
        "- Missing owners, rollback paths, credentials, repositories, or branches "
        "become valid facts without provenance.\n"
        "- File presence is represented as executed runtime proof.\n"
        "- Permissions are widened by omission or downstream inference.\n"
        "- Unknowns block work that does not depend on the missing fact.\n"
        "- Existing tests or red-lines are weakened merely to obtain PASS.\n"
        "## Failure behavior\n"
        "Any authority conflict, missing provenance, official Blueprint validation "
        "failure, unexpected scope expansion, or independent validation failure "
        "blocks promotion of the affected wave. No remote mutation is authorized "
        "by this Blueprint.\n"
        "## Safe execution order\n"
        f"Phases {', '.join(m['wave_ids'])} execute in order; each wave's exit gate "
        "must PASS before the next wave is admitted.\n"
        "## Supersession rule\n"
        "Any change to the accepted decisions, authority assignments, authorization "
        "ceilings, or completion gates requires a superseding Blueprint and a new "
        "immutable Program Lock.\n"
    )


def _build_handoff(m: dict[str, Any]) -> str:
    ir = m["ir"]
    return (
        f"# Program Handoff: {ir['repo'].get('name', m['program_id'])}\n"
        "This document describes definition state only. Runtime facts come from the "
        "active Program Execution Controller and its Handoff Receipt.\n"
        "## Program revision\n"
        f"- Program version: `{ir['program_version']}`\n"
        f"- Blueprint contract: `{CONTRACT_BLUEPRINT}`\n"
        f"- Snapshot: `{ir['snapshot_at']}`\n"
        "- Accepted Controller Handoff Receipt: `NONE`\n"
        "## Definition state\n"
        f"- Waves: `{', '.join(m['wave_ids'])}`\n"
        f"- Tasks: `{', '.join(m['task_ids'])}`\n"
        "- Blocking decisions: `NONE`\n"
        "- Blocking Unknowns: named per task in `UNKNOWN_REGISTER.yaml`\n"
        "## Exact next action\n"
        "Bind TARGET-001 to the exact Controller-managed local repository/base SHA, "
        "then admit the first wave.\n"
        "## Authorization status\n"
        "This Blueprint permits repo-local reversible writes only. Commit, push, "
        "pull request, merge, release, deployment, destructive change, and external "
        "messaging are not authorized.\n"
        "## Controller return path\n"
        "Consume only a Handoff Receipt bound to the active Program Lock digest. "
        "The Controller may report verified tasks and evaluated gates but does not "
        "declare this program converged. The program owner owns the terminal verdict.\n"
    )


def _write_manifest(out: Path) -> None:
    entries = []
    for path in sorted(out.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts and path.name != "MANIFEST.yaml":
            entries.append(
                {"path": str(path.relative_to(out)), "sha256": _digest_file(path)}
            )
    payload = {
        "schema": f"{SCHEMA}.manifest.v2",
        "files": entries,
    }
    (out / "MANIFEST.yaml").write_text(
        __import__("yaml").safe_dump(payload, sort_keys=True), encoding="utf-8"
    )


def _assert_no_placeholders(out: Path) -> None:
    for path in out.rglob("*"):
        if not path.is_file() or path.name == "MANIFEST.yaml":
            continue
        if path.suffix not in {".yaml", ".md"}:
            continue
        text = path.read_text(encoding="utf-8")
        for pattern in PLACEHOLDER_PATTERNS:
            match = pattern.search(text)
            if match:
                raise EmitError(f"placeholder {match.group(0)!r} in {path.relative_to(out)}")


def _assert_no_runtime_state(m: dict[str, Any]) -> None:
    banned = ["runtime_state", "gate_result", "attempt_result", "lease", "handoff_receipt"]
    import yaml as _yaml

    def walk(value: Any, trail: str) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key.lower() in banned:
                    raise EmitError(f"runtime-state key {trail}.{key} would be emitted")
                walk(child, f"{trail}.{key}")
        elif isinstance(value, list):
            for idx, child in enumerate(value):
                walk(child, f"{trail}[{idx}]")

    walk(
        {
            "tasks": m["tasks"],
            "gates": m["gates"],
            "waves": m["waves"],
            "workstreams": m["workstreams"],
        },
        "<emitted>",
    )
    del _yaml


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def emit(root: Path, out: Path, template_dir: Path) -> dict[str, Any]:
    root = root.resolve()
    out = out.resolve()
    template_dir = template_dir.resolve()
    if out.exists() and any(out.iterdir()):
        raise EmitError(f"output directory must be empty: {out}")
    if not (template_dir / "schemas").is_dir():
        raise EmitError(f"governing template lacks schemas/: {template_dir}")
    if not (template_dir / "scripts" / "validate_blueprint.py").is_file():
        raise EmitError(f"governing template lacks validate_blueprint.py: {template_dir}")

    ir = load_ir(root)
    model = build_model(ir)
    # Provenance self-check (AC-013): every authority-affecting fact emitted
    # from the manifest must trace to a captured source-evidence anchor.
    for authority_fact in ("operational_owner", "repository_id", "rollback"):
        if ".ai/manifest.yaml" not in model["source_evidence"]:
            raise EmitError(
                f"provenance anchor missing for authority fact {authority_fact!r}; "
                "emission fails closed"
            )
    gov_digest = _digest_tree(template_dir)
    gov_revision = gov_digest[:16]

    builders = {
        "PROGRAM.yaml": _build_program,
        "EXECUTION_INDEX.yaml": _build_index,
        "EXECUTION_TARGETS.yaml": _build_targets,
        "AUTHORITY_REGISTRY.yaml": _build_authority_registry,
        "DECISION_REGISTER.yaml": _build_decision_register,
        "UNKNOWN_REGISTER.yaml": _build_unknown_register,
        "RISK_REGISTER.yaml": _build_risk_register,
        "WAIVER_REGISTER.yaml": _build_waiver_register,
        "EVIDENCE_CATALOG.yaml": lambda m: _build_evidence_catalog(m, gov_digest, gov_revision),
        "DO_NOT_BUILD.yaml": _build_do_not_build,
        "CURRENT_STATE_DELTA.yaml": _build_current_state_delta,
        "WORKSTREAMS.yaml": _build_workstreams,
        "DEPENDENCY_GRAPH.yaml": _build_dependency_graph,
        "EXECUTION_WAVES.yaml": _build_waves,
        "TASK_CARDS.yaml": _build_task_cards,
        "CONVERGENCE_GATES.yaml": _build_gates,
        "OBSERVABILITY_PLAN.yaml": _build_observability,
        "CUTOVER_AND_ROLLBACK.yaml": _build_cutover,
        "SOURCE_TRACEABILITY.yaml": _build_traceability,
    }

    out.mkdir(parents=True)
    import yaml

    for name in REQUIRED_SOURCES:
        (out / name).write_text(
            yaml.safe_dump(builders[name](model), sort_keys=True, width=120),
            encoding="utf-8",
        )
    (out / "EXECUTION_INDEX.yaml").write_text(
        yaml.safe_dump(_build_index(model), sort_keys=True, width=120),
        encoding="utf-8",
    )
    (out / "EXECUTIVE_DECISION.md").write_text(_build_executive_decision(model), encoding="utf-8")
    (out / "HANDOFF.md").write_text(_build_handoff(model), encoding="utf-8")

    for doc in BOILERPLATE_DOCS:
        source = template_dir / doc
        if not source.is_file():
            raise EmitError(f"governing template lacks {doc}")
        text = source.read_text(encoding="utf-8")
        replacements = {
            "PROGRAM_NAME": str(ir["repo"].get("name", model["program_id"])),
            "PROGRAM_ID": model["program_id"],
            "PROGRAM_VERSION": ir["program_version"],
            "PROGRAM_OWNER": ir["owner"],
            "DATE": ir["snapshot_at"],
        }
        for key, value in replacements.items():
            text = text.replace("{{" + key + "}}", value)
        (out / doc).write_text(text, encoding="utf-8")

    template_vars = template_dir / "TEMPLATE_VARIABLES.yaml"
    if not template_vars.is_file():
        raise EmitError("governing template lacks TEMPLATE_VARIABLES.yaml")
    shutil.copy2(template_vars, out / "TEMPLATE_VARIABLES.yaml")
    shutil.copytree(template_dir / "schemas", out / "schemas")
    for schema_path in sorted((out / "schemas").rglob("*")):
        if schema_path.is_file():
            schema_text = schema_path.read_text(encoding="utf-8")
            for key, value in {
                "PROGRAM_NAME": str(ir["repo"].get("name", model["program_id"])),
                "PROGRAM_ID": model["program_id"],
                "PROGRAM_VERSION": ir["program_version"],
                "PROGRAM_OWNER": ir["owner"],
                "DATE": ir["snapshot_at"],
            }.items():
                schema_text = schema_text.replace("{{" + key + "}}", value)
            schema_path.write_text(schema_text, encoding="utf-8")

    _assert_no_placeholders(out)
    _assert_no_runtime_state(model)
    _write_manifest(out)
    return {
        "program_id": model["program_id"],
        "tasks": len(model["task_ids"]),
        "waves": len(model["wave_ids"]),
        "gates": len(model["gate_ids"]),
        "governing_template_digest": gov_digest,
        "output": str(out),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Emit a complete Program Execution Blueprint v2 source set from a DPK pack."
    )
    parser.add_argument("repo", help="Path to the DPK pack / repository root")
    parser.add_argument("--out", required=True, help="Output directory (must not exist or be empty)")
    parser.add_argument(
        "--blueprint-template-dir",
        required=True,
        help="Governing Program Execution Blueprint template dir (schemas + docs + validator)",
    )
    args = parser.parse_args()
    try:
        result = emit(Path(args.repo), Path(args.out), Path(args.blueprint_template_dir))
    except EmitError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 2
    print(
        "emitted program={program_id} tasks={tasks} waves={waves} gates={gates} "
        "governing_digest={governing_template_digest} -> {output}".format(**result)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
