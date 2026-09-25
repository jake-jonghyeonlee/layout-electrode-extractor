# P0 A7 re-review (F1–F3): independent Opus review, 2026-09-25

- Reviewer: fresh Claude Code session, model `claude-opus-5-5`, launched as the high-effort
  independent reviewer for this Task. The session cannot observe its own effort setting, so
  the coordinator should confirm it from the terminal. This reviewer did not write or
  coordinate any of the reviewed changes.
- Run `run_5ebf21e5c7f7`, Task `task_a3bc212d1d1e`, Dispatch `ctx_87cdcd507bca`.
- Contract: the F1–F3 findings in `docs/orca/P0-OPUS-REVIEW-20260925.md`. The latest user
  decision is recorded in `README.md:150-155` and `docs/orca/CHECKPOINT.md:6`. In both
  legacy and configured modes, `seed: null` is allowed only when the row's layer has
  exactly one contact rule and that rule has no explicit `holes` list; every other null is
  rejected. Every explicit seed must match its raw component and belong to its declared
  rule's holes. A missing cut-row seed must raise `ManifestError`. I1 output must stay
  unchanged.
- This file is the only one written in the repository. Probes ran in the session
  scratchpad on copies of fixtures.

## Exact candidate

| Item | Value |
|---|---|
| Root product commit | `8ca5ff8b33ee023f229f49ebf382c18094fa4fd4`. Its diff from parent `425989a` touches only `src/layout_electrode_extractor/contact_export.py` and `tests/test_synthetic_adapter.py`. |
| HEAD at review | `b52e6ec`. `git diff --stat 8ca5ff8 HEAD` shows only `docs/orca/CHECKPOINT.md` (+1). The tree was clean before this report. |
| Isolated copy | `7213deb38c23aeac99628bbf6236a444b6b3440f`, clean `status --porcelain` (read with `GIT_OPTIONAL_LOCKS=0`) |
| Cumulative patch | SHA-256 `e715b36910ac57577d927496a067fab98584e6890d5d453101836c7f859936f4`. This equals the SHA-256 of `git diff 4f2a94c 7213deb` in the copy. |
| Original particle-sim | HEAD `aae492a6728116e8d584b657dd91b7934e4bff18`. Its only untracked file is `docs/layout-electrode-extraction-plan.md`, and the index SHA-256 is `cc93792e3e008cd99a9626a6e85743b4e3395dd84a7573c2d2a6defccfbe4dd6`. It was not modified. |

## Verdict

**A7 (F1, F2, F3) on exact root product `8ca5ff8`: PASS.**

- All three findings are fixed, and the fixes follow the recorded user decision.
- The I1 output and the legacy output are byte-identical to the accepted references.
- No blocking or actionable finding remains.
- The copy `7213deb` and the patch `e715b369…` are unchanged. Their earlier PASS in
  `P0-OPUS-REVIEW-20260925.md` still stands, and they were not re-reviewed in depth.
- One pre-existing low advisory (R1) is below. It is outside the F1–F3 scope and does not
  change product bytes.

## Change review (`contact_export.py`)

| Finding | Fix at `8ca5ff8` | Assessment |
|---|---|---|
| F1: null seed accepted on a multi-rule layer | `_check_raw_seed` (`contact_export.py:95-101`) now rejects a null seed if the referenced rule has any `holes` value, or if the row's layer does not have exactly one rule in `contacts`. | Matches the decision in both modes. `holes: []` also rejects null (probe below). A row whose layer has no rule gets a count of 0 and is rejected. |
| F2: seed checked against its component, not its rule | New check at `contact_export.py:115-116`: `holes` must be a list and `seed` must be in it. This runs after the component-match check. | Every explicit seed is now tied to both its raw component and its declared rule's hole list. This applies to raw rows in both preflights and to cut rows in `prepare_contacts` (`:384-386`). An explicit seed on a rule without `holes` is rejected. The engine never emits that shape, because it emits `seed=None` exactly when a layer's single rule has `holes is None` (`engine.py:104-105, 140, 158`). |
| F3: cut row missing `seed` raised `KeyError` | `seed` added to the required keys for `components` (`contact_export.py:71`). | `_validate_hole_rows` runs first in both `prepare_contacts` (`:273`) and `diagnose_physical_holes` (`:129`), so both legacy and configured modes raise `ManifestError("malformed components hole provenance")`. `raw_components` already required `seed` at `4410ec3`, so no new compatibility break is introduced for older folders. |

Call sites checked: `particle_sim_adapter.py:220-240`.

- Configured mode runs `prepare_contacts(mixed=True)`, then `diagnose_physical_holes(strict=True)`.
- Legacy mode runs `_legacy_contacts`, then `diagnose_physical_holes(strict=False)`.
- Both paths run before any output is created. In configured mode, `prepare_contacts:397-407`
  still binds `contact_rule_index` to the row's layer and endpoint pair.

New tests (`tests/test_synthetic_adapter.py`):

| Test | What it covers |
|---|---|
| `missing_cut_seed` parametrized case | F3 |
| `test_multi_rule_null_seed_rejected_even_without_rule_holes` | F1, through both preflights, non-strict diagnose, and export; asserts no output parent |
| `test_configured_single_rule_without_holes_allows_null_seed` | The accepted exception (CNT2) |
| `test_explicit_rule_holes_reject_null_seed_on_single_rule_layer` | Null seed on a single rule that has explicit holes |
| `test_explicit_seed_requires_declared_rule_holes` | Explicit seed on a rule without holes |
| `test_swapped_rule_assignment_rejected_by_seed_rule_membership` | F2, second form: swap index/lower/upper and keep the seeds; covers both preflights and export |

The changed `rule_index` expectation (`seed .* is not in declared rule holes`) is correct: the
new membership check now fires before the later endpoint check.

## Independent evidence

| Check | Result |
|---|---|
| `PYTHONDONTWRITEBYTECODE=1 .venv/bin/pytest -q -p no:cacheprovider tests` | **115 passed** (19.1 s) |
| `.venv/bin/ruff check --no-cache src tests` | All checks passed |
| I1 regeneration: `export_particle_sim(i1-latest/extraction, <scratch>, i1-latest/process-config.json)` | `product.yaml` SHA-256 `eda454fd9c8167dc57e363c06cf8d03f7a10459f43cc22f135c9775d37ed1cd2`. It and all 164 masks are byte-identical to `i1-latest/particle-sim-e3` and to `outputs/p0-hardening-a7-a9-i1-product`. |
| Legacy regeneration from the existing folder `outputs/p2-check-20260924/legacy-extracted` (every seed is null, one rule per layer, no `--config`) | Accepted. `product.yaml` SHA-256 `993b6a061d258a19fcd5c96478bdd99838382dd901fd8199cca1cba2186927e7`. It and all 174 masks are byte-identical to `outputs/p2-check-20260924/legacy-product`. |

### Counterexample probes (fresh `make_synthetic` + `extract` mixed fixture; example config)

| Probe | Expected | Result |
|---|---|---|
| Unmodified mixed fixture, configured export | accept | ACCEPTED |
| F1: remove `holes` from both CNT1 rules and null every CNT1 raw/cut seed (the prior review's repro) | reject | `CNT1: missing raw hole seed` in configured export and in `diagnose(strict=False)` |
| F1b: null one CNT1 row and remove `holes` only from its own rule | reject | `CNT1: missing raw hole seed` |
| F2: swap `contact_rule_index`/`lower`/`upper` for **every** different-rule CNT1 pair (33 pairs), updating raw and cut rows | reject by seed-rule check | 99/99 rejections (`prepare`, `diagnose strict`, `diagnose non-strict` × 33) all raised `seed … is not in declared rule holes`; none accepted and no other error |
| F2 variant: swap only the cut-row assignment | reject | `CNT1: seed [100, 55] is not in declared rule holes` |
| F2 variant: cut-row seed replaced by a seed of another component under the same rule | reject | `seed [180, 55] does not match raw_component=1` |
| F3: pop `seed` from `components[0]`, configured mode | ManifestError | `malformed components hole provenance` |
| F3: pop `seed` from `components[0]`, legacy mode | ManifestError | `malformed components hole provenance` |
| CNT2 (one rule, no `holes`), every seed null, configured mode | accept | ACCEPTED |
| CNT2 with `holes: []`, every seed null | reject | `CNT2: missing raw hole seed` |
| Legacy: add explicit `holes` to the single CNT1 rule and set matching seeds | accept | ACCEPTED |
| Legacy: same, but one raw seed null | reject | `CNT1: missing raw hole seed` |
| Legacy: same, but one seed is a different pixel of the correct component (not in `holes`) | reject | `CNT1: seed [94, 48] is not in declared rule holes` |

## Advisory (pre-existing, not blocking)

### R1: Legacy diagnostics do not bind `contact_rule_index` to the row's layer (low)

- Where: `diagnose_physical_holes` (`contact_export.py:153-167`). With `strict=False`, it
  never checks that `contacts[rule_index]["layer"] == hole`. `_check_raw_seed` reads `holes`
  from the referenced rule but counts rules on the row's layer.
- Probe: on the legacy folder, I pointed every CNT1 raw/cut row at the CNT2 rule (index 1)
  and kept the null seeds. The export was **accepted**. `product.yaml` and all 174 masks
  are still byte-identical to the reference, because `_legacy_contacts` builds masks from
  `contacts` directly. However, `adapter-provenance.json` `physical_hole_diagnostics`
  labels the CNT1 holes as `OACTIVE→METAL1` with rule index 1.
- The parent `425989a` (run from `git archive`) produces a byte-identical
  `adapter-provenance.json`, so this issue predates `8ca5ff8`.
- It is not an F1–F3 regression. Under the recorded decision, the null is legitimate
  because CNT1 has exactly one rule and that rule has no `holes`; the defect is in
  rule-index binding.
- Configured mode is unaffected because `prepare_contacts:397-407` rejects it.
- Optional fix: in `diagnose_physical_holes`, reject any row with
  `contacts[rule_index]["layer"] != hole` regardless of `strict`. This is byte-neutral for
  engine output.

## Out of scope / not established

- A deep re-review of copy `7213deb` and patch `e715b369…`. I confirmed only that they are
  unchanged.
- Running particle-sim `validate-input`. It was not rerun because the product bytes are
  identical to the evidence already accepted.
- Everything else the earlier report listed as out of scope: P1/P2, A4/A5/A6/A10, physical
  CNO/open correctness, general periodic-connectivity correctness, and applying the patch
  to the original.
