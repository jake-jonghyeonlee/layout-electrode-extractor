# P3 physical-hole diagnostics

Task `task_a3efef16c211` in Run `run_5463d205f39d`; based on `e457737`
(P2 baseline `937a7db` plus settled E1 copy checkpoint). This change is confined to
the extractor adapter, contact export, tests, and README. No engine, schema, or
original `particle-sim` source files changed.

## Contract and policy

`adapter-provenance.json` now contains `physical_hole_diagnostics`: one row per
raw physical CNT/VIA component per 2×2 tile. Each row names the layer, raw
component, seed, tile, rule, and declared endpoints; raw/cut/TR-removed/effective
pixel counts; lower and upper raw/cut enclosure counts and fractions; and raw/cut
intersections with every other conductor (including zero counts). The physical
full **cut** hole is the planned CNO denominator. Configured export currently
requires raw=cut and rejects damaged holes before output publication.

- `hole_in_tr`: configured export rejects a partially or fully removed physical
  hole with its raw component, seed, and raw/cut/removed counts. Legacy export
  keeps its prior behavior and records the code on each affected diagnostic row.
- `hole_through_intermediate_conductor`: configured export rejects a raw hole
  intersecting a conductor strictly between its declared endpoints. The error
  names the intermediate layer and raw hit count. Legacy export records the code.
- `metal_over_tr`: raw metal component overlap with TR is recorded separately
  under `mask_diagnostics.metal_over_tr` and allowed when the all-layer cut is
  conserved. This is a geometry observation, not an etch or short assertion.
- Raw intersections with conductors outside the declared endpoint interval are
  recorded as `undeclared_conductor_raw_intersection` and allowed as geometry
  observations. They do not create contact graph edges or a fabricated short.

Malformed, duplicate, or missing hole provenance and invalid rule indices fail
with `ManifestError`. Configured export still stages output in a sibling folder
and publishes only after validation. Legacy one-pair-per-layer output and its
simulator manifest remain compatible.

## Evidence

The valid synthetic fixture has 600×600 input at 0.1 µm/px, 1200×1200 output,
40 TRs, two physical CNT masks, 100 exported hole instances, 155 electrode rows,
three contact rows, and 11,879 included electrode pairs. Every raw and cut hole
has 225 px; effective sizes are 120, 195, or 225 px. All 100 per-hole rows have
zero intermediate conductor raw hits. The regenerated extraction matches the
accepted `outputs/rgb-metal-bridge-20260924/extraction` baseline byte-for-byte
across 265 files (raw/cut/electrode/TR PNGs, `connectivity.json`, and `tr_union.png`);
electrode and TR IDs match. The comparison and counts are recorded in ignored
`outputs/p3-hole-diagnostics-20260924/p3-verification.json`.

Four source-mask counterexamples exercise partial `hole_in_tr`, full
`hole_in_tr`, `metal_over_tr`, and ACTIVE–METAL1 CNT1 through undeclared GAT2.
The first, second, and fourth fail configured export before the output directory
exists; metal-over-TR exports with a distinct sidecar code. A legacy split-hole
test confirms permissive export plus four coded per-tile rows.

Validation: `.venv/bin/pytest -q tests` passed (103 tests).
Ruff check and format checks passed. The original simulator's read-only
`validate-input` returned `status: ok`, shape 1200×1200, 155 electrodes,
11,879 pairs, and zero unresolved pairs for the valid configured export. This
validates input compatibility, not the planned 50% CNO physics.
