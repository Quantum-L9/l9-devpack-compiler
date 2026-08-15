# Blueprint Runbook

## 1. Instantiate

```bash
python scripts/instantiate.py --name "Program Name" --id program-id --version 0.1.0 --owner "Owner" --target ../program-id-blueprint
```

## 2. Establish authority before decomposition

Complete `PROGRAM.yaml`, `EXECUTIVE_DECISION.md`, `EXECUTION_TARGETS.yaml`, `AUTHORITY_REGISTRY.yaml`, and current-state evidence first.

## 3. Resolve blockers

Do not mark a task ready while a required decision is pending or a named Unknown is open.

## 4. Build the execution map

Define workstreams, then Task Cards, then encode all task-to-task dependency edges in `DEPENDENCY_GRAPH.yaml`, then assign tasks to waves.

## 5. Define proof before mutation

Set acceptance, validation, negative cases, rollback, risk, authorization ceiling, and completion gates before importing the task into a Controller.

## 6. Validate and reseal

```bash
python scripts/validate_blueprint.py . --mode instantiated
```

Regenerate `MANIFEST.yaml` after every accepted change. A Controller runtime becomes stale when an imported source digest changes.
