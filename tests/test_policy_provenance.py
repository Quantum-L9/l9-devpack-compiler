"""Provenance law tests for validate_devpack (DEC-003).

Authority-affecting defaults (operational_owner, library rollback) may be
derived only from an explicit governing policy with recorded provenance.
Negative cases assert the red line fails closed when provenance is absent.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from validate_devpack import evaluate  # noqa: E402


def _write(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _manifest(owner: str | None = None, repo_type: str = "service") -> dict:
    manifest: dict = {"repository": {"type": repo_type}}
    if owner is not None:
        manifest["ownership"] = {"operational_owner": owner}
    return manifest


def build_pack(
    owner: str | None = None,
    repo_type: str = "service",
    policy: dict | None = None,
    rollback: bool = False,
) -> Path:
    root = Path(tempfile.mkdtemp(prefix="dpk-policy-"))
    (root / ".ai").mkdir(parents=True)
    _write(root, ".ai/manifest.yaml", json.dumps(_manifest(owner, repo_type)))
    if policy is not None:
        _write(root, ".ai/policy.yaml", json.dumps({"policy_derived_defaults": policy}))
    if rollback:
        _write(root, "scripts/rollback.sh", "#!/bin/sh\nexit 0\n")
    return root


def _provenance(report: dict) -> list[dict]:
    return report.get("policy_provenance") or []


class MissingOwnerTests(unittest.TestCase):
    def test_missing_owner_without_policy_fails(self) -> None:
        report = evaluate(build_pack(owner=None))
        self.assertEqual(report["red_lines"]["ops_owner"], "fail")
        self.assertEqual(report["band"], "blocked")
        self.assertEqual(_provenance(report), [])

    def test_declared_owner_passes_without_derivation(self) -> None:
        report = evaluate(build_pack(owner="platform-team"))
        self.assertEqual(report["red_lines"]["ops_owner"], "pass")
        self.assertEqual(_provenance(report), [])

    def test_policy_default_with_provenance_applies(self) -> None:
        policy = {
            "operational_owner": {
                "value": "quantum-ai",
                "source_id": "quantum-ai-org-policy",
                "source_revision": "2026-07",
            }
        }
        report = evaluate(build_pack(owner=None, policy=policy))
        self.assertEqual(report["red_lines"]["ops_owner"], "pass")
        derived = [p for p in _provenance(report) if p["status"] == "derived_from_policy"]
        self.assertEqual(len(derived), 1)
        self.assertEqual(derived[0]["derived_value"], "quantum-ai")
        self.assertEqual(derived[0]["governing_source"]["id"], "quantum-ai-org-policy")
        self.assertEqual(derived[0]["governing_source"]["revision"], "2026-07")

    def test_policy_entry_without_source_id_rejected(self) -> None:
        policy = {"operational_owner": {"value": "quantum-ai"}}
        report = evaluate(build_pack(owner=None, policy=policy))
        self.assertEqual(report["red_lines"]["ops_owner"], "fail")
        statuses = [p["status"] for p in _provenance(report)]
        self.assertIn("rejected_missing_provenance", statuses)

    def test_policy_entry_placeholder_source_rejected(self) -> None:
        policy = {"operational_owner": {"value": "quantum-ai", "source_id": "tbd"}}
        report = evaluate(build_pack(owner=None, policy=policy))
        self.assertEqual(report["red_lines"]["ops_owner"], "fail")
        self.assertIn(
            "rejected_missing_provenance", [p["status"] for p in _provenance(report)]
        )

    def test_operator_default_without_source_rejected(self) -> None:
        report = evaluate(
            build_pack(owner=None), owner_default="quantum-ai", owner_source=None
        )
        self.assertEqual(report["red_lines"]["ops_owner"], "fail")
        self.assertIn(
            "rejected_missing_provenance", [p["status"] for p in _provenance(report)]
        )

    def test_operator_default_with_source_applies(self) -> None:
        report = evaluate(
            build_pack(owner=None),
            owner_default="quantum-ai",
            owner_source="org-policy@2026-07",
        )
        self.assertEqual(report["red_lines"]["ops_owner"], "pass")
        derived = [
            p for p in _provenance(report) if p["status"] == "derived_from_operator_supply"
        ]
        self.assertEqual(len(derived), 1)
        self.assertEqual(derived[0]["governing_source"]["id"], "org-policy")
        self.assertEqual(derived[0]["governing_source"]["revision"], "2026-07")

    def test_provenance_recorded_in_machine_output(self) -> None:
        policy = {
            "operational_owner": {
                "value": "quantum-ai",
                "source_id": "quantum-ai-org-policy",
            }
        }
        report = evaluate(build_pack(owner=None, policy=policy))
        dumped = json.dumps(report)
        self.assertIn("policy_provenance", dumped)
        self.assertIn("governing_source", dumped)
        self.assertIn("quantum-ai-org-policy", dumped)


class LibraryRollbackTests(unittest.TestCase):
    def test_library_missing_rollback_without_policy_fails(self) -> None:
        report = evaluate(build_pack(owner="platform-team", repo_type="library"))
        self.assertEqual(report["red_lines"]["rollback"], "fail")

    def test_library_rollback_policy_with_provenance_applies(self) -> None:
        policy = {
            "library_rollback": {
                "value": "version-pin-yank",
                "source_id": "dpk-1.0-library-adapter",
                "source_revision": "1.2.0",
            }
        }
        report = evaluate(
            build_pack(owner="platform-team", repo_type="library", policy=policy)
        )
        self.assertEqual(report["red_lines"]["rollback"], "pass")
        derived = [p for p in _provenance(report) if p["fact"] == "library_rollback"]
        self.assertEqual(len(derived), 1)
        self.assertEqual(derived[0]["status"], "derived_from_policy")
        self.assertEqual(derived[0]["governing_source"]["id"], "dpk-1.0-library-adapter")

    def test_library_rollback_policy_without_source_rejected(self) -> None:
        policy = {"library_rollback": {"value": "version-pin-yank"}}
        report = evaluate(
            build_pack(owner="platform-team", repo_type="library", policy=policy)
        )
        self.assertEqual(report["red_lines"]["rollback"], "fail")
        self.assertIn(
            "rejected_missing_provenance", [p["status"] for p in _provenance(report)]
        )

    def test_declared_rollback_passes_without_policy(self) -> None:
        report = evaluate(build_pack(owner="platform-team", rollback=True))
        self.assertEqual(report["red_lines"]["rollback"], "pass")


if __name__ == "__main__":
    unittest.main()
