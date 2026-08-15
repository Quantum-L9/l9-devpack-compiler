# Instantiation Guide

Use an Execution Program when work spans multiple dependent systems, repositories, teams, authority boundaries, migrations, cutovers, releases, or evidence gates. Use an ordinary implementation plan for a small isolated feature.

## Required sequence

1. Name the objective, problem, target state, scope, owner, and contract versions.
2. Register every target with a stable target ID. Do not use human prose as repository identity.
3. Assign one owner per durable responsibility.
4. Catalog current evidence and its freshness.
5. Record decisions, Unknowns, risks, waivers, and prohibited paths.
6. Define workstreams and bounded Task Cards.
7. Encode dependencies once in `DEPENDENCY_GRAPH.yaml`.
8. Assign tasks to waves and gates.
9. Define observability, cutover, rollback, and Definition of Done.
10. Validate in instantiated mode and import into the Controller.

Every placeholder must be resolved before the Blueprint is considered executable.

## Acceptance transition

The instantiated copy remains `draft` while domain placeholders, evidence, decisions, Unknowns, task cards, and gates are completed. Set `program.definition_status: accepted` only after `--mode instantiated` validation passes.
