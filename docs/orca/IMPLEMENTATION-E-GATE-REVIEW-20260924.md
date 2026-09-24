# E-stage gate review: X1–X3, P2/P3 and E1/E2/E3 contracts (2026-09-24)

- Reviewer: Claude Opus 5.5 high. Read-only. Run `run_5463d205f39d`, Task `task_073f47a22cb8`, Dispatch `ctx_5cc7181e2b45`.
- Target: plan v2 at `bf4e8c2` (the working-tree file is unchanged from that commit). Also read review v1/v2 and v5.
- Extractor citations come from `bf4e8c2`. P0/P1 editor `ctx_73ef1feaf894` is live, so I did not read or rely on working-tree adapter files.
- particle-sim `aae492a` was read only. Its tree was the same as before: one untracked `docs/layout-electrode-extraction-plan.md`.
- I edited no repository file and ran no tests. This is a plan gate, not a code-review PASS.

## Verdicts

| Item | Verdict | Blocks |
| --- | --- | --- |
| X1 per-centre CNO/open relation | **FAIL** (the contract text needs fixes; no replan is needed) | Blocks E3 dispatch. It does not block E1. |
| X2 auto-open semantics | **PASS with 2 required pins** | Pin 1 goes into the E1 acceptance. Pin 2 goes into the P2 acceptance. |
| X3 isolated copy / original read-only | **FAIL** (concrete write/provenance leak) | Blocks any E dispatch. |
| P2/P3 contract | Implementable if split and pinned | See below. |
| E1/E2/E3 contracts | E1 and E2 are bounded once pinned. E3 is not implementable until X1 is fixed. | See below. |

The principles in v2 L12 are correct. These are:
- the per-centre key `(source_step, diameter_um, centre_y, centre_x, particle_shape)`;
- an explicit relation table, never derived from the net;
- `open_final = open_raw & ~OR(related CNO)`;
- raw results are preserved, and shorts and unrelated opens are never removed;
- CNO uses the full cut hole, `2*covered>=area`, and margin 0.

The failures come from missing pins at the particle-sim interface.

## X1 — FAIL

1. **Relation granularity is ambiguous ("CNO hole/link ID").**
   - particle-sim has two IDs:
     - link unit `cno:{contact_id}:{lower}__{upper}` (`particle-sim geometry/contacts.py:43-44`);
     - per-hole `{contact_id}#{hole_index}`, where `hole_index` is the scipy default 4-connected label order of each contact mask (`contacts.py:87,97`; the name format is in `failure/auto_open.py:51`).
   - Counterexample: link L has parallel holes h1 and h2. A particle covers 60% of h1 and 0% of h2, and also cuts open path P.
     - If the relation row is `h2→P`, nothing is removed.
     - If the row is `L→P`, the open is removed, because the any_hole link CNO is true (`contact_not_open.py:59-61`).
     - Both readings pass v2 L12.
   - Pin: relation keys are **link unit IDs** exactly as `cno_unit_id` formats them. Removal uses the link CNO map, which is the OR over holes of the per-hole 50% events. Per-hole maps are kept only as raw diagnostics.
   - (Alternative: key by `contact_id#hole_index`, with that index rule stated. Pick one.)
   - Add a synthetic unit test with a two-hole link. The 2×2 fixture may not exercise multi-hole links.
2. **No carrier for the relation table.**
   - Every particle-sim manifest model is `extra="forbid"` (`schema.py:17,70,123…`), so `cno_open_relations` cannot travel in `product.yaml`.
   - Pin: P2 writes the table to the adapter sidecar. E3 reads it in a post-processing step. (Alternative: E3 extends the copy's schema. State which.)
   - Unknown or duplicate link/path IDs, or a relation to a CNO link that is not applicable at any step, must fail **before** computation. They must not silently remove nothing.
3. **Full-hole pixels are discarded today.**
   - `ContactHole.ys/xs` hold effective pixels only (`contacts.py:20-22,125-133`).
   - Auto-open terminals consume those same arrays (`auto_open.py:47-55`).
   - Pin: E1 adds a **separate** full-cut-component pixel field (raw/cut/effective counts). It must not repurpose `ys/xs`.
4. **Step applicability.**
   - CNO units are empty at non-applicable steps (`units.py:163-164`). Open paths with empty steps apply at all steps (`units.py:63`).
   - Required test: removal is empty at every non-CNO step. At the CNT stage, removal is non-empty only where the related link's CNO is true.
5. **Exact acceptance invariants for E3.** For every (step, diameter):
   - (a) `removed_P = open_raw_P & OR(related CNO)` and `open_final_P | removed_P == open_raw_P`;
   - (b) the `any` union map is pixel-identical before and after dedup, because removed pixels are CNO pixels;
   - (c) unrelated open and all short/pair maps are byte-identical to raw;
   - (d) the raw `ca.parquet`, `ca_union.parquet` and allocated/unique columns (`pipeline.py:367-448`) stay raw. Dedup goes into separate tables, with central-window counts and the `[300,900)²` denominator.
   - Also check that the CNO map used for dedup is the E1 margin-0 map, even when the manifest `contact_margin_um>0`. `units.py:154,178-180` currently passes the manifest margin.

## X2 — PASS, with pins

- v2 L10/L12 keep auto-open out of scope, and the adapter emits empty `open_applicable_steps_by_layer` (`adapter.py@bf4e8c2:259-263`). That matches.
- **Pin 1 (E1):** `auto_open.py` must stay untouched. Add a regression test that auto-open output is identical to `aae492a` on a fixture with auto-open enabled. That would catch the `ys/xs` repurposing from X1.3.
  - E3/I1 must refuse to report dedup statistics when any `auto_open:` unit exists.
- **Pin 2 (P2):** an explicit `OpenPath` can still use `fallback="roi_boundary"` (`schema.py:80`), which reintroduces ROI-edge-as-terminal.
  - P2 must emit only explicit point/mask terminals with `fallback="error"`, and must reject roi_boundary before output.

## X3 — FAIL

1. **Provenance leak and index lock.**
   - particle-sim `_git_identity()` runs `git rev-parse HEAD` and `git status --porcelain` in the process cwd (`io/outputs.py:310-324`).
   - A `git archive` copy under extractor `outputs/` has no `.git`. From that cwd, git walks up to the **extractor** repo.
   - Result: the copy's run_manifest records the extractor HEAD with dirty=true. `git status` may also take `.git/index.lock` in the extractor while the P0/P1 editor is live.
   - With cwd = original, it records the original HEAD for copy code and may refresh the original index.
2. **The before/after check can itself write.**
   - Plain `git status` in the original can rewrite `.git/index` with refreshed stat data.
   - Pin: use `git -C <orig> --no-optional-locks status --porcelain=v1 -uall` and `rev-parse HEAD`.
3. **Recording the original `.venv` package path by importing** `particle_sim` with the original interpreter writes `__pycache__` into the original `src`, unless `PYTHONDONTWRITEBYTECODE=1`.
   - Pin: read `.venv/lib/python*/site-packages/_editable_impl_particle_sim.pth` instead. It currently contains `/Users/jonghyeonlee/git/particle-sim/src`.
4. **With the original .venv plus `PYTHONPATH=<copy>/src`, the original src is still on sys.path** (after the copy, through the `.pth`).
   - Precedence holds, but it must be asserted. Using the same environment, `python -c 'import particle_sim; print(particle_sim.__file__)'` must print a path under the copy. Fail otherwise.
5. **Pinned procedure.**
   - Create the copy:
     - `git -C orig archive aae492a | tar -x -C outputs/<new>`;
     - then `git init` plus a baseline commit **inside the copy**, recording the source SHA.
     - The copy then has its own `.git`: `_git_identity` resolves to the copy, and E-Task patches are `git -C copy format-patch`.
   - Every copy run sets `GIT_OPTIONAL_LOCKS=0`, `PYTHONDONTWRITEBYTECODE=1` and `GIT_CEILING_DIRECTORIES=<copy parent>`, and uses cwd = copy.
   - `-p no:cacheprovider` is already in `pyproject.toml:37` addopts.
   - Before and after each E Task:
     - check that original HEAD, porcelain status, the `.git/index` sha256 and the `.pth` content are identical;
     - check that `find <orig> -newer <stamp> -not -path '*/.git/objects/*'` is empty.

## P2/P3 contracts

- **Split into P2 (adapter/config: net_map, pairs, open paths, relations sidecar) and P3 (extractor `engine.py`/`schema.py` diagnostics, per v5 §5), with explicit file ownership each.** Serial after P0/P1.
- P3 acceptance: extraction outputs for the fixture must be byte-identical except for the new diagnostic fields. That covers raw/cut masks, TR40, periodic instance IDs, 100 holes and 25/unit×225 px.
- P2 acceptance, in addition to v2:
  - relation IDs are built by construction using the pinned X1.1 format;
  - `fallback="error"` (X2 pin 2);
  - net_map changes to the 11,879-pair baseline are itemized;
  - the same-raw-GAT TR sides and S/D are not auto-merged;
  - with no relation table and no open paths, the output is identical to the P0/P1 output.

## E1/E2/E3 contracts

- **E1** is bounded with these pins:
  - a separate full-hole field (X1.3);
  - CNO stamp `particle_footprint(grid, r, 0.0)` regardless of the manifest margin, with a test at `contact_margin_um=0.5`;
  - a new classification/rule string replaces `cno_full_cover`/`full_cover_any_hole` (`contact_not_open.py:20-24`);
  - an auto-open identity regression (X2 pin 1).
- **E2:** drop the "check whether `lands_after_layer` can express open-before-fill" item. B2 already decided it is unsupported (flat film).
  - Scope: the central-window crop/denominator plus a per-diameter support gate. For each of the 32 diameters, the gate is radius + margin + full-hole half-span + short reach ≤ 300 px. It must print that open connectivity is *not* certified by the gate.
- **E3:** implementable only after the X1 pins. It depends on P2 (sidecar relations and explicit open paths) and on E1 (margin-0 per-link maps). Use the invariants in X1.5.

## Dependency order

P0/P1 (live) → P2 → P3 (extractor, one editor)
  → E1 (after X3 is pinned; copy editing still counts as the one editor)
  → E2 → E3 (needs P2 + E1) → I1.

E1 unit work may run before P2, but only while no other editor is live. Apply the X3 fixes before any E dispatch. Apply the X1 fixes before the E3 contract is saved.
