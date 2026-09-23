# Implementation contract for the Orca coordinator

The user authorized implementation and validation via saved Orca Tasks. This is a
new local repository. Implement the agreed first release, not just a plan or a
throwaway demonstration. Keep the original particle-sim repository unchanged.

Read-only references:
- /Users/jonghyeonlee/git/particle-sim/docs/layout-electrode-extraction-plan.md
- /Users/jonghyeonlee/git/particle-sim/outputs/layout-electrode-prototype/build_fixture.py
- /Users/jonghyeonlee/git/particle-sim/src/particle_sim/{schema.py,io/masks.py,geometry/contacts.py}

Create all real Tasks in the Run before execution; baseline each task against the
actual candidate at dispatch. Suggested linear dependency chain below reflects
real component dependencies and the one-editor requirement. You may refine task
boundaries, preserving saved contracts and outcomes. Start no unnecessary planning worker.

## T1 — extraction engine and exact periodic connectivity (Sol high)

Target: pyproject, src/layout_electrode_extractor, engine/schema/io/CLI tests.
Change: installable Python package and CLI accepting an explicit layer/stack/TR
manifest; aligned binary masks; TR intersections by source layer pair; remove TR
union from ALL layers including GAT/contact masks; label residual conductors;
contact connectivity; output full 2x2 masks per global electrode/layer and per TR;
metadata with scale, origin, layers, connectivity and hashes. Preserve raw masks.
Ownership: sole editor of this repository for this task. No changes to particle-sim.
Constraints: preserve pixel grid; no automatic dilation/closing; layer-role and
contact endpoints explicit; safe paths/IDs; deterministic IDs; fail on malformed
input. Distinguish repeated independent electrode instances. Bound arbitrary
resource use. No unsupported assumption that 3x3/6x6 convergence proves periodic connectivity.
Periodic algorithm: use tile-displacement-labelled graph and exact reachability
in its Z^2 lift (cycle displacement subgroup membership is one viable method).
Include contacts/TR spanning boundaries. If a case cannot be established, return
explicit unresolved and do not silently output a confirmed merge. Default four-neighbour
convention with documented options. Contact holes that connect multiple independent
lower/upper components must be diagnosed, not silently made strict-adapter-compatible.
Acceptance: meaningful adversarial tests for winding paths, independent copies,
boundary contacts/TR, diagonal contact policy, infinite bus, all-layer removal,
mask partition conservation and invalid manifests; pytest and ruff.
Report APIs and any limitations for T2/T3. Commit implementation when tests pass.

## T2 — human naming and circuit assistance (Sol medium/high)

Target: local review UI, annotations persistence, circuit import/matching, UI tests.
Change: runnable localhost review interface for output with layer switching,
whole-electrode highlighting, TR selection, naming, unnamed list, annotation
save/reload, corrected export folders and provenance. Separate internal IDs from
names and reject collisions/path traversal. Changed input/extraction invalidates
stale name correspondences. Avoid giant inline base64 per-electrode stacks if possible.
Circuit: accept a documented explicit JSON/CSV netlist (and optionally a carefully
bounded SPICE MOS subset); display an imported schematic image beside layout for
manual verification. Support editable TR-terminal/net correspondence and anchored
name candidates from graph structure. Never auto-confirm ambiguous symmetric matches.
Preserve pre-cut gate evidence separately because ALL-layer TR removal may split
one schematic net into multiple output electrodes. Allow one-to-many mappings.
Image assistance: local optional OCR of labels is useful if available; absence must
not block the core. Distinguish text recognition from complete wire/graph recognition.
Full unattended arbitrary schematic-image understanding is a later capability;
the first release must support the image plus human-corrected connectivity workflow.
Ownership: sole editor. Read predecessor interfaces; ask coordinator if contracts conflict.
Acceptance: naming persistence/reload/export/stale-input/collision/path tests;
circuit matching tests with anchors and ambiguous symmetric graph; runnable UI,
representative browser smoke if available, no external paid services. Commit.

## T3 — reproducible synthetic cases, adapter and user documentation (Luna high)

Target: synthetic generator, examples, particle-sim export adapter, integration tests,
README with exact commands and assumptions.
Change: make-synthetic generates 600x600 at 0.1 um/px, ~20 px wires, GAT1/GAT2,
ACTIVE/OACTIVE, CNT1/CNT2, METAL1 and assumed stack/circuit; branching, bends,
loops, contacts, independent islands and cross-boundary geometry. End-to-end output
is 1200x1200. Keep generated outputs ignored; retain reproducible generator/config.
Adapter emits manifest schema 2.0 and masks consumable by current particle-sim.
Use supplied physical/process settings; synthetic defaults must be labelled assumed.
Multiple masks/layers belonging to one extracted electrode share net_id. Use
TR-cut contact masks with provenance. Explicitly handle unsupported contact topology.
Classify required different-net electrode pairs with a documented policy, never
silently omit them. No fake physical validation claims. Explain 4x area normalization,
outer-boundary limitations and ROI-as-open-terminal risks. Do not claim periodic
particle-sim support. Reuse particle-sim .venv read-only if helpful for validate-input.
Ownership: sole editor. Baseline predecessor commits, preserve their APIs or ask.
Acceptance: generate, extract, review/annotation example, export; execute actual
particle-sim validate-input on emitted manifest; a bounded representative simulation
smoke if feasible with clearly scoped pair set and one particle size; tests and ruff;
record counts, runtime and artifact paths. Commit.

## T4 — independent review (Claude Sonnet high, read-only)

Target: exact candidate commits/diff, specs, relevant tests and acceptance evidence.
Change: assess periodic maths/identity, TR removal, contact rules, annotations and
schema/API boundaries, safe local UI/file handling, adapter correctness and limits.
Ownership: no product edits. Write only the assigned review report if needed.
Acceptance: explicit PASS or actionable findings with file/line and reproduction,
bound to exact commit. Author cannot supply this PASS. Route local fixes to author;
Sol for design defects. Retest and refresh review after any product fix.

## Coordinator completion

Only the dedicated terminal owns lifecycle; the source chat is an observer. Use
the canonical check/ack loop and keep meaningful checkpoint updates. Verify relevant
commands yourself against the reviewed candidate. Do not simply trust worker summaries.
Never poll faster than useful progress warrants; keep waits bounded for responsiveness.
After all settlements and worker cleanup, write docs/orca/FINAL-REPORT.md containing
Run and Task outcomes, exact commits, validation commands/results, output locations,
known limitations, and a ready-to-run user quickstart. End coordinator work in a stable
idle state, leaving its own terminal available for the source chat to read.
