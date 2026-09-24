# P2 adapter circuit declarations and P3 adapter diagnostics

Candidate baseline: `main` at `7d2d8ee`. All generated files below are under ignored
`outputs/p2-check-20260924/`. The original `/Users/jonghyeonlee/git/particle-sim`
checkout was used read-only for `validate-input`; no simulation or physical CNO result
is claimed.

## Result

The optional complete `net_map` separates confirmed circuit net IDs from extracted
electrode IDs, including many-to-one mapping, while retaining every physical electrode
mask. The sidecar classifies every unordered electrode pair with a stable ID and a
reason for every exclusion; the simulator manifest includes supported different-net
included/excluded pairs. Explicit point-terminal open paths require a mapped circuit
net, circuit connection ID, source steps, and two distinct connected points on the
finite electrode mask. The manifest uses `fallback: error` and empty auto-open step
lists. CNO/open relationships use exact simulator link unit IDs in the sidecar and
are checked for valid path, connection, net, and shared source step. Raw/cut/effective
contact-hole counts remain distinct. Adapter diagnostics record all-layer TR cuts,
masked source-stage counts, and raw intermediate conductor overlaps as observations
only. Engine/schema P3 work remains a separate serialized Task per coordinator follow-up.

| Case | Electrode rows | Net IDs | Holes | Contact rows | Raw conductor masks | Included pairs | Explicit exclusions | Open paths | Sizes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Latest unconfigured circuit | 155 | 101 provisional | 100 | 3 | 6 | 11,879 | 0 | 0 | 32 |
| Latest mapped, one many-to-one net and one CNO/open relation | 155 | 100 declared | 100 | 3 | 6 | 11,878 | 0 | 1 | 32 |
| Latest mapped with one explicit pair exclusion | 155 | 100 declared | 100 | 3 | 6 | 11,877 | 1 | 1 | 32 |
| Legacy one-pair-per-CNT-layer | 166 | 110 provisional | 80 | 2 | 6 | 13,639 | 0 | 0 | 1 |

All latest cases have 11,935 inventory pairs (`155 choose 2`), eight all-layer TR
diagnostic rows, 40 extracted TR masks, 100 full CNT holes of 225 raw and 225 cut
pixels each, three configured source stages, and seven observed raw conductor-layer
overlap pairs. The mapped relation link occurs in the original simulator's
`failure_units` list. The latest output is 1200×1200 at 0.1 µm/px; the original
synthetic input is 600×600.

## Validation

- `.venv/bin/pytest -q`: 97 passed. Includes complete/unknown/unsafe net map,
  many-to-one mapping, full pair partition, explicit exclusion, open terminal and
  relationship validation, bad source steps, and no auto-open.
- `.venv/bin/ruff check .`: passed.
- `.venv/bin/ruff format --check` on changed Python files: passed. Existing unrelated
  formatting differences remain in `engine.py` and `test_contact_holes.py`.
- `PYTHONDONTWRITEBYTECODE=1 /Users/jonghyeonlee/git/particle-sim/.venv/bin/particle-sim
  validate-input --product-config <generated>/product.yaml`: passed for mapped,
  mapped-with-exclusion, and legacy exports. Results are
  `mapped-validate-final.json`, `mapped-exclusion-validate.json`, and
  `legacy-validate-final.json` in the ignored output folder. All report
  `status: ok`, `unresolved_electrode_pairs: 0`, and shape 1200×1200.

The first two original simulator validation invocations preceded the coordinator's
`PYTHONDONTWRITEBYTECODE=1` instruction and did not set that variable. Subsequent
invocations did. No recent source-tree `.pyc` files were observed; ignored venv
cache writes cannot be ruled out. The original checkout remained at
`aae492a6728116e8d584b657dd91b7934e4bff18` with only its pre-existing
untracked `docs/layout-electrode-extraction-plan.md` in `git --no-optional-locks
status --short` after validation. No original-repository cleanup or edits were made.
