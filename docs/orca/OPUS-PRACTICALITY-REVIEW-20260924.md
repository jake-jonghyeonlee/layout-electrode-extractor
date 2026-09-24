# Opus 5.5 실용성 독립 검토 — 2026-09-24

- Run `run_5463d205f39d`, Task `task_e317341a234d`, Dispatch `ctx_bdbd92049991`. 검토자: Claude Opus 5.5 high. 읽기 전용이며 제품 코드, particle-sim, 추적 출력은 바꾸지 않았다.
- 대상: `main` `d8d80a1` (제품 코드 `79a4d68`), particle-sim `aae492a` (읽기 전용). 작업 트리는 추적 파일이 깨끗한 상태에서 시작했다. 검토 중 `docs/orca/CHECKPOINT.md`가 수정 상태로 나타났지만 검토자가 바꾼 것이 아니므로 그대로 두었다. `docs/orca/FINAL-REPORT.ko.md`는 건드리지 않았다.
- 기준 재확인: `pytest -q -p no:cacheprovider` 결과 **53 passed**.
- 표기: **[사실]**은 코드 줄 또는 이번에 실행한 출력으로 확인한 내용이다. **[추론]**은 코드에서 끌어낸 판단이지만 실행해 보지 않은 것이다. **[미검증]**은 자료나 실행이 없어 판단할 수 없는 것이다.

## 0. 결론

1. **`validate-input` 수준 연계는 작고 범위가 정해진 adapter 변경으로 가능하다. [사실, scratch probe]** 현재 추출물 `outputs/particle-sim-link-check-20260924/extraction`에서 CNT1을 `contact_holes.components[].contact_rule_index`로 나눠 contact row 두 개(두 row 모두 `hole_layer=CNT1`)를 만들었다. 이 임시 export에 particle-sim `validate-input`을 실행한 결과는 다음과 같다: **exit 0**, `status: ok`, 1200×1200, 전극 155개, net 101개, pair 11,879개, contact hole **100개**, CNO link 54개, 미해결 pair 0개. particle-sim schema나 loader를 바꿀 필요는 없었다. 이 결과는 **scratch probe**이며 제품 export가 통과했다는 증거가 아니다.
2. **물리 simulation 수치로 쓰는 것은 아직 불가하다.** 우선순위 blocker는 세 가지다.
   - (B3) 추출 전극 ID를 그대로 `net_id`로 쓴다. 그래서 자기 TR 때문에 잘린 같은 gate 선 조각 **40쌍**이 서로 다른 net의 short pair로 선언된다(간격 2.1 µm).
   - (B4) CNO가 `SOURCE_AFTER_TOP_CONDUCTOR` 단계에 걸려 있다. 이 시점에는 hole이 이미 채워져 있으므로 물리적으로 모순이다.
   - (B2) particle-sim은 **빠진 hole을 발견하지 못한다**. hole 하나를 빼도 `status: ok`였다.
3. 현재 fixture는 우연히 안전하다. METAL1·CNT가 TR과 겹치지 않고, hole이 중간 도체층을 지나지도 않는다. **[사실]** 하지만 extractor에는 이 둘을 막는 검사가 없다. 반례 세 개가 모두 **issue 0개, exit 0**으로 통과했다. **[사실]**

## 1. 사용한 증거와 probe 방법

| 증거 | 값 |
|---|---|
| 추출 manifest | 전극 101개(rank 0: 96, rank 1: 5), TR 40개, raw hole 성분 25개/unit, hole instance 100개/2×2, issue 0개 |
| TR 층별 교집합(unit) | `METAL1∩TR = 0`, `CNT1∩TR = 0`, `CNT2∩TR = 0`. GAT1/GAT2/GAT3/ACTIVE/OACTIVE에서 1600/800/1600/1600/2400 px 제거 |
| 중간 도체 관통 | raw hole 25개 모두 `physical_stack`상 lower와 upper 사이 도체층과 0 px 겹침 |
| hole의 lower 밖 돌출 | CNT1 4개(각 30 px), CNT2 6개(30 px 4개, 105 px 2개)가 ACTIVE/OACTIVE 끝단 밖으로 나감. upper 밖 돌출은 0 |
| TR로 선언하지 않은 도체 겹침 | ACTIVE∩METAL1, GAT1∩METAL1, GAT2∩METAL1, OACTIVE∩METAL1만 있음(모두 층간 절연 전제). GAT2∩ACTIVE, GAT3∩ACTIVE, GAT1∩OACTIVE는 0 |
| 기존 로그 | `logs/mixed-export.log`: exit 2 거부. `logs/legacy-validate-input.log`: 옛 fixture의 양성 대조군(98 전극, 4,743 pair, 16 hole) |

Scratch probe는 세션 scratchpad(비영구)에서만 실행했다. 제품 `outputs/`와 particle-sim에는 아무것도 쓰지 않았고, bytecode 캐시도 끄고 실행했다.

- `probe_export.py <variant>`는 현재 adapter와 같은 규칙으로 export를 만든다. 전극은 `<E>_<layer>`, `net_id`는 `<E>`, 모든 다른 net pair를 넣고 raw layer는 2×2로 타일한다. 차이는 두 가지다. `_stack_layers`에는 hole layer별로 중복을 없앤 rule만 넘기고, CNT1 cut 성분은 `contact_rule_index`에 따라 별도 mask로 나눈다. contact ID는 `CNT1_R0_ACTIVE_METAL1`, `CNT1_R1_GAT2_METAL1`, `CNT2_R2_OACTIVE_METAL1`이다.
- `cx.py`는 `make-synthetic` 원본을 scratch에서 변형한 뒤 `extract`를 실행한다.

| probe | 결과 |
|---|---|
| `split` (정상 분할) | union 검사 결과 누락 0, 초과 0. `validate-input` exit 0, `ok`, holes 100, links 54, unresolved 0 |
| `drop_one_hole` (GAT2–METAL1 hole 하나 제거) | adapter union 검사 결과 **누락 225 px**. 그래도 **`validate-input` exit 0, `ok`, holes 96** → particle-sim은 hole 누락을 잡지 못함 |
| `full_mask_both` (두 row 모두 CNT1 전체 mask) | exit 2: "아래 전극 0개, 위 전극 1개" |
| `swap_rule` (GAT2 row에 ACTIVE hole) | exit 2: "아래 전극 0개" |
| `dup_id` (두 row의 `contact_id=CNT1`) | exit 2: "contact_id 'CNT1'이 중복" |
| `hole_in_tr` (ACTIVE–METAL1 hole을 TR 중심에 추가, seed 선언) | extract **exit 0**, raw hole 26 → cut hole 25, **issue 0**. 선언한 hole이 조용히 사라짐 |
| `hole_through_gat2` (기존 hole (180,55) 위에 GAT2 stub 추가) | extract **exit 0**, TR 40(GAT2∩ACTIVE는 TR pair가 아니므로 제외), **issue 0**. 실제로는 hole이 GAT2를 관통해 short가 됨 |
| `metal_over_tr` (METAL1 strap이 GAT1×ACTIVE TR 위를 지남) | extract exit 0, raw strap 1개 → cut 성분 **2개**, 전극 101 → 109, **issue 0** |

## 2. 질문 1 — 실제 적용 가능성, 필수 blocker와 선택 개선

### 필수 blocker (순위순)

**B1. adapter 분할 export가 없다(`validate-input` 차단).**
- [사실] `particle_sim_adapter.py:152-157`이 hole layer가 중복된 rule을 거부한다.
- [사실] 허용되는 경로에서도 `:194-210`은 `contact_id=hole`과 CNT 전체 cut mask 하나를 쓴다.
- [사실] 분할한 row를 그대로 `_stack_layers`에 넘기면 `:108-113`이 같은 hole layer를 두 번 방출하려다 `duplicate layer ID`로 실패한다. 따라서 stack을 만들 때 **hole layer별로 한 번만 방출**하도록 바꿔야 한다. 두 rule의 upper가 모두 METAL1이라 위치는 같다.
- [사실] 이 변경만으로 `validate-input`은 통과한다(`split` probe).

**B2. partition 검사를 adapter가 직접 해야 한다.**
- [사실] particle-sim은 contact mask마다 성분별 endpoint만 검사한다(`particle-sim/src/particle_sim/geometry/contacts.py:95-115`). hole layer의 원래 mask와 비교하는 union·coverage 검사는 없다(`io/masks.py:322-326`).
- [사실] 그래서 `drop_one_hole`이 `ok`로 통과한다. 누락된 hole은 CNO 단위와 auto-open 단자에서 빠지고, 이는 계산 결과의 조용한 과소평가로 이어진다.
- 필요한 검사: hole layer마다 ① row mask끼리 겹치지 않음, ② union이 `cut_layers/<hole>.png`를 2×2로 타일한 것과 정확히 같음, ③ 각 cut 성분이 정확히 한 row에 속함, ④ 각 row의 성분이 모두 같은 `(lower, upper)`를 가짐, ⑤ 빈 row 없음. 빈 row가 있으면 particle-sim이 "mask가 비어 있습니다"로 실패한다(`contacts.py:88-94`).

**B3. net 정체성이 물리 net이 아니다(pair 분류가 왜곡됨).**
- [사실] `particle_sim_adapter.py:172`가 `net_id = electrode["id"]`를 쓰고, `:212-226`은 net이 다른 모든 pair를 short 후보로 넣는다.
- [사실] `engine.py:388`은 TR union을 **모든 층**에서 제거한다. 그래서 GAT 선도 자기 TR에서 끊긴다. 예: `E00003`(R bus 조각)은 rank 0이다.
- [사실] TR 40개의 `terminal_adjacency` gate 쪽 조각 쌍 40개가 모두 `split` probe에서 `declared` lateral_short pair였고, 최소 xy 간격은 모두 **2.1 µm**였다. 지름이 약 2.1 µm보다 큰 도전성 이물이 TR 위에 떨어지면 같은 gate 선의 두 조각을 "short"로 센다. 물리적으로는 같은 net이다.
- 계약 문서도 이 분할을 알고 있다(`docs/orca/IMPLEMENTATION-CONTRACT.md:53-54` "one schematic net → multiple output electrodes. Allow one-to-many"). `circuit.py:137-141`에도 gate 조각 net 전파 로직이 있다. 그러나 adapter는 이것을 쓰지 않는다.
- ACTIVE/OACTIVE의 S/D 분리(40쌍)는 물리적으로 맞다.
- 필요한 사용자 결정: pair 분류용 `net_id`를 확정 annotation이나 회로 대응에서 가져올지, 최소한 "같은 TR의 gate 쪽 조각끼리는 병합"할지 정해야 한다.

**B4. 이물 유입 단계가 물리적으로 맞지 않는다.**
- [사실] 모든 contact가 `SOURCE_AFTER_TOP_CONDUCTOR` 하나에 걸려 있다(`particle_sim_adapter.py:203`, `:228-235`, `lands_after_layer=METAL1`, flat).
- [추론] CNO(hole 막힘)는 CNT 식각 뒤, fill/METAL1 전 단계에서만 성립한다. METAL1 뒤에 떨어진 이물은 사실상 METAL1 층 short만 만든다.
- 단계와 적용 범위를 공정별로 나누기 전에는 CNO와 하부층 short 수치에 물리적 의미가 없다.
- [사실] auto-open은 `open_applicable_steps_by_layer`가 빈 목록이라 꺼져 있다(`particle_sim_adapter.py:261-263`, particle-sim `units.py:66-68`).

**B5. TR 전층 절단의 부작용이 조용히 지나간다(extractor 진단 누락).**
- [사실] `engine.py:146-161`은 cut 성분만 대표로 삼는다. 그래서 TR에 완전히 덮인 raw hole은 누락 경고 없이 사라진다(`hole_in_tr`).
- [사실] `test_contact_holes.py:127-138`은 이 동작을 **정상으로 고정**하고 있다.
- [사실] METAL1/CNT도 TR에서 잘린다(`metal_over_tr`: 1 → 2 성분).
- 사용자 지시("All layers are cut by TR")를 바꾸자는 것이 아니다. 필요한 것은 두 가지다: ① `contact_removed_by_tr`, `contact_partially_cut_by_tr`, `non_device_layer_cut_by_tr` issue를 내고, ② export가 이런 경우를 명시적으로 승인받지 않으면 거부하는 것이다.
- 현재 fixture에는 해당 사례가 0개다. [사실]

**B6. hole의 중간 도체층 관통과 선언되지 않은 GAT×channel 겹침을 검사하지 않는다.**
- [사실] contact edge는 선언된 lower/upper와의 겹침만 본다(`engine.py:75-86`, `_contact_issues` `:260-272`).
- [사실] `schema.py:183-186`은 `physical_stack` 순서만 검사한다.
- [사실] particle-sim도 hole layer가 endpoint 사이에 있는지만 본다(`schema.py:447-449`).
- `hole_through_gat2` 반례가 issue 0으로 통과했다. 현재 fixture는 0 px이다. [사실]

### 선택 개선 (실제 적용 전 권장)

- **O1 enclosure 검사.** hole 10개/unit이 channel 끝단 밖으로 30–105 px 나간다. [사실] 실제 공정이라면 DRC 위반이고 hole이 field/STI 위에 걸린다. particle-sim은 `hole ∩ lower ∩ upper`만 유효 pixel로 쓴다(`contacts.py:111-113`). 그래서 CNO 판정 면적이 원래 hole보다 작아진다. [추론]
- **O2 연결성 불일치.** particle-sim은 hole을 scipy 기본값인 **4-연결**로 label한다(`contacts.py:87`). extractor는 `connectivity: 8`을 허용한다(`schema.py:106-108`). 8-연결 manifest에서 대각선으로만 이어진 hole은 particle-sim에서 hole 두 개가 되고, 각각 endpoint 검사를 받는다. [추론] adapter는 8-연결 입력을 거부하거나 4-연결로 재검증해야 한다.
- **O3 `contact_id` 문자 제약.** particle-sim은 `:`와 `__`를 금지한다(`schema.py:428-429`). extractor ID 정규식은 `CNT__1` 같은 이름을 허용한다(`schema.py:15`). ID 합성 규칙과 검사가 필요하다.
- **O4 pair 규모.** 분할 뒤 per-layer 전극 155개와 pair 11,879개였다. [사실] `validate-input`에는 문제가 없었다. 실제 simulation 비용은 [미검증]이다. 거리 기반 제외는 particle-sim `excluded_electrode_pairs`에 사유와 함께 명시할 때만 허용해야 한다(최대 입경의 근거 필요). 1 µm 이하 간격 pair는 200개, 2 µm 이하는 280개였다. [사실]
- **O5 CNO 입도.** per-layer 전극은 서로 떨어진 섬들을 하나로 합친다. 예: `E00023_METAL1` = 좌측 trunk + bridge 2 금속. [사실, 형상 분석] 따라서 CNO link 하나에 직렬 경로의 hole들이 섞인다. any-hole 규칙(`contact_not_open.py:23-24`)이면 합집합 면적은 같지만 단위별 보고 의미는 달라진다. [추론]
- **O6 legacy rule 회귀.** 단일 rule(legacy) export는 분할 이후에도 byte 또는 수치가 같아야 한다(98 전극, 4,743 pair, 16 hole).

## 3. 질문 2 — 분할 CNT1 mask + 공유 `hole_layer` + 고유 `contact_id` + 공통 net이 충분한가

**`validate-input` 통과에는 충분하다 [사실]. 정합성에는 불충분하다.** 부족한 부분은 B2(partition), O2(연결성), O3(ID)가 채워야 한다.

- [사실] particle-sim은 `hole_layer`가 여러 row에 걸리는 것을 금지하지 않는다. `contact_id` 고유성만 검사한다(`schema.py:424`).
- [사실] endpoint는 명시 `lower_layer`/`upper_layer`로 결정된다(`resolve_contact_layers`, `schema.py:134-155`).
- [사실] 공통 net은 extractor가 hole을 두 endpoint에 모두 이어 하나의 전극으로 만들기 때문에 구조적으로 보장된다(`engine.py:75-86`).

반례와 각각의 검출 위치:

| 반례 | 현재 검출 위치 | 필요한 조치 |
|---|---|---|
| 누락 hole(mask에서 빠짐) | **없음** (`drop_one_hole` ok) [사실] | B2 union 검사 |
| 합쳐진 hole(raw 성분 하나에 서로 다른 endpoint seed) | extractor가 `duplicate or ambiguous hole assignment`로 거부(`engine.py:115-120`) [사실] | 유지 |
| cut 뒤 한 hole이 lower 두 개에 걸침 | extractor `multi_endpoint_contact` issue, particle-sim "아래 전극 2개" [사실: 코드] | issue가 있으면 export 거부를 명시 |
| 다른 net을 잇는 hole | extractor 구조상 불가(hole이 두 endpoint를 합침). 다만 B3 정책으로 net을 병합·분리하면 다시 생길 수 있음 [추론] | net 정책 변경 시 particle-sim 재검증 |
| 주기 인스턴스(unit seam을 걸친 hole) | extractor가 lattice coset으로 정체성 보존, 충돌 pair 거부(`engine.py:126-135`, test `:141-163`) [사실]. 2×2 **외곽** ROI 경계에서는 hole이 반쪽으로 잘림 → 유효 pixel 감소 → CNO full-cover가 쉬워짐 [추론] | 외곽 반쪽 hole 목록을 provenance에 기록, 회계 창(§4) 적용 |
| 무한 hole bus(rank ≥ 1 hole 성분) | `periodic_contact_network` issue. adapter는 provenance에만 남기고 export는 계속함(`particle_sim_adapter.py:295-305`) [사실] | 분할 export는 이런 issue가 있으면 거부 |
| TR에 완전히 덮인 hole | **없음** (`hole_in_tr`) [사실] | B5 |
| TR 경계에 걸려 일부 잘린 hole | issue 없음. cut 조각이 endpoint에 닿으면 통과(`hole_half_tr` probe, instance 104) [사실] | B5 경고, 유효 면적 기록 |
| 중간 도체 관통 | **없음** (`hole_through_gat2`) [사실] | B6 |
| 두 row에 같은 `(layer, lower, upper)`(seed가 나뉜 동일 pair) | extractor는 허용(test `:159-163`) [사실]. rule index 기반 ID면 row 두 개, pair 기반 ID면 row 하나 | pair 기반 `contact_id`(`<hole>_<lower>_<upper>`) 권장. CNO 단위가 rule 분할에 흔들리지 않음 |
| 8-연결에서 대각선으로만 이어진 hole | particle-sim이 hole 두 개로 셈 [추론] | O2 |

CNO 의미: CNO 단위 키는 `(contact_id, lower_electrode, upper_electrode)`이다(`contacts.py:43-44`, `:139-141`). lower 전극 ID에 이미 층 이름이 들어 있으므로(`E00023_ACTIVE`와 `E00023_GAT2`), 분할로 달라지는 것은 **ID 접두사뿐**이다. 묶는 방식 자체는 바뀌지 않는다. [사실: probe links 54, `CNT1_R0…`/`CNT1_R1…`] 병렬 중복 hole도 any-hole 규칙에서는 불량으로 계산된다. 예: bridge 1과 trunk 경로는 서로 병렬이다. 이 규칙은 보수적이고 잠정적이다(particle-sim 자체 `TODO_PHYSICS`).

## 4. 질문 3 — 물리 stack, 2×2 ROI, TR 절단, pair, CNO가 적용 범위를 어디까지 제한하는가

**물리 stack.** [사실] adapter는 `physical_stack`을 읽지 않고, 역할 기반 가정 stack을 새로 만든다(`particle_sim_adapter.py:17-138`). probe 결과 순서는 다음과 같다.

`ACTIVE, GAT1, GAT2, ILD_ACTIVE_OACTIVE, OACTIVE, GAT3, ILD_OACTIVE_METAL, CNT1, CNT2, METAL1`

- 이 순서는 hole이 endpoint 사이에 있어야 한다는 조건만 만족한다.
- ACTIVE–GAT와 OACTIVE–GAT3 사이에 절연층이 없다. [사실] 그래서 pair audit의 `min_z_gap`은 0이다.
- 두께 0.05/0.1/0.2 µm와 planarization 0.5는 가정값이다.
- CNT1은 두께 0.02 µm의 비패턴 판이다. hole 깊이, 식각 정지, liner/fill은 모델에 없다.
- 결론: 2-D 겹침과 순서는 제조 가능성이나 관통 안전성의 증거가 아니다. B6 검사는 2-D 필요조건일 뿐이다.

**2×2 유한 ROI와 주기 연결.** [사실] 전극 정체성은 lattice coset으로 정확히 정해진다(`periodic.py:82-93`, `engine.py:170-176`). 예를 들어 GAT1 20조각은 ROI 좌우 끝의 다른 instance를 구분한 결과다. 반면 particle-sim은 wrap이 없는 유한 이미지를 받는다(`particle_sim_adapter.py:293`).

[추론] ROI는 정확히 2주기(1200 px)다. 따라서 **이물 중심을 한 주기 창 [300, 900)²로 제한하고 반지름을 300 px(30 µm) 이하로 두면**, 이물이 덮는 영역은 모두 ROI 안에 있다. 그 안의 전극 정체성도 주기 해석과 같다. 그러면 단위당 critical area를 경계 오차 없이 셀 수 있다. particle-sim에 이런 회계 창 옵션이 있는지는 [미검증]이다. 없다면 후처리나 particle-sim 쪽 변경이 필요하고, 이는 이번 범위 밖이다. 창 없이 ROI 전체를 세면 외곽 조각과 반쪽 hole이 오차를 만든다.

**TR 전층 절단.** 사용자 지시이며 S/D 분리에는 맞다. 다만 세 가지 부작용이 있다.
- gate 선 분할: B3, 40쌍 [사실]
- METAL/CNT 분할: B5, 현재 fixture에는 0 [사실]
- adapter의 층 mask는 **raw**를 쓴다(`:184-189`). 즉 지형 계산에는 TR 영역이 포함되고 전극에서는 빠진다. 전극이 층의 부분집합이라는 particle-sim 조건은 만족한다(`masks.py` 5단계). TR 영역 pixel은 `layer_unassigned_regions`로 보고된다. 예: ACTIVE 6,400 px. [사실]

**이종 net pair 전수 분류.** 규모 자체는 blocker가 아니다(11,879 pair로 validate 통과). [사실] 의미는 B3에 달려 있다. 또 모든 pair가 단일 step·flat 가정에 묶여 있으므로(B4), 하부층 vertical_short의 물리적 해석이 불명확하다. [추론]

**CNO.** 위 §3 참조. full-cover + any-hole 기준, hole 유효 면적 축소(O1), step 불일치(B4) 때문에 CNO 수치는 현재 정성적 지표로만 쓸 수 있다.

## 5. 질문 4 — 최소 작업 순서와 acceptance

0. **결정(coordinator/사용자).** 아래 세 가지를 정한다. 이 결정은 W1–W3과 독립이므로 병행할 수 있다.
   - B3 net 정책: 확정 annotation 맵을 쓸지, TR gate 조각 병합을 기본으로 할지
   - B5: METAL/CNT의 TR 절단을 유지하되 경고할지, 거부할지
   - B4: 공정 단계 목록
1. **W1 adapter 분할 export (B1+B2, O2, O3).**
   - `contact_holes.components`로 hole layer별 row를 나눈다. `contact_id`는 `<hole>_<lower>_<upper>`로 하고 `:`/`__` 금지를 검사한다.
   - stack은 hole layer별로 한 번만 방출한다.
   - B2 partition 검사 ①–⑤를 넣는다.
   - issue 목록에 `periodic_contact_network`, `multi_endpoint_contact`, `missing_endpoint_contact`, `orphan_contact`가 있거나 `connectivity != 4`이면 출력을 만들기 전에 거부한다.
2. **W2 adapter 반례 테스트.**
   - 거부해야 하는 경우: hole 누락, 두 row 중복, 규칙 교차, 빈 row, 8-연결, ID 문자 위반, 금지 issue가 있을 때
   - 기존 legacy fixture export 결과(98/4,743/16 hole)가 그대로여야 한다.
3. **W3 extractor 진단 (B5, B6, O1).**
   - `contact_removed_by_tr`, `contact_partially_cut_by_tr`, `non_device_layer_cut_by_tr`
   - `hole_crosses_intermediate_conductor` (`physical_stack` 기준 lower와 upper 사이 도체층의 raw 겹침)
   - `undeclared_gate_channel_overlap` (TR pair로 선언되지 않은 GAT×ACTIVE/OACTIVE raw 겹침)
   - `hole_enclosure` (raw hole ⊄ raw lower 또는 upper)
   - `test_contact_holes.py:127`의 기대값을 "issue 발생"으로 바꾼다.
   - 이번 문서의 반례 `hole_in_tr`, `hole_through_gat2`, `metal_over_tr`를 회귀 테스트로 만든다.
4. **W4 net 정책 구현(결정 후).** 기본 fixture의 gate 조각 40쌍을 pair 목록에서 빼거나 같은 net으로 합친다. 변경된 pair 수와 사유를 `adapter-report.json`에 남긴다.
5. **W5 공정 단계.** 단계를 최소 두 개로 나눈다: CNT 개구 뒤(CNO 적용), METAL1 뒤(METAL1 short). 하부층 pair의 적용 단계는 공정 자료에 맞춰 정한다.
6. **W6 회계 창.** §4의 한 주기 창을 적용한다(particle-sim 기능 확인 뒤).

단계별 acceptance. 새 Git 무시 경로를 쓰고 기존 출력은 덮어쓰지 않는다.

```sh
.venv/bin/pytest -q && .venv/bin/ruff check .
OUT=outputs/split-contact-check-<date>
.venv/bin/layout-electrode-extractor make-synthetic $OUT/source
.venv/bin/layout-electrode-extractor extract $OUT/source/manifest.json $OUT/extraction
.venv/bin/layout-electrode-extractor export-particle-sim $OUT/extraction $OUT/export        # W1: exit 0
/Users/jonghyeonlee/git/particle-sim/.venv/bin/particle-sim validate-input \
  --product-config $OUT/export/product.yaml > $OUT/validate.json                              # exit 0
```

W1의 합격 기준은 현재 net 정책 기준이다.
- `validate.json`: `status == "ok"`, `contacts.holes == 100`, `unresolved_electrode_pairs == 0`, CNT1 row 2개(ACTIVE–METAL1, GAT2–METAL1), CNT2 row 1개, link 54개(ID 접두사만 다를 수 있음). 전극 155개와 pair 11,879개(W4 이후에는 변경분이 설명되어야 함)
- 분할 mask 검사: 같은 CNT1끼리 pairwise AND = 0, OR가 `np.tile(cut_layers/CNT1.png,(2,2))`와 byte 단위로 같을 것
- 반례 export는 모두 exit 2여야 하고 출력 폴더는 생기지 않아야 한다
- legacy 양성 대조군도 다시 export·validate해서 이전 수치와 같아야 한다

`validate-input` 이후 **물리 simulation을 주장하기 전에** 필요한 자료와 확인은 다음과 같다. 모두 [미검증]이다.
- 공정 흐름과 이물 유입 단계별 입경 분포·밀도(`fab_distribution_layer`)
- 층 두께, 게이트/층간 절연막 두께, 평탄화 계수
- CNT1 식각이 ACTIVE와 GAT2 두 깊이에 동시에 도달하는지, 식각 정지층과 liner/fill
- 이물 전도성, 매립 깊이, `contact_margin_um`
- CNO 부분 가림 기준과 병렬 hole 처리
- enclosure를 포함한 DRC 규칙
- **확정 netlist와 전극–net 대응**(B3). 현재 `naming_complete: false`
- 금속의 TR 위 통과가 실제로 끊기는지에 대한 사용자 판단

particle-sim `validate-input`의 경고 8개(`TODO_PHYSICS`)가 모두 해소되거나 명시적으로 수용되기 전에는 결과를 "합성 fixture 기능 시험"으로만 표기해야 한다.

## 6. 한계

- 제품 adapter를 구현하지 않았다. 분할 export는 scratch probe로만 확인했다.
- particle-sim `simulate-*`는 실행하지 않았다.
- 회계 창과 경계 오차 크기는 계산하지 않았다.
- CNO와 이종 pair의 물리적 타당성은 자료가 없어 판단할 수 없다.
- 유한 halo 안정화는 이번 검토에서 사용하지 않았다. 주기 정체성 판단은 `periodic.py`의 lattice 코드와 출력 coset에 근거한다.
