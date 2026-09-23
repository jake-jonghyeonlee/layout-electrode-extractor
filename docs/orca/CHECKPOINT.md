# Orca checkpoint

- Run: `run_3cf905a17b81`; coordinator: `term_2b2539fe-3275-42de-8d69-008f8559c7d7`.
- Base: `439372f5897ffcb9175a0d330f6990d12ff1d0b7` on `main`; repository initially clean.
- T1 extraction and exact periodic connectivity: `task_b92fb0d783ae` (ready).
- T2 review UI, annotations and circuit assistance: `task_64d014d8fc4c` (depends on T1).
- T3 synthetic fixture, particle-sim adapter and documentation: `task_4a52361c281a` (depends on T2).
- T4 independent candidate review: `task_693c45297d8e` (depends on T3).
- No Dispatch started yet. The source chat is an observer; this coordinator consumes the Run inbox.
- Applicable contract: `AGENTS.md`, `docs/PLAN.md`, and `docs/orca/IMPLEMENTATION-CONTRACT.md`. All Tasks are saved in Orca. One editor at a time.
