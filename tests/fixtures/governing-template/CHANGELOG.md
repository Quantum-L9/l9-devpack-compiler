# Changelog

## 2.0.0

See the distribution root `CHANGELOG.md` for the complete aligned-system change set.

## 2.0.0 alignment hardening

- Added typed execution targets, evidence catalog, waiver register, observability plan, and cutover/rollback contract.
- Made the dependency graph the sole owner of task dependencies.
- Removed runtime results from gate definitions and runtime state from Task Cards.
- Added explicit authorization ceilings, evidence obligations, negative cases, rollback, and completion gates.
- Deepened JSON Schemas and cross-file validation.
- Preserved instantiated Blueprints as `draft` until all domain placeholders and executable obligations pass instantiated validation.
