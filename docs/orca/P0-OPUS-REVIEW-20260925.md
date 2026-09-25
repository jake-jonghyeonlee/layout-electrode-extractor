# P0 hardening — independent Opus review, 2026-09-25

- Reviewer: fresh Claude Code session `claude-opus-5-5`, effort high, read-only. It did not
  author or coordinate any of the reviewed changes.
- Run `run_5ebf21e5c7f7`, Task `task_20b120c436b2`, Dispatch `ctx_edd2300a5cbe`.
- Contract: `docs/orca/P0-HARDENING-BRIEF-20260925.md`, advisories A1/A2/A3/A7/A8/A9 in
  `docs/orca/FINAL-OPUS-CODE-REVIEW-20260925.md`, and the user's seed decision recorded in
  `docs/orca/CHECKPOINT.md`.
- Only this file was written in the repository. Probes ran in the session scratchpad.

## Exact candidates reviewed

| Item | Value |
|---|---|
| Extractor product commit | `4410ec3144537659dafe7fb72e2d68f05d3d9bfe` (A1 at `f2b6b4ee961b6367c31c2e279965d53323fe927a`; baseline `7ac6f84a5b538c3a3bd3d7ab33362586f990430a`) |
| Extractor HEAD at review | `f016bcb35cce59a041944b8a5926415d094a48e4`, which adds only README/CHECKPOINT/FINAL-REPORT.ko docs after `4410ec3` (`git diff --stat` checked) |
| Isolated copy | `7213deb38c23aeac99628bbf6236a444b6b3440f` (A2/A3 at `a56216253b53898c5ebabbf5d2b073d6e2415d1c`; baseline `3bedd086319eb5820fb884e78d2446d4a6bdf43f`), clean tree |
| Cumulative patch | `outputs/v5-integration-20260924/particle-sim-v5-cumulative-aae492a-to-7213deb.patch`, SHA-256 `e715b36910ac57577d927496a067fab98584e6890d5d453101836c7f859936f4` |
| Original particle-sim | `aae492a6728116e8d584b657dd91b7934e4bff18`, sole untracked `docs/layout-electrode-extraction-plan.md`, index SHA-256 `cc93792e3e008cd99a9626a6e85743b4e3395dd84a7573c2d2a6defccfbe4dd6`. These were identical before and after this review. |

## Verdict

- **Copy `7213deb` (A2, A3, A9 on the E3 side): PASS.**
- **Cumulative patch `e715b369…`: PASS.** It is byte-identical to `git diff 4f2a94c 7213deb`
  in the copy, and `4f2a94c` has the same tree as the original `aae492a`
  (`27c76834…`). Read-only `git apply --check` passed.
- **Extractor `4410ec3`: A1, A8 and the A9 extractor side PASS. A7 is NOT PASS.** There
  are two low-severity actionable findings, F1 and F2 below. F1 contradicts the recorded
  user seed decision, so A7 cannot be accepted as recorded.

Both A7 fixes are root-only, and the patch contains only copy changes. After those fixes,
the copy and patch PASS still stands; only the new root commit needs re-review.

## Findings (actionable)

### F1 — Null seed accepted on a multi-rule layer (low; contradicts the accepted user policy)

- Where: `src/layout_electrode_extractor/contact_export.py:90-96` (`_check_raw_seed`).
- The recorded decision is: accept `seed: null` only in single-rule rows, and reject null
  in configured or multi-rule hole rules. The code does not check the rule count. It
  rejects null only when `contacts[rule_index].get("holes") is not None`. As a result,
  deleting the `holes` key from the rules also disables the null-seed check.
- Counterexample (reproduced): mixed fixture extraction (`make_synthetic` + `extract`) with
  the example synthetic config. CNT1 has two rules (0 ACTIVE–METAL1 with 11 seeds,
  1 GAT2–METAL1 with 3 seeds). I removed `holes` from both CNT1 rules and set every CNT1
  `raw_components`/`components` seed to null. `export_particle_sim(..., config)` returned
  **ACCEPTED**. On such a layer, the seed check can no longer detect any endpoint swap.
- The engine never emits this shape: it raises "mixed legacy and seeded contact rules" for
  a multi-rule layer without holes. So this matters only for hand-edited folders, which
  is exactly A7's threat model.
- Fix: allow null only when exactly one contact rule exists for `row["layer"]`, for example
  `sum(r["layer"] == row["layer"] for r in contacts) == 1`. This keeps the legitimate
  configured single-rule layer (CNT2 in the mixed fixture) and the legacy rows. Add this
  counterexample as a regression test.

### F2 — The seed is checked against its component, not its rule (low; A7 is only half closed)

- Where: same function. It verifies `labels[y, x] == raw_component` but never checks that
  the seed belongs to `contacts[contact_rule_index]["holes"]`. The engine derives each
  seed from exactly that list (`engine.py:112-121`).
- A7's scenario is two holes swapping endpoint pairs. That can be written two ways:
  1. Swap `raw_component` between rows. The new check catches this.
  2. Swap `contact_rule_index`/`lower`/`upper` between rows and keep the seeds. The new
     check does **not** catch this.
- The new test `test_swapped_same_rule_seeds_rejected_by_both_preflights` swaps seeds only
  within the same rule, so it covers only the first form.
- Probe: I swapped the rule assignment between 12 different-rule CNT1 row pairs, updating
  the matching `components` rows too. In every case `_check_raw_seed` passed for all rows.
  All 12 exports were rejected, but only later, by the graph-edge/geometry check
  (`CNT1 component N: missing graph edge to …`). That evidence comes from
  `connectivity.json` in the same hand-editable folder, and geometry would not catch a
  swap where both rules are geometrically valid.
- Fix (one condition, byte-neutral for engine output): when the rule has `holes`, also
  require `seed in contacts[rule_index]["holes"]`. Add a test that swaps
  `contact_rule_index`/`lower`/`upper` and expects the seed error.

### F3 — A `components` row missing `seed` raises `KeyError` (low; fails closed)

- Where: `_validate_hole_rows` (`contact_export.py:66-88`) requires `seed` only for
  `raw_components`. `prepare_contacts` now calls `_check_raw_seed(labels, cut_row, …)`,
  which reads `row["seed"]`.
- Probe: I popped `seed` from `contact_holes.components[0]` in the configured case. The
  export raised `KeyError: 'seed'`, which is outside the CLI's handled set
  (`cli.py:69`), so the CLI prints a traceback instead of a `ManifestError`. No output is
  produced.
- Fix: add `seed` to the required keys for `components`, or skip the cut-row call, since
  the raw row is already checked and `cut_row["raw_component"] == component` is enforced
  below.

## Per-item assessment

| Item | Result | Evidence |
|---|---|---|
| A1 legacy 8-connectivity | PASS | Fail-closed rejection is kept. `_check_four_partition` reports the layer, the diagonal pixel pair, both 4-connected labels and the 8-component, and `diagnose_physical_holes` now runs it before provenance lookup. README text matches the behaviour. Regression tests: unit (2×2 diagonal) and end-to-end (legacy `connectivity: 8`, pixels (10,10)/(11,11), asserts no output). Independent probe: the legacy 4-connectivity fixture exported with `762a239` (from `git archive`) and with the candidate gives byte-identical `product.yaml` and all 174 masks. `adapter-report.json` differs only in fields added by earlier accepted commits before P0. |
| A2 E3 atomic output | PASS | `analyze_cno_open` finishes all input validation, writes into a `mkdtemp` sibling, renames into place on success, and removes the stage (and the parent, if it created it) on any `BaseException`. Nothing in the written output records the stage path. |
| A3 E3 malformed tests | PASS | All 14 listed cases plus 3 hash cases are parametrized, and each asserts no output and no stage leftovers. Against `3bedd08` source, the candidate test file fails exactly 6 cases (3 late map checks + 3 hash checks) and passes the rest, which were already guarded early. Of the 17 cases, 14 use `match=None`. I captured each exception and confirmed every case reaches its intended guard, and that the unmodified fixture succeeds (4 rows). |
| A7 seed check | **NOT PASS** | See F1 and F2 (F3 is incidental). The `labels[seed] == raw_component` check exists in both `prepare_contacts` and `diagnose_physical_holes` and catches component swaps. |
| A8 publish safety | PASS | `output.parent.mkdir` now follows `circuit_declarations` and `mask_diagnostics`, the last validations. Anything after it is only I/O. `_publish_noreplace` uses `renamex_np(..., RENAME_EXCL=0x4)` on macOS and `renameat2(AT_FDCWD=-100, ..., RENAME_NOREPLACE=1)` on Linux, maps `EEXIST`/`ENOTEMPTY` to `FileExistsError`, and fails closed otherwise. Tests cover a concurrent empty and non-empty claimant, and a parent that is never created on preflight failure. The electrode-row reorder keeps dict order, so output is unchanged. |
| A9 hash binding | PASS | The extractor hashes the staged `product.yaml` bytes it just wrote; publish is a rename, so the bytes are identical. E3 checks for a mapping sidecar and `product_yaml_sha256 == file_sha256(manifest_path)` before any relation or output work. |

### Independent reruns

| Check | Result |
|---|---|
| Root `pytest -q -p no:cacheprovider tests` (`PYTHONDONTWRITEBYTECODE=1`) at HEAD = product `4410ec3` + docs | **109 passed**; `ruff check --no-cache src tests` passed |
| Copy `pytest -q -p no:cacheprovider tests` in the protected environment: copy cwd, `PYTHONPATH=<copy>/src`, `PYTHONDONTWRITEBYTECODE=1`, `GIT_OPTIONAL_LOCKS=0`, copy-parent `GIT_CEILING_DIRECTORIES`, copy `.venv` Python 3.11.15, `particle_sim.__file__` asserted under `<copy>/src` | **369 passed**; Ruff passed |
| I1 configured export regenerated with the candidate (`i1-latest/extraction` + `process-config.json`) | 155 electrodes, 11,879 pairs, 1 open path. `product.yaml` and all 164 masks are byte-identical to `i1-latest/particle-sim-e3`. The sidecar only adds `product_yaml_sha256 = eda454fd9c8167dc57e363c06cf8d03f7a10459f43cc22f135c9775d37ed1cd2`, which equals the product SHA recorded by the sparse probe. The output is identical to the worker's `outputs/p0-hardening-a7-a9-i1-product`. |
| E3 old vs new on the exact I1 product and the actual sparse raw run (`e3-sparse-geometry-probe/raw`) | `3bedd08` with the old sidecar and `7213deb` with the new sidecar both give 96 rows. `cno_open_dedup.parquet` and `dedup_open.zarr` are byte-identical. `dedup_manifest.json` differs only in sidecar path and SHA. The candidate rejects the old hashless sidecar and leaves no output. A tree hash of the raw run was unchanged. |
| Patch | Bytes equal `git diff 4f2a94c 7213deb`. `git apply --check` against the original passed, with the original fingerprint unchanged before and after. |

The coordinator's `validate-input` evidence was not rerun, because it imports the original.
The product bytes are identical to the ones that evidence covered.

## Advisories (no action required for P0)

- **I1.** On the Linux `renameat2` path, only the argument layout was reviewed; it cannot
  be tested on this macOS host. A libc without `renameat2` raises `AttributeError`, and a
  filesystem without no-replace support raises `OSError`. Both fail closed, and staging is
  removed.
- **I2.** E3 publish uses `rmdir` on a pre-existing empty output, then `rename`, which
  leaves a small window. On failure it removes only the immediate parent it created, so
  deeper created ancestors can remain empty. No derived data is left behind in either case.
- **I3.** Passing `match=` strings for the 14 message-less E3 cases would keep them tied to
  their guards.
- **I4.** Because of A9, any re-serialized product needs a matching sidecar. An example is
  `i1-latest/build_e3_probe.py`, which rewrites `particle_sizes_um`. The old `e3-probe`
  flow no longer runs unmodified. This is intended.
- **I5.** The root worktree has an uncommitted `AGENTS.md` routing edit that this reviewer
  did not make. It was not reviewed and was left untouched.

## Out of scope / not established

This review does not cover applying the patch to the original, P1/P2 items, A4/A5/A6/A10,
physical correctness of CNO/open accounting, or general periodic-connectivity correctness.
