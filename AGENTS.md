# Ownership and workflow

This repository is being built through an Orca Run. The dedicated Codex Sol medium
coordinator terminal owns Run, Task, Dispatch, lifecycle and final verification.
The originating chat observes progress and communicates with the user; it does not
consume the coordinator mailbox or create competing dispatches.

Read the installed `/Users/jonghyeonlee/.agents/skills/orchestration/SKILL.md` and
the version-matched `orca skills get orchestration` before lifecycle actions.
Use saved Orca Tasks and supervised Dispatches, not native subagents.
One editing worker at a time; at most one additional read-only worker.
Workers do not launch nested workers. Coordinator alone accepts completion.

Routing: default implementation Luna high; difficult periodic connectivity and
cross-module design Sol medium/high. Coordinator Sol medium. Independent review
of core calculations, schemas, security and recovery: Claude Sonnet high.
Only subscription authentication is authorized, never additional API billing.

Use explicit terminals until a new read-only structured-worker smoke is proven:
`orca terminal create --worktree path:/Users/jonghyeonlee/git/layout-electrode-extractor --command 'codex --model gpt-6-luna -c model_reasoning_effort="high" --dangerously-bypass-approvals-and-sandbox --dangerously-bypass-hook-trust' --json`
Then `terminal wait --for tui-idle` and `orchestration worker-start --task ... --terminal ...`.
For Sol substitute the selected model/effort. For Claude use sonnet/high.
Review `~/.codex/hooks.json` before unattended Codex launch after any hook change.
Verify actual model/effort from the terminal, not only the launch receipt.

Never retry uncertain dispatches, abandon live authority, or revert partial work.
Inspect exact recovery receipts. Process the canonical coordinator inbox, validate
worker_done, and reuse/release every settled worker before acknowledging delivery.
Checkpoint Run/Task/Dispatch IDs and acceptance evidence in docs/orca/CHECKPOINT.md.
Every task has target, change, constraints, ownership, acceptance and baseline.

Do not edit /Users/jonghyeonlee/git/particle-sim. It is read-only integration context.
No remote publication is requested. Local commits to this new repository are allowed.
Generated examples/output, environments and caches must be ignored by Git.

# Product contract

Read docs/PLAN.md and docs/orca/IMPLEMENTATION-CONTRACT.md.
Latest user instruction supersedes the original plan: output is 2x2 unit images,
same 0.1 um/px, typical 600x600 input -> 1200x1200 output. All layers are cut by TR.
Two GAT, one ACTIVE, one OACTIVE, two CNT for synthetic validation; add a metal
layer for contacts as needed. Wire width about 2 um = 20 px. Stack/circuit may be synthetic.
Periodic connectivity must preserve instance identity; never simply tile each
already-labelled electrode. Never claim finite halo stabilization proves general correctness.
