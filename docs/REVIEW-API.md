# Local review, annotations and circuit table

Install with `python -m pip install -e '.[dev]'`, then start the loopback UI:

```sh
layout-electrode-extractor review outputs/extracted \
  --circuit examples/circuit.json --schematic examples/schematic.png --port 8765
```

Open `http://127.0.0.1:8765/`. The server binds only to loopback and saves
`outputs/extracted/annotations.json`. The UI can switch layers, highlight every
mask belonging to one electrode, select a TR, show unnamed objects, edit names
and terminal links, and display the supplied schematic image beside the layout.
Images are served as individual PNG requests; they are not embedded as base64
stacks in the HTML. A circuit image is a visual reference, not a source of
automatically recovered wire connectivity. No arbitrary schematic-image graph
recognition or OCR is asserted by this release.

The UI's **Export named masks** button writes a sibling directory named
`<extraction>-reviewed`. The equivalent explicit command is:

```sh
layout-electrode-extractor export-reviewed outputs/extracted outputs/reviewed \
  --circuit examples/circuit.json --schematic examples/schematic.png
```

The same circuit and schematic paths must be supplied when reopening or
exporting a review that was saved with them. An export must target a new
directory outside the extraction. It copies raw and cut unit masks, TR union,
connectivity and issue files; named electrode and TR folders contain the full
2×2 masks. `manifest.json` updates their paths and names and includes
`review_provenance` with extraction, circuit, schematic and annotation hashes.
It also includes the circuit table and schematic image under `review/` when
provided. Unnamed folders use their internal ID and `naming_complete` stays
false. The original extraction remains intact.

## Circuit table

A JSON circuit table has the following form:

```json
{
  "schema_version": 1,
  "devices": [
    {
      "id": "M1",
      "channel_role": "ACTIVE",
      "terminals": {"G": "VDD", "S": "IN", "D": "OUT"}
    }
  ]
}
```

`channel_role` may be `ACTIVE`, `OACTIVE`, or omitted. Device IDs are ASCII
letters followed by letters, digits or underscores. Net IDs may also contain
`.`, `:`, `+` and `-`. Every device specifies `G`, `S` and `D`. A body net `B`
is optional for four-terminal MOS devices; a three-terminal display TFT stays
three-terminal and receives no fabricated body net. A CSV table has one row
per supplied terminal:

```csv
device,terminal,net,channel_role
M1,G,VDD,ACTIVE
M1,S,IN,ACTIVE
M1,D,OUT,ACTIVE
```

The CSV `channel_role` column may be omitted. Add a `B` row only when the
device explicitly has a body terminal. The importer validates all required
terminals and unique IDs; it does not infer a circuit from a diagram.
The review form shows `B` for a four-terminal device and leaves it absent for
a three-terminal TFT; a body link can also be added explicitly without an
imported table.

## Annotation contract

`ReviewProject(extraction, circuit_path=None, schematic_path=None)` loads a
review, and `save_annotations(data, revision)` atomically persists it. The
saved JSON has schema version 1, fingerprints for extraction/circuit/schematic,
`electrodes`, `tr`, and `terminal_links`. An electrode row is
`{"name":"VDD","net":"VDD"}`; a TR row is
`{"name":"T1","device_id":"M1"}`. `terminal_links[TR_ID][G|S|D]` (and
`[B]` only when explicitly present) contains
`{"net":"VDD","electrodes":["E00001","E00002"]}`. Multiple cut gate
segments may therefore map to one schematic net without being joined in the
extraction. Display names and internal IDs remain separate. Names cannot
contain path separators or control characters; normalized display-name and
folder-slug collisions are rejected.

The annotation document is bound to the exact extraction artifact fingerprint
and, when present, the circuit table and schematic image hashes. Changing any
of them marks the saved annotations stale and prevents automatic reuse. The
caller must move the old `annotations.json` aside or review a fresh extraction
before saving new correspondences. A revision hash prevents one open browser
from silently overwriting another's annotation edits.

`layout_electrode_extractor.circuit.suggest_matches(metadata, circuit, annotations)`
returns conservative name candidates. Anchored TR/device links propagate known
net possibilities through shared layout electrode IDs: all gate branches of
one anchored TR may map to its `G` net, while channel branches retain an
unordered `S`/`D` choice until a person resolves orientation. Candidate devices
are filtered by role and these net constraints. A single candidate is still a
suggestion requiring confirmation; symmetric candidates remain ambiguous.
Conflicting anchors are reported. Body terminals and long-range schematic
relations require explicit human links.
