# l9-devpack-compiler

DPK-1.0 Developer Pack Compiler. Compiles a source repository into a
six-layer machine-parseable control plane plus an execution package.

This repository is the recovered **v1.2.0** skill pack (2026-07-15),
imported from the local Skills load pack so Program Execution can bind
`repository_id=l9-devpack-compiler` to an exact git SHA.

It was never previously a git repository. Dropbox is not the SSOT.

## Layout

| Path | Role |
|---|---|
| `SKILL.md` | Skill entrypoint (v1.2.0) |
| `scripts/validate_devpack.py` | Structural compile-readiness scorer |
| `scripts/validate_exemplary_skill.py` | Exemplary-skill validator |
| `references/` | DPK layer, quality, execution-package, spec contracts |
| `schemas/` | Build-spec schema + example |

## Provenance

- Source tree: `L9 Load Packs/Skills 06-07-2026/l9-devpack-compiler`
- Skill `updated`: 2026-07-15
- PE campaign that hardens this pack: `l9-devpack-program-execution-hardening`
