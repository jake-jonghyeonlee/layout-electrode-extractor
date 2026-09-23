# T4 independent review

Reviewer: Claude Sonnet, high effort, read-only (Task `task_693c45297d8e`, Dispatch `ctx_4277921705f5`).
Candidate: `753eb0f4333cd90bf213c70204d32cda36de35d4` (base `439372f`; T1 `723efc5`; T2 `153f8e2`;
T3 `1b96df6`; `753eb0f` is a formatting-only + checkpoint-doc commit over T3, verified by diff —
no logic changes to `particle_sim_adapter.py` or `synthetic.py`, only whitespace/line-wrap and one
doc update). Independently reran on this exact SHA: `pytest -q` — 22 passed; `ruff check .` — all
checks passed. Reviewed `docs/PLAN.md`, `docs/orca/IMPLEMENTATION-CONTRACT.md`,
`docs/EXTRACTION-API.md`, `docs/REVIEW-API.md`, `README.md`, and all of
`src/layout_electrode_extractor/{periodic,engine,schema,particle_sim_adapter,synthetic,review,
server,circuit,cli}.py` plus `tests/test_engine.py`, `tests/test_review.py`,
`tests/test_synthetic_adapter.py`.

## Verdict

Not an unconditional PASS. One actionable, reproducible correctness/documentation defect in the
particle-sim adapter (below); everything else reviewed — periodic math/instance identity, TR
removal, contact-rule diagnosis, manifest/annotation safety — is sound and matches the contract,
with two low-severity observations noted for completeness. Author must not self-approve; route the
adapter fix to its author and re-review after any change, per the T4 contract.

## Finding 1 (actionable) — adapter hardcodes literal layer IDs instead of using `role`

`src/layout_electrode_extractor/particle_sim_adapter.py:55-56,66-67,91`

```python
if name == "ACTIVE":          # line 55 — should branch on layers[name]["role"] == "ACTIVE"
    ...
if name == "OACTIVE":         # line 66 — should branch on role == "OACTIVE"
    ...
metal_order = next(i for i, row in enumerate(product_layers) if row["layer_name"] == "METAL1")  # line 91
```

`schema.py` deliberately separates a layer's user-chosen `id` (any string matching `_ID`, e.g.
`ACT_A`) from its semantic `role` (`GAT`/`ACTIVE`/`OACTIVE`/`METAL`/`CONDUCTOR`/...). Every other
part of the pipeline (engine.py's `conductors`/`holes` sets, TR-pair validation, contact-endpoint
validation) is role-driven, so a manifest is free to name its ACTIVE-role layer `ACT_A` or its only
metal layer `MTL_TOP`. The adapter alone breaks this contract:

- **Silent incompleteness**: if the ACTIVE-role or OACTIVE-role layer is not literally named
  `"ACTIVE"`/`"OACTIVE"`, the `ILD_ACTIVE_OACTIVE` / `ILD_OACTIVE_METAL1` dielectric rows are never
  emitted (lines 55-76), producing a physically incomplete stack with no error or diagnostic.
- **Unhandled crash**: if no conductor layer is literally named `"METAL1"` (e.g. a manifest using
  `METAL_A`, or a stack with `METAL1`+`METAL2` where the CNT/VIA layer's `upper` endpoint isn't
  spelled `"METAL1"`), line 91's `next(...)` raises an uncaught `StopIteration` instead of a
  `ManifestError`/documented limitation — the CLI's `except` clause in `cli.py:68` does not catch
  `StopIteration`, so `export-particle-sim` crashes with a raw traceback.
- **Comment/code mismatch**: the comment at line 89 ("All non-patterned contact layers must sort
  between their declared endpoints") describes endpoint-aware placement, but the code (lines
  90-94) unconditionally inserts every contact layer immediately before whichever row is literally
  named `METAL1`, never reading `contact["lower"]`/`contact["upper"]`. This only happens to be
  correct for the T3 fixture because both `CNT1` and `CNT2` have `upper == "METAL1"`. A contact
  whose `upper` endpoint is a different conductor (anything besides the literal `METAL1` layer)
  would be ordered incorrectly in `product_layers` without any diagnostic.

**Reproduction**: construct a manifest with `layers: [{"id":"ACT_A","role":"ACTIVE",...}, ...]`
(schema.py accepts this; only `role` is checked at `schema.py:147,161`) and a stack whose top
conductor is named e.g. `"METAL_A"` instead of `"METAL1"`. `extract()` succeeds normally.
`export_particle_sim()` either silently omits both ILD rows (if only the ACTIVE/OACTIVE names
differ) or raises `StopIteration` (if no layer is literally `"METAL1"`).

**Scope**: not exercised by `tests/test_synthetic_adapter.py`, whose only fixture
(`synthetic.py`) uses exactly the literal names `ACTIVE`/`OACTIVE`/`METAL1`. Not disclosed as a
limitation in `README.md`, `docs/PLAN.md`, or the adapter's own `adapter-provenance.json` output —
all of which discuss physical/process assumptions but not this naming constraint. This is squarely
inside the T3/T4 charge to "explicitly handle unsupported ... topology" and "documented limits":
right now the limitation exists but is neither guarded nor documented, and IMPLEMENTATION-CONTRACT.md
positions T3's synthetic fixture as a rehearsal for later real (non-`ACTIVE`/`METAL1`-named) input,
which this code would silently or fatally mishandle. Route to the T3 author (Luna) for a fix
(branch on `role`, and raise a clear `ManifestError`-style diagnostic instead of `StopIteration`
when no upper-most conductor is resolvable); re-review after any change per the T4 contract — this
finding is not itself grounds to block T1/T2, whose scope it doesn't touch.

## Verified sound (no findings)

- **Periodic math / instance identity** (`periodic.py`): traced `Lattice.add`/`key` for rank
  0/1/2 by hand against the standard 2-D HNF/Bezout merge algorithm (determinant/index formula
  `gcd(gx·gv, gx·y − yr·x, gv·x)` at `periodic.py:77` matches the textbook 3-generator merge);
  traced `PeriodicGraph.solve()`'s BFS-with-potentials + cycle-lattice accumulation for
  double-edge-direction idempotency (a back-edge and its mirror both reduce to a no-op or the same
  generator). `tests/test_engine.py::test_independent_repeated_instances_and_infinite_bus` and
  `::test_lattice_cosets_and_winding_graph` are genuinely adversarial (isolated single-pixel islands
  stay 4 distinct instances; an infinite periodic bus in one axis correctly collapses to exactly 2
  instances — one per un-connected axis — not 1 or 4; a 3-node winding cycle's net displacement is
  verified algebraically), not tautological. Matches PLAN.md's explicit warning against naively
  tiling already-labelled electrodes.
- **TR removal from all layers**: `engine.py:272` applies `raw & ~tr_union` to every manifest
  layer including GAT/contact masks, matching the "cut before connectivity" contract; TR-pair
  pixel overlap between distinct pairs is a hard `ManifestError` (`engine.py:265-266`), matching
  PLAN.md's "no GAT may double-cover one TR pixel" rule.
- **Contact rules**: `_contact_issues` diagnoses `periodic_contact_network` (infinite hole bus),
  `multi_endpoint_contact`/`missing_endpoint_contact`, and `orphan_contact` rather than silently
  accepting or hiding them, per PLAN.md/AGENTS.md. `test_multi_component_contact_is_diagnosed` and
  `test_diagonal_contact_policy` confirm this with concrete pixel fixtures, including the
  4-vs-8-connectivity distinction.
- **Naming/schema security**: `schema.py`'s `_ID`/`_NET` regexes, symlink-and-escape-safe
  `resolve(strict=True)` + `is_relative_to` checks (`schema.py:124-126`, `review.py:112-121`), and
  `review.py`'s allowlist-by-construction (`_validate_assets`) close path traversal. Annotation
  saves/exports are guarded by extraction/circuit/schematic content fingerprints
  (`StaleAnnotationsError`) and an optimistic-concurrency revision check, matching PLAN.md's "stale
  correspondence must be flagged" requirement. `server.py` binds loopback-only, requires a
  same-origin check plus a random CSRF token on every `POST`, and serves only an explicit asset
  allowlist.

## Minor observations (not blocking)

1. `server.py:_allowed_origin` accepts a `GET` when the `Origin` header is absent, checking only
   the `Host` header. This is standard and safe against the DNS-rebinding case (Host would not
   match a loopback name), and every state-changing `POST` is independently gated by the CSRF
   token, so I could not construct an exploit; flagging only because a same-site `<img>`/simple-GET
   without an `Origin` header is a known class of local-server probing and this code relies on
   modern browsers reliably sending `Origin` cross-origin for `fetch`/`XHR` (which they do) rather
   than defense-in-depth for every GET. Low confidence, low severity for a single-user loopback
   review tool serving non-secret PNG masks.
2. No browser/UI smoke evidence exists against the final T3 fixture (88 electrodes, 32 TRs,
   2 µm wires). `outputs/browser-smoke.json` covers only the superseded thin-wire T1 fixture on the
   T2 candidate (`153f8e2`), which the checkpoint already discloses honestly. Pytest/ruff and the
   particle-sim `validate-input` run do cover the final T3 output; only an interactive UI
   walkthrough at the final scale is missing. Acceptance-evidence gap, not a code defect.

## What's left

Finding 1 needs an author fix (role-driven layer matching, explicit diagnostic instead of
`StopIteration`, endpoint-aware contact ordering, and a README/adapter-provenance note documenting
the constraint until fixed) and a re-review bound to the new SHA before this candidate can carry an
unconditional PASS.

# T5 candidate re-review (T6)

Reviewer: Claude Sonnet, high effort, read-only (Task `task_904c4294584e`, Dispatch
`ctx_aa6a7336c310`). Candidate: `23f71965da20b0e1fc13eba039ded0eece2b9f26` (baseline
`0b5e98edf9db4f42980552f67110a74610dd539b`, the commit that recorded the T4 findings above). Diff
scope confirmed by `git diff 0b5e98e 23f7196 --stat`: `README.md`, `src/layout_electrode_extractor/
particle_sim_adapter.py`, `tests/test_synthetic_adapter.py` only — no other product file touched.
Independently reran on this exact SHA: `pytest -q` — 25 passed (22 before, +3 new adapter tests);
`ruff check .` — all checks passed; `ruff format --check .` — only flags the Python fence inside
this reviewer-owned `docs/orca/REVIEW.md` file (pre-existing since T4, not a T5 regression, not a
source/test file). Regenerated the full T3-scale synthetic fixture end-to-end (`make_synthetic` →
`extract` → `export_particle_sim`) against the candidate: 88 electrode instances, 32 TR instances,
98 electrode masks, 4,743 classified pairs — matches the T3 checkpoint exactly, so the final
synthetic output is unregressed. Ran the actual `particle-sim validate-input` CLI (from the
sibling `~/git/particle-sim` checkout, read-only) against the regenerated `product.yaml`: `status:
"ok"`, `shape_yx: [1200, 1200]`, `pixel_size_um: [0.1, 0.1]`, `unresolved_electrode_pairs: 0` —
end-to-end validity of the exact candidate's output confirmed, not just unit tests.

## Verdict

Not an unconditional PASS. All three T4 Finding-1 bullets are fixed and independently verified
(below); one new, narrower actionable gap remains (Finding 2) in the same silent-incompleteness
class. Author must not self-approve; route Finding 2 to its author and re-review after any change.

## T4 Finding 1 — verified fixed

- **Silent incompleteness (renamed ACTIVE/OACTIVE)**: `_stack_layers`
  (`particle_sim_adapter.py:17-131`) now branches on `layers[layer_id]["role"]`
  (`by_role.setdefault(layers[layer_id]["role"], []).append(layer_id)` at line 30), not on literal
  IDs. I reran the candidate's own `test_renamed_roles_and_non_top_metal_contact_endpoint`, which
  renames `ACTIVE→ACT_A`, `OACTIVE→OACT_A`, `METAL1→MTL_TOP` and reproduces T4's exact repro
  scenario: `ILD_ACTIVE_OACTIVE`/`ILD_OACTIVE_METAL` rows are still emitted, keyed on role. Passes.
- **Unhandled `StopIteration` crash**: the old `next(...)` search for a literal `"METAL1"` row is
  gone. Unresolvable/ambiguous stacks now raise `ManifestError` (e.g. `particle_sim_adapter.py:
  24-26,34-38,40-43,49-52,58-62,69-72,104,128-130`), and `export_particle_sim` calls `_stack_layers`
  (line 145) before `output.mkdir` (line 169), so no partial output is created on failure — verified
  by reading the ordering and by the candidate's own
  `test_ambiguous_role_stack_fails_before_creating_output` and
  `test_unsupported_contact_endpoint_fails_before_creating_output`, both asserting
  `not output.exists()` after the raise. `ManifestError` is a `ValueError` subclass caught by
  `cli.py:68`'s existing `except (ManifestError, ResourceError, ReviewError, CircuitError,
  OSError)` clause, confirmed by reading `cli.py`, so `export-particle-sim` now exits with a clean
  diagnostic instead of a raw traceback.
- **Comment/code mismatch (contact ordering)**: contacts are now queued by their declared `upper`
  endpoint (`contact_by_upper.setdefault(upper, []).append(contact)` at line 73) and emitted
  immediately before that exact conductor's row in the per-`layer_id` loop (lines 89-115), not
  before a hardcoded `METAL1` search. The candidate's new test asserts this directly for a contact
  whose `upper` is `MTL_MID`, a non-topmost conductor: `stack_order["ACT_A"] < stack_order["CNT1"]
  < stack_order["MTL_MID"]` and `product["contacts"][0]["upper_layer"] == "MTL_MID"`. I reran it —
  passes.

## Finding 2 (actionable, narrower) — OACTIVE→METAL dielectric silently skipped for a `CONDUCTOR`-role top layer

`src/layout_electrode_extractor/particle_sim_adapter.py:14,23,33,54-63`

```python
_CONDUCTOR_ROLES = {"GAT", "ACTIVE", "OACTIVE", "METAL", "CONDUCTOR"}   # line 14 — CONDUCTOR is an
                                                                         # accepted stack role
...
        if layer_id not in layers or layers[layer_id].get("role") not in _CONDUCTOR_ROLES:  # 23
...
    metal_ids = by_role.get("METAL", [])   # line 33 — only the literal "METAL" role is collected
...
    if oactive_ids and metal_ids:          # line 54 — false whenever no layer anywhere in the
                                            # stack has role "METAL", even if a role="CONDUCTOR"
                                            # layer sits above OACTIVE and needs the same isolation
        ...
```

`schema.py:18` (`_CONDUCTORS = {"GAT", "ACTIVE", "OACTIVE", "METAL", "CONDUCTOR"}`) and the
adapter's own `_CONDUCTOR_ROLES` at line 14 both treat `METAL` and `CONDUCTOR` as equally valid,
generic "conductor" stack roles — nothing in the schema or in the adapter's own admission check
signals that only `METAL` gets ILD treatment above OACTIVE. But the `ILD_OACTIVE_METAL` placement
logic (lines 54-63) only ever looks at `by_role.get("METAL", [])`. If a manifest's stack has an
OACTIVE-role layer followed by a conductor role `CONDUCTOR` instead of `METAL` — a role
`schema.py` and the adapter's own line 23 both accept for stack membership — `metal_ids` is empty,
the `if oactive_ids and metal_ids:` guard is false, and the block is skipped entirely with **no
error and no diagnostic**, silently omitting the `ILD_OACTIVE_METAL` dielectric row. This is the
same "silent incompleteness" failure class as T4 Finding 1's first bullet, just triggered by role
choice instead of ID naming; the explicit `ManifestError` at line 60 ("no METAL-role conductor
follows OACTIVE") only fires when `METAL`-role layers exist elsewhere but not after OACTIVE — it
does not fire when there are zero `METAL`-role layers in the whole stack, which is exactly the case
this reproduces.

**Reproduction** (against the exact `23f7196` candidate): take `make_synthetic()`'s manifest and
change only `METAL1`'s `role` from `"METAL"` to `"CONDUCTOR"` (stack, contacts, and all layer IDs
left unchanged — `CNT2`'s `upper` is still `METAL1`). `extract()` then `export_particle_sim()` both
succeed; `product["stack"]` contains `ACTIVE`, `ILD_ACTIVE_OACTIVE`, `OACTIVE`, `CNT1`, `CNT2`,
`METAL1` but **no** `ILD_OACTIVE_METAL` row, and no error or warning is raised or recorded anywhere
in the output. I ran this exact repro via `.venv/bin/python3` against the candidate and confirmed
the missing row and the absence of any diagnostic.

**Scope**: narrower than T4 Finding 1 — it requires a manifest author to deliberately declare the
isolating layer above OACTIVE with role `CONDUCTOR` rather than `METAL` (an available, schema-legal
choice, not a naming accident), and `README.md`'s new adapter section already discloses that
placement happens "before... the first METAL role above" OACTIVE, so the `METAL`-only scope is
documented rather than fully hidden. Not exercised by either of the candidate's new tests, which
both use `role: "METAL"` for the renamed top layer. Given T5's explicit charter was to make silent,
undiagnosed incompleteness impossible for unsupported topology, recommend either treating `METAL`
and `CONDUCTOR` alike for `ILD_OACTIVE_METAL` placement, or raising an explicit `ManifestError` when
`oactive_ids` is non-empty but no conductor of any role follows it in stack order that the adapter
is prepared to isolate, instead of silently proceeding. This finding is not itself grounds to
re-open the three T4 Finding-1 bullets, which are independently verified fixed above.

## Minor observation (not blocking)

`export_particle_sim`'s `if conductors[-1] not in layers:` check at `particle_sim_adapter.py:146`
is unreachable dead code: `_stack_layers` (called immediately before, line 145) already raises
`ManifestError` for any `conductor_ids` entry — including the last one — that is not a key in
`layers` (lines 22-26). Harmless, but worth deleting for clarity in a future pass.

## What's left

Finding 2 needs an author decision (treat `CONDUCTOR` like `METAL` for OACTIVE-side ILD placement,
or raise an explicit diagnostic) and a re-review bound to the new SHA before this candidate can
carry an unconditional PASS. The three T4 Finding-1 bullets are closed and need no further action.
