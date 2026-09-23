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
