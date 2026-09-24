# CNO sparse overlap: independent review (Claude Opus 5.5 high, 2026-09-25)

- Task `task_d1d15681c2aa`, Dispatch `ctx_31b549e505a6`, Run `run_5463d205f39d`.
- Reviewer terminal `term_241e5443-931d-4900-9a21-de52db684d13`. The parent process was launched as `claude --model claude-opus-5-5 --effort high` (PID 41110, read with `ps`), and the session reports model ID `claude-opus-5-5`.
- Candidate: isolated copy `outputs/v5-integration-20260924/particle-sim-copy` at `3bedd086319eb5820fb884e78d2446d4a6bdf43f`. Baseline is `9a7cc2b466146d17878422acc48c4d9905dea54e`. The extractor root is frozen at `6893fe69c3b373727965411132b69edec2610f58`.
- Scope: the copy files `src/particle_sim/failure/contact_not_open.py` and `tests/unit/test_contacts_cno.py`, the `particle_footprint` footprint, the call sites (`units.py`, `contacts.py`) and the ignored evidence in `cno-sparse-bench/`.
- This review was read-only. The only file I wrote is this report. Scratch scripts and logs are outside the repository.

## Verdict

**PASS for exact commit `3bedd08`.** I found no blocking defect. For every input inside the validated contract, the sparse row-run/difference accumulator gives the same result as the old `scipy.ndimage.correlate` path. That contract is: unique coordinates of a physical TR-cut hole, and a binary stamp of any finite shape, including asymmetric and even dimensions. I checked this against two independent oracles, and on every hole and link of the exact I1 fixture.

This PASS covers only `3bedd08`. It does not cover the extractor or any later change. It makes no physical-validity claim: CNO is still a synthetic geometric rule (at least half of the full cut hole, a margin-0 disc, and a link fails if any one of its holes fails) on assumed fixture masks.

The earlier `FINAL-OPUS-CODE-REVIEW-20260925.md` PASS covered `9a7cc2b` and is stale for this commit. Its advisories A1, A2, A7 and A9 are pre-existing, out of scope here, and neither changed nor resolved by this diff.

## Validation I actually reran

Every run used the copy as working directory, with `PYTHONDONTWRITEBYTECODE=1`, `GIT_OPTIONAL_LOCKS=0`, `PYTHONPATH=<copy>/src` and copy-parent `GIT_CEILING_DIRECTORIES`. I used the interpreter `/Users/jonghyeonlee/git/particle-sim/.venv/bin/python` (Python 3.12.13, NumPy 2.5.3, SciPy 1.18.1) without installing or writing anything. `particle_sim.__file__` was asserted to resolve to `<copy>/src/particle_sim/__init__.py`. One early version query (`python -c "import scipy,numpy"`) ran before these controls were applied. The fingerprint check below shows that nothing in the original repo changed.

| Check | Result |
|---|---|
| 4,000 randomized cases. Stamps 1–15 × 1–15 with densities 0–1, including all-empty stamps and rows with several runs. Images 1–24 × 1–24. Holes are scattered pixels or blocks touching sides and corners. Compared with (a) a **full-image** `correlate` (no ROI) and (b) an independent translate-and-add oracle that places a flipped stamp at each hole pixel. The check also asserts that **no blocked centre lies outside the returned ROI**. | All equal; ROI complete |
| Pathological stamps: empty 3×4; a single pixel in the top-left of 2×2 and bottom-right of 4×6; a 6×7 checkerboard; a 1×9 row with gaps; 2×1. Holes are a single pixel in each image corner and the whole image, on image shapes (1,1), (5,5) and (9,12). | All equal |
| Thresholds: 49, 50 and 51 covered of 100, and 112 and 113 covered of 225 (odd). | Blocked is F/T/T and F/T, as required |
| Exact I1 fixture `i1-latest/particle-sim-e3/product.yaml` (1200×1200, 54 links, 100 holes, every hole 225 cut pixels): no hole has duplicate coordinates. | Verified, 100 of 100 |
| The three benchmark links at 1, 30, 40 and 50 µm: `simulate_cno(..., margin=0.5)`, which ignores the margin, compared with the translate oracle OR-ed over every hole using the full-cut denominator. | All 12 equal. Failure-pixel counts are identical to `results.json` (0/0/0, 197690/258817/51553, 296282/366763/82628, 395052/452875/113644) |
| Representative hole at all 32 manifest bins (1–30, 40 and 50 µm), compared with the translate oracle, including the full-image outside-ROI check. | All equal |
| Every one of the 100 fixture holes at 1, 2 and 5 µm, compared with the old ROI `correlate` expression. | All equal |
| Full copy suite `pytest -q -p no:cacheprovider tests` | **352 passed** in 49.93 s (50.27 s wall, 368 MB max RSS) |
| Focused `test_contacts_cno.py` and `test_cno_open_dedup.py` | 34 passed |
| My verification script, including the oracles and fixture loading | 13.45 s wall, 791 MB max RSS, 772 MB peak footprint |

Items I inspected but did not rerun: `ruff.log` (All checks passed) and the benchmark `time.txt`.

## Correctness analysis

- **Placement.** SciPy correlate computes `out[c] = Σ_j in[c + j − ⌊size/2⌋]·w[j]`, so `p − c = j − half`. The code at lines 57 and 63–64 uses `cy = hy − (sy − half_y)` and `x ∈ [hx − (sx1 − half_x), hx − (sx0 − half_x)]`, which is the same relation for any H and W, odd or even.
- **ROI completeness.** Centres that can reach a hole lie in `[p − (H−1−half), p + half]`. For even H, `H−1−half = half−1`, so the window `[min − half, max + half]` still contains them. Clipping to the image loses only centres outside the image. I verified this empirically with the full-image oracle.
- **Clipping.** `x0 = max(left, …)` and `x1 = min(right, …)` feed a `width+1` difference row, so index `x1 − left ≤ width` is always in range. Rows outside the ROI are skipped.
- **Overflow.** Each `covered` value is at most `min(n_hole, stamp_pixels)`. Individual `diff` entries are bounded by pairs of hole pixels and runs, which is far below 2³¹ for 1200×1200 frames. Even if a `diff` entry wrapped, int32 two's-complement prefix sums are modular, so `covered` stays exact whenever the true count fits in int32. `2*covered` overflows only for holes larger than about 1.07e9 pixels. The old code used int32 as well.
- **Denominator and any-hole rule.** The denominator is `len(ys)` of `hole.cut_ys`, the whole TR-cut component, not the effective pixels. `simulate_cno` ORs the result of each hole into `failure[rows, cols]`. The stamp is `particle_footprint(grid, d/2, 0.0)`, so the margin is 0. None of this changed from the baseline.

## Non-blocking findings

**N1: duplicate coordinates (coordinator question). This is outside the validated contract, not a production regression.** Counterexample: `hole_blocked_centres(ys=[2,2,2], xs=[2,2,3], (5,5), ones((1,1)))`. The new code blocks centre (2,2), because its count of 2 is at least 3/2. The old code blocked nothing: its bitmap deduplicated the numerator to 1 while `len(ys)` still counted 3.

Every production caller passes `np.nonzero(labels == k)` (`contacts.py:114`), which cannot repeat a coordinate. I verified all 100 fixture holes. The old behaviour was not a coherent reference either, because it deduplicated the numerator but not the denominator. The new code is at least internally consistent, since it weights both the same way.

Because the helper is public, an optional hardening would be a docstring line or a cheap uniqueness check, for example `np.unique(ys * W + xs).size == len(ys)`, that fails closed. It does not block this candidate.

**N2: non-binary stamp values are outside the contract.** With `stamp=[[0.5, 2.0, 0.0]]`, the new code treats every nonzero value as 1, while the old code truncated through `astype(int32)`, which turns 0.5 into 0. `particle_footprint` always returns `bool`, so production is unaffected. A `stamp.dtype == bool` assertion would make the contract explicit.

**N3: benchmark provenance gap, now closed by rerun.** `cno-sparse-bench/results.json` records `"copy_head": "9a7cc2b…"`. The benchmark ran at 00:34, before the 00:36:52 commit, so `REPORT.md` shows results for the uncommitted tree, not the exact commit.

My rerun on committed `3bedd08` reproduces all 12 link failure counts and the equality at all 32 bins. The hashes in `REPORT.md` match the files: patch `6fdfc6a9…`, which equals `git diff 9a7cc2b 3bedd08`, script `3cf94088…`, results `b3efb565…`, product `eda454fd…` and sidecar `0f8973a1…`. The working-tree blobs equal HEAD: `5dca1a5` and `43d33dc`.

**N4: test coverage.** The new randomized test compares against an ROI-sliced oracle, so it cannot detect a centre missing from the ROI. It also uses `replace=False`, so it never exercises duplicates. My full-image oracle closes the first gap for this review. Committed coverage stays narrower than the claim of "arbitrary finite binary stamps".

**N5: cosmetic.** `half_x` and `half_y` are recomputed at lines 46 and 54 with the same values.

**N6: performance and memory.**
- Cost is `O(n_hole × stamp_rows × runs)` in a Python loop.
- One 225-pixel hole takes 0.78 s across all 32 bins, and 0.10–0.11 s at 50 µm.
- Across 100 holes that is about 78 s single-threaded for one full CNO bin sweep. That number is an extrapolation, not a measurement. The pipeline shares `open_cache` across steps, keyed by `(unit, diameter, margin)`.
- Working memory is one int32 difference image the size of the local ROI (at most about 460×300 at 50 µm, under 1 MB). This replaces the old `NI_Correlate` path.
- **Unmeasured, and not introduced by this diff:** retaining full-frame cached failure maps for 54 links × 32 bins could reach a few GB.

## Evidence boundaries (checked against logs, not narrative)

- **Aborted traces.** `i1-latest/logs/resource-boundary-note.md` records, for the broad-radius CNO correlation attempt, 58.52 s, 20,406,697,984 B max RSS and **51,967,808,664 B peak footprint (51.97 GB)**. The open attempt recorded 51,772,789,864 B.
  - The raw `/usr/bin/time` output for those aborted runs is **not preserved** as its own file. The note is a transcription.
  - The supporting raw sample `logs/e3-geometry-probe-sample-current.txt` shows `NI_Correlate` in `_nd_image` on the stack and a 32.1 GB physical footprint at sampling time.
- **New bounded benchmark.** `cno-sparse-bench/time.txt` shows 529,448,960 B max RSS (about 529 MB, 505 MiB), 510,034,760 B peak footprint and 6.70 s. These numbers match `REPORT.md`, subject to N3.
- **I1 actual-kernel evidence before optimization** (`i1-latest/e3-geometry-probe/geometry-probe.json`):
  - `evaluated_kernel_counts = {short_pair_maps: 12, contact_maps: 3, contact_diameters_um: [1.0], open_kernel_maps: 0}`. That is 3 pairs × 4 sizes of short maps, and 3 CNO links at 1 µm only.
  - `"open terminals/maps are synthetic": true` and `open_connectivity_supported: false`. The `geometry_meaning` field reads "Selected geometry kernels on assumed fixture masks; not physical validation."
  - The synthetic open maps are not actual-kernel output. The 30, 40 and 50 µm CNO maps come from this candidate's bounded benchmark and my rerun, not from I1.
  - No sweep of all pairs across 32 bins was run by the benchmark, by I1 or by me.
- **Original repository untouched.** `/Users/jonghyeonlee/git/particle-sim` is still at HEAD `aae492a`. Its status shows only the pre-existing `?? docs/layout-electrode-extraction-plan.md`. The `.git/index` mtime is unchanged at 1790048915, the `.venv` mtime is unchanged, and no file in the tree is newer than the review start (00:38 KST).
- **Copy state.** HEAD is `3bedd08` and the working tree is clean at the end of the review, so the review is not stale. The `.git` directory mtime moved at 00:44:00 with no new entry and an unchanged `index` mtime. This is consistent with a transient lock from a concurrent read-only git call, and it did not change the content.
- **Extractor root.** HEAD is `6893fe6`. `docs/orca/FINAL-REPORT.ko.md` and the other untracked docs are untouched.
