# Orca checkpoint

- Run: `run_3cf905a17b81`; coordinator: `term_2b2539fe-3275-42de-8d69-008f8559c7d7`.
- Base: `439372f5897ffcb9175a0d330f6990d12ff1d0b7` on `main`; repository initially clean.
- T1 extraction and exact periodic connectivity: `task_b92fb0d783ae` (ready).
- T2 review UI, annotations and circuit assistance: `task_64d014d8fc4c` (depends on T1).
- T3 synthetic fixture, particle-sim adapter and documentation: `task_4a52361c281a` (depends on T2).
- T4 independent candidate review: `task_693c45297d8e` (depends on T3).
- T1 Dispatch: `ctx_b59e4fb6ede0`, supervised terminal `term_3a1c1118-2624-4136-8a5d-80ef7bfd91fd`, started from checkpoint commit `d0bba8e`. Terminal displayed GPT-6-Sol high. Settled succeeded at `723efc5`; coordinator reran 15 pytest cases, Ruff lint and format checks successfully. A 600×600 CLI smoke reported 1200×1200 output, 32 electrodes, 8 TRs and conserved residual masks. T1 API: `load_manifest`, `extract`; see `docs/EXTRACTION-API.md`.
- The source chat is an observer; this coordinator consumes the Run inbox.
- Applicable contract: `AGENTS.md`, `docs/PLAN.md`, and `docs/orca/IMPLEMENTATION-CONTRACT.md`. All Tasks are saved in Orca. One editor at a time.
