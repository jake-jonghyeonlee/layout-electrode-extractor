# 구현 실행계약 v2 좁은 재검토 (B1–B3) — 2026-09-24

- 검토자: Claude Opus 5.5 (`claude-opus-5-5`, high), 읽기 전용. Run `run_5463d205f39d`, Task `task_5979401f5b09`, Dispatch `ctx_1120f8acd148`.
- 대상: extractor commit `bf4e8c2`의 [IMPLEMENTATION-PLAN-v2](IMPLEMENTATION-PLAN-v2-20260924.md). 기준 finding은 [검토 v1](IMPLEMENTATION-PLAN-REVIEW-v1-20260924.md)의 B1–B3다. 관련 호출부는 읽기만 했다: extractor `cli.py`, `particle_sim_adapter.py`, `schema.py`, `synthetic.py`와 particle-sim `aae492a`의 `schema.py`, `cli.py`, `pipeline.py`, `geometry/contacts.py`.
- 범위: P0/P1 편집 Dispatch를 시작해도 되는지만 판정한다. X1–X3는 E 단계 gate라서 v2가 P0/P1과 직접 모순되는지만 확인했다. 테스트는 다시 돌리지 않았다. 이 파일만 새로 썼고 `FINAL-REPORT.ko.md`와 particle-sim은 건드리지 않았다. particle-sim은 여전히 HEAD `aae492a`이고 untracked plan 파일 하나만 있다.

## 판정

**PASS: P0/P1 편집 Dispatch를 시작해도 된다.** B1–B3는 모두 구체적으로 해소됐다. 남은 blocking finding은 없다. 아래 C1–C4는 v2 문장이 두 가지로 읽히는 부분이다. 코디네이터가 P0/P1 Task 계약에 한 줄씩 적어 고정하면 되고, 이를 위해 계획을 다시 검토받을 필요는 없다. 고정하지 않으면 worker가 둘 중 어느 쪽으로 구현하든 수락 기준을 통과할 수 있어서, I1 단계에 가서야 틀어진 것이 드러난다. 이 PASS는 `bf4e8c2`의 v2 문서에만 유효하다.

| v1 finding | v2 반영 위치 | 상태 |
| --- | --- | --- |
| B1 config 형식 | L8: 최소 JSON 필드, 타입과 범위, 중복·extra 필드 거부, projection 동일성, hole/dielectric/conductor 행 변환 규칙, `after_layer` 제약, 가정값 synthetic 예시를 P0 산출물로 지정 | 해소 (C3는 세부 고정) |
| B2 CNT stage 모순 | L9: synthetic은 CNT stage를 emit하고 `flat_film_approximation_unsupported`를 기록하며 contact 적용 단계를 CNT stage로만 제한. measured는 거부. legacy는 유지. L8은 `semantics` 값을 두 개로 제한 | 해소 (C2는 세부 고정) |
| B3 CLI 모드와 32 입경 | L7: `--config` 옵션과 (a)/(b)/(c) 모드 표. L17: 세 모드 시험, 32 지름 목록과 순서·중복 검증을 P0/P1 소유로 지정 | 해소 (C1은 세부 고정) |

확인한 정합성은 다음과 같다.
- (a) 모드(legacy)는 현재 코드와 일치한다. 한 물리 CNT 층에 endpoint pair가 둘 이상이면 거부하고(`particle_sim_adapter.py:152-157`), 입경은 `[1.0]`이고(L264), 적용 단계는 `SOURCE_AFTER_TOP_CONDUCTOR`다(L203, L228-235).
- synthetic에서 contact row마다 CNT stage를 붙이는 방식은 particle-sim 검사를 통과한다. 적용 단계 목록이 비어 있지 않아야 하고 선언된 step이어야 한다는 조건(`particle-sim schema.py:450-455`), `lands_after_layer`가 stack에 있어야 한다는 조건(L295-300)을 모두 만족한다. nominal pipeline은 step 순서로 contact를 거르지 않는다(`pipeline.py:337-346`).
- hole row를 lower와 upper 사이에 두어야 한다는 particle-sim 조건(`schema.py:445-449`)이 있다. L8은 masked projection을 extractor `physical_stack`과 같게 강제한다. extractor는 이미 `lower < hole < upper`를 강제하므로(`extractor schema.py:183-186`) 이 조건은 자동으로 성립한다.
- 최신 fixture는 mask 층이 8개다(`synthetic.py:122-123`: 도체 6 + CNT 2). L8의 "8개 mask 층"과 L17의 "6 raw `layer_mask` row"와 맞다.

## P0/P1 Task 계약에 고정할 조건 (비차단)

### C1. `particle_sizes_um` 설정값이 전체 32개와 정확히 같아야 하는지, 부분집합도 되는지 정하지 않았다 (B3 잔여)
- 근거: v2 L8은 `particle_sizes_um`을 config 필드로 둔다. L7(b)와 L12는 "확정 32 지름만"이라고 한다. L17은 "32 지름 목록과 순서·중복 검증"을 P0 소유로 둔다. 그런데 L20의 I1 bounded probe는 입경 1·30·40·50 µm만 쓴다. particle-sim `simulate-nominal`에는 입경을 고르는 옵션이 없고(`particle-sim cli.py:384-387`) manifest의 입경 전체를 돈다(`pipeline.py:267`).
- 실패 시나리오: worker가 "정확히 32개와 같아야 함"으로 구현한다고 하자. 그러면 I1이 4-입경 probe를 만들려면 export된 `product.yaml`을 손으로 고쳐야 하고, 이는 adapter 검증을 우회한다. 반대로 임의 입경을 허용하면 "32개만"이라는 규칙이 깨진다. 두 구현 모두 L17 수락 기준을 통과하므로 문제는 I1에서야 드러난다.
- 고정안(권장): 필드를 생략하면 32개 전체를 쓴다. 값을 주면 32개 집합의 비어 있지 않은 엄격 증가 부분집합이어야 하고, 아니면 출력 전에 실패한다. 부분집합을 썼다면 sidecar에 표시한다. synthetic 수락 시험은 32개 전체로 한다. 다른 방법으로, 정확히 32개만 허용하고 I1 probe manifest를 만드는 변환 절차를 I1 계약에 적어도 된다. 둘 중 하나를 고르면 된다.

### C2. measured 모드에서 contact row가 있을 때의 동작과 synthetic의 CNT stage 필수 여부를 명문화해야 한다 (B2 잔여)
- 근거:
  - particle-sim은 모든 contact row에 적용 단계를 1개 이상 요구한다(`schema.py:450-451`).
  - v2 L9는 measured 모드에서 CNT 개구 stage를 거부한다. 따라서 measured 모드에서 contact row가 검증을 통과하는 방법은 `contact_applicable_stages`에 CNT가 아닌 stage(예: METAL1 `after_pattern`)를 명시하는 것뿐이다. 이는 v5가 "METAL1 뒤 CNO를 자동 긍정하지 않는다"고 한 경우와 사실상 같다.
  - L8은 `source_stages`를 "명시된 부분집합"으로 허용한다. 그래서 synthetic config에서 CNT1 stage를 빼 버릴 수도 있다.
- 실패 시나리오: 두 가지다.
  - measured config에 contact를 METAL1 stage로 붙이면 validate-input은 통과한다. 결과적으로 의미상 거짓인 CNO가 "measured"라는 이름으로 나간다.
  - synthetic에서 CNT1 stage를 빼면 CNT1 contact row에 붙일 step이 없다. adapter가 이를 미리 거르지 않으면 출력 폴더가 만들어진 뒤 validate-input에서야 실패한다.
- 고정안:
  - measured 모드: contact row가 하나라도 있으면 출력 전에 거부하고, 사유로 "CNT open stage unsupported"를 남긴다. P0의 measured 시험은 거부 경로만 다룬다.
  - synthetic 모드: contact row가 있는 hole layer마다 `semantics=cnt_open_before_fill_approximation`인 stage가 정확히 하나 있어야 한다. `contact_applicable_stages[hole]`은 그 stage 하나와 정확히 같아야 한다. 어긋나면 출력 전에 실패한다.

### C3. config 행 필드끼리의 중복 표현과 교차 검사를 고정해야 한다 (B1 잔여)
- 근거:
  - L8은 `kind`와 `patterned`/`material_type`/`mask_layer`를 모두 입력으로 받는다. 동시에 hole 행은 "non-patterned inorganic으로 변환", conductor 행은 "patterned conductor"라고 정한다. 입력값이 이 변환과 충돌할 때(hole 행에 `patterned=true`나 `organic`) 오류인지 덮어쓰기인지가 없다.
  - extractor의 `physical_stack`은 선택 필드인데(`extractor schema.py:81, 140-155`), L8의 projection 동일성 검사는 이 필드를 전제로 한다.
  - particle-sim은 `surface_model=partial`이면 landing 층 이하의 모든 비도체 행에 `planarization_factor`를 요구한다(`particle-sim schema.py:385-399`). L8은 "simulator가 지원하는 값만"이라고만 적었다.
- 실패 시나리오: worker가 충돌하는 값을 조용히 덮어쓴다고 하자. 그러면 sidecar에 적힌 config와 실제로 emit된 stack이 달라진다. 또 `partial` config는 adapter를 통과한 뒤 validate-input에서야 실패한다. 이는 "출력 전 실패" 계약을 어긴다.
- 고정안:
  - `kind`가 나머지 값을 결정한다. 충돌하는 명시 값은 오류로 처리한다.
    - hole: `mask_layer`가 있어야 하고, `patterned=false`, material은 비도체다.
    - conductor: `patterned=true`, `material_type=conductor`, `mask_layer`가 있어야 한다.
    - dielectric: `mask_layer=null`, `patterned=false`, material은 비도체다.
  - `--config`를 주었는데 extraction에 `physical_stack`이 없으면 출력 전에 거부한다.
  - P0는 `surface_model`을 `flat`으로 제한하거나, `partial`의 planarization 교차 규칙을 adapter에서 미리 검사한다.

### C4. 분할 contact ID와 endpoint 전극의 net 조건을 particle-sim 제약에 맞춰야 한다 (P1)
- 근거:
  - particle-sim은 `contact_id`에 `:`와 `__`를 쓰지 못하게 한다(`schema.py:428-429`).
  - particle-sim은 각 홀의 lower 전극과 upper 전극이 같은 `net_id`여야 한다(`geometry/contacts.py:106-109`). 현재 임시 net은 추출 전극 ID이므로(`particle_sim_adapter.py:172`) 이 조건을 만족한다.
  - particle-sim의 effective 픽셀은 홀 안에서 아래 전극과 위 전극이 동시에 겹치는 픽셀이다(`contacts.py:110-115`).
- 실패 시나리오: 두 가지다.
  - worker가 `CNT1__ACTIVE` 같은 분할 ID를 만든다. adapter 검사는 통과하지만 validate-input에서 실패한다.
  - P1이 sidecar에 넣는 effective 픽셀 수를 다른 정의로 계산한다. 그러면 E1이 effective와 전체 홀의 차이를 비교할 때 기준이 어긋난다.
- 고정안:
  - 생성하는 contact ID는 `[A-Za-z0-9_-]`만 쓰고 `__`를 금지한다. adapter가 이를 출력 전에 검사한다.
  - effective 픽셀 수는 위의 particle-sim 정의로 계산한다.
  - 수락 기준에 v5 P1 행의 "기존 legacy에서 16홀" 양성 대조군을 명시한다. v2 L17에는 legacy 양성만 있고 홀 수가 없다.

## X1–X3와 P0/P1의 직접 모순 확인

모순은 없다.
- L10과 L12는 auto-open을 끄고 `open_applicable_steps_by_layer`를 빈 목록으로 둔다(X2). 이는 현재 adapter 출력(`particle_sim_adapter.py:261-263`)과 같다.
- L12의 명시 관계표와 사건 키(X1)는 P2와 E3에서 쓸 필드다. P0/P1은 "P2 필드가 없으면 합성 임시 net과 open 미설정 상태를 유지한다"(L8)고만 하므로 서로 충돌하지 않는다.
- L19의 `git archive` 복사본 절차(X3)는 P0/P1이 소유한 파일을 건드리지 않는다.
- X1–X3를 실제로 해소했는지는 E1/E3 gate에서 따로 판정한다. 이 검토는 그 판정을 대신하지 않는다.
