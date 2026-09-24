# Final independent implementation review — Claude Opus 5.5 high, 2026-09-25

- Run `run_5463d205f39d`, Task `task_a337cbfa1342`, Dispatch `ctx_02df87892eaf`.
- Reviewer: fresh `claude-opus-5-5` high session. Read-only; this report is the only file written in the repository.
- **Extractor candidate:** `6893fe69c3b373727965411132b69edec2610f58` (`6893fe6`). Product diff reviewed: `762a239..6893fe6` (P0/P1 `7d2d8ee`, P2 `36d7966`, P3 `b8eb3af`, test collection `6893fe6`). Engine, periodic, and schema modules are unchanged in that range.
- **Isolated copy candidate:** `outputs/v5-integration-20260924/particle-sim-copy` at `9a7cc2b466146d17878422acc48c4d9905dea54e` (`9a7cc2b`). Copy baseline `4f2a94c` is the archive of original `aae492a`. E1 `6e2ecfd`, E2 `d93e1a6`, E3 `9a7cc2b`. Patch files `e1/e2/e3-*.patch` sit beside the copy.
- Original `/Users/jonghyeonlee/git/particle-sim` at `aae492a` was not written. HEAD, porcelain status, `.git/index` SHA-256 and the venv `.pth` content were byte-identical before and after my copy test run. `find -newer` returned no paths outside `.git/objects`.
- I1 artifacts under `outputs/v5-integration-20260924/i1-latest/` were being generated at the same time. I did **not** use them as evidence. Following the coordinator's note, I also did not treat the E3 synthetic raw-map probe as evidence about the actual kernels.

## Verdict

**PASS for the exact candidates `6893fe6` (extractor) and `9a7cc2b` (isolated copy).** I found no blocking defect: no case where the code silently publishes a wrong electrode, contact, CNO/open or short result for input inside the contract. Every counterexample I built failed closed, with an explicit error, before a simulator manifest was published.

This PASS covers only these two commits. It does not cover any later change or the concurrent I1 artifacts. It says nothing about physical fabrication or process correctness: CNT source stages are still a flat-film approximation, stack values are assumed, and CNO/open accounting is a geometric rule. It also does not claim that a finite halo proves general periodic correctness.

The following advisory findings are not blocking. A2 and A1 should be resolved or documented before the E-stage patch is applied to the original particle-sim, or before the legacy behaviour is described as "unchanged".

## Evidence I ran myself

| Check | Result |
|---|---|
| Root `.venv/bin/pytest -q -p no:cacheprovider` at `6893fe6` | **103 passed** |
| Root `ruff check --no-cache src tests` | All checks passed |
| Copy `pytest tests/unit -q -p no:cacheprovider` (cwd = copy, `PYTHONPATH=<copy>/src`, `PYTHONDONTWRITEBYTECODE=1`, `GIT_OPTIONAL_LOCKS=0`, `GIT_CEILING_DIRECTORIES=<copy parent>`); asserted `particle_sim.__file__` is under the copy | **350 passed** |
| Copy `ruff check --no-cache src tests` | All checks passed |
| Randomized `Lattice` membership vs brute-force Z² closure (1500 generator sets, \|v\|≤4, window ±8) | 0 mismatches |
| Legacy (no `--config`), 4-connectivity fixture: HEAD vs `762a239` archive | `product.yaml` and all masks byte-identical; the sidecar only gains keys |
| Legacy, `connectivity=8`, one diagonal-only CNT1 pixel: HEAD vs `762a239` | HEAD rejects; baseline exported (A1) |
| E3 guard probe: 14 malformed-input mutations on the unit-test case | All 14 rejected with the specific error; 3 of them leave a partial output (A2) |
| E2 `analyze_central` support-only on `outputs/p2-check-20260924/mapped-product` | 96 rows; see the reach table below |
| Original particle-sim before/after fingerprint | Identical |

E2 reaches on the actual P2 mapped export, using the actual `legacy_iterations` and a hole half-span of 7 px:

| step | d (µm) | footprint | contact/short | legacy kernel | full cut hole | supported |
|---|---|---|---|---|---|---|
| SOURCE_CNT1_OPEN | 1 / 30 / 40 / 50 | 5 / 150 / 200 / 250 | same | 6 / 150 / 200 / 250 | 12 / 157 / 207 / 257 | false: `nonlocal_open_connectivity_not_certified` only (OPEN_1 applies) |
| SOURCE_CNT2_OPEN | same | same | same | same | same | true |
| SOURCE_AFTER_METAL1 | same | same | same | same | 5 / 150 / 200 / 250 | true |

The largest local reach is 257 px against the 300 px halo, so every one of the 32 bins passes locally. Open units are always reported as nonlocal and are never certified.

## Acceptance items reviewed

1. **Explicit process stack and masked source stages** (`export_config.py:41-199`). The validator checks the fields strictly. Conductor and hole rows need their own mask and `patterned=true`, and dielectric rows need `mask_layer=null`. The masked projection must equal `physical_stack`, and the conductor projection must equal `stack`. Each contact must satisfy lower < hole < upper in process order. Source stages must be in order, unique, and placed only after mask-bearing rows. Semantics must match the row kind, and only `flat` is accepted. In the synthetic profile, each CNT has exactly one approximation stage. The measured profile is rejected whenever contact rules exist, and the extraction schema requires a rule for every CNT/VIA layer, so a measured-profile CNT stage cannot be published. Particle sizes must be a strictly increasing subset of the 32 bins. `product_stack` emits hole rows as non-patterned inorganic films, and `layer_masks` stay **raw**. `mask_diagnostics` (`export_semantics.py:232-318`) records overlaps with earlier conductors for each stage, as observations only. OK.
2. **Mixed CNT1 split (100 holes, 155 masks) and legacy compatibility.** `prepare_contacts` (`contact_export.py:213-438`) checks that the TR union tiles 2×2 and that cut = raw & ~TR on every physical layer. It rejects any hole that touches TR or the unit edge. It checks the 4- vs 8-connectivity partition, and raw/cut provenance numbering and rule agreement. Each hole needs a graph edge to both endpoint layers and exactly one lower and one upper electrode of the same extracted instance, with a nonempty effective area. Row masks must not overlap, and their union must equal the tiled cut hole layer. Tests pin 155 electrodes, 101 provisional nets, 3 contact rows, 100 holes, 11,879 pairs and 6 raw `layer_masks`. Legacy output is byte-identical for 4-connectivity (probe above); see A1 for the regression.
3. **P3 hole-level raw/cut, intermediate conductor, TR and enclosure diagnostics** (`contact_export.py:66-210`). Each hole gets raw, cut, TR-removed and effective counts, lower/upper enclosure (raw/cut pixels and fractions), and intersections with every other conductor classified as `intermediate` or `undeclared`. In strict mode, `hole_in_tr` (partial or full) and `hole_through_intermediate_conductor` are raised before output. `metal_over_tr` is allowed as an observation. Tests cover rejection counterexamples for partial TR, full TR and a GAT2 intermediate, plus the allowed METAL-over-TR case. Gaps are listed in A6.
4. **E1: full TR-cut denominator, inclusive ≥50%, margin 0** (`contact_not_open.py:31-64`, `contacts.py:112-181`). The denominator is the whole 4-connected component of the contact-row mask (`cut_ys/cut_xs`), not the effective endpoint. The test is `2*covered >= len(ys)` with an inclusive disc (`distance <= r`), and `particle_footprint(..., 0.0)` ignores the manifest margin. `simulate_cno` is the only CNO path (`units.py:178`). Auto-open still uses the effective `ys/xs`. The extractor always emits full cut holes as contact-row masks, and configured mode guarantees raw = cut. The 49/50/51 and 112/113 threshold cases, brute-force comparison and auto-open byte-identity to `aae492a` are tested. OK; A4 notes a side effect.
5. **E2: 32 diameters, central [300,900)² support, nonlocal open limitation** (`central_window.py`). The module requires exactly 32 bins, a 1200² ROI and 0.1 µm/px. It rejects source stages after maskless layers. Reaches for footprint, contact margin, actual legacy kernel, short geometry and hole are measured per axis, which is the right metric for containment in an axis-aligned box. Open units are always marked `nonlocal_open_connectivity_not_certified`. Probability runs are marked unsupported. The code reads only the central slice, opens the source store read-only, and refuses output inside the run. The CNO hole reach is sound here because strict validation rejects ROI-edge holes, so any hole within reach of a central centre lies entirely inside the ROI. See A5.
6. **E3: sidecar link/path/connection provenance, raw/removed/final partition, unrelated open and short preservation, raw any-union identity, read-only source** (`cno_open_dedup.py`). Relations must use the exact particle-sim link unit ID; `export_semantics.py:178` and `contacts.py:49-50` produce the same format. A relation must reference a link present in the strict topology and an explicit path with `fallback=error` and explicit terminals. It must match the circuit connection ID, and both link electrodes and the path must share the declared net. At least one applicable step must overlap. There is no inference from net alone, and `auto_open:` units are refused. For each condition, `removed = raw & OR(CNO)` and `final = raw & ~OR(CNO)`, and `final|removed == raw` is asserted. Removal is zero on steps where the path or link does not apply. `raw ⊆ any` and `CNO ⊆ any` are checked, so the any-union stays pixel-identical by construction. Unrelated opens and all shorts are never written. The source Zarr is opened with `mode="r"`, and CA tables are only hashed. The run must be nominal (`random_seed is None`) and match the config hash. OK; see A2 and A3.
7. **Periodic instance/net identity.** `engine.py` and `periodic.py` are unchanged in this range. My randomized Lattice probe agrees with brute-force closure. The adapter copies per-instance electrode masks and never relabels finite 2×2 components. In `prepare_contacts`, endpoint identity comes from the instance index, and CNO links are keyed by instance electrode IDs. Independent tile copies therefore stay separate links, while one periodic instance (for example an infinite bus) owns every tile's holes in a single any-hole link, which is the adopted rule. Open-path terminal connectivity uses the finite 4-connected mask, the same as particle-sim's `label`.
8. **Copy import/provenance protections.** The copy has its own `.git` at `4f2a94c→9a7cc2b`, and `GIT_CEILING_DIRECTORIES` stops Git from walking up to the parent repository. With `PYTHONPATH` set, `particle_sim.__file__` resolves under the copy. The original fingerprint matched before and after my run. The copy is under the extractor's ignored `outputs/` and its working tree is clean.

## Advisory findings (non-blocking), most important first

**A2 — E3 leaves partial derived output when a late check fails (medium; fix before original application).**
- Where: `particle-sim-copy/src/particle_sim/validation/cno_open_dedup.py:186-232`. `output_dir.mkdir` and `zarr.open_group(..., "w-")` with zero-filled `open_final`/`removed` arrays run before the per-condition checks `_binary_map`, "raw any union omits an open pixel" and "… a CNO pixel".
- Counterexample: my probe with a non-binary value (2) in an open map, an any-union missing an open pixel, or a CNO pixel outside the any-union. Each raised `InputContractError`, but `derived/dedup_open.zarr` was left behind, zero-filled or partly filled, with no `dedup_manifest.json` or parquet. A consumer opening the Zarr would read "no removal / no final open" for conditions that were never computed.
- Fix: validate every map first, or write to a sibling staging directory and rename it into place, as the extractor's `export_particle_sim` does. At minimum, delete the output on failure.

**A1 — Legacy (no `--config`) export regresses for 8-connectivity extractions and older extraction folders (medium; document or relax).**
- Where: `contact_export.py:89-96`. `diagnose_physical_holes(..., strict=False)` relabels raw holes with 4-connectivity and raises `missing raw hole provenance` whatever the value of `strict`. `_validate_hole_rows` (`contact_export.py:40-43`) likewise raises when `contact_holes` is missing.
- Counterexample: the legacy fixture with `connectivity: 8` and one CNT1 pixel diagonal to a hole corner. At `762a239` the export succeeds (2 contacts, 166 electrodes). At `6893fe6` it fails with `ManifestError: missing raw hole provenance: CNT1 raw_component=10`. Extraction folders produced before `d9941c9`, which have no `contact_holes`, are also refused.
- Effect: this fails closed, so no wrong output is produced. It contradicts the checkpoint statement that legacy "remains permissive with diagnostic codes", and it blocks legacy mode on inputs it used to accept. Either record a diagnostic code in non-strict mode instead of raising, or document the narrowed legacy contract. (4-connectivity legacy output is unchanged, per the probe.)

**A3 — E3 malformed map/run guards have no unit tests (low).** The copy tests cover unknown or duplicate link/path, connection mismatch, no shared step, duplicate metadata and auto-open. None of the following is tested: non-binary map, any-union omission (open or CNO), output inside or non-empty, `random_seed` set, config-hash mismatch, missing `ca_union.parquet`, a sidecar that is not a mapping or not valid JSON, `net_status` not declared, link or path net mismatch, and `fallback≠error`. My probe confirmed all 14 are rejected correctly. They should be added to `tests/unit/test_cno_open_dedup.py` so they cannot regress.

**A4 — E1 changes ROI-edge hole behaviour beyond the CNO rule (low; document).** `contacts.py:115-125`. With strict loading (`validate-input`, `load_product_masks`), any contact hole that touches the ROI edge is now rejected; `aae492a` accepted such manifests. On non-strict paths (`geometry/transforms.py:144`, `pipeline.py:235`, used for overlay/CD scenarios), an edge-touching hole is now dropped and counted as `lost`. A link can then become `CONTACT_LOST`, which gives an all-zero failure map, where the baseline evaluated the hole. The auto-open byte-identity evidence covers only the fixed fixture. The extractor never emits edge holes in configured mode, so the current integration is unaffected. Document this as a deliberate compatibility change of the patch.

**A5 — The E2 hole reach uses the bounding-box half-span (info).** `central_window.py:67-81,112`. `r + half_span` bounds the reach for convex, near-symmetric holes (all fixture holes are 15×15 squares). For a nonconvex hole, such as a blob with a long tail, 50% coverage can leave far pixels up to `r + full_span` away. Correctness does not depend on this number today: it rests on strict ROI-edge hole rejection and r ≤ 250 < 300, leaving 43 px of slack. Using the full span would be conservative at no cost.

**A6 — Remaining P3 hole-level gaps (info).**
- Diagnostics emit four rows per hole (`contact_export.py:170-205`). The `tx/ty` loop does not use the tile, so the rows are copies of one measurement from the unit masks rather than independent per-tile measurements. This is valid only because configured mode enforces exact 2×2 tiling and raw = cut.
- Hole-to-hole overlap between CNT1 and CNT2 is not diagnosed.
- `metal_over_tr` covers only role `METAL`, not `CONDUCTOR`.
- Enclosure is recorded without a threshold. Only a nonempty effective area is enforced; the fixture's effective areas are 120, 195 and 225 px.

**A7 — Defense in depth for hole numbering (low).** `prepare_contacts` and `diagnose_physical_holes` assume the engine's `raw_component` numbering matches the exporter's 4-connected labels. That holds for engine output: both use scipy's raster order, and the partition check confirms it. The recorded `seed` is never re-verified (`labels[seed_y, seed_x] == raw_component`). In a hand-edited manifest, two holes whose rules are both geometrically valid could swap endpoint pairs without detection. A one-line seed check would close this.

**A8 — Race in atomic publish (low).** `particle_sim_adapter.py:258-260`. The code checks `output.exists()` and then calls `os.rename`. On POSIX, `rename` replaces an *empty* destination directory, so a concurrently created empty output directory would be silently replaced. Also, `output.parent.mkdir(parents=True)` (line 238) runs before `circuit_declarations` and `mask_diagnostics` validate, so a failure can leave newly created parent directories behind. The staging directory itself is always removed.

**A9 — Relation and sidecar binding (info).**
- `adapter-provenance.json` does not record the SHA-256 of `product.yaml`. E3 checks that IDs and nets agree, not that the files are the same, so a sidecar from another export with matching IDs would be accepted.
- Relations are authoritative declarations. Neither side checks that the open path's electrode geometrically carries the related link (for example, electrode ∈ {link lower, link upper}); this is intended by design.
- In the E3 bounded probe, `ca.parquet` and `ca_union.parquet` are the same placeholder bytes (both SHA `850ca59b…`), so that probe's "raw CA preserved" claim is weak. The unit test checks byte preservation directly.

**A10 — E2 vs extractor size subsets (info).** The extractor allows strict subsets of the 32 bins (`export_config.py:190-197`), for example `[1,30,40,50]`. E2 `analyze-central` requires exactly 32 (`central_window.py:40`), so it rejects subset exports. This fits the E2 contract; document it for users.

## Out of scope / not established

- Physical CNT open-before-fill topography, measured stack and material values, and real fab distributions.
- A full pair × size × step simulation.
- Actual-kernel nominal maps for the P2 fixture. I1 will provide that evidence and it is not part of this PASS.
- Circuit-open connectivity, which is nonlocal and is never certified by local reach.
