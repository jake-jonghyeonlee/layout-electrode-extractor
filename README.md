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

The adapter currently requires one endpoint pair per physical CNT/VIA mask, so
`export-particle-sim` rejects this mixed CNT1 example before creating output. The tests retain
a separate legacy one-pair-per-layer fixture to validate the adapter's supported path.
The [2026-09-24 linkage check](docs/orca/PARTICLE-SIM-LINK-CHECK-20260924.md) records a fresh
CLI extraction, the exact export failure, a separate particle-sim `validate-input` positive
control, an actual extracted-electrode mask preview, and the remaining integration work.

Extraction preserves the 0.1 µm/px pitch and writes 1200×1200 px, or 120×120 µm. This has four
times the unit cell area (14,400 µm² versus 3,600 µm²); raw critical area and defect counts do
not follow a guaranteed exact fourfold scaling. Periodic identity is used while extracting the
layout. The exported particle-sim product is a finite 2×2 image: particle-sim does not apply
periodic boundaries. Its outer image edge can therefore affect results. A trace cut at an ROI
edge is still open at that finite boundary, and treating that edge as an open terminal can create
an artificial terminal; this fixture declares no automatic ROI-boundary terminals.

## Validate and run particle-sim

Install or use the read-only particle-sim checkout separately. For a supported legacy
one-pair-per-layer export, validate its generated schema 2.0 manifest with:

```sh
/Users/jonghyeonlee/git/particle-sim/.venv/bin/particle-sim validate-input \
  --product-config PATH/TO/LEGACY/particle-sim/product.yaml
```

The adapter writes raw repeated conductor masks for topography and passes TR-cut CNT/VIA masks
with source extraction provenance. Each per-layer mask exported from one extracted electrode
uses that electrode ID as its shared `net_id`. A finite contact is particle-sim compatible only
when it touches exactly one lower and one upper electrode of the same net; unsupported contact
components are listed in `adapter-provenance.json` and validation may reject them. The adapter
classifies every unordered different-net electrode pair: same-layer pairs are `lateral_short`,
and cross-layer pairs are `vertical_short`. No pairs are silently omitted. This can create a
large pair set; select a separately reviewed, explicitly excluded pair subset for bounded smoke
runs, and do not interpret such a smoke as validation of all pairs or of physical failure rates.

Adapter stack placement uses semantic `role` values, not layer IDs, so names such as `ACT_A`,
`OACT_A`, and `MTL_TOP` work. The assumed ILD rows are placed before the OACTIVE role and the
first METAL- or CONDUCTOR-role layer above it, while each contact marker is placed immediately
before its declared upper endpoint. The particle source step lands after the last conductor in
the declared stack.
If ACTIVE/OACTIVE roles make assumed dielectric placement ambiguous, or a contact's endpoints
cannot be placed in source-stack order, export raises a `ManifestError` before creating output.
These assumed dielectric locations and thicknesses remain illustrative process settings, not
inferred physical measurements.

## Commands and outputs

```sh
.venv/bin/layout-electrode-extractor --help
.venv/bin/pytest
.venv/bin/ruff check .
```

`outputs/`, virtual environments, caches, and build artifacts are ignored. Keep the generator
and example inputs under version control; do not commit generated masks or simulation results.
