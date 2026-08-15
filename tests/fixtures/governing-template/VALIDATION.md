# Blueprint Validation

```bash
python scripts/validate_blueprint.py . --mode template
python scripts/validate_blueprint.py /path/to/instantiated-blueprint --mode instantiated
```

Validation covers required files, JSON Schema execution, IDs, allowed values, target resolution, authority uniqueness, decision and Unknown blockers, dependency acyclicity, task/wave alignment, gate/evidence references, authorization ceilings, markdown links, Python compilation, manifest integrity, and placeholder removal.

A pass proves Blueprint coherence, not runtime success. Runtime proof belongs to Controller receipts.
