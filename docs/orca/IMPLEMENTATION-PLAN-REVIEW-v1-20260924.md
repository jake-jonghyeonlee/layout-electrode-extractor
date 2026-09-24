# 구현 실행계약 v1 독립 계획 검토 — 2026-09-24

- 검토자: Claude Opus 5.5 (`claude-opus-5-5`, high), 읽기 전용. Run `run_5463d205f39d`, Task `task_75492d9ab79f`, Dispatch `ctx_e9179a8ee916`.
- 대상: extractor commit `f214cd8`의 [IMPLEMENTATION-PLAN-v1](IMPLEMENTATION-PLAN-v1-20260924.md)과 [PARTICLE-SIM-REVISION-PLAN-v5](PARTICLE-SIM-REVISION-PLAN-v5-20260924.md). particle-sim은 HEAD `aae492a`이고 untracked `docs/layout-electrode-extraction-plan.md`가 있어 clean 상태가 아니다. 원본은 읽기만 했다.
- 직접 확인한 증거: `f214cd8`에서 pytest **53 passed**, `ruff check .` 통과. 캐시와 bytecode는 쓰지 않았다. 최신 fixture 추출물 `outputs/particle-sim-link-check-20260924/extraction`을 확인했다. unit 기준 CNT1 raw 성분 14개와 CNT2 11개가 모두 **225 px**다. unit 외곽에 닿는 홀과 TR로 절단된 홀 픽셀(raw−cut)은 **0**이다. 2×2 hole instance는 100개이고 member가 둘 이상인 instance는 0개다.
- 이 저장소에서 변경한 것은 이 파일뿐이다. `FINAL-REPORT.ko.md`는 건드리지 않았다.

## 판정

**FAIL (v1 @ `f214cd8` 그대로는 첫 편집 Dispatch 불가).** 첫 편집 Task P0/P1 시작 전에 막는 finding은 B1–B3 세 건이다. 외부 E1/E3 시안 Dispatch 전에 막는 finding은 X1–X3 세 건이다. B1–B3를 반영한 계획 개정본이 나오면 P0/P1은 시작할 수 있다. X1–X3는 E Task 계약을 저장하기 전까지 해결하면 된다. 이 판정은 위 문서 버전과 commit에만 유효하다.

범위가 잘 잡힌 부분도 있다. 50% 정수 경계(100 px: 49 F/50 T/51 T, 225 px: 112 F/113 T)는 `2*covered>=area`와 일치한다. legacy 양성 대조군 유지, 출력 전 실패, 원시 사건과 dedup 결과 병행 보존, 합성 결과와 물리 결과의 구분, 라벨 단순 타일링 금지, finite halo 비교를 일반 증명으로 쓰지 않는다는 원칙도 타당하다.

## 차단 finding — P0/P1 시작 전

### B1. process config 형식이 없어 P0 수락 기준을 판정할 수 없다
- 근거: v1 L8은 "full stack row, source stage, net mapping, pair/open 정책"을 나열만 한다. v5 L69는 P0의 선행 조건으로 "공정 입력 형식과 노출 시점 확정"을 두는데, v1은 이것이 해결됐다고 말하지 않는다. particle-sim에는 이미 여러 제약이 있다. hole_layer는 비도체여야 하고 endpoint 사이의 process_order에 있어야 한다(`particle-sim/src/particle_sim/schema.py:432-449`). patterned 층은 layer_mask가 필요하고 non-patterned 층에는 mask가 없어야 한다(같은 파일 L281). step은 stack의 layer ID만 가리킬 수 있다(L295-300).
- 실패 시나리오: worker가 필드 이름과 의미를 임의로 정한다. 예를 들어 ILD 행이 CNT가 관통하는 막인지 별도 막인지, `mask_source`가 bool인지 mask 파일인지, 두께 단위, planarization 필수 여부가 제각각 정해진다. 그러면 P2(net map)와 I1이 같은 파일을 다시 설계해야 하고, "필수값 누락 시 출력 전 실패"라는 기준도 무엇을 기준으로 누락인지 정할 수 없다.
- 요구: Task 계약에 최소 JSON 형태와 검증 규칙을 적는다. 권장 필드는 `profile: synthetic|measured`, `stack[]={id, kind: conductor|hole|dielectric, mask_layer|null, thickness_um, material_type, planarization_factor?}`, `source_stages[]={stage_id, after_row, semantics, surface_model, fab_distribution_layer}`, `contact_applicable_stages`, `particle_sizes_um`, `net_map?`, `pair_policy?`다. 여기에 particle-sim 행 변환 규칙을 붙인다. 기존 `physical_stack`/`stack` 투영 동일성 검사는 v1 L8에 그대로 둔다.

### B2. CNT "개구 후·충전 전" stage를 particle-sim이 표현하지 못해 계약이 모순된다
- 근거: adapter는 CNT를 두께 0.02 µm의 `patterned: False` 평막 행으로 만든다(`src/layout_electrode_extractor/particle_sim_adapter.py:108-122`). particle-sim의 landing surface는 `lands_after_layer` 행의 `z_top`이다(`particle-sim/src/particle_sim/io/stack.py:55-75`). 따라서 `lands_after_layer=CNT1`은 열린 홀이 아니라 평막 위에 착지하는 것으로 모델링된다. v1 L8은 이 stage의 nominal 의미를 기록하라고 하면서, simulator 표현 범위 밖의 단계는 거부하거나 미지원으로 표시하라고도 한다. 두 지시가 같은 stage에 동시에 걸린다. 게다가 contact row마다 적용 step이 1개 이상이어야 한다(`particle-sim/src/particle_sim/schema.py:450-451`). v5 L53은 METAL1 이후 CNO를 자동으로 긍정하지 말라고 한다.
- 실패 시나리오: CNT stage를 미지원으로 두면 contact row에 붙일 수 있는 합법적인 step이 하나도 없다. 그러면 `validate-input`이 실패하고 100홀 수락 기준을 달성할 수 없다. 반대로 CNT stage를 emit하면 `validate-input`은 통과하지만 의미상 거짓인 CNO 적용이 조용히 섞인다.
- 요구: profile별로 명시 결정한다. 권장안은 두 가지다. synthetic profile은 CNT stage를 emit하되 provenance에 `surface_semantics: "flat_film_approximation_unsupported"`를 기록하고, contact 적용 step은 CNT stage로만 제한한다. measured profile은 외부 schema 확장 전까지 CNT stage를 거부한다. legacy 모드(`SOURCE_AFTER_TOP_CONDUCTOR`)는 기존 동작을 유지한다고 명시한다.

### B3. CLI 모드와 32개 입경을 어느 Task가 담당하는지 불명확하다
- 근거: v1 L7의 "mixed CNT1의 기본 export는 오류 대신 명시적인 synthetic test profile을 호출했을 때만 가능"은 문장이 모호하다. 현재 CLI에는 `--config`가 없다(`src/layout_electrode_extractor/cli.py:39-43`). 현재 export는 `particle_sizes_um: [1.0]`로 고정돼 있다(`particle_sim_adapter.py:264`). 32개 지름은 v1 L11의 계약에만 있고 P0/P1/P2/P3 중 어느 Task의 수락 기준에도 없다. I1(v1 L19)만 32 size 입력을 전제한다.
- 실패 시나리오: P0/P1이 legacy 입경 `[1.0]`을 유지한 채 settle된다. 그러면 I1에서 32 size 입력을 만들 수 없거나, 코디네이터가 수락 범위 밖의 adapter 변경을 새로 떠안는다.
- 요구: 세 모드를 표로 고정한다. (a) config가 없으면 legacy 단일 pair이고, mixed CNT1은 지금처럼 거부하며 `[1.0]`을 유지한다. (b) config에 `profile=synthetic`이 있으면 mixed CNT1 분할을 허용하고 32 입경을 emit하며 가정 표시를 붙인다. (c) `profile=measured`에서 실측값이 누락되면 출력 전에 실패한다. 32 입경 emit과 순서·중복 검증은 P0 수락 기준에 넣는다.

## 차단 finding — E1/E3 외부 시안 Dispatch 전

### X1. dedup 키가 particle-sim 계산 모델과 맞지 않고, "동일 연결" 관계가 정의되지 않았다
- 근거: particle-sim nominal은 sample이나 사건 목록이 아니다. unit마다 (step, 입경) 별로 **중심 픽셀 map**을 만들고 합산한다(`pipeline.py:331-365`, `aggregation/critical_area.py:10-30`). CNO unit은 `cno_unit_id(contact_id, lower, upper)` 단위의 link이고 홀 OR `any_hole`로 판정한다(`failure/contact_not_open.py:22-24,59-61`, `units.py:83-98`). open unit은 `open_paths.path_id`이거나 `AUTO_OPEN_<electrode>`다(`units.py:54-81`). v5 L59의 "sample/위치/크기·형상/step + 확정 회로 연결 ID"는 이 구조로 옮기는 규칙이 없다. net ID는 한 net 안의 여러 홀과 분기를 구분하지 못할 만큼 거칠다. "여러 가림 footprint의 union"(v5 L59, L75)은 입자 하나에 footprint 하나인 현재 모델에서는 빈 조건이다.
- 실패 시나리오: 한 net에 병렬 홀 두 개와 독립 open path 두 개가 있다고 하자. net 단위로 매칭하면 다른 경로의 open까지 CNO 우선으로 지워진다. 이는 v5가 요구하는 "다른 연결 open 보존"을 위반한다.
- 요구: E3 계약에 명시할 내용은 네 가지다. ① 매칭 단위는 `(step, diameter, centre_yx)` 픽셀이다. ② CNO 홀 또는 link에서 영향받는 open unit으로 가는 **명시 관계표**를 둔다. 출처는 config 또는 topology에서의 결정적 도출이고, 미정이면 unclassified로 남긴다. ③ `open_final = open ∧ ¬OR(관련 CNO)`를 쓰고, 원시 map과 관계표를 저장한다. ④ CNO 통계 단위가 홀별 50% 사건인지 기존 link `any_hole`인지 정하고, 둘 다 보고할지도 정한다.

### X2. 기존 auto-open에 full-cover CNO 제외 규칙이 이미 들어 있다
- 근거: `failure/auto_open.py:4-7`과 `:137-138`은 완전히 덮인 contact terminal을 open 비교에서 빼고 CNO로 취급한다. 이 동작은 v5 L13의 "CNO와 open 독립 계산 뒤 후처리 dedup"과 충돌한다. 기준도 새 50%가 아니라 full cover다.
- 실패 시나리오: 60%가 덮인 홀을 생각해 보자. 이 홀은 새 규칙으로 CNO이지만 auto-open에서는 terminal로 살아 있다. 반대로 100%가 덮인 홀은 open 원시 결과에서 이미 제거되어 있다. 그 결과 "원시 open"이 독립 계산 결과가 아니게 되고 dedup 대응표를 재현할 수 없다.
- 요구: E1/E3 범위에 `auto_open.py`를 넣거나(원시 계산에서는 CNO 제외를 끄는 옵션), auto-open을 지원 범위 밖으로 명시한다. 현재 adapter처럼 `open_applicable_steps_by_layer`를 빈 목록으로 두는 것이 기본값이어야 한다.

### X3. 독립 복사본 절차가 원본 읽기 전용 제약을 깰 수 있다
- 근거: v1 L3과 L18은 "무시 경로의 독립 복사본"만 말하고 방법을 정하지 않는다. AGENTS.md는 particle-sim `.venv`를 읽기 전용으로 재사용하라고 한다.
- 실패 시나리오는 세 가지다. `git worktree add`는 원본 `.git/worktrees`에 쓴다. 복사본을 원본 `.venv`에 `pip install -e`로 설치하면 원본 환경의 경로 해석이 바뀐다. 원본 테스트를 import하면 `__pycache__`나 `.pytest_cache`가 원본 트리에 생긴다. 어느 경우든 원본 status/SHA 기록과 "원본 무변경" 주장이 거짓이 된다.
- 요구: 복사본은 `git clone --no-hardlinks <원본> outputs/<새 ignored 경로>` 또는 `git archive`로 만든다. 실행은 복사본 전용 venv를 쓰거나 `PYTHONPATH=<copy>/src` + `PYTHONDONTWRITEBYTECODE=1` + `-p no:cacheprovider`로 한다. 전후로 원본의 `git status --porcelain`, HEAD, `.venv` 내 `particle_sim` 경로를 기록한다. 현재 untracked plan 파일이 있으므로 before/after 비교는 clean 여부가 아니라 동일성으로 판단한다.

## 비차단 finding

1. **중앙 창 집계와 instance별 unit.** `[300,900)²`은 정확히 한 unit 주기이므로, 중심 기준 합계는 주기 사건을 한 번씩 센다. 그런데 pair/CNO unit은 2×2 instance 단위다(`particle_sim_adapter.py:163-226`에서 전극 ID마다 unit이 생긴다). 이음선 근처 사건은 복사본마다 다른 unit에 나뉘어 들어간다. 따라서 instance별 CA는 부분값이다. 보고 기준을 전체 합 또는 주기 등가류(instance 좌표 mod lattice)별 합으로 고정하고, 분모를 600²·0.01 µm²로 둔다. 현재 분모는 `roi_area_um2` 전체다(`critical_area.py:28-30`).
2. **layer mask는 raw다.** `layer_masks`는 `raw_path`를 타일링한다(`particle_sim_adapter.py:184-189`). "모든 층 TR cut"은 전극·접점 mask에 대한 규칙이고, raw layer mask는 지형용이다(LINK-CHECK L36). 이 점을 계약에 적어야 worker가 layer mask를 cut으로 "고치는" 회귀를 막을 수 있다.
3. **수치 용어.** v1 L16의 "155 layer mask"는 layer_mask 행이 아니라 **층별 전극 row 155개**다(OPUS-PRACTICALITY L10, L91). layer_mask 행은 도체 6개다. net 101개와 pair 11,879개도 함께 baseline으로 적는다.
4. **홀 연결성 규약.** particle-sim은 `scipy.ndimage.label` 기본값인 4-연결로 홀을 라벨링한다(`geometry/contacts.py:87`). 추출 manifest는 8-연결일 수 있다. adapter에서 행마다 4-연결 성분 집합이 extractor 성분 집합과 픽셀 단위로 같은지 검증하는 항목을 P1 수락 기준에 넣는다. "8연결 반례"를 나열만 해서는 부족하다.
5. **provenance에 픽셀 수가 없다.** `contact_holes.components/raw_components`에는 raw/cut 픽셀 수가 없다. cut→raw 매핑은 대표 픽셀 하나로 한다(`engine.py:145-160`). 부분 절단과 소실은 P1이 raw/cut mask에서 성분별로 직접 계산해야 한다. 소실된 raw 홀은 `raw_components`에만 나타난다. 양성 fixture는 이 경로를 전혀 거치지 않으므로(위 증거) 반례 fixture가 필수다.
6. **P1→E1 의존의 실제 범위.** particle-sim은 cut contact mask만 받고, schema가 `extra="forbid"`라 raw provenance를 manifest에 넣을 수 없다. 권장안은 부분 TR 절단 홀을 adapter에서 거부하고 provenance는 sidecar JSON으로 남기는 것이다. 그러면 E1은 ROI 외곽 잘림만 다루면 된다. E1 core 단위 테스트는 P1과 독립적이고, fixture 통합만 P1에 의존한다. v1 L18의 "실제 의존"은 이 범위로 좁혀 적는다.
7. **CNO 가림 footprint와 margin.** `particle_footprint`는 `radius+contact_margin`을 포함한다(`failure/open_failure.py:218-226`). 50% 판정의 분자를 순수 입자 disc로 할지 margin을 더한 disc로 할지 E1에서 정한다. support gate(v1 L12)도 같은 정의를 쓴다.
8. **export 중단과 재시도.** 출력 폴더를 만든 뒤 쓰는 도중 I/O 실패가 나면 불완전한 폴더가 남는다(`particle_sim_adapter.py:180-191`). 재시도는 `FileExistsError`로 막힌다(L145-146). 형식 검증 실패는 폴더 생성 전에 처리되지만, 소비자는 불완전 출력을 구별할 수 없다. 임시 sibling에 쓴 뒤 rename하는 방식이나 완료 marker를 권장한다. I1 재시도는 새 경로로 한다.
9. **auto-open ROI terminal.** auto-open은 2×2 외곽 run을 terminal로 쓰고, 그 run이 덮이면 open으로 본다(`auto_open.py:52-60,130-133`). 확정 net과 단자가 없으면 `open_applicable_steps_by_layer`는 계속 빈 목록이어야 한다. 이 내용을 P2 수락 기준에 명시한다.
10. **I1 계산량.** legacy short hotspot은 step과 무관하게 pair×size 전부에 대해 계산된다(`pipeline.py:300-330`). 11,879 pair × 32 size 조합이므로 bounded probe의 pair 부분집합과 제외 사유를 사전에 고정한다.
11. **기준 표기.** v1 L3은 기준을 `762a239`로 적지만 검토 대상 문서는 `f214cd8`에 있다. 개정본과 checkpoint에서 검토한 commit을 명시해 PASS 대상을 고정한다.

## 요구사항 추적 요약

| 요구 | v1/v5 반영 | 비고 |
| --- | --- | --- |
| 2×2·0.1 µm/px·all-layer TR cut·TR 40 | 반영 | 비차단 2(raw layer mask) 명시 필요 |
| 무마스크 ILD source 0개 | 반영 | B1 형식, B2 CNT 의미 |
| 32 지름 | 계약 반영, Task 미배정 | B3 |
| 개별 홀 전체 면적 50% | 반영 | 비차단 4·7, X2 |
| 중앙 창·support gate·open 비국소 | 반영 | 비차단 1 |
| CNO/open dedup | 원칙만 반영 | X1 |
| periodic identity/halo 재계산 | 반영 | 해당 없음 |
| 합성 대 물리 구분 | 반영 | B2 provenance |
| 중단·재시도 | 원칙 반영 | 비차단 8, X3 |
