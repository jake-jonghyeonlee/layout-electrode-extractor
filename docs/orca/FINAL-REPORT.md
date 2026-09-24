# First local release report

## 2026-09-24 metal-bridge fixture update

The follow-up [particle-sim linkage check](PARTICLE-SIM-LINK-CHECK-20260924.md) reran the current
fixture CLI and documented the mixed-CNT1 export blocker, actual extracted-electrode mask
preview, and a separate legacy positive control validated by particle-sim. It did not change
the adapter or particle-sim.

The later fixture candidate `79a4d68` in existing Orca Run `run_5463d205f39d` implements two separate ACTIVE→CNT1→METAL1→CNT1→GAT2 paths. It removes direct ACTIVE/GAT2 contact holes and raw overlap. `physical_stack` records the synthetic bottom-to-top order `ACTIVE,GAT1,GAT2,OACTIVE,GAT3,CNT1,CNT2,METAL1`; the legacy conductor-only `stack` remains its projection. CNT1 has ACTIVE/METAL1 or GAT2/METAL1 endpoints by hole; CNT2 has OACTIVE/METAL1 endpoints. Existing manifests remain compatible.

The new ignored artifact set is `outputs/rgb-metal-bridge-20260924/`: `images/contact-routing-guide.png`, `images/extracted-overlay-1200.png`, `images/raw-composite-1200.png`, `images/raw-layer-sheet.png`, plus `verification.json`, source masks, extraction, and assumptions. It retains R/G/B horizontal GAT1/GAT2/GAT1 buses, extracted full-height METAL1 trunks, 10 TR/unit (40 in 2×2), all-layer cuts, 25 valid contact holes/unit across exactly two CNT masks, 20 px wires, and 0.1 µm/px 600→1200 output. Tests and verification check distinct contact components, exact graph-edge provenance, continuous cut metal between bridge holes, contact enclosure and undeclared conductor overlap, and periodic seams.

Coordinator validation on exact product candidate: 53 pytest passed, Ruff passed for tracked code and the ignored renderer, fresh generation/extraction matched saved masks and provenance, and images were inspected. Independent Claude Sonnet high review of `79a4d68` gave PASS and reproduced the key checks. Its low note: the first bridge is electrically parallel to an existing pad/trunk/direct-GAT route; the second is partition-essential. Both are real metal bridges with two distinct declared CNT1 edges. Synthetic layer order and hole geometry do not establish fabrication feasibility. The particle-sim adapter explicitly rejects this mixed-CNT1 topology before output; no physical simulation or remote publication was performed. All three saved Tasks settled, their workers were released, deliveries acknowledged, and no reclaimable worker remained. See [CHECKPOINT.md](CHECKPOINT.md) for lifecycle IDs.

## Result

The first local release is implemented and validated on `main`. The product candidate is
`6b8bd682f9d1dfaf4df4d1e84e9027c09c016b04`, built from base
`439372f5897ffcb9175a0d330f6990d12ff1d0b7`. Independent Claude Sonnet high review gave an
unconditional PASS bound to that exact product SHA in [REVIEW.md](REVIEW.md). No remote publication
was performed. This report and the checkpoint are documentation commits after the reviewed
product SHA; they do not change product code.

Orca Run `run_3cf905a17b81` was owned by coordinator terminal
`term_2b2539fe-3275-42de-8d69-008f8559c7d7`. All eight saved Tasks completed. Every settled
worker received an Orca release decision and its delivery was acknowledged. The final
`worker-list --terminal-state reclaimable` query returned zero workers. Explicit terminals are
retained as external resources by Orca; none is an active editor or reviewer Dispatch.

| Task | Saved Task ID | Result |
| --- | --- | --- |
| T1 exact periodic extraction | `task_b92fb0d783ae` | `723efc5`, accepted |
| T2 review UI, names, circuit | `task_64d014d8fc4c` | `153f8e2`, accepted |
| T3 synthetic and particle-sim adapter | `task_4a52361c281a` | `1b96df6`, accepted |
| T4 independent review | `task_693c45297d8e` | Findings recorded; no PASS |
| T5 role/contact adapter correction | `task_81b3de404c06` | `23f7196`, accepted |
| T6 independent re-review | `task_904c4294584e` | Narrower Finding 2 recorded; no PASS |
| T7 CONDUCTOR-role correction | `task_bc341f6eee99` | `6b8bd68`, accepted |
| T8 independent final review | `task_dfe47171b5f3` | Unconditional PASS on `6b8bd68` |

The review startup failures remain in Orca history: T4 `ctx_44bee5c8742b` stopped at workspace
trust and was fenced after positive terminal evidence; T4 `ctx_1da55f0d22ba` and T6
`ctx_96cf7be3dfa2` failed at `agent_readiness`/identity change without materialized resources.
Fresh explicit Claude terminals successfully completed T4, T6, and T8. No failed attempt was
erased or treated as a product review PASS.

## Delivered behavior

- A strict manifest and installable CLI extract all declared layers after removing the TR union,
  including contact layers. Exact periodic connectivity preserves component and instance identity
  across the 2D lattice. It does not use finite halo stabilization as a correctness argument.
- Extraction writes 2×2 images at the unchanged 0.1 µm/px pitch. The supplied 600×600 synthetic
  unit produces 1200×1200 images with approximately 20 px (2 µm) wires, two GAT layers, ACTIVE,
  OACTIVE, two CNT layers, and METAL1.
- The local review UI supports electrode/TR selection, naming, saved annotations, circuit links,
  and named-mask export. JSON/CSV circuit tables support G/S/D TFT devices with optional B, so a
  body connection is not invented for a three-terminal TFT; they also support four-terminal MOS
  devices. There is no direct SPICE import. A supplied schematic image is a visual reference for
  human-confirmed connectivity; the UI does not infer a wire graph or run OCR on it.
- The particle-sim adapter exports schema 2.0 input, explicit pair classifications, stack rows,
  contact provenance, and per-layer masks. Assumed dielectric placement uses declared roles and
  treats METAL and CONDUCTOR as valid upper conductors. Unsupported or ambiguous stacks raise
  `ManifestError` before output is created.

## Verification on the final product SHA

Coordinator reran `.venv/bin/pytest -q` (26 passed), `.venv/bin/ruff check .` (passed),
`.venv/bin/ruff format --check src tests` (14 files already formatted), and
`node --check src/layout_electrode_extractor/static/app.js` (passed). The independent reviewer
reran the tests and reproduced both the corrected CONDUCTOR-role dielectric placement and the
explicit diagnostic when no upper METAL/CONDUCTOR role exists.

Coordinator independently ran the actual read-only sibling particle-sim `validate-input` CLI
against these Git-ignored final outputs:

| Product manifest | Size and pitch | Masks | Pairs | Result |
| --- | --- | ---: | ---: | --- |
| `outputs/task-final-default/particle-sim/product.yaml` | 1200×1200, 0.1 µm/px | 98 | 4,743 | `ok`, zero unresolved |
| `outputs/task-final-renamed/particle-sim/product.yaml` | 1200×1200, 0.1 µm/px | 120 | 7,130 | `ok`, zero unresolved |
| `outputs/task-final-conductor/particle-sim/product.yaml` | 1200×1200, 0.1 µm/px | 98 | 4,743 | `ok`, zero unresolved |

The bounded representative particle-sim run is in `outputs/t3-final/smoke-run-final`: one pair
was simulated, with the other 4,742 pairs explicitly excluded in that smoke manifest. It
demonstrates execution only for the selected pair.

The source chat used Aside Playwright on candidate `153f8e2`; its Git-ignored
`outputs/browser-smoke.json` records 1200×1200 rendering, E00001 selection, saving
`Browser_Gate`, persistence after reload, GAT1 switching, TR00001 selection, saving
`Browser_T1`, the G/S/D form with optional B, and named export paths in
`outputs/t1-smoke/extracted-reviewed`. A separate browser visual check of the final 2 µm
synthetic fixture rendered its repeated bends, branches, and loops with 88 electrode and 32 TR
instances; screenshot: `outputs/layout-review-final.png`. The first browser smoke used the
earlier thin-wire fixture; the final fixture check was visual only.

## Run locally

Follow [README.md](../../README.md) for environment setup, generation, extraction, reviewed
export, and particle-sim commands. To inspect the already generated final fixture:

```sh
.venv/bin/layout-electrode-extractor review outputs/t3-final/extraction --port 18876
```

Open `http://127.0.0.1:18876/`. This is a restart command, not a background release server.
The browser check used temporary port 18769 because another process occupied 18765.

## Limits

The synthetic circuit, stack thicknesses, dielectric properties, and particle settings are
illustrative assumptions. particle-sim receives a finite 2×2 image and does not apply periodic
boundary conditions; its outer edge can affect simulated behavior. Pair counts and critical
area do not imply a fourfold physical failure-rate scaling. Only a one-pair bounded simulation
was run, while all emitted pairs passed input validation. Named review exports depend on user
annotations. A whole-repository `ruff format --check .` flags a Python code fence in the
reviewer-owned `docs/orca/REVIEW.md`; source and test formatting checks pass.
