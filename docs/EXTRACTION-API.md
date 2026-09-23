# Extraction engine contract (release 0.1)

Install with `python -m pip install -e '.[dev]'`. Run with
`layout-electrode-extractor extract input.json outputs/run-1` or call
`layout_electrode_extractor.extract(manifest_path, output_dir)`.
The output directory must not already exist. The function returns the same object
it writes to `manifest.json` and raises `ManifestError` or `ResourceError` for
invalid input or resource limits. CLI errors exit with status 2.

## Input manifest

```json
{
  "schema_version": 1,
  "pixel_size_um": 0.1,
  "origin_um": [0.0, 0.0],
  "connectivity": 4,
  "layers": [
    {"id": "GAT1", "role": "GAT", "path": "GAT1.png"},
    {"id": "ACTIVE", "role": "ACTIVE", "path": "ACTIVE.png"},
    {"id": "METAL1", "role": "METAL", "path": "METAL1.png"},
    {"id": "CNT1", "role": "CNT", "path": "CNT1.png"}
  ],
  "stack": ["GAT1", "ACTIVE", "METAL1"],
  "physical_stack": ["GAT1", "ACTIVE", "CNT1", "METAL1"],
  "tr_pairs": [{"gat": "GAT1", "channel": "ACTIVE"}],
  "contacts": [{"layer": "CNT1", "lower": "ACTIVE", "upper": "METAL1"}]
}
```

`layers` lists all input images, including `OTHER` layers. Every conductor
(`GAT`, `ACTIVE`, `OACTIVE`, `METAL`, `CONDUCTOR`) appears once in `stack`, in
height order. Every `CNT` or `VIA` layer has contact rules whose lower and upper
IDs are conductors in the stack, in that order.

`physical_stack` is optional. When present, it lists each conductor and each
`CNT`/`VIA` layer ID exactly once, from bottom to top; `OTHER` layers are excluded.
Removing the `CNT`/`VIA` IDs from it must reproduce `stack` exactly. Each
contact rule's `lower` conductor must precede its physical hole layer, and its
`upper` conductor must follow that layer. The endpoints need not be adjacent to
the hole in the list. This field records declared layer order only: it does not
infer contact endpoints, process thickness, or other fabrication properties.
Without it, the existing conductor-only `stack` and contact validation apply.

A legacy layer has one rule without `holes`; it applies to every hole in that
layer. To use more than one endpoint pair on one physical layer, every rule must have a
non-empty `holes` list of `[x, y]` integer pixel seeds. For example:

```json
"contacts": [
  {"layer": "CNT", "lower": "ACTIVE", "upper": "METAL1", "holes": [[12, 20]]},
  {"layer": "CNT", "lower": "OACTIVE", "upper": "METAL1", "holes": [[45, 20]]}
]
```

Each seed must be inside a raw hole component in the specified physical layer.
Every within-unit raw component requires exactly one seed, even if that seed is
subsequently removed by a TR cut; duplicate seeds on one component and
unassigned components are errors. Thus, two fragments that join only across a
periodic boundary each need a seed. All cut fragments of a raw component inherit
its rule. Components joined across a periodic boundary must declare the same
endpoint pair. An
empty raw layer is valid with its single legacy rule; seeded rules require at
least one actual raw hole. A TR pair names a `GAT` and
an `ACTIVE` or `OACTIVE` layer. At least one TR pair is required; pairs may
produce empty intersections. Overlapping intersections from separate source
pairs are rejected.

All PNGs must use a single grayscale or binary channel with **only 0 and 255**
values, aligned pixel dimensions, and the same pixel size and origin specified
for the unit. Paths are relative to the manifest directory and may not escape
it, including through symlinks. IDs are ASCII letters followed by letters,
digits, or underscores, up to 64 characters. Unknown fields, roles, or rules
fail validation. `connectivity` defaults to 4 and may be 8; it applies to
conductor, contact, and TR components and periodic boundary adjacency.
Contact endpoints require same-pixel overlap after the TR cut. There is no
morphology, resize, inferred contact endpoint, or diagonal overlap shortcut.

## Output

`manifest.json` is the stable index. Its `electrodes` array gives an extraction
ID and per-layer path, foreground pixel count, and SHA-256 of decoded 0/255
pixels. Every electrode PNG covers the full 2×2 output ROI, with 0.1 µm/px
unchanged if that was the input scale. A layer omitted from an electrode is
empty. All remaining conductor and contact pixels in the 2×2 ROI are partitioned
among electrode masks without overlap. `tr` lists a separate full-size PNG and
source pair for each TR instance. The total TR union is `tr_union.png`.

`raw_layers/*.png` preserves each original unit mask; `cut_layers/*.png`
records each unit mask after **the union of every TR intersection** was removed,
including gate, contact, and `OTHER` layers. `source_manifest_sha256` and
`raw_sha256_pixels` support stale annotation detection. The `origin_um`,
`pixel_size_um`, unit/output shapes and physical sizes explicitly describe the
2×2 grid. IDs are deterministic for identical inputs; display names and
annotation state belong in a separate file. `naming_complete` starts false.
If supplied, the validated `physical_stack` is copied to extraction `manifest.json`
and preserved in the reviewed export. Legacy manifests produce no
`physical_stack` output field.

`tr[].terminal_adjacency` records direct post-cut neighbors on each source
layer, including the split gate branches. Each record gives a layer, electrode
ID when that instance appears in the 2×2 ROI, graph component, coset, and
number of adjacent pixel edges. A null electrode ID denotes a neighbor beyond
the 2×2 output. The raw gate mask is available for pre-cut net evidence; these
neighbors are **not** an instruction to merge electrodes across a TR.

`connectivity.json` records each within-unit segment node and periodic edge's
tile displacement, plus the cycle subgroup generators for each graph component.
The electrode `graph_component` and `coset` identify a connected instance in
the infinite periodic lift. Equal local shape or base graph component alone
does not identify the same electrode. TR graph component numbers have their own
source-pair namespace.

`review/issues.json` repeats `manifest.json`'s issues. A contact touching more
than one independent lower or upper component is reported as
`multi_endpoint_contact`; a missing side as `missing_endpoint_contact`.
`periodic_contact_network` reports a hole mask with an unbounded periodic
component. Such cases remain extracted, but a strict one-to-one contact
adapter must reject them. `orphan_contact` reports a contact-only electrode.
`contact_holes.raw_components` records every assigned raw component, including
those completely removed by TR. `contact_holes.components` maps every surviving
unit cut component to its raw component, seed, rule index, and lower/upper
endpoints. `contact_holes.instances`
records each visible 2×2 periodic hole instance, its member cut components and
tiles, and the resolved rule indices and pair. Contact issues include the pair
and rule indices used for that instance. Review export carries this provenance.
The particle-sim adapter rejects multiple rules on one physical CNT/VIA layer
before creating output, because it cannot express mixed endpoint pairs with its
current one-mask-per-contact-layer contract.

## Exact periodic rule and limits

The engine labels components inside one unit and adds displacement-labelled
edges for boundary pixel adjacency and contact overlap. In each finite graph
component, tree paths provide a potential for every node; cycle displacements
generate a subgroup of Z². Two `(segment, tile_x, tile_y)` states belong to
one electrode exactly when their potential-adjusted tile difference lies in
that subgroup. This handles winding paths, infinite buses, contacts and TRs
crossing unit boundaries without a finite halo assumption. A 2×2 image is then
rendered from the four unit copies using those exact instance identities.

A unit may contain at most 2,000,000 pixels, all input layers together at most
20,000,000 layer-pixels, 32 layers, 100,000 graph nodes, 1,000,000 graph edges,
and 1 GB of decoded output mask bytes. Exceeding a limit is a hard error;
limits are resource protection, not an approximation of connectivity.
