# Layout electrode extractor

This package extracts electrode connectivity from binary layout layers using exact periodic
identity, stores a 2×2 unit image at the original pixel pitch, and provides a local review UI
for names and circuit anchors. It is a geometry workflow; generated synthetic values and the
particle-sim export do not establish physical process validity.

## Reproducible synthetic example

Python 3.11 or newer is required. From the repository root:

```sh
python -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/layout-electrode-extractor make-synthetic outputs/demo/input
.venv/bin/layout-electrode-extractor extract outputs/demo/input/manifest.json outputs/demo/extraction
.venv/bin/layout-electrode-extractor review outputs/demo/extraction --circuit examples/circuit.csv
```

The last command opens the local review page at `http://127.0.0.1:8765`. Select TRs and
electrodes, enter names and optional circuit links, then save annotations in the UI. In another
terminal, or after stopping the review server, export the reviewed folders:

```sh
.venv/bin/layout-electrode-extractor export-reviewed outputs/demo/extraction outputs/demo/reviewed --circuit examples/circuit.csv
```

The generator writes a 600×600 px unit at 0.1 µm/px with approximately 20 px (2 µm) wires,
three GAT layers, ACTIVE, OACTIVE, two contact layers, and METAL1. Two distinct horizontal
GAT1 buses represent R and B, while a GAT2 bus represents G. Vertical channels make ten
orthogonal declared gate crossings per unit: 4 GAT1/ACTIVE, 2 GAT2/OACTIVE, and 4
GAT3/OACTIVE. The 2×2 extraction contains 40 TRs. The declared bottom-to-top physical
order is ACTIVE, GAT1, GAT2, OACTIVE, GAT3, CNT1, CNT2, METAL1; the conductor-only
`stack` omits CNT1 and CNT2.

CNT1 is one physical mask with 14 separate holes: 11 ACTIVE–METAL1 and 3
GAT2–METAL1. Nine ACTIVE holes are direct landings, one GAT2 hole at (40,200)
joins its bus directly to the left METAL1 trunk, and the other four holes form
two metal bridges. Bridge 1 has CNT1 A on ACTIVE (100,120), a continuous METAL1
trace, and CNT1 B on GAT2 (150,200). Bridge 2 similarly connects ACTIVE
(180,325) through METAL1 to GAT2 (215,200). Each bridge hole overlaps its own
declared conductor and METAL1 across its full 15×15 px area; no hole overlaps an
undeclared conductor. The GAT2 and ACTIVE raw masks do not overlap. CNT2 has 11
OACTIVE–METAL1 holes. The left and right METAL1 trunks separately span the unit
vertically; independent direct METAL1–ACTIVE and METAL1–OACTIVE examples remain.
TR intersections are removed from every layer and never conduct. The wire width
is approximately 20 px. These layer orders, endpoints, and geometry are fixture
assumptions, not measured process data.

The ignored `outputs/rgb-metal-bridge-20260924/` directory contains source masks,
the actual extraction, 600/1200 px raw composites, a layer sheet, an extracted
1200 px overlay, a labelled contact routing guide, and a machine-readable
verification record. Earlier review directories are preserved.

The adapter supports mixed CNT1 only with the explicit
[synthetic export config](examples/synthetic-particle-config.json). It partitions the one
physical CNT1 mask into endpoint-pair contact rows while retaining `hole_layer: CNT1`.
Without `--config`, the legacy one-pair-per-layer export remains available and rejects
mixed CNT1 before creating output. The config values are synthetic assumptions.
The [2026-09-24 linkage check](docs/orca/PARTICLE-SIM-LINK-CHECK-20260924.md) records a fresh
CLI extraction, the earlier legacy export result, an actual extracted-electrode mask preview,
and the remaining integration work.

Extraction preserves the 0.1 µm/px pitch and writes 1200×1200 px, or 120×120 µm. This has four
times the unit cell area (14,400 µm² versus 3,600 µm²); raw critical area and defect counts do
not follow a guaranteed exact fourfold scaling. Periodic identity is used while extracting the
layout. The exported particle-sim product is a finite 2×2 image: particle-sim does not apply
periodic boundaries. Its outer image edge can therefore affect results. A trace cut at an ROI
edge is still open at that finite boundary, and treating that edge as an open terminal can create
an artificial terminal; this fixture declares no automatic ROI-boundary terminals.

## Validate and run particle-sim

For the current mixed synthetic extraction, export and validate with:

```sh
.venv/bin/layout-electrode-extractor export-particle-sim \
  outputs/rgb-metal-bridge-20260924/extraction outputs/my-mixed-export \
  --config examples/synthetic-particle-config.json
/Users/jonghyeonlee/git/particle-sim/.venv/bin/particle-sim validate-input \
  --product-config outputs/my-mixed-export/product.yaml
```

The version-one JSON config requires an ordered physical process stack and ordered source
stages. Conductor rows have their own mask and patterned conductor material; hole rows have
their own physical mask and are converted to non-patterned inorganic simulator stack rows;
unmasked dielectric rows have no stage. The example emits 32 particle diameters, 1–30, 40,
and 50 µm. An explicit synthetic size list must be a strictly increasing subset of those
diameters. `adapter-provenance.json` records the selected list, stage semantics, and each
hole's raw, cut, and effective pixel counts. The CNT open stages use a flat-film approximation;
they establish API and geometry compatibility, not physical CNO validity. A measured config
with contacts is rejected because particle-sim cannot yet model the open CNT surface.

The config may also declare `net_map`, an object mapping **every** extracted electrode ID
from `manifest.json` to a confirmed circuit net ID. Several extracted IDs may map to one net;
their electrode masks and IDs stay separate. Without `net_map`, the manifest still uses
extracted IDs as provisional simulator `net_id` values, and `adapter-report.json` reports
`declared_circuit_nets: 0` and `provisional_extracted_nets` separately. These provisional
pairs are geometry candidates, not confirmed circuit shorts.

Optional `excluded_pairs` is a list of `{electrode_a, electrode_b, reason}` objects using
layer-specific exported electrode IDs (for example, `E0001_GAT1`). Every unordered electrode
pair gets a stable ID and an included or excluded status in
`adapter-provenance.json` → `circuit.pair_inventory`; same-net pairs receive the explicit
`same_declared_net` or `same_provisional_net` reason. Different-net exclusions require a
nonblank reason and are also emitted in the simulator manifest. Omitted exclusions mean all
different-net pairs remain included.

Explicit `open_paths` require a complete `net_map`. Each entry has `path_id`, `electrode`,
`circuit_net_id`, `circuit_connection_id`, two distinct `terminal_a_yx_px` and
`terminal_b_yx_px` coordinates on the same finite electrode mask, and a nonempty
`applicable_particle_source_steps` list. The coordinates are `[y, x]` in the 1200×1200
export. The adapter checks both terminals and their finite-mask connection, and emits
`fallback: error`. It never derives terminals from ROI edges or enables auto-open;
`open_applicable_steps_by_layer` stays empty. A circuit path spanning disconnected finite
mask pieces is unsupported by this explicit terminal contract.

Optional `cno_open_relations` entries are `{cno_link_id, open_path_id,
circuit_connection_id}`. `cno_link_id` must match an exact `cno:<contact_id>:<lower_electrode>__<upper_electrode>`
link listed on a contact hole in the provenance sidecar; the declared circuit connection,
net, and applicable source steps must agree. These relations are validated and stored only
in the sidecar because the current simulator manifest has no relationship field. No relation
is inferred from equal net IDs. With no explicit path or relation, the report states
`unsupported_unconfigured_no_explicit_terminals`.

`adapter-provenance.json` also records all-layer raw/cut/TR pixel counts, each configured
source stage's raw and cut mask counts, and observed raw conductor overlaps. Raw overlaps
are geometry observations and do not establish a process short. The full cut CNT hole count
is preserved for downstream CNO thresholds; effective endpoint overlap is recorded separately.
`physical_hole_diagnostics` has one row per physical raw CNT/VIA component and 2×2 tile,
keyed by `hole_layer`, `raw_component`, `seed`, `tile_xy`, and declared endpoints. Each row
gives raw, cut, TR-removed, and effective pixels; raw and cut enclosure counts and fractions
for both endpoints; and raw and cut intersections with every other conductor, including
zero counts. The CNO denominator is the **full cut hole**, not the effective overlap.
Current configured export requires raw=cut so a TR-hit hole cannot silently shrink that
denominator. It rejects `hole_in_tr` and `hole_through_intermediate_conductor` with the
component, seed, pair, and offending layer in the error before publishing any output.
These are export diagnostics; `validate-input` does not establish that the unmodified
simulator implements the 50% full-hole CNO rule. The isolated simulator candidate below
implements and tests that rule.
An undeclared conductor outside the endpoint stack interval is recorded as
`undeclared_conductor_raw_intersection`; it is an observation, not a fabricated short.
`mask_diagnostics.metal_over_tr` separately records raw metal components crossing TR and
allows them because the all-layer cut removes the intersection. Legacy export records hole
diagnostic codes, but its compatibility contract is narrower than the original permissive
path: 4-connected extractions with complete `contact_holes` provenance validate, while
8-connected CNT/VIA masks that merge diagonal-only, distinct 4-connected holes are rejected.
The error reports the layer, the diagonal pixel pair, and both 4-connected component labels
within the merged 8-connected component. Older extraction folders without `contact_holes`
provenance are also rejected. For hole provenance, every explicit seed must match its raw
4-connected component and belong to the declared contact rule's holes. A missing cut-row seed
is a manifest error. In both legacy and configured modes, `seed: null` is allowed only when
the row's layer has exactly one contact rule and that rule has no explicit `holes` list.
Multi-rule layers and rules with an explicit `holes` list require a matching seed. See the
[independent P0 re-review](docs/orca/P0-OPUS-REREVIEW-20260925.md).

For a legacy one-pair-per-layer extraction, omit `--config` and validate its schema 2.0
manifest with:

```sh
/Users/jonghyeonlee/git/particle-sim/.venv/bin/particle-sim validate-input \
  --product-config PATH/TO/LEGACY/particle-sim/product.yaml
```

The adapter writes raw repeated conductor masks for topography and passes TR-cut CNT/VIA masks
with source extraction provenance. Per-layer masks from one extracted electrode retain one
shared `net_id`: the declared circuit net when mapped, or its provisional extracted ID.
A finite contact is particle-sim compatible only
when it touches exactly one lower and one upper electrode of the same net; unsupported contact
components are listed in `adapter-provenance.json` and validation may reject them. The adapter
classifies every unordered different-net electrode pair: same-layer pairs are `lateral_short`,
and cross-layer pairs are `vertical_short`. No pairs are silently omitted. This can create a
large pair set; select a separately reviewed, explicitly excluded pair subset for bounded smoke
runs, and do not interpret such a smoke as validation of all pairs or of physical failure rates.

Adapter stack placement uses semantic `role` values, not layer IDs, so names such as `ACT_A`,
`OACT_A`, and `MTL_TOP` work. The assumed ILD rows are placed before the OACTIVE role and the
first METAL- or CONDUCTOR-role layer above it, while each contact marker is placed immediately
before its declared upper endpoint. Legacy export places its particle source step after the
last conductor; configured export uses explicit ordered stages on mask-bearing layers.
If ACTIVE/OACTIVE roles make assumed dielectric placement ambiguous, or a contact's endpoints
cannot be placed in source-stack order, export raises a `ManifestError` before creating output.
These assumed dielectric locations and thicknesses remain illustrative process settings, not
inferred physical measurements.

## Current particle-sim integration candidate

The [latest integration report](docs/orca/I1-INTEGRATION-REPORT-20260924.md) records a fresh
1200×1200 extraction: 40 TRs, 100 CNT holes on two physical masks, 101 extracted
electrodes, 155 exported electrode/layer masks, and 101 synthetic identity nets. Inspect the
[source overlay](outputs/v5-integration-20260924/i1-latest/images/source-overlay-1200.png),
[extracted overlay](outputs/v5-integration-20260924/i1-latest/images/extracted-overlay-1200.png),
and [actual electrode mask sheet](outputs/v5-integration-20260924/i1-latest/images/actual-extracted-electrode-mask-sheet.png).
The exact [product manifest](outputs/v5-integration-20260924/i1-latest/particle-sim-e3/product.yaml),
[per-hole provenance](outputs/v5-integration-20260924/i1-latest/particle-sim-e3/adapter-provenance.json),
and [verification record](outputs/v5-integration-20260924/i1-latest/verification.json)
are preserved with the images. The extraction code is at `6893fe6`; the isolated
particle-sim candidate is at `3bedd08`. The latter passed 352 copy tests and an
[independent Opus 5.5 review](docs/orca/CNO-SPARSE-OPUS-REVIEW-20260925.md).

The single [cumulative simulator patch](outputs/v5-integration-20260924/particle-sim-v5-cumulative-aae492a-to-3bedd08.patch)
contains E1–E3 and the exact integer CNO performance fix, from the original simulator
tree `aae492a` to copy commit `3bedd08`. Its SHA-256 is
`14b5f6701fb54365905e21d847a1005df8a8f8c722a082adf0d1daf342e97bb4`.
The two baseline Git trees are identical; the following read-only preflight passed on the
original checkout:

```sh
GIT_OPTIONAL_LOCKS=0 git -C /Users/jonghyeonlee/git/particle-sim apply --check \
  /Users/jonghyeonlee/git/layout-electrode-extractor/outputs/v5-integration-20260924/particle-sim-v5-cumulative-aae492a-to-3bedd08.patch
```

The original particle-sim checkout has **not** been patched. After reviewing the exact
patch and resolving the [remaining adapter and derived-output advisories](docs/orca/FINAL-OPUS-CODE-REVIEW-20260925.md),
an operator can apply it with `git -C /Users/jonghyeonlee/git/particle-sim apply <patch-path>`.
Then verify from that repository with `.venv/bin/python -m pytest -q tests`,
`.venv/bin/ruff check src tests`, and `.venv/bin/particle-sim validate-input
--product-config <absolute-path-to-product.yaml>` using the manifest linked above.

The [sparse CNO benchmark](outputs/v5-integration-20260924/cno-sparse-bench/REPORT.md)
measures three real CNT1 links at 1, 30, 40 and 50 µm and all 32 sizes on one
225-pixel hole. The [refreshed bounded geometry result](outputs/v5-integration-20260924/i1-latest/e3-sparse-geometry-probe/geometry-probe.json)
and [candidate provenance](outputs/v5-integration-20260924/i1-latest/e3-sparse-geometry-probe/provenance.json)
record 12 actual short maps and 12 actual CNO maps from the latest export, with a
synthetic open map at 1 µm. It ran in 6.81 seconds with 844 MB maximum RSS. That
synthetic open map is not an actual open-kernel result. General circuit-open behaviour,
the full pair-by-size sweep, and fabrication physics are unverified; the central-window
audit explicitly marks nonlocal open connectivity unsupported. Process thicknesses,
insulating materials and particle occurrence weights still require measured inputs.

## Commands and outputs

```sh
.venv/bin/layout-electrode-extractor --help
.venv/bin/pytest
.venv/bin/ruff check .
```

`outputs/`, virtual environments, caches, and build artifacts are ignored. Keep the generator
and example inputs under version control; do not commit generated masks or simulation results.
