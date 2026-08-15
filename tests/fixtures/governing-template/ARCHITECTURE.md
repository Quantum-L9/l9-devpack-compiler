# Blueprint Architecture

## Definition layer

`PROGRAM.yaml`, `EXECUTIVE_DECISION.md`, and `ARCHITECTURE.md` define the undertaking and target state.

## Authority layer

`EXECUTION_TARGETS.yaml`, `AUTHORITY_REGISTRY.yaml`, `DECISION_REGISTER.yaml`, `UNKNOWN_REGISTER.yaml`, `RISK_REGISTER.yaml`, `WAIVER_REGISTER.yaml`, and `DO_NOT_BUILD.yaml` define ownership and constraints.

## Execution map layer

`WORKSTREAMS.yaml`, `DEPENDENCY_GRAPH.yaml`, `EXECUTION_WAVES.yaml`, and `TASK_CARDS.yaml` define decomposed work. `DEPENDENCY_GRAPH.yaml` is the only canonical owner of task-to-task dependencies.

## Proof layer

`EVIDENCE_CATALOG.yaml`, `CONVERGENCE_GATES.yaml`, `OBSERVABILITY_PLAN.yaml`, `CUTOVER_AND_ROLLBACK.yaml`, `DEFINITION_OF_DONE.md`, and `SOURCE_TRACEABILITY.yaml` define proof and closure.

## Runtime boundary

The Controller imports all sources listed by `EXECUTION_INDEX.yaml`, validates them, and creates an immutable Program Lock. The Controller may project definitions into runtime state but cannot reinterpret their meaning.
