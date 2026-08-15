#!/usr/bin/env python3
"""Validate a compiled DPK-1.0 developer pack, fail-closed on red lines.

Static, deterministic check of a repository's dev pack: it scores the eight
readiness categories from structural evidence and enforces the four red-line
overrides that instantly zero the score. It does NOT run tests or builds -- it
verifies the machine envelope is present, complete, and internally consistent.

Red lines (any one -> score 0, verdict blocked):
  1. no production operations owner in .ai/manifest.yaml (ownership.operational_owner)
  2. no machine-executable rollback target
  3. a non-deterministic AI feature with no evaluation suite
  4. an alert whose runbook link does not resolve to a real file

Provenance law (DEC-003): an authority-affecting default (operational_owner,
library rollback) may be derived ONLY from an explicit governing policy with
recorded provenance. The validator loads `.ai/policy.yaml` ->
`policy_derived_defaults`, applies an entry only when its `source_id` is a real
governing identity, and records the derivation in the machine report under
`policy_provenance`. Without a provenanced policy entry the red line fails.
The operator may also supply provenance on the command line (--owner +
--owner-source), which is explicit and recorded the same way. There is no
undocumented fallback: a missing fact stays a red-line failure.

Evidence scope (DEC-004): this validator reports STRUCTURAL COMPILE-READINESS
only. Artifact presence is never represented as executed proof: the report
declares `evidence_scope: structural_compile_readiness`, per-category
`category_evidence` entries state their presence-based evidence level, and
`executed_proof` (tests, rollback dry-run, evals, architecture-alignment
verification) is always false here — runtime proof requires independent
execution by another authority (e.g., the Program Execution Controller).

Exit codes: 0 compile_ready/compile_ready_conditional, 1 blocked (red-line or
score < 80), 2 error.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

WEIGHTS = {
    "repository_clarity": 10,
    "architecture_mapping": 15,
    "local_reproducibility": 10,
    "test_eval_coverage": 15,
    "security_boundaries": 10,
    "observability_integrity": 15,
    "deployment_rollback": 10,
    "transition_clarity": 15,
}

# A red-line value that is a placeholder does NOT satisfy the red line. A pack
# that declares its ops owner or rollback command as Unknown/TBD/<...> is not
# operable — the decision is simply undocumented.
_PLACEHOLDERS = {"", "unknown", "tbd", "todo", "none", "n/a", "na", "?", "fixme"}

# Canonical policy artifact declaring policy-derived defaults. Each entry must
# carry governing provenance (source_id is a real identity) or it is ignored
# fail-closed and the fact remains a red-line failure.
POLICY_FILE = ".ai/policy.yaml"


def _is_real(value: Any) -> bool:
    """True when value is a concrete decision, not a placeholder."""
    if not isinstance(value, str):
        return bool(value)
    stripped = value.strip()
    if stripped.lower() in _PLACEHOLDERS:
        return False
    if "<" in stripped and ">" in stripped:  # <PINNED_VERSION>, <prev>, ...
        return False
    return bool(stripped)


def _load_yaml(path: Path) -> Any:
    """Parse YAML when PyYAML is present; else return None (callers text-scan)."""
    if not path.exists():
        return None
    try:
        import yaml  # type: ignore[import-not-found]

        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _first_existing(root: Path, *rel: str) -> Path | None:
    for r in rel:
        p = root / r
        if p.exists():
            return p
    return None


def _has_ai_features(root: Path, manifest: Any) -> bool:
    if isinstance(manifest, dict):
        repo = manifest.get("repository", {})
        if isinstance(repo, dict) and repo.get("type") == "ai-service":
            return True
    if (root / "prompts").is_dir():
        return True
    return bool(
        _first_existing(root, ".ai/models.yaml", ".ai/prompts.yaml", "models.yaml", "prompts.yaml")
    )


def _rollback_present(root: Path, manifest: Any) -> bool:
    if isinstance(manifest, dict):
        dep = manifest.get("deployment", {})
        if isinstance(dep, dict) and isinstance(dep.get("rollback"), dict):
            if _is_real(dep["rollback"].get("command")):
                return True
    if _first_existing(root, "scripts/rollback", "scripts/rollback.sh", "ops/rollback.sh"):
        return True
    # text fallback across .ai/*.yaml
    for p in (root / ".ai").glob("*.yaml") if (root / ".ai").is_dir() else []:
        if re.search(r"rollback:\s*\n(?:.*\n)*?\s*command:\s*\S", _text(p)):
            return True
    return False


def _collect_alerts(root: Path) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    candidates: list[Path] = []
    for d in (".ai/alerts", "docs/alerts", "alerts"):
        dp = root / d
        if dp.is_dir():
            candidates += sorted(dp.glob("*.y*ml"))
    for extra in (".ai/alerts.yaml", ".ai/observability.yaml"):
        p = root / extra
        if p.exists():
            candidates.append(p)
    for p in candidates:
        data = _load_yaml(p)
        if isinstance(data, dict) and "alert" in data:
            alerts.append(data["alert"] if isinstance(data["alert"], dict) else {"raw": p})
        elif isinstance(data, dict) and "alerts" in data and isinstance(data["alerts"], list):
            alerts += [a for a in data["alerts"] if isinstance(a, dict)]
        elif data is None:
            # text fallback: find runbook: lines
            for m in re.finditer(r"runbook:\s*(\S+)", _text(p)):
                alerts.append({"name": p.name, "runbook": m.group(1)})
    return alerts


def _eval_suite_resolves(root: Path) -> bool:
    for name in (".ai/models.yaml", ".ai/prompts.yaml", "models.yaml", "prompts.yaml"):
        p = root / name
        if not p.exists():
            continue
        for m in re.finditer(r"(?:eval_suite|eval_baseline):\s*(\S+)", _text(p)):
            if (root / m.group(1)).exists():
                return True
    return (root / "evals").is_dir()


def _has_verification_block(root: Path) -> bool:
    for rel in ("docs/ARCHITECTURE.md", "ARCHITECTURE.md", "README.md"):
        p = root / rel
        if p.exists() and ("document_status" in _text(p) or "last_verified" in _text(p)):
            return True
    for p in (root / ".ai").glob("*.yaml") if (root / ".ai").is_dir() else []:
        if "last_verified" in _text(p):
            return True
    return False


def _debt_ledger_present(root: Path) -> bool:
    for rel in (".ai/debt.yaml", "docs/DEBT.md", ".ai/transition.yaml"):
        p = root / rel
        if p.exists() and ("debt:" in _text(p) or "target_state" in _text(p)):
            return True
    for p in (root / ".ai").glob("*.y*ml") if (root / ".ai").is_dir() else []:
        if "target_state" in _text(p):
            return True
    return False


def _is_library(manifest: Any, manifest_text: str) -> bool:
    if isinstance(manifest, dict):
        repo = manifest.get("repository", {})
        if isinstance(repo, dict):
            return str(repo.get("type", "")).lower() in {"library", "sdk", "package"}
    return bool(re.search(r"type:\s*(library|sdk|package)\b", manifest_text))


def _policy_defaults(root: Path) -> dict[str, dict[str, Any]]:
    """Load `.ai/policy.yaml` -> policy_derived_defaults (empty when absent)."""
    data = _load_yaml(root / POLICY_FILE)
    if not isinstance(data, dict):
        return {}
    defaults = data.get("policy_derived_defaults")
    if not isinstance(defaults, dict):
        return {}
    return {k: v for k, v in defaults.items() if isinstance(v, dict)}


def _provenanced_entry(
    entry: dict[str, Any], fact: str, provenance: list[dict[str, Any]]
) -> tuple[str | None, dict[str, str] | None]:
    """Return (value, governing_source) for a policy entry that carries real
    provenance; otherwise record the rejection and return (None, None)."""
    value = entry.get("value")
    source_id = entry.get("source_id")
    if not _is_real(value) or not _is_real(source_id):
        provenance.append(
            {
                "fact": fact,
                "status": "rejected_missing_provenance",
                "reason": "policy entry lacks a real value or governing source_id",
            }
        )
        return None, None
    revision = entry.get("source_revision")
    governing = {
        "id": str(source_id).strip(),
        "revision": str(revision).strip() if _is_real(revision) else None,
    }
    provenance.append(
        {
            "fact": fact,
            "status": "derived_from_policy",
            "derived_value": str(value).strip(),
            "governing_source": governing,
        }
    )
    return str(value).strip(), governing


def _cli_provenance(
    value: str, source: str, fact: str, provenance: list[dict[str, Any]]
) -> str:
    """Record an operator-supplied (command-line) default with provenance."""
    source_id, _, revision = source.partition("@")
    provenance.append(
        {
            "fact": fact,
            "status": "derived_from_operator_supply",
            "derived_value": value,
            "governing_source": {
                "id": source_id,
                "revision": revision or None,
            },
        }
    )
    return value


def evaluate(
    root: Path,
    *,
    owner_default: str | None = None,
    owner_source: str | None = None,
) -> dict[str, Any]:
    manifest = _load_yaml(root / ".ai" / "manifest.yaml")
    manifest_text = _text(root / ".ai" / "manifest.yaml")
    provenance: list[dict[str, Any]] = []

    # --- Red lines ---
    ops_owner = False
    if isinstance(manifest, dict):
        own = manifest.get("ownership", {})
        ops_owner = bool(isinstance(own, dict) and _is_real(own.get("operational_owner", "")))
    elif manifest_text:
        m = re.search(r"operational_owner:\s*(.+)", manifest_text)
        ops_owner = bool(m and _is_real(m.group(1).split("#", 1)[0]))

    # Missing owner: derive only from explicit provenanced policy, or from an
    # operator-supplied default that names its governing source. No other
    # fallback exists — the fact otherwise stays a red-line failure.
    if not ops_owner:
        policy_entry = _policy_defaults(root).get("operational_owner")
        if isinstance(policy_entry, dict):
            value, _gov = _provenanced_entry(policy_entry, "operational_owner", provenance)
            if value is not None:
                ops_owner = True
        elif owner_default is not None and owner_source is not None and _is_real(owner_source):
            _cli_provenance(owner_default, owner_source, "operational_owner", provenance)
            ops_owner = True
        elif owner_default is not None and (owner_source is None or not _is_real(owner_source)):
            provenance.append(
                {
                    "fact": "operational_owner",
                    "status": "rejected_missing_provenance",
                    "reason": "--owner supplied without a real --owner-source",
                }
            )

    rollback = _rollback_present(root, manifest)
    if not rollback and _is_library(manifest, manifest_text):
        # Library/SDK rollback may default to the version pin/yank target only
        # from an explicit provenanced policy entry.
        policy_entry = _policy_defaults(root).get("library_rollback")
        if isinstance(policy_entry, dict):
            value, _gov = _provenanced_entry(policy_entry, "library_rollback", provenance)
            if value is not None:
                rollback = True

    ai = _has_ai_features(root, manifest)
    eval_ok = (not ai) or _eval_suite_resolves(root)

    alerts = _collect_alerts(root)
    broken_runbooks = [
        str(a.get("runbook"))
        for a in alerts
        if a.get("runbook") and not (root / str(a["runbook"])).exists()
    ]
    runbook_links_ok = len(broken_runbooks) == 0

    red_lines = {
        "ops_owner": "pass" if ops_owner else "fail",
        "rollback": "pass" if rollback else "fail",
        "eval_suite": "pass" if eval_ok else "fail",
        "runbook_links": "pass" if runbook_links_ok else "fail",
    }
    red_line_tripped = any(v == "fail" for v in red_lines.values())

    # --- Category scores (static presence/structure) ---
    # Each signal is presence evidence only; nothing here is executed proof.
    sig_verification = _has_verification_block(root)
    sig_repo_map = (root / ".ai" / "repository-map.yaml").exists()
    sig_bootstrap = _first_existing(
        root, "scripts/bootstrap", "scripts/bootstrap.sh", "Makefile"
    ) is not None
    tests_present = (root / "tests").is_dir() or (root / "test").is_dir()
    sig_constraints = (root / ".ai" / "constraints.yaml").exists()
    sig_alerts = bool(alerts) and runbook_links_ok
    sig_debt = _debt_ledger_present(root)

    cats: dict[str, int] = {}
    cats["repository_clarity"] = WEIGHTS["repository_clarity"] if sig_verification else 0
    cats["architecture_mapping"] = WEIGHTS["architecture_mapping"] if sig_repo_map else 0
    cats["local_reproducibility"] = WEIGHTS["local_reproducibility"] if sig_bootstrap else 0
    cats["test_eval_coverage"] = (
        WEIGHTS["test_eval_coverage"] if tests_present and eval_ok else (7 if tests_present else 0)
    )
    cats["security_boundaries"] = WEIGHTS["security_boundaries"] if sig_constraints else 0
    cats["observability_integrity"] = WEIGHTS["observability_integrity"] if sig_alerts else 0
    cats["deployment_rollback"] = WEIGHTS["deployment_rollback"] if rollback else 0
    cats["transition_clarity"] = WEIGHTS["transition_clarity"] if sig_debt else 0

    # Every readiness result declares the evidence level behind it. Claims are
    # presence statements only; no executed proof is attributed to a category.
    category_evidence: dict[str, dict[str, Any]] = {
        "repository_clarity": {
            "score": cats["repository_clarity"],
            "weight": WEIGHTS["repository_clarity"],
            "evidence_level": "structural_presence",
            "claim": (
                "verification tokens present in structural docs (presence only; "
                "claims not independently re-verified)"
                if sig_verification
                else "no verification block found"
            ),
            "proved_claims": [],
        },
        "architecture_mapping": {
            "score": cats["architecture_mapping"],
            "weight": WEIGHTS["architecture_mapping"],
            "evidence_level": "structural_presence",
            "claim": (
                "repository-map file present; import-alignment verification is "
                "not performed by this validator"
                if sig_repo_map
                else "repository-map file missing"
            ),
            "proved_claims": [],
        },
        "local_reproducibility": {
            "score": cats["local_reproducibility"],
            "weight": WEIGHTS["local_reproducibility"],
            "evidence_level": "structural_presence",
            "claim": (
                "bootstrap entrypoint present; setup not executed here"
                if sig_bootstrap
                else "no bootstrap entrypoint found"
            ),
            "proved_claims": [],
        },
        "test_eval_coverage": {
            "score": cats["test_eval_coverage"],
            "weight": WEIGHTS["test_eval_coverage"],
            "evidence_level": "structural_presence",
            "claim": (
                "test directory present; no test execution is claimed by this "
                "validator"
                if tests_present
                else "no test directory found"
            ),
            "proved_claims": [],
        },
        "security_boundaries": {
            "score": cats["security_boundaries"],
            "weight": WEIGHTS["security_boundaries"],
            "evidence_level": "structural_presence",
            "claim": (
                "constraints file present; credential/authorization checks not "
                "executed here"
                if sig_constraints
                else "constraints file missing"
            ),
            "proved_claims": [],
        },
        "observability_integrity": {
            "score": cats["observability_integrity"],
            "weight": WEIGHTS["observability_integrity"],
            "evidence_level": "structural_presence",
            "claim": (
                "alert entries present and runbook links resolve statically"
                if sig_alerts
                else "no statically-resolving alert->runbook set found"
            ),
            "proved_claims": [],
        },
        "deployment_rollback": {
            "score": cats["deployment_rollback"],
            "weight": WEIGHTS["deployment_rollback"],
            "evidence_level": "structural_presence",
            "claim": (
                "rollback target declared; dry-run execution is NOT claimed"
                if rollback
                else "no declared rollback target"
            ),
            "proved_claims": [],
        },
        "transition_clarity": {
            "score": cats["transition_clarity"],
            "weight": WEIGHTS["transition_clarity"],
            "evidence_level": "structural_presence",
            "claim": (
                "debt ledger present; remediation targets not verified here"
                if sig_debt
                else "no debt ledger found"
            ),
            "proved_claims": [],
        },
    }

    red_line_evidence: dict[str, dict[str, Any]] = {
        "ops_owner": {
            "status": red_lines["ops_owner"],
            "evidence_level": "structural_declaration",
            "executed": False,
            "claim": "ownership.operational_owner declared (or provenanced default derived)",
        },
        "rollback": {
            "status": red_lines["rollback"],
            "evidence_level": "structural_declaration",
            "executed": False,
            "claim": "machine-executable rollback target declared; dry-run NOT executed",
        },
        "eval_suite": {
            "status": red_lines["eval_suite"],
            "evidence_level": "structural_declaration",
            "executed": False,
            "claim": "eval_suite/eval_baseline reference resolves; eval NOT executed",
        },
        "runbook_links": {
            "status": red_lines["runbook_links"],
            "evidence_level": "structural_declaration",
            "executed": False,
            "claim": "alert runbook links statically resolve to real files",
        },
    }

    raw_score = sum(cats.values())
    score = 0 if red_line_tripped else raw_score
    if red_line_tripped or score < 80:
        band = "blocked"
    elif score >= 90:
        band = "compile_ready"
    else:
        band = "compile_ready_conditional"

    remediation: list[str] = []
    if not ops_owner:
        remediation.append(
            "add ownership.operational_owner to .ai/manifest.yaml or derive it from a "
            "provenanced .ai/policy.yaml default (red line)"
        )
    if not rollback:
        remediation.append(
            "declare a machine-executable rollback target or derive a library rollback "
            "from a provenanced .ai/policy.yaml default (red line)"
        )
    if not eval_ok:
        remediation.append("add an eval suite for the non-deterministic AI feature (red line)")
    if broken_runbooks:
        remediation.append(f"fix broken alert runbook links: {broken_runbooks} (red line)")
    for cat, val in cats.items():
        if val == 0 and cat not in ("observability_integrity", "deployment_rollback"):
            remediation.append(f"raise {cat}: missing required artifact")

    return {
        "root": str(root),
        "evidence_scope": "structural_compile_readiness",
        "ai_service": ai,
        "red_lines": red_lines,
        "red_line_evidence": red_line_evidence,
        "red_line_tripped": red_line_tripped,
        "categories": cats,
        "category_evidence": category_evidence,
        "executed_proof": {
            "tests_executed": False,
            "rollback_dry_run_executed": False,
            "eval_executed": False,
            "architecture_alignment_verified": False,
            "note": (
                "structural validation never executes tests, rollback dry-runs, "
                "evals, or alignment checks; runtime proof requires independent "
                "execution by another authority (e.g., the Program Execution "
                "Controller)"
            ),
        },
        "score": score,
        "raw_score": raw_score,
        "band": band,
        "alerts_found": len(alerts),
        "broken_runbooks": broken_runbooks,
        "policy_provenance": provenance,
        "remediation": remediation,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a DPK-1.0 developer pack.")
    parser.add_argument("repo", help="Path to the repository / dev-pack root")
    parser.add_argument("--json", action="store_true", help="Emit the full report as JSON")
    parser.add_argument(
        "--strict",
        action="store_true",
        help=(
            "Deprecated: fail-closed is now the only mode. Accepted for "
            "compatibility with DPK-1.0 callers."
        ),
    )
    parser.add_argument(
        "--owner",
        default=None,
        help=(
            "Operator-supplied ops-owner default. Requires --owner-source "
            "<id>[@revision]; without it the default is rejected (fail closed)."
        ),
    )
    parser.add_argument(
        "--owner-source",
        default=None,
        help="Governing source identity for --owner, e.g. org-policy@2026-07.",
    )
    args = parser.parse_args()
    root = Path(args.repo)
    if not root.exists() or not root.is_dir():
        print(f"FAIL: not a directory: {root}", file=sys.stderr)
        return 2
    report = evaluate(root, owner_default=args.owner, owner_source=args.owner_source)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"score={report['score']} band={report['band']} red_lines={report['red_lines']}")
        for item in report["remediation"]:
            print(f"  - {item}")
        for item in report["policy_provenance"]:
            print(f"  [provenance] {item['fact']}: {item['status']}")
    return 0 if report["band"] in ("compile_ready", "compile_ready_conditional") else 1


if __name__ == "__main__":
    raise SystemExit(main())
