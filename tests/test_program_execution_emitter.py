"""Emitter tests (TASK-005): completeness, honesty, determinism, fail-closed.

Validates the emitted set against the pinned governing template snapshot,
including the official validate_blueprint.py in instantiated mode.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from emit_program_execution_v2 import (  # noqa: E402
    AUTH_ACTIONS,
    REQUIRED_SOURCES,
    EmitError,
    emit,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
PACK = FIXTURES / "dpk_mini"
TEMPLATE = FIXTURES / "governing-template"

BANNED_RUNTIME_KEYS = {
    "runtime_state",
    "gate_result",
    "gate_results",
    "attempt_result",
    "attempt_results",
    "lease",
    "leases",
    "handoff_receipt",
    "receipts",
}


def pack_copy(tmp: Path) -> Path:
    target = tmp / "pack"
    shutil.copytree(PACK, target)
    return target


def emit_once(tmp: Path, pack: Path | None = None) -> Path:
    out = tmp / "emitted"
    result = emit(pack or pack_copy(tmp), out, TEMPLATE)
    assert result["output"] == str(out.resolve())
    return out


def load_yaml(path: Path):
    import yaml  # type: ignore[import-not-found]

    return yaml.safe_load(path.read_text(encoding="utf-8"))


class CompletenessTests(unittest.TestCase):
    def test_emits_all_required_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = emit_once(Path(tmp))
            for name in REQUIRED_SOURCES:
                self.assertTrue((out / name).is_file(), f"missing {name}")
            for extra in (
                "EXECUTIVE_DECISION.md",
                "HANDOFF.md",
                "MANIFEST.yaml",
                "TEMPLATE_VARIABLES.yaml",
            ):
                self.assertTrue((out / extra).is_file(), f"missing {extra}")
            self.assertTrue((out / "schemas" / "task-card.schema.json").is_file())

    def test_emission_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            first = emit_once(tmp_path / "a")
            second = emit_once(tmp_path / "b")
            first_files = sorted(p.relative_to(first) for p in first.rglob("*") if p.is_file())
            second_files = sorted(p.relative_to(second) for p in second.rglob("*") if p.is_file())
            self.assertEqual(first_files, second_files)
            for rel in first_files:
                self.assertEqual(
                    (first / rel).read_bytes(),
                    (second / rel).read_bytes(),
                    f"nondeterministic file: {rel}",
                )

    def test_official_instantiated_validation_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = emit_once(Path(tmp))
            completed = subprocess.run(
                [
                    sys.executable,
                    str(TEMPLATE / "scripts" / "validate_blueprint.py"),
                    str(out),
                    "--mode",
                    "instantiated",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            self.assertIn("PASS", completed.stdout)


class HonestyTests(unittest.TestCase):
    def test_no_runtime_state_keys_emitted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = emit_once(Path(tmp))

            def walk(value, trail):
                if isinstance(value, dict):
                    for key, child in value.items():
                        self.assertNotIn(
                            key.lower(),
                            BANNED_RUNTIME_KEYS,
                            f"runtime-state key at {trail}.{key}",
                        )
                        walk(child, f"{trail}.{key}")
                elif isinstance(value, list):
                    for idx, child in enumerate(value):
                        walk(child, f"{trail}[{idx}]")

            for name in REQUIRED_SOURCES:
                walk(load_yaml(out / name), name)

    def test_canonical_ceiling_on_every_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = emit_once(Path(tmp))
            tasks = load_yaml(out / "TASK_CARDS.yaml")["tasks"]
            self.assertTrue(tasks)
            for task in tasks:
                ceiling = task["authorization_ceiling"]
                self.assertEqual(set(ceiling), set(AUTH_ACTIONS), task["id"])
                for action in (
                    "commit",
                    "push",
                    "pull_request",
                    "merge",
                    "publish_or_release",
                    "deploy_or_migrate",
                    "destructive_change",
                    "external_message",
                ):
                    self.assertFalse(ceiling[action], f"{task['id']}.{action} widened by emission")
                self.assertTrue(ceiling["inspect"])
                self.assertTrue(ceiling["local_write"])

    def test_program_owner_has_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = emit_once(Path(tmp))
            program = load_yaml(out / "PROGRAM.yaml")["program"]
            self.assertEqual(program["owner"], "platform-team")
            evidence = {
                e["source"]: e for e in load_yaml(out / "EVIDENCE_CATALOG.yaml")["evidence"]
            }
            self.assertIn(".ai/manifest.yaml", evidence)
            self.assertEqual(evidence[".ai/manifest.yaml"]["status"], "available")

    def test_unknown_blocks_only_named_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = emit_once(Path(tmp))
            unknowns = load_yaml(out / "UNKNOWN_REGISTER.yaml")["unknowns"]
            blocking = [u for u in unknowns if u["id"] == "UNK-001"]
            self.assertEqual(len(blocking), 1)
            self.assertEqual(blocking[0]["blocks"], ["TASK-002"])
            tasks = {t["id"]: t for t in load_yaml(out / "TASK_CARDS.yaml")["tasks"]}
            self.assertEqual(tasks["TASK-002"]["blocking_unknown_ids"], ["UNK-001"])
            self.assertEqual(tasks["TASK-001"]["blocking_unknown_ids"], [])

    def test_cross_references_resolve(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = emit_once(Path(tmp))
            data = {name: load_yaml(out / name) for name in REQUIRED_SOURCES}
            task_ids = {t["id"] for t in data["TASK_CARDS.yaml"]["tasks"]}
            wave_ids = {w["id"] for w in data["EXECUTION_WAVES.yaml"]["waves"]}
            gate_ids = {g["id"] for g in data["CONVERGENCE_GATES.yaml"]["gates"]}
            ws_ids = {w["id"] for w in data["WORKSTREAMS.yaml"]["workstreams"]}
            evidence_ids = {e["id"] for e in data["EVIDENCE_CATALOG.yaml"]["evidence"]}
            for task in data["TASK_CARDS.yaml"]["tasks"]:
                self.assertIn(task["wave_id"], wave_ids, task["id"])
                self.assertIn(task["workstream_id"], ws_ids, task["id"])
                for gate in task["completion_gate_ids"]:
                    self.assertIn(gate, gate_ids, task["id"])
                for evidence in task["input_evidence_ids"]:
                    self.assertIn(evidence, evidence_ids, task["id"])
            nodes = {n["id"] for n in data["DEPENDENCY_GRAPH.yaml"]["nodes"]}
            self.assertEqual(nodes, task_ids)
            for gate in data["CONVERGENCE_GATES.yaml"]["gates"]:
                for evidence in gate["required_evidence_ids"]:
                    self.assertIn(evidence, evidence_ids, gate["id"])


class FailClosedTests(unittest.TestCase):
    def _emit_error(self, pack: Path) -> EmitError:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(EmitError):
                emit(pack, Path(tmp) / "out", TEMPLATE)

    def test_missing_owner_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pack = pack_copy(Path(tmp))
            manifest = pack / ".ai" / "manifest.yaml"
            manifest.write_text(
                manifest.read_text(encoding="utf-8").replace(
                    "  operational_owner: platform-team", ""
                ),
                encoding="utf-8",
            )
            with self.assertRaises(EmitError):
                emit(pack, Path(tmp) / "out", TEMPLATE)

    def test_invented_repository_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pack = pack_copy(Path(tmp))
            manifest = pack / ".ai" / "manifest.yaml"
            manifest.write_text(
                manifest.read_text(encoding="utf-8").replace("id: demo-service", "id: tbd"),
                encoding="utf-8",
            )
            with self.assertRaises(EmitError):
                emit(pack, Path(tmp) / "out", TEMPLATE)

    def test_phase_without_validation_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pack = pack_copy(Path(tmp))
            package = pack / ".ai" / "execution-package.yaml"
            package.write_text(
                package.read_text(encoding="utf-8").replace(
                    '      validation:\n        - "python3 -m unittest discover -s tests -p \'test_*.py\'"\n    - phase: 2-hardening',
                    "      validation: []\n    - phase: 2-hardening",
                ),
                encoding="utf-8",
            )
            with self.assertRaises(EmitError):
                emit(pack, Path(tmp) / "out", TEMPLATE)

    def test_missing_overlay_config_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pack = pack_copy(Path(tmp))
            (pack / ".ai" / "program-execution-v2.yaml").unlink()
            with self.assertRaises(EmitError):
                emit(pack, Path(tmp) / "out", TEMPLATE)


if __name__ == "__main__":
    unittest.main()
