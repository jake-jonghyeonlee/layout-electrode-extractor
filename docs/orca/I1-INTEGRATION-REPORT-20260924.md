# I1 latest synthetic integration report

Run `run_5463d205f39d`, Task `task_8eb3ce28a954`. Root baseline `6893fe69c3b373727965411132b69edec2610f58`; original `particle-sim` remained at `aae492a6728116e8d584b657dd91b7934e4bff18`; the isolated copy remained at `9a7cc2b466146d17878422acc48c4d9905dea54e`.

## Result

A fresh run of the committed synthetic generator and extractor is in ignored `outputs/v5-integration-20260924/i1-latest/`. The source is a 600×600 unit at 0.1 µm/px; extraction and simulator export are 1200×1200 at the same pitch. The extraction has 40 TR masks, 101 global extracted electrodes, and the export has 155 layer/electrode rows, 101 identity-mapped nets, 100 hole instances, three contact rows, and 11,879 classified different-net pairs. The contact pair inventory contains all 11,935 unordered row pairs, with same-net pairs explicitly excluded and no unclassified or unresolved pairs.

The accepted current generator has **three** gate layers, `GAT1`, `GAT2`, and `GAT3`. It produces 16 `GAT1–ACTIVE`, 8 `GAT2–OACTIVE`, and 16 `GAT3–OACTIVE` TR masks across the 2×2 result, with ten TRs in each tile. The project-doc text that says two GAT layers is stale for this task; the coordinator confirmed to use the latest three-GAT generator and keep its source unchanged.

The assumed unit contains 14 `CNT1` holes and 11 `CNT2` holes. Over four tiles, the adapter exports 56 and 44 full cut-hole instances respectively. Every row is 225 raw and cut pixels, has zero TR-removed pixels, and has no diagnostic code. Mixed `CNT1` endpoint pairs remain separated into three contact rows (`ACTIVE–METAL1`, `GAT2–METAL1`, `OACTIVE–METAL1`). The explicit `net_map` maps each extracted ID to its own matching ID: it is a complete synthetic identity mapping, not a circuit-confirmed netlist.

Both bridge routes use separate ACTIVE and GAT2 CNT1 holes and a continuous METAL1 route. The fresh displacement-labelled connectivity graph records a four-edge, zero-displacement path for each bridge into `E00023`; the exported sidecar carries their individual hole provenance. The RGB bus IDs are R=`E00003`, G=`E00022`, B=`E00013`; the left and right METAL seam identities are `E00023`/`E00022` and `E00085`/`E00084`. The verification record and actual-mask sheet are freshly generated from this extraction.

## Particle-sim validation and E2 support

The final configured export is [`particle-sim-e3`](../../outputs/v5-integration-20260924/i1-latest/particle-sim-e3/). Original and isolated-copy `validate-input` both returned `status: ok`, 1200×1200, 0.1 µm/px, 155 electrodes, 11,879 pairs, and zero unresolved pairs. The copy invocation asserted that `particle_sim.__file__` resolved inside the ignored isolated copy before calling the CLI.

Support-only E2 ran on that exact final export. It wrote 96 support rows (32 diameters × three configured source stages), zero simulated unit maps, and zero union maps. The central region is `[300,900) × [300,900)`, 360,000 pixels or 3,600 µm². Radii for 1, 30, 40, and 50 µm are 5, 150, 200, and 250 px. All local geometric reaches are at most 257 px and pass the 300 px bound. E2 marks the 32 `SOURCE_CNT1_OPEN` rows unsupported because the explicit open path is nonlocal; all 32 rows at each other source stage pass. This support audit does not certify open connectivity or physical accuracy.

## Bounded geometry and E3 evidence

The reproducible [`run_e3_geometry_probe.py`](../../outputs/v5-integration-20260924/i1-latest/run_e3_geometry_probe.py) imports the isolated copy's simulator modules and uses the exact exported product and sidecar. At `SOURCE_CNT1_OPEN`, it evaluated three selected electrode pairs for 1, 30, 40, and 50 µm: `PAIR_7034347E163829BD` (`E00003_GAT1`/`E00023_GAT2`), `PAIR_E883582546374E43` (`E00056_ACTIVE`/`E00085_OACTIVE`), and `PAIR_3F743844FA34387B` (`E00022_METAL1`/`E00084_METAL1`). That is 12 actual short geometry maps. It also ran the actual CNO kernel for three selected CNT1 contact links at 1 µm; those maps had zero blocked centres. The selected-map central counts are included beside full-map counts in [`geometry-probe.json`](../../outputs/v5-integration-20260924/i1-latest/e3-geometry-probe/geometry-probe.json). The completed run took 3.31 seconds and peaked at 769,343,488 bytes RSS (`/usr/bin/time -l`). No all-pairs/all-sizes simulation ran.

The exact sidecar relation `OPEN_BRIDGE_E00023` ↔ `cno:CNT1_GAT2_METAL1:E00023_GAT2__E00023_METAL1` passed E3 relationship validation. The geometry probe uses a two-pixel synthetic open raw map because an actual open-kernel call on the long GAT2 bus did not fit the bounded resource envelope. Its actual 1 µm CNO map was empty, so the relation partition was raw=2, removed=0, final=2. A separate exact-sidecar E3 fixture puts one synthetic CNO pixel under that synthetic open map and verifies raw=2, removed=1, final=1. Both results are clearly distinguished in the probe JSON and logs; neither is a physical correctness claim.

The attempted actual open/CNO probe on the long bus was stopped after 231.62 seconds at about 20.99 GB maximum RSS (about 51.78 GB peak footprint). A later larger-diameter CNO attempt was stopped after 58.52 seconds at about 20.41 GB RSS. These runs exposed the cost of the current broad-radius connectivity/correlation kernels. Their partial ignored artifacts and sample traces are preserved under `e3-geometry-probe-aborted*` and `logs/`; no particle-sim source was changed. The final bounded probe excludes open-kernel maps and limits actual CNO maps to 1 µm. The E3 CLI sidecar relation check still ran against fresh raw maps without simulating pairs.

## Visual and validation artifacts

I visually inspected the fresh source overlay, extracted overlay, and actual per-electrode mask sheet. The sheet displays the extracted bridge electrode `E00023` and three distinct electrodes (`E00056`, `E00085`, `E00003`). Images: [source overlay](../../outputs/v5-integration-20260924/i1-latest/images/source-overlay-1200.png), [extracted overlay](../../outputs/v5-integration-20260924/i1-latest/images/extracted-overlay-1200.png), [actual extracted electrode masks](../../outputs/v5-integration-20260924/i1-latest/images/actual-extracted-electrode-mask-sheet.png). [`verification.json`](../../outputs/v5-integration-20260924/i1-latest/verification.json) records all-layer raw/cut TR conservation, TR distribution, physical-hole validity, bridge graph paths, and seam IDs.

Root validation passed: `.venv/bin/pytest -q` → 103 passed; `.venv/bin/ruff check src/layout_electrode_extractor tests` → all checks passed. Full JSON validation outputs, commands, and test logs are under [`logs/`](../../outputs/v5-integration-20260924/i1-latest/logs/).

The original repository remained at its original commit with only its pre-existing untracked `docs/layout-electrode-extraction-plan.md`; its Git index hash stayed `cc93792e3e008cd99a9626a6e85743b4e3395dd84a7573c2d2a6defccfbe4dd6`. The isolated copy stayed at `9a7cc2b466146d17878422acc48c4d9905dea54e` with a clean status. Copy runs used `GIT_OPTIONAL_LOCKS=0`, `PYTHONDONTWRITEBYTECODE=1`, `GIT_CEILING_DIRECTORIES=/Users/jonghyeonlee/git/layout-electrode-extractor/outputs/v5-integration-20260924`, `PYTHONPATH=/Users/jonghyeonlee/git/layout-electrode-extractor/outputs/v5-integration-20260924/particle-sim-copy/src`, and the copy as cwd. The Korean untracked final report and prior images were left untouched.

## Reproduction

From the extractor repository root:

```sh
.venv/bin/layout-electrode-extractor make-synthetic outputs/v5-integration-20260924/i1-latest/source
.venv/bin/layout-electrode-extractor extract \
  outputs/v5-integration-20260924/i1-latest/source/manifest.json \
  outputs/v5-integration-20260924/i1-latest/extraction
```

Build the complete identity mapping and the synthetic open path/CNO relation with the saved config script, then export and validate:

```sh
.venv/bin/python outputs/v5-integration-20260924/i1-latest/build_process_config.py
.venv/bin/layout-electrode-extractor export-particle-sim \
  outputs/v5-integration-20260924/i1-latest/extraction \
  outputs/v5-integration-20260924/i1-latest/particle-sim-e3 \
  --config outputs/v5-integration-20260924/i1-latest/process-config.json
PYTHONDONTWRITEBYTECODE=1 /Users/jonghyeonlee/git/particle-sim/.venv/bin/particle-sim validate-input \
  --product-config outputs/v5-integration-20260924/i1-latest/particle-sim-e3/product.yaml
```

For isolated-copy commands, change cwd to `outputs/v5-integration-20260924/particle-sim-copy` and set the four protected environment variables above. Invoke the original venv's Python with `-c`, assert that `particle_sim.__file__` equals `<copy>/src/particle_sim/__init__.py`, import `particle_sim.cli.main`, then call it with the same arguments as the logged `validate-input`, `analyze-central`, and `analyze-cno-open` commands. The actual selected geometry kernels are reproducible with:

```sh
# From the isolated copy cwd, with the protected environment above:
/usr/bin/time -l /Users/jonghyeonlee/git/particle-sim/.venv/bin/python \
  /Users/jonghyeonlee/git/layout-electrode-extractor/outputs/v5-integration-20260924/i1-latest/run_e3_geometry_probe.py
```

## Key SHA-256 values

| Artifact | SHA-256 |
|---|---|
| Source manifest | `f0d33a1d9c29bdc978e5c9d88eca10eb42260b616fc3d2ccddfc321491f5b671` |
| Extraction manifest | `8308f375fd859f2a226dba962569a736cfb5a6c148d874666b35442183cf1077` |
| Connectivity graph | `dca33fbaf6ba48f7e9bcfc7e6654b5bc20967238547de433283021f97adc8ce9` |
| Process config | `925a9f3bd151a5d419ec9b4d17894e5802977cfc92bb35d03a512663b3f4f489` |
| Final product manifest | `eda454fd9c8167dc57e363c06cf8d03f7a10459f43cc22f135c9775d37ed1cd2` |
| Final adapter provenance | `0f8973a132966447ee10c4154e10bb0b02aea494c6ecc7066da61c9655045211` |
| E2 support audit | `4d03200c57c49c45cb7c71ae71d73221418aeb1b5f233ae66499ba6919bcf2bb` |
| Bounded geometry probe | `da48cf668f3cfd7cf4eb43d085d2e91157fec7bd8ed4ad96438477beed2f1ef6` |
| E3 dedup manifest | `5dd6c0543bac86c8f011a63268b32277768fbc10e682f554547b3b9a47b71b49` |

`outputs/v5-integration-20260924/i1-latest/inventory.json` lists the fresh artifact files and their hashes.
