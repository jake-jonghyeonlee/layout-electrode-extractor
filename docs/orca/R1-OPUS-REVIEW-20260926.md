# R1 rule-layer binding: independent Opus review, 2026-09-26

- Reviewer: fresh read-only Claude Code session, model `claude-opus-5-5`, effort `high`.
  The reviewer did not author this change.
- Orca: Task `task_8654810e3888`, Dispatch `ctx_3f063e661349`. The coordinator keeps
  lifecycle authority.
- Candidate: exact root product commit `77b335a91deecdab87b50ddb0c1e0870137fc407`. Its
  parent is `1a64cac`, which is docs-only on top of the accepted `8ca5ff8`. The working
  tree was clean at HEAD `77b335a` when the review started.
- Requirement: every `raw_components` and `components` row's `contact_rule_index` must
  reference a contact rule on the row's own layer. This must hold in strict diagnostics,
  in non-strict diagnostics, and in configured preparation. It is advisory R1 in
  `docs/orca/P0-OPUS-REREVIEW-20260925.md`.
- Write scope: this file only. No source or product edits, copy/original edits, patch
  application, push, or nested workers.

## Verdict

**R1 on exact root product `77b335a`: PASS.**

There are no blocking findings. The two notes below are low-severity or informational.

## Diff inspected

| File | Change |
|---|---|
| `src/layout_electrode_extractor/contact_export.py:82-83` | `_validate_hole_rows` now checks `contacts[index]["layer"] != row["layer"]` and raises `ManifestError("{kind} contact_rule_index does not match row layer")`. This runs right after the existing type and range check on the index, so `IndexError` or `KeyError` cannot occur. |
| `tests/test_synthetic_adapter.py:138-161` | New `test_legacy_cross_layer_contact_rule_index_rejected_before_output`. |
| `tests/test_synthetic_adapter.py:950,955` | Updates the expected messages of the existing `rule_index` and `extra` mutation cases to the new, earlier rejection. |

## The shared validator runs before every use

- There are only two consumers of `meta["contact_holes"]` rows:
  - `diagnose_physical_holes`, which calls `_validate_hole_rows` as its first statement
    (`:128`).
  - `prepare_contacts`, which does the same (`:275`).
- `_check_raw_seed` is called only from those two functions (`:153`, `:383`, `:385`), so
  `contacts[row["contact_rule_index"]]` is always read after the layer binding.
- The adapter (`particle_sim_adapter.py:230-240`) calls both of them before it creates any
  output:
  - Configured mode calls `prepare_contacts` and then `diagnose(strict=True)`.
  - Legacy mode calls `_legacy_contacts` and then `diagnose(strict=False)`.

  `_legacy_contacts` never reads hole rows.
- `grep` finds no other consumer. `contact_holes.instances` is emitted by the engine but
  never read by the exporter.
- The check does not depend on `strict`. That closes the gap described in R1: non-strict
  diagnostics previously labelled CNT1 holes with the CNT2 rule's endpoints.
- Engine compatibility: `_resolve_contacts` assigns indices only from
  `[(i, rule) for i, rule in enumerate(manifest.contacts) if rule.layer == layer]`
  (`engine.py:103`). Engine output therefore always satisfies the new check, and the
  change is byte-neutral for extracted folders.

## Consistency with the accepted F1–F3 rules

- F1 (a null seed is allowed only when the layer has exactly one rule and that rule has no
  `holes`) is unchanged. Before this commit, `_check_raw_seed` counted rules on the row's
  layer but read `holes` from the referenced rule, which could be on another layer. That
  mismatch is now impossible because the referenced rule is always on the row's layer.
- F2 (an explicit seed must belong to its rule's `holes`) is unchanged. Same-layer swaps
  are still caught by the seed-membership check, and
  `test_swapped_rule_assignment_rejected_by_seed_rule_membership` still asserts
  `seed … is not in declared rule holes`.
- F3 (a missing cut-row `seed` raises `malformed components hole provenance`) is
  unchanged. The required-keys check still runs before the new check.

## Commands and results

| Command / probe | Result |
|---|---|
| `.venv/bin/python -m pytest -q -p no:cacheprovider tests` at `77b335a` | `116 passed` |
| `.venv/bin/ruff check src tests` | `All checks passed!` |
| New and changed tests run against the parent source. HEAD `tests/` was used with `PYTHONPATH` set to a `git archive 1a64cac src` extract; the import path was confirmed to be the extract. | The new cross-layer test fails with `DID NOT RAISE ManifestError`, and `rule_index` and `extra` fail on regex mismatch. The regression test therefore discriminates parent from candidate. |
| I1 regeneration: `export_particle_sim(i1-latest/extraction, <scratch>, i1-latest/process-config.json)` | `product.yaml` SHA-256 `eda454fd9c8167dc57e363c06cf8d03f7a10459f43cc22f135c9775d37ed1cd2`. It and all 164 masks are byte-identical to `i1-latest/particle-sim-e3` and to `outputs/p0-hardening-a7-a9-i1-product`. |
| Legacy regeneration: `export_particle_sim(p2-check-20260924/legacy-extracted, <scratch>)` | `product.yaml` SHA-256 `993b6a061d258a19fcd5c96478bdd99838382dd901fd8199cca1cba2186927e7`. It and all 174 masks are byte-identical to `p2-check-20260924/legacy-product`. |
| Exhaustive single-row probe, I1 (rules CNT1, CNT1, CNT2 with holes, holes, none). Every raw and cut row was re-pointed to every rule on another layer (24 mutations), then passed through `diagnose(strict=False)`, `diagnose(strict=True)`, and `prepare_contacts(mixed=True)`. | 72/72 rejected, every one with `contact_rule_index does not match row layer`. None were accepted, and no other exception type occurred. |
| Same probe on the legacy folder (one rule per layer, every seed null) | 40/40 rejected with the same message. |
| The R1 repro through the full export: every CNT1 row was pointed at the CNT2 rule. Three variants were run (raw only, cut only, and both) on both the legacy (no config) and I1 (configured) folders. | 6/6 raised `ManifestError … contact_rule_index does not match row layer`, and none created the output's parent directory. Before this commit, the legacy variant was accepted, as recorded in R1. |
| Reviewed the legacy test probe in `test_legacy_cross_layer_contact_rule_index_rejected_before_output` | It asserts that CNT2 is rule 1 and that the mutated CNT1 rows really have null seeds, which is the F1-legitimate shape R1 exploited. It then covers raw-only, cut-only, and both, across `diagnose` in both modes and `prepare_contacts`. For the both-kinds case it runs the full legacy `export_particle_sim` and asserts that `output.parent` (`absent/`) does not exist, which is stronger than checking `output` alone. It does not produce vacuous passes: `assert rows` guarantees that mutations occurred. |
| Isolated copy `outputs/v5-integration-20260924/particle-sim-copy` | HEAD `7213deb38c23aeac99628bbf6236a444b6b3440f`, clean. |
| Patch `particle-sim-v5-cumulative-aae492a-to-7213deb.patch` | SHA-256 `e715b36910ac57577d927496a067fab98584e6890d5d453101836c7f859936f4`, unchanged. |
| Original `/Users/jonghyeonlee/git/particle-sim` | HEAD `aae492a6728116e8d584b657dd91b7934e4bff18`. The only status entry is the untracked `docs/layout-electrode-extraction-plan.md`. Branch `v5-extractor-integration` does not exist, so the patch has not been applied. |

## Findings (non-blocking)

### N1: Loss of test coverage for `missing or unknown hole layers` (low, test coverage)

- The `extra` mutation case used to be the only test of
  `prepare_contacts`'s `contact provenance has missing or unknown hole layers` branch
  (`contact_export.py:359-360`). An unknown-layer row now fails the earlier layer-binding
  check, so this branch has no test.
- The branch is still reachable. On I1, removing every CNT2 raw/cut row and calling
  `prepare_contacts(mixed=True)` raises exactly that message.
- The redirected expectation is correct, and the product behaviour is unaffected.
- Optional fix: a mutation case that drops all rows of one hole layer.

### N2: New error message omits location details (informational)

- The new message names only `kind`.
- Nearby messages include layer, component, and seed. Adding
  `row["layer"]`, `row["raw_component"]`, `index`, and `contacts[index]["layer"]` would help
  triage. This is not a correctness issue.

## Limits

- This review covered only R1 in `contact_export.py`, its call sites, and its tests.
- Out of scope:
  - Non-strict row `lower`/`upper` agreement with the referenced rule on the same layer.
    Diagnostics use the rule's endpoints, and configured mode checks that agreement.
  - Malformed `contact_rules` entries, such as a missing `layer` key. These fail earlier
    in the adapter with a pre-existing `KeyError` shape.
  - `contact_holes.instances`.
- Also out of scope: physical CNO/open correctness, general periodic-connectivity
  correctness, a deep re-review of copy `7213deb` or the patch (only confirmed unchanged),
  and running particle-sim `validate-input`. That run was unnecessary because product
  bytes are identical to accepted evidence.
- Probe scratch outputs are under the session scratchpad, outside the repository.
