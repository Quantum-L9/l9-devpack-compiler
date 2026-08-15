# Design Rationale

The v2 Blueprint deepens the reusable execution model without importing domain-specific doctrine.

Key decisions:

- separate target identity from task prose;
- separate definition state, runtime state, evidence result, and program verdict;
- make the dependency graph the sole owner of task dependency edges;
- make Blueprint gates definitions only and Controller gate records evaluations only;
- model authorization as a ceiling that downstream layers can narrow but never widen;
- make evidence and waivers first-class, scoped, digestible, and expiring;
- define observability and rollback before cutover;
- return runtime evidence through a Handoff Receipt rather than mutating governance source files.
