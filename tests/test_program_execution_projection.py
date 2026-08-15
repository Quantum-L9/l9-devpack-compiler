"""Projection tests (TASK-006): provenance, scoped Unknowns, authorization ceilings.

AC-011 (exact canonical ceiling, no authority by omission), AC-012 (Unknowns
block only consuming tasks), AC-013 (material emitted authority traces to
source evidence).
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from emit_program_execution_v2 import AUTH_ACTIONS, EmitError, emit  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"
PACK = FIXTURES / "dpk_mini"
TEMPLATE = FIXTURES / "governing-template"
TARGET_SCHEMA = ROOT / "schemas" / "program-execution-v2-target.schema.json"


def pack_copy(tmp: Path) -> Path:
    target = tmp / "pack"
    shutil.copytree(PACK, target)
    return target


def emit_into(tmp: Path, pack: Path) -> Path:
    out = tmp / "emitted"
    emit(pack, out, TEMPLATE)
    return out


def load_yaml(path: Path):
    import yaml  # type: ignore[import-not-found]

    return yaml.safe_load(path.read_text(encoding="utf-8"))


def load_schema():
    return json.loads(TARGET_SCHEMA.read_text(encoding="utf-8"))


def schema_shape(name: str):
    return load_schema()["properties"][name]


class CeilingProjectionTests(unittest.TestCase):
    def test_every_task_matches_schema_ceiling_shape(self) -> None:
        from jsonschema import Draft202012Validator

        ceiling_schema = schema_shape("emitted_authorization_ceiling")
        validator = Draft202012Validator(ceiling_schema)
        with tempfile.TemporaryDirectory() as tmp:
            out = emit_into(Path(tmp), pack_copy(Path(tmp)))
            tasks = load_yaml(out / "TASK_CARDS.yaml")["tasks"]
            for task in tasks:
                errors = list(validator.iter_errors(task["authorization_ceiling"]))
                self.assertEqual(errors, [], f"{task['id']} ceiling violates the overlay schema")
                self.assertEqual(
                    set(task["authorization_ceiling"]),
                    set(AUTH_ACTIONS),
                    f"{task['id']}: ceiling must carry exactly the canonical ten actions",
                )

    def test_ceiling_override_config_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pack = pack_copy(Path(tmp))
            overlay = pack / ".ai" / "program-execution-v2.yaml"
            overlay.write_text(
                overlay.read_text(encoding="utf-8")
                + "authorization_ceiling:\n  commit: true\n",
                encoding="utf-8",
            )
            with self.assertRaises(EmitError):
                emit(pack, Path(tmp) / "out", TEMPLATE)

    def test_no_action_granted_by_omission(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = emit_into(Path(tmp), pack_copy(Path(tmp)))
            tasks = load_yaml(out / "TASK_CARDS.yaml")["tasks"]
            for task in tasks:
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
                    self.assertIs(
                        task["authorization_ceiling"][action],
                        False,
                        f"{task['id']}.{action} must be false",
                    )


class ScopedUnknownProjectionTests(unittest.TestCase):
    def test_unknown_blocks_only_consuming_tasks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = emit_into(Path(tmp), pack_copy(Path(tmp)))
            unknowns = load_yaml(out / "UNKNOWN_REGISTER.yaml")["unknowns"]
            tasks = {t["id"]: t for t in load_yaml(out / "TASK_CARDS.yaml")["tasks"]}
            for unknown in unknowns:
                for blocked in unknown["blocks"]:
                    self.assertIn(blocked, tasks, unknown["id"])
                for task_id, task in tasks.items():
                    if task_id not in unknown["blocks"]:
                        self.assertNotIn(
                            unknown["id"],
                            task["blocking_unknown_ids"],
                            f"{unknown['id']} blocks {task_id} outside its scoped list",
                        )

    def test_unknown_targeting_missing_task_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pack = pack_copy(Path(tmp))
            overlay = pack / ".ai" / "program-execution-v2.yaml"
            overlay.write_text(
                overlay.read_text(encoding="utf-8").replace(
                    "    blocks_tasks:\n      - TASK-002",
                    "    blocks_tasks:\n      - TASK-999",
                ),
                encoding="utf-8",
            )
            with self.assertRaises(EmitError):
                emit(pack, Path(tmp) / "out", TEMPLATE)

    def test_emitted_unknown_matches_schema_shape(self) -> None:
        from jsonschema import Draft202012Validator

        unknown_schema = schema_shape("emitted_unknown")
        validator = Draft202012Validator(unknown_schema)
        with tempfile.TemporaryDirectory() as tmp:
            out = emit_into(Path(tmp), pack_copy(Path(tmp)))
            unknowns = load_yaml(out / "UNKNOWN_REGISTER.yaml")["unknowns"]
            for unknown in unknowns:
                errors = list(validator.iter_errors(unknown))
                self.assertEqual(errors, [], unknown["id"])


class ProvenanceProjectionTests(unittest.TestCase):
    def test_authority_facts_trace_to_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = emit_into(Path(tmp), pack_copy(Path(tmp)))
            evidence = {e["source"]: e for e in load_yaml(out / "EVIDENCE_CATALOG.yaml")["evidence"]}
            self.assertIn(".ai/manifest.yaml", evidence)
            program = load_yaml(out / "PROGRAM.yaml")["program"]
            targets = load_yaml(out / "EXECUTION_TARGETS.yaml")["targets"]
            cutover = load_yaml(out / "CUTOVER_AND_ROLLBACK.yaml")
            manifest_evidence = evidence[".ai/manifest.yaml"]
            # owner, repository id, and rollback all trace to the manifest anchor
            self.assertEqual(program["owner"], "platform-team")
            self.assertEqual(targets[0]["repository_id"], "demo-service")
            self.assertEqual(manifest_evidence["status"], "available")
            self.assertTrue(manifest_evidence["digest"])
            self.assertEqual(
                cutover["rollback"]["declared_rollback"]["strategy"], "inverse-patch"
            )
            traceability = load_yaml(out / "SOURCE_TRACEABILITY.yaml")["sources"]
            self.assertTrue(
                any(".ai/manifest.yaml" in s["source"] for s in traceability)
            )

    def test_missing_owner_fails_closed_no_invention(self) -> None:
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

    def test_red_line_tripped_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pack = pack_copy(Path(tmp))
            manifest = pack / ".ai" / "manifest.yaml"
            manifest.write_text(
                manifest.read_text(encoding="utf-8").replace(
                    "deployment:\n  rollback:", "deployment:\n  rollback_absent:"
                ),
                encoding="utf-8",
            )
            with self.assertRaises(EmitError):
                emit(pack, Path(tmp) / "out", TEMPLATE)


class RuntimeBoundaryProjectionTests(unittest.TestCase):
    def test_schema_runtime_keys_never_emitted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = emit_into(Path(tmp), pack_copy(Path(tmp)))
            banned = set(schema_shape("runtime_state_keys")["items"]["enum"])

            def walk(value, trail):
                if isinstance(value, dict):
                    for key, child in value.items():
                        self.assertNotIn(key, banned, f"{trail}.{key}")
                        walk(child, f"{trail}.{key}")
                elif isinstance(value, list):
                    for idx, child in enumerate(value):
                        walk(child, f"{trail}[{idx}]")

            for name in ("TASK_CARDS.yaml", "CONVERGENCE_GATES.yaml", "EXECUTION_WAVES.yaml"):
                walk(load_yaml(out / name), name)


if __name__ == "__main__":
    unittest.main()
