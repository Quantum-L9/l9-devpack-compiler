"""Authority-order regression tests (DEC-001, DEC-002).

Accepted architecture and contracts must sit above the approved Task Contract
(a narrowing scope projection); DPK must describe itself as a compiler /
design-time authority that disclaims Controller-owned runtime state.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _text(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


class SkillAuthorityOrderTests(unittest.TestCase):
    def test_skill_authority_order_architecture_above_task_contract(self) -> None:
        text = _text("SKILL.md")
        arch = text.index("Accepted architecture and contracts")
        task = text.index("Approved Task Contract")
        self.assertLess(arch, task)

    def test_skill_defines_task_contract_as_narrowing(self) -> None:
        text = _text("SKILL.md")
        self.assertIn("narrowing", text)
        self.assertIn("never override", text)

    def test_skill_disclaims_runtime_authority(self) -> None:
        text = _text("SKILL.md")
        self.assertIn("does **not** own runtime task state", text)
        self.assertIn("gate evaluation", text)
        self.assertIn("Program Execution Controller", text)
        self.assertIn("design-time authority", text)

    def test_skill_describes_dpk_as_compiler(self) -> None:
        text = _text("SKILL.md")
        self.assertIn("compiler", text.lower())
        self.assertIn("Role boundary", text)

    def test_legacy_task_contract_above_architecture_absent(self) -> None:
        text = _text("SKILL.md")
        self.assertNotIn("Explicit Task Contract definitions", text)
        # legacy ordering: Task Contract directly after security/safety/legal
        legacy = re.search(
            r"1\.\s+Security, safety, and legal constraints\.\s*\n\s*2\.\s+Explicit Task",
            text,
        )
        self.assertIsNone(legacy)


class ModelAuthorityOrderTests(unittest.TestCase):
    def test_expertise_hierarchy_architecture_above_task_contract(self) -> None:
        text = _text("expertise_model.yaml")
        self.assertIn(
            "accepted_architecture_and_contracts > approved_task_contract", text
        )
        self.assertIn("security_safety_legal > accepted_architecture_and_contracts", text)
        self.assertNotIn("explicit_task_contract > architecture_invariants", text)

    def test_report_authority_model_architecture_above_task_contract(self) -> None:
        text = _text("skill_intelligence_report.yaml")
        order = text[text.index("order:") : text.index("conflict_rules:")]
        self.assertLess(
            order.index("accepted_architecture_and_contracts"),
            order.index("approved_task_contract_narrowing"),
        )
        self.assertNotIn("explicit_task_contract", text)

    def test_report_conflict_rules_narrowing_only(self) -> None:
        text = _text("skill_intelligence_report.yaml")
        self.assertIn("may narrow but never widen upstream authority", text)

    def test_model_disclaims_runtime_ownership(self) -> None:
        for rel in ("expertise_model.yaml", "skill_intelligence_report.yaml"):
            text = _text(rel)
            self.assertIn("Program Execution Controller", text)


class LayerContractAuthorityTests(unittest.TestCase):
    def test_layer_contract_task_contract_narrowing(self) -> None:
        text = _text("references/dpk-layer-contract.md")
        self.assertIn("narrowing scope projection", text)
        self.assertIn("may **never override** accepted architecture", text)
        order = text[text.index("The authority cascade"):]
        self.assertLess(
            order.index("accepted architecture and contracts"),
            order.index("approved"),
        )

    def test_spec_schema_band_language_migrated(self) -> None:
        text = _text("references/spec-schema.md")
        self.assertIn("compile_ready", text)
        self.assertNotIn("keeps the pack out of `operable`", text)


if __name__ == "__main__":
    unittest.main()
