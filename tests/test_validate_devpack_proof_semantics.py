"""Proof-semantics tests for validate_devpack (DEC-004).

Structural presence must never be represented as executed proof. These tests
assert the honest evidence scope: compile-readiness labels only, presence-only
claims, and executed_proof always false.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from validate_devpack import evaluate, main  # noqa: E402

VALID_BANDS = {"compile_ready", "compile_ready_conditional", "blocked"}


def _write(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def complete_pack(extra: dict | None = None) -> Path:
    """A pack that structurally satisfies every category; score >= 90."""
    root = Path(tempfile.mkdtemp(prefix="dpk-proof-"))
    manifest = {
        "repository": {"type": "service", "name": "demo"},
        "ownership": {"operational_owner": "platform-team"},
        "deployment": {"rollback": {"strategy": "inverse-patch", "command": "scripts/rollback --dry-run"}},
    }
    if extra:
        manifest.update(extra)
    _write(root, ".ai/manifest.yaml", json.dumps(manifest))
    _write(
        root,
        ".ai/repository-map.yaml",
        json.dumps({"domains": {"core": {"paths": ["src/"], "purpose": "demo"}}}),
    )
    _write(root, ".ai/constraints.yaml", json.dumps({"latency": {"request_budget_ms": 100}}))
    _write(root, "scripts/bootstrap.sh", "#!/bin/sh\nexit 0\n")
    (root / "tests").mkdir(parents=True)
    _write(root, "README.md", "document_status:\n  last_verified: 2026-08-15\n")
    _write(
        root,
        ".ai/alerts.yaml",
        json.dumps(
            {"alert": {"name": "Demo", "severity": "ticket", "runbook": "docs/runbooks/demo.md"}}
        ),
    )
    _write(root, "docs/runbooks/demo.md", "# runbook\n")
    _write(root, ".ai/debt.yaml", json.dumps({"debt": [{"id": "TD-1", "target_state": "x"}]}))
    return root


class EvidenceScopeTests(unittest.TestCase):
    def test_report_declares_structural_evidence_scope(self) -> None:
        report = evaluate(complete_pack())
        self.assertEqual(report["evidence_scope"], "structural_compile_readiness")

    def test_bands_never_claim_runtime_operability(self) -> None:
        report = evaluate(complete_pack())
        self.assertIn(report["band"], VALID_BANDS)
        self.assertNotIn(report["band"], {"operable", "conditional"})
        self.assertNotIn("operable", json.dumps(report))
        self.assertNotIn("Independently Operable", json.dumps(report))

    def test_full_structural_pack_is_compile_ready(self) -> None:
        report = evaluate(complete_pack())
        self.assertEqual(report["band"], "compile_ready")
        self.assertGreaterEqual(report["score"], 90)


class PresenceIsNotProofTests(unittest.TestCase):
    def test_test_dir_presence_does_not_claim_execution(self) -> None:
        report = evaluate(complete_pack())
        self.assertFalse(report["executed_proof"]["tests_executed"])
        self.assertEqual(
            report["category_evidence"]["test_eval_coverage"]["evidence_level"],
            "structural_presence",
        )
        self.assertEqual(
            report["category_evidence"]["test_eval_coverage"]["proved_claims"], []
        )
        self.assertIn(
            "no test execution is claimed",
            report["category_evidence"]["test_eval_coverage"]["claim"],
        )

    def test_rollback_presence_does_not_claim_dry_run(self) -> None:
        report = evaluate(complete_pack())
        self.assertEqual(report["red_lines"]["rollback"], "pass")
        self.assertFalse(report["executed_proof"]["rollback_dry_run_executed"])
        self.assertFalse(report["red_line_evidence"]["rollback"]["executed"])
        self.assertIn(
            "NOT", report["category_evidence"]["deployment_rollback"]["claim"]
        )

    def test_repo_map_presence_does_not_claim_alignment(self) -> None:
        report = evaluate(complete_pack())
        self.assertEqual(report["categories"]["architecture_mapping"], 15)
        self.assertFalse(report["executed_proof"]["architecture_alignment_verified"])
        claim = report["category_evidence"]["architecture_mapping"]["claim"]
        self.assertNotIn("100%", claim)
        self.assertIn("not performed", claim)

    def test_every_category_declares_evidence_level(self) -> None:
        report = evaluate(complete_pack())
        for cat in report["categories"]:
            self.assertEqual(
                report["category_evidence"][cat]["evidence_level"],
                "structural_presence",
            )

    def test_empty_tests_dir_still_no_execution_claim(self) -> None:
        root = complete_pack()
        report = evaluate(root)
        self.assertFalse(report["executed_proof"]["tests_executed"])
        self.assertEqual(report["category_evidence"]["test_eval_coverage"]["proved_claims"], [])

    def test_red_line_blocked_report_stays_structural(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="dpk-proof-"))
        _write(
            root,
            ".ai/manifest.yaml",
            json.dumps({"repository": {"type": "service"}}),
        )
        report = evaluate(root)
        self.assertEqual(report["band"], "blocked")
        self.assertEqual(report["evidence_scope"], "structural_compile_readiness")


class ExitCodeTests(unittest.TestCase):
    def test_cli_exit_code_zero_for_compile_ready(self) -> None:
        root = complete_pack()
        sys.argv = ["validate_devpack.py", str(root)]
        try:
            code = main()
        finally:
            sys.argv = ["validate_devpack.py"]
        self.assertEqual(code, 0)

    def test_cli_exit_code_one_for_blocked(self) -> None:
        root = Path(tempfile.mkdtemp(prefix="dpk-proof-"))
        _write(
            root,
            ".ai/manifest.yaml",
            json.dumps({"repository": {"type": "service"}}),
        )
        sys.argv = ["validate_devpack.py", str(root)]
        try:
            code = main()
        finally:
            sys.argv = ["validate_devpack.py"]
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
