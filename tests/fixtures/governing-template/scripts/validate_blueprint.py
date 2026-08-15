#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

REQUIRED_FILES = [
    "README.md",
    "PROGRAM.yaml",
    "EXECUTION_INDEX.yaml",
    "EXECUTIVE_DECISION.md",
    "ARCHITECTURE.md",
    "OPERATING_MODEL.md",
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
    "DEFINITION_OF_DONE.md",
    "AGENT_EXECUTION_CONTRACT.md",
    "HANDOFF.md",
    "RUNBOOK.md",
    "INSTANTIATION_GUIDE.md",
    "VALIDATION.md",
    "DESIGN_RATIONALE.md",
    "TEMPLATE_VARIABLES.yaml",
    "CHANGELOG.md",
    "MANIFEST.yaml",
]
SCHEMA_MAP = {
    "PROGRAM.yaml": "program.schema.json",
    "EXECUTION_INDEX.yaml": "execution-index.schema.json",
    "EXECUTION_TARGETS.yaml": "execution-targets.schema.json",
    "AUTHORITY_REGISTRY.yaml": "authority-registry.schema.json",
    "DECISION_REGISTER.yaml": "decision-register.schema.json",
    "UNKNOWN_REGISTER.yaml": "unknown-register.schema.json",
    "RISK_REGISTER.yaml": "risk-register.schema.json",
    "WAIVER_REGISTER.yaml": "waiver-register.schema.json",
    "EVIDENCE_CATALOG.yaml": "evidence-catalog.schema.json",
    "CURRENT_STATE_DELTA.yaml": "current-state-delta.schema.json",
    "DO_NOT_BUILD.yaml": "do-not-build.schema.json",
    "WORKSTREAMS.yaml": "workstreams.schema.json",
    "DEPENDENCY_GRAPH.yaml": "dependency-graph.schema.json",
    "EXECUTION_WAVES.yaml": "execution-waves.schema.json",
    "TASK_CARDS.yaml": "task-cards.schema.json",
    "CONVERGENCE_GATES.yaml": "convergence-gates.schema.json",
    "OBSERVABILITY_PLAN.yaml": "observability-plan.schema.json",
    "CUTOVER_AND_ROLLBACK.yaml": "cutover-and-rollback.schema.json",
    "SOURCE_TRACEABILITY.yaml": "source-traceability.schema.json",
}
PLACEHOLDERS = [re.compile(r"\{\{[A-Z0-9_]+\}\}"), re.compile(r"REPLACE_WITH_[A-Z0-9_]+")]
MARKDOWN_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def _is_external_or_fragment_link(target: str) -> bool:
    """True for URL/mailto links and in-page fragments (skip filesystem checks)."""
    if target.startswith("#"):
        return True
    if ":" not in target:
        return False
    scheme = target.split(":", 1)[0].lower()
    return scheme in {"http", "https", "mailto"}


AUTH_ACTIONS = {
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
}


def load_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def collect_ids(items: list[dict[str, Any]], label: str, errors: list[str]) -> set[str]:
    values: list[str] = []
    for idx, item in enumerate(items):
        value = item.get("id")
        if not isinstance(value, str) or not value:
            errors.append(f"{label}[{idx}] missing id")
        else:
            values.append(value)
    duplicates = sorted({v for v in values if values.count(v) > 1})
    if duplicates:
        errors.append(f"duplicate {label} IDs: {duplicates}")
    return set(values)


def check_refs(values: list[str], valid: set[str], context: str, errors: list[str]) -> None:
    for value in values:
        if value not in valid:
            errors.append(f"{context}: unresolved reference {value}")


def check_dag(nodes: set[str], edges: list[dict[str, Any]], errors: list[str]) -> None:
    graph = {node: [] for node in nodes}
    for edge in edges:
        source, target = edge.get("from"), edge.get("to")
        if source in graph and target in graph:
            graph[source].append(target)
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str, trail: list[str]) -> None:
        if node in visiting:
            errors.append("dependency cycle: " + " -> ".join(trail + [node]))
            return
        if node in visited:
            return
        visiting.add(node)
        for nxt in graph[node]:
            visit(nxt, trail + [node])
        visiting.remove(node)
        visited.add(node)

    for node in sorted(nodes):
        visit(node, [])


def validate(root: Path, mode: str) -> list[str]:
    root = root.resolve()
    errors: list[str] = []
    for rel in REQUIRED_FILES:
        if not (root / rel).is_file():
            errors.append(f"missing required file: {rel}")
    if errors:
        return errors

    data: dict[str, Any] = {}
    for rel, schema_name in SCHEMA_MAP.items():
        try:
            value = load_yaml(root / rel)
            schema = json.loads((root / "schemas" / schema_name).read_text(encoding="utf-8"))
            validation_errors = sorted(
                Draft202012Validator(schema).iter_errors(value), key=lambda e: list(e.path)
            )
            for exc in validation_errors:
                path = ".".join(str(p) for p in exc.path) or "<root>"
                errors.append(f"{rel}:{path}: schema violation: {exc.message}")
            data[rel] = value
        except Exception as exc:
            errors.append(f"{rel}: parse/schema failure: {exc}")

    for path in root.rglob("*.json"):
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append(f"{path.relative_to(root)}: JSON parse failed: {exc}")

    if errors:
        return errors

    index = data["EXECUTION_INDEX.yaml"]
    indexed = set(index.get("required_sources") or [])
    expected_index = {name for name in SCHEMA_MAP if name not in {"EXECUTION_INDEX.yaml"}}
    if indexed != expected_index:
        errors.append(
            f"EXECUTION_INDEX required_sources mismatch: missing={sorted(expected_index - indexed)}, extra={sorted(indexed - expected_index)}"  # noqa: E501
        )

    program = data["PROGRAM.yaml"]["program"]
    if program["contracts"] != {
        "blueprint": "program-execution-blueprint.v2",
        "controller_minimum": "program-execution-controller.v2",
        "pair": "program-execution-system.v2",
    }:
        errors.append("PROGRAM.yaml contract identifiers are not canonical v2 values")

    targets = data["EXECUTION_TARGETS.yaml"]["targets"]
    authorities = data["AUTHORITY_REGISTRY.yaml"]["responsibilities"]
    decisions = data["DECISION_REGISTER.yaml"]["decisions"]
    unknowns = data["UNKNOWN_REGISTER.yaml"]["unknowns"]
    risks = data["RISK_REGISTER.yaml"]["risks"]
    waivers = data["WAIVER_REGISTER.yaml"]["waivers"]
    evidence = data["EVIDENCE_CATALOG.yaml"]["evidence"]
    workstreams = data["WORKSTREAMS.yaml"]["workstreams"]
    graph = data["DEPENDENCY_GRAPH.yaml"]
    waves = data["EXECUTION_WAVES.yaml"]["waves"]
    tasks = data["TASK_CARDS.yaml"]["tasks"]
    gates = data["CONVERGENCE_GATES.yaml"]["gates"]
    sources = data["SOURCE_TRACEABILITY.yaml"]["sources"]

    target_ids = collect_ids(targets, "target", errors)
    authority_ids = collect_ids(authorities, "authority", errors)
    decision_ids = collect_ids(decisions, "decision", errors)
    unknown_ids = collect_ids(unknowns, "unknown", errors)
    risk_ids = collect_ids(risks, "risk", errors)
    waiver_ids = collect_ids(waivers, "waiver", errors)
    evidence_ids = collect_ids(evidence, "evidence", errors)
    workstream_ids = collect_ids(workstreams, "workstream", errors)
    task_ids = collect_ids(tasks, "task", errors)
    gate_ids = collect_ids(gates, "gate", errors)
    wave_ids = collect_ids(waves, "wave", errors)
    collect_ids(sources, "source", errors)
    node_ids = collect_ids(graph.get("nodes") or [], "dependency node", errors)
    edge_ids = collect_ids(graph.get("edges") or [], "dependency edge", errors)
    _ = risk_ids, waiver_ids, edge_ids

    repo_ids = [t.get("repository_id") for t in targets if t.get("repository_id")]
    dup_repo = sorted({x for x in repo_ids if repo_ids.count(x) > 1})
    if dup_repo:
        errors.append(f"duplicate repository_id values: {dup_repo}")
    for target in targets:
        if target["execution_mode"] == "repo_local" and not target.get("repository_id"):
            errors.append(f"target {target['id']}: repo_local requires repository_id")
        if (
            target["execution_mode"] != "repo_local"
            and target.get("repository_id")
            and target["kind"] != "git_repository"
        ):
            errors.append(
                f"target {target['id']}: repository_id is only valid for git_repository targets"
            )

    normalized_responsibilities = [a["responsibility"].strip().lower() for a in authorities]
    duplicates = sorted(
        {x for x in normalized_responsibilities if normalized_responsibilities.count(x) > 1}
    )
    if duplicates:
        errors.append(f"duplicate authoritative responsibilities: {duplicates}")
    for authority in authorities:
        check_refs(
            [authority["owner_target_id"]], target_ids, f"authority {authority['id']} owner", errors
        )
        check_refs(
            authority.get("prohibited_owner_target_ids") or [],
            target_ids,
            f"authority {authority['id']} prohibited owners",
            errors,
        )
        check_refs(
            authority.get("validation_gate_ids") or [],
            gate_ids,
            f"authority {authority['id']} gates",
            errors,
        )

    for decision in decisions:
        check_refs(
            decision.get("evidence_ids") or [],
            evidence_ids,
            f"decision {decision['id']} evidence",
            errors,
        )
        check_refs(
            decision.get("blocks") or [], task_ids, f"decision {decision['id']} blocks", errors
        )
        if decision["status"] == "accepted" and not decision.get("selected_option"):
            errors.append(f"decision {decision['id']}: accepted decision requires selected_option")
        if decision.get("selected_option") and decision["selected_option"] not in {
            o["id"] for o in decision["options"]
        }:
            errors.append(
                f"decision {decision['id']}: selected_option is not one of the declared options"
            )

    for item in unknowns:
        check_refs(item.get("blocks") or [], task_ids, f"unknown {item['id']} blocks", errors)
        check_refs(
            item.get("resolution_evidence_ids") or [],
            evidence_ids,
            f"unknown {item['id']} evidence",
            errors,
        )
        if item["status"] == "resolved" and not item.get("resolution_evidence_ids"):
            errors.append(f"unknown {item['id']}: resolved status requires resolution evidence")

    for risk in risks:
        check_refs(risk.get("related_tasks") or [], task_ids, f"risk {risk['id']} tasks", errors)
        check_refs(risk.get("related_gates") or [], gate_ids, f"risk {risk['id']} gates", errors)
        if risk.get("acceptance_decision_id"):
            check_refs(
                [risk["acceptance_decision_id"]],
                decision_ids,
                f"risk {risk['id']} acceptance decision",
                errors,
            )

    for waiver in waivers:
        check_refs(waiver.get("scope") or [], gate_ids, f"waiver {waiver['id']} scope", errors)
        check_refs(
            waiver.get("evidence_ids") or [],
            evidence_ids,
            f"waiver {waiver['id']} evidence",
            errors,
        )
        if waiver["status"] == "active" and not waiver.get("evidence_ids"):
            errors.append(f"waiver {waiver['id']}: active waiver requires evidence")

    for ws in workstreams:
        check_refs(ws.get("target_ids") or [], target_ids, f"workstream {ws['id']} targets", errors)
        check_refs(
            ws.get("entry_gate_ids") or [], gate_ids, f"workstream {ws['id']} entry gates", errors
        )
        check_refs(
            ws.get("exit_gate_ids") or [], gate_ids, f"workstream {ws['id']} exit gates", errors
        )

    if node_ids != task_ids:
        errors.append(
            f"dependency nodes must exactly match task IDs: missing={sorted(task_ids - node_ids)}, extra={sorted(node_ids - task_ids)}"  # noqa: E501
        )
    for edge in graph.get("edges") or []:
        check_refs([edge["from"], edge["to"]], node_ids, f"edge {edge['id']}", errors)
        check_refs(
            edge.get("proof_gate_ids") or [], gate_ids, f"edge {edge['id']} proof gates", errors
        )
        if edge["from"] == edge["to"]:
            errors.append(f"edge {edge['id']}: self-dependency forbidden")
    check_dag(node_ids, graph.get("edges") or [], errors)
    check_refs(graph.get("critical_path") or [], node_ids, "critical_path", errors)

    task_wave_membership: dict[str, list[str]] = {task_id: [] for task_id in task_ids}
    last_sequence = -1
    for wave in sorted(waves, key=lambda x: x["sequence"]):
        if wave["sequence"] <= last_sequence:
            errors.append("wave sequence values must be strictly increasing")
        last_sequence = wave["sequence"]
        check_refs(
            wave.get("depends_on") or [], wave_ids, f"wave {wave['id']} dependencies", errors
        )
        check_refs(
            wave.get("workstream_ids") or [],
            workstream_ids,
            f"wave {wave['id']} workstreams",
            errors,
        )
        check_refs(wave.get("task_ids") or [], task_ids, f"wave {wave['id']} tasks", errors)
        check_refs(
            wave.get("entry_gate_ids") or [], gate_ids, f"wave {wave['id']} entry gates", errors
        )
        check_refs(
            wave.get("exit_gate_ids") or [], gate_ids, f"wave {wave['id']} exit gates", errors
        )
        for task_id in wave.get("task_ids") or []:
            task_wave_membership[task_id].append(wave["id"])
    for task_id, memberships in task_wave_membership.items():
        if len(memberships) != 1:
            errors.append(f"task {task_id}: must appear in exactly one wave, found {memberships}")

    for task in tasks:
        if "target" in task or "status" in task or "depends_on" in task:
            errors.append(f"task {task['id']}: legacy ambiguous field present")
        check_refs([task["workstream_id"]], workstream_ids, f"task {task['id']} workstream", errors)
        check_refs([task["wave_id"]], wave_ids, f"task {task['id']} wave", errors)
        check_refs([task["target_id"]], target_ids, f"task {task['id']} target", errors)
        check_refs(
            task.get("authority_basis_ids") or [],
            authority_ids,
            f"task {task['id']} authorities",
            errors,
        )
        check_refs(
            task.get("required_decision_ids") or [],
            decision_ids,
            f"task {task['id']} decisions",
            errors,
        )
        check_refs(
            task.get("blocking_unknown_ids") or [],
            unknown_ids,
            f"task {task['id']} unknowns",
            errors,
        )
        check_refs(
            task.get("input_evidence_ids") or [],
            evidence_ids,
            f"task {task['id']} evidence",
            errors,
        )
        check_refs(
            task.get("completion_gate_ids") or [],
            gate_ids,
            f"task {task['id']} completion gates",
            errors,
        )
        if task_wave_membership.get(task["id"]) != [task["wave_id"]]:
            errors.append(f"task {task['id']}: wave_id disagrees with EXECUTION_WAVES.yaml")
        if set(task["authorization_ceiling"]) != AUTH_ACTIONS:
            errors.append(f"task {task['id']}: authorization_ceiling keys are not canonical")
        if (
            task["execution_kind"] == "program_control"
            and task["authorization_ceiling"]["local_write"]
        ):
            errors.append(
                f"task {task['id']}: program_control task cannot authorize repository local_write"
            )
        if task["risk"]["tier"] == "T4" and not task["authorization_ceiling"]["destructive_change"]:
            errors.append(
                f"task {task['id']}: T4 task must explicitly declare destructive_change ceiling"
            )

    for gate in gates:
        if "status" in gate:
            errors.append(f"gate {gate['id']}: runtime status is forbidden in Blueprint definition")
        check_refs(
            gate["scope"].get("wave_ids") or [], wave_ids, f"gate {gate['id']} waves", errors
        )
        check_refs(
            gate["scope"].get("task_ids") or [], task_ids, f"gate {gate['id']} tasks", errors
        )
        check_refs(
            gate.get("required_evidence_ids") or [],
            evidence_ids,
            f"gate {gate['id']} evidence",
            errors,
        )

    current = data["CURRENT_STATE_DELTA.yaml"]
    for source in current.get("sources") or []:
        check_refs(
            [source.get("evidence_id")], evidence_ids, "current-state source evidence", errors
        )
    for delta in current.get("deltas") or []:
        check_refs([delta.get("target_id")], target_ids, f"delta {delta.get('id')} target", errors)
        check_refs(
            delta.get("evidence_ids") or [],
            evidence_ids,
            f"delta {delta.get('id')} evidence",
            errors,
        )

    for source in sources:
        check_refs(
            [source.get("evidence_id")], evidence_ids, f"source {source['id']} evidence", errors
        )
        check_refs(
            source.get("target_ids") or [], target_ids, f"source {source['id']} targets", errors
        )
        check_refs(
            source.get("workstream_ids") or [],
            workstream_ids,
            f"source {source['id']} workstreams",
            errors,
        )
        check_refs(source.get("task_ids") or [], task_ids, f"source {source['id']} tasks", errors)
        check_refs(source.get("gate_ids") or [], gate_ids, f"source {source['id']} gates", errors)

    for md in root.rglob("*.md"):
        content = md.read_text(encoding="utf-8")
        for target in MARKDOWN_LINK.findall(content):
            if _is_external_or_fragment_link(target):
                continue
            clean = target.split("#", 1)[0]
            if clean and not (md.parent / clean).resolve().exists():
                errors.append(f"{md.relative_to(root)}: broken link {target}")

    for py in root.rglob("*.py"):
        try:
            compile(py.read_text(encoding="utf-8"), str(py), "exec")
        except Exception as exc:
            errors.append(f"{py.relative_to(root)}: Python compile failed: {exc}")

    manifest = load_yaml(root / "MANIFEST.yaml")
    expected = {entry["path"]: entry["sha256"] for entry in manifest.get("files") or []}
    actual = {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.rglob("*")
        if p.is_file()
        and p.name != "MANIFEST.yaml"
        and "__pycache__" not in p.parts
        and p.suffix != ".pyc"
    }
    if set(expected) != set(actual):
        errors.append(
            f"manifest path mismatch: missing={sorted(set(actual) - set(expected))}, stale={sorted(set(expected) - set(actual))}"  # noqa: E501
        )
    for rel in sorted(set(expected) & set(actual)):
        if expected[rel] != actual[rel]:
            errors.append(f"manifest checksum mismatch: {rel}")

    if any(p.name == "__pycache__" or p.suffix == ".pyc" for p in root.rglob("*")):
        errors.append("compiled Python debris present")

    if mode == "instantiated":
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {
                ".md",
                ".yaml",
                ".yml",
                ".json",
                ".py",
            }:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for pattern in PLACEHOLDERS:
                match = pattern.search(text)
                if match:
                    errors.append(
                        f"{path.relative_to(root)}: unresolved placeholder {match.group(0)}"
                    )
                    break
        if program["definition_status"] != "accepted":
            errors.append(
                "instantiated executable Blueprint requires program.definition_status=accepted"
            )
        for task in tasks:
            if task["definition_status"] not in {"ready", "blocked", "cancelled", "superseded"}:
                errors.append(
                    f"task {task['id']}: instantiated definition_status must be ready, blocked, cancelled, or superseded"  # noqa: E501
                )

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--mode", choices=["template", "instantiated"], default="template")
    args = parser.parse_args()
    errors = validate(args.root, args.mode)
    if errors:
        print("FAIL")
        for error in errors:
            print(f"- {error}")
        return 1
    print("PASS")
    print(f"mode={args.mode}")
    print(f"root={args.root.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
