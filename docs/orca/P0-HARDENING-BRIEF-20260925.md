# P0 hardening brief — 2026-09-25

The user requested that P0 follow-up work proceed as Orca Tasks. This brief is from
the originating chat, which only observes the Run. The previous coordinator
`term_3b155c62-298f-41f3-ae26-ccde2492da62` for Run `run_5463d205f39d` is closed
(`exitCause: operator_close`, disconnected) after its final checkpoint. You are
the new sole coordinator (Codex `gpt-6-sol`, effort medium) for this work.

Before any lifecycle action, read `AGENTS.md`,
`/Users/jonghyeonlee/.agents/skills/orchestration/SKILL.md`, and the version-matched
`orca skills get orchestration`. Also read `docs/orca/CHECKPOINT.md` (top section),
`docs/orca/FINAL-OPUS-CODE-REVIEW-20260925.md` (advisories A1–A10), and
`docs/orca/CNO-SPARSE-OPUS-REVIEW-20260925.md`.

Create a new Run for this work, for example the objective "P0 hardening before
applying the v5 particle-sim patch". Record `run_5463d205f39d` as its predecessor
in the checkpoint. Do not re-bind or consume the old Run's inbox.

## Baseline

- Extractor `main` is at `20a6575`. The untracked `docs/orca/FINAL-REPORT.ko.md` and
  this brief belong to the originating chat. You may commit both unchanged as a
  documentation baseline before the first Dispatch.
- Isolated simulator copy `outputs/v5-integration-20260924/particle-sim-copy` is at
  `3bedd08` with a clean working tree.
- Original `/Users/jonghyeonlee/git/particle-sim` is at `aae492a`. It stays read-only
  and must **not** be patched in this work.
- Existing cumulative patch:
  `outputs/v5-integration-20260924/particle-sim-v5-cumulative-aae492a-to-3bedd08.patch`.

## Scope (P0 items 1–4 from FINAL-REPORT.ko.md)

Only one editor may work at a time, including across the extractor and the copy.
Implementation defaults to Luna high per `AGENTS.md`; use Sol for cross-module
design. Suggested Tasks and dependencies are below. Adjust them only with evidence
and keep every contract field.

### T-A2 — E3 atomic derived output, plus A3 tests (copy only)

- Target: copy `src/particle_sim/validation/cno_open_dedup.py` and
  `tests/unit/test_cno_open_dedup.py`.
- Change: E3 must never leave `derived/dedup_open.zarr` or any partial derived
  output when a late validation fails. Validate every map before writing, or
  stage in a sibling directory and rename it into place only after success.
  Add unit tests for the 14 malformed inputs the reviewer probed (A3): non-binary
  map, any-union missing an open pixel, any-union missing a CNO pixel, output inside
  or non-empty, `random_seed` set, config-hash mismatch, missing `ca_union.parquet`,
  sidecar not a mapping or not valid JSON, undeclared `net_status`, link or path net
  mismatch, and `fallback != error`. Every test must also assert that no derived
  output remains.
- Constraints: results for valid inputs stay byte-identical to `3bedd08`. Do not
  touch short, open, or CNO kernels. Use the protected copy environment
  (`PYTHONDONTWRITEBYTECODE=1`, `GIT_OPTIONAL_LOCKS=0`, `PYTHONPATH=<copy>/src`,
  copy-parent `GIT_CEILING_DIRECTORIES`, and an assertion that `particle_sim.__file__`
  is under the copy).
- Ownership: the copy files above only; commit in the copy's own Git.
- Acceptance: the full copy suite (`pytest -q -p no:cacheprovider tests`) passes,
  Ruff passes, the new tests fail on `3bedd08` and pass on the candidate, and the E3
  output for the I1 exact export is unchanged.

### T-A1 — legacy 8-connectivity contract (extractor)

- Target: `src/layout_electrode_extractor/contact_export.py` legacy path, tests,
  and README.
- Default decision (the originating chat applied this because the user asked for
  no alternative): keep the fail-closed rejection of a diagonal-only CNT pixel
  under `connectivity=8`. Document the narrowed legacy contract in the README and
  make the error message name the offending layer, pixel, and component. Add a
  regression test. If you find evidence that a diagnostic-only non-strict path
  is required, escalate to the user instead of choosing silently.
- Acceptance: 4-connectivity legacy output remains byte-identical to `762a239`
  (the reviewer's probe), all tests pass, and Ruff passes.

### T-A9A7A8 — provenance binding and publish safety (extractor, then copy)

- A9: record the SHA-256 of the published `product.yaml` in
  `adapter-provenance.json`. E3 in the copy must reject a sidecar whose recorded
  hash differs from the product it is given. This spans both repositories, so
  serialize the extractor edit first and the copy edit second (as two Tasks or one
  Sol Task).
- A7: verify `labels[seed_y, seed_x] == raw_component` for every hole in both
  `prepare_contacts` and `diagnose_physical_holes`. Add a hand-edited
  swapped-seed counterexample test.
- A8: create parent directories only after all validation succeeds, and make the
  publish step refuse or detect a concurrently created destination, including an
  empty one, rather than letting `os.rename` replace it silently.
- Acceptance: extractor and copy tests pass, Ruff passes, and the I1 configured
  export regenerates with identical masks and `product.yaml`. The only allowed
  sidecar change is the added hash, and the diff must show it. Original
  `validate-input` still returns `ok` with 155 electrodes, 11,879 pairs, and zero
  unresolved pairs.

### T-PATCH — regenerate the cumulative patch (coordinator may do this directly)

- Create `particle-sim-v5-cumulative-aae492a-to-<new copy HEAD>.patch` next to the
  old one and record its SHA-256. Run read-only
  `git -C /Users/jonghyeonlee/git/particle-sim apply --check` against the
  original. Confirm the original's HEAD, status, and index hash are unchanged.

### T-REVIEW — fresh independent review

- A fresh, read-only `claude --model claude-opus-5-5 --effort high` session (the
  same route as the two most recent reviews) reviews the exact extractor candidate,
  the copy candidate, and the new patch against this brief and A1/A2/A3/A7/A8/A9.
- It writes only `docs/orca/P0-OPUS-REVIEW-20260925.md`. A PASS is valid only for
  the exact SHAs it reviewed. Route findings by cause and re-review after fixes.

## Out of scope

- Applying the patch to the original particle-sim, which requires explicit user
  approval.
- P1 and P2 items: real netlist, stack and material data, the open-kernel cost,
  full simulation, and advisories A4, A5, A6, and A10.
- Remote publication and any non-subscription billing.

## Completion

Update `docs/orca/CHECKPOINT.md` with Run, Task, and Dispatch IDs, the exact SHAs,
the patch hash, and validation evidence. Add a short Korean status section to
`docs/orca/FINAL-REPORT.ko.md`. Release or explicitly retain every settled worker.
Make local commits only; do not push.
