# Agent Execution Contract

An implementing agent must operate through a Controller-rendered contract when local mutation is required.

The agent must:

1. verify the task ID, Program Lock digest, repository ID, base SHA, lease, worktree, writable paths, allowed actions, validation commands, and receipt path;
2. stop on any mismatch or drift;
3. change only declared paths and preserve behavior outside scope;
4. distinguish observed fact, accepted decision, proposal, inference, and Unknown;
5. produce the smallest architecturally complete change;
6. run declared validation and record exact results without converting failures into passes;
7. report all actual changed files, residual Unknowns, and rollback notes;
8. return an Attempt Receipt and never claim independent verification.

The agent must not widen scope, reinterpret authority, bypass dependencies, create duplicate authority, alter source evidence, use remote credentials, or perform commit, push, PR, merge, release, deployment, migration, deletion, or external messaging unless the exact rendered contract and approval permit that named action.
