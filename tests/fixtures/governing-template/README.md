# Program Execution Blueprint Template

A Program Execution Blueprint is the canonical design-time authority pack for an **Execution Program**. It replaces vague backlog containers with explicit target state, authority, evidence, dependencies, authorization ceilings, convergence gates, rollback, and a terminal verdict.

## What it owns

- program identity, objective, scope, target state, and authority order;
- execution targets and their authoritative identities;
- decisions, Unknowns, risks, waivers, and prohibited paths;
- workstreams, task definitions, dependency graph, waves, and gates;
- evidence requirements, observability, cutover, rollback, and Definition of Done.

It does **not** own repository HEADs, leases, worker attempts, mutable task runtime state, or runtime gate evaluations. Those belong to the Program Execution Controller.

## Start here

1. Read `INSTANTIATION_GUIDE.md` and `../shared/INTERFACE_CONTRACT.md` when using the paired distribution.
2. Instantiate with `python scripts/instantiate.py --help`.
3. Complete files in the sequence defined by `EXECUTION_INDEX.yaml`.
4. Validate with `python scripts/validate_blueprint.py . --mode instantiated`.
5. Import the accepted Blueprint into a compatible Controller. Never hand-edit the Controller Program Lock.

## Core law

No downstream artifact may invent, widen, override, or bypass an upstream authority, decision, dependency, authorization ceiling, evidence obligation, or convergence gate.
