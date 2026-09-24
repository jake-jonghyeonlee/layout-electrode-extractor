# particle-sim 연계 수정계획 v2 — 2026-09-24

**상태:** 계획만 작성. 구현·simulation·새 worker Dispatch 없음. 기존 Orca Run `run_5463d205f39d`, 직접 문서 Task `task_f82d2c2df4c3`, 기준 `86e7a06`(제품 `79a4d68`). [현황 시험](PARTICLE-SIM-LINK-CHECK-20260924.md), [Opus 검토](OPUS-PRACTICALITY-REVIEW-20260924.md), [코디네이터 채택](OPUS-REVIEW-ADOPTION-20260924.md)을 최신 사용자 규칙으로 갱신하는 계획이다. `/Users/jonghyeonlee/git/particle-sim`은 읽기 전용이며 그 저장소의 변경은 **외부 의존 작업 제안**으로만 적는다.

## 1. 확정 규칙과 보존할 계약

| 주제 | 확정 내용 |
| --- | --- |
| 공정 stack | 층 두께와 절연막의 위치·물성은 추후 외부 입력으로 받는다. 마스크가 없는 절연층도 전체 공정 순서에는 포함한다. 임의의 두께·ILD를 실제값으로 확정하지 않는다. |
| 이물 유입 | **마스크가 있는 물리 층만** source stage 후보로 만든다. 마스크 없는 절연층의 source stage 수는 0이다. CNT1/CNT2는 도체 전극이 아니어도 접점 마스크가 있는 물리 층이다. |
| CNO | 가림률 **50% 이상**을 홀 가림 사건으로 판정한다. 50%는 포함한다. 분모와 여러 홀을 하나의 회로 단선으로 집계하는 방법은 아직 미정이다. |
| 추출 | 600×600 unit, 0.1 µm/px, 20 px 배선, 1200×1200 2×2 출력. TR 10개/unit·40개/2×2, **모든 층 TR 절단**, 두 물리 CNT 마스크, ACTIVE→CNT1→METAL1→CNT1→GAT2 브리지 두 개, RGB GAT 버스·수직 METAL trunk·주기적 인스턴스 정체성을 유지한다. |
| 연락·소유권 | extractor 저장소만 이후 승인된 구현 대상이다. particle-sim core의 CNO·ROI 변경은 해당 저장소 소유자의 별도 구현/검토가 필요하다. 구독 외 결제나 원격 게시를 전제하지 않는다. |

현재 extractor `physical_stack`은 **마스크가 있는 도체와 CNT/VIA ID만** 허용한다([schema.py:140–155](../../src/layout_electrode_extractor/schema.py#L140-L155)). 따라서 외부 입력의 **전체 process stack**에는 무마스크 절연층을 포함하고, 기존 `physical_stack`은 그중 마스크 층의 순서 투영으로 유지하는 안을 권장한다. 이를 동일 필드에 무리하게 섞지 않아 기존 manifest를 깨뜨리지 않는다. 전체 process stack의 conductor 투영은 현재 `stack`과 같아야 한다. 실제 절연층의 수·순서·두께는 입력 전까지 미정이다.

## 2. 사용자가 물은 “2×2 경계”의 정확한 뜻

원본 unit 600×600을 가로·세로 두 개씩 놓은 계산 이미지는 좌표 `x,y=0…1199`이다. **내부 이음선**은 `x=599/600`, `y=599/600`; **2×2 외곽 경계**는 `x=0/1199`, `y=0/1199`이다. 추출기는 반복 배선이 내부 이음선을 지날 때도 별도 반복 인스턴스 ID를 보존한다. particle-sim은 이 1200×1200 이미지를 유한한 ROI로 받아 바깥쪽을 자동으로 주기 연결하지 않는다. 그러므로 외곽에서 잘린 CNT 홀이나 배선에 대해 원래 unit 밖의 다음 반복 복사본을 particle-sim이 보지 못할 수 있고, ROI 경계를 단자로 쓰는 open 판정도 별도 선택이다([auto_open.py:1–7](../../../particle-sim/src/particle_sim/failure/auto_open.py#L1-L7), [terminal 구성](../../../particle-sim/src/particle_sim/failure/auto_open.py#L43-L65)). 현재 fixture의 `open_applicable_steps_by_layer`는 빈 목록이라 자동 open을 켜지 않는다. **중앙 `[300,900)×[300,900)` 600 px 창만 집계하는 안은 잠정 권장**이다. 이 창의 각 변에서 1200 px ROI 외곽까지의 여유는 **300 px = 30 µm = 0.5 unit**이다. 이는 창 밖의 주변 영역 전체가 1 unit 두께라는 뜻이 아니다. 입자 footprint·커널 지원 범위, 접점 홀 전체와 endpoint 유효 영역, CNO/open/short 판정이 참조하는 공간 범위, margin을 합쳐 외곽의 영향이 중앙 집계에 들어오지 않는지 따로 검증해야 한다. 입자 반지름만 `≤300 px`라는 조건으로 충분하다고 단정하지 않는다. 정확한 평가 창·허용 입력 범위·기여 면적은 아직 정하지 않았다. 유한 2×2 전체 집계나 별도 periodic simulation도 가능한 선택지다.

## 3. 코드상 현재 상태와 필요한 변화

| 범위 | 현재 코드·출력 사실 | 계획된 변경 또는 외부 의존 |
| --- | --- | --- |
| 접점 export | 같은 CNT1 물리 mask의 두 endpoint pair는 adapter가 출력 전에 거부한다([adapter:150–157](../../src/layout_electrode_extractor/particle_sim_adapter.py#L150-L157)). 임시 분할은 particle-sim `validate-input`을 통과했지만 누락 홀도 통과했다([재현 증거](../../outputs/opus-practicality-probes-20260924/README.md)). | extractor adapter에서 홀별 provenance로 **물리 CNT1 mask를 endpoint pair별 비중첩 export mask로 분할**하고 두 row는 고유 ID·동일 `hole_layer=CNT1`을 사용한다. CNT1/CNT2 원본 raw·TR-cut mask와의 union·누락·중복·빈 성분 검사를 출력 생성 전에 한다. |
| 출력 net | 현재 `net_id=추출 전극 ID`([adapter:163–178](../../src/layout_electrode_extractor/particle_sim_adapter.py#L163-L178)); 자기 TR에 의해 분리된 같은 gate 40쌍이 다른-net short 후보가 됐다. | **추출 전극 ID와 회로 net ID를 분리**한 확인된 대응표를 입력받는다. 전층 TR cut/전극 mask는 바꾸지 않는다. 원본 gate 연결과 확정 회로 annotation만 근거로 같은 net을 묶고, S/D나 비접점 층간 교차는 자동 병합하지 않는다. 미확정 pair는 불확실 상태/명시 제외 사유로 남긴다. |
| 공정 입력·source 단계 | adapter는 역할 기반 가정 ILD·두께를 만들고 단일 `SOURCE_AFTER_TOP_CONDUCTOR`에 모든 contact를 붙인다([adapter:17–138](../../src/layout_electrode_extractor/particle_sim_adapter.py#L17-L138), [contact row](../../src/layout_electrode_extractor/particle_sim_adapter.py#L193-L210)). particle-sim `ParticleSourceStep`는 `lands_after_layer`와 분포층 이름을 가진다([schema.py:58–64](../../../particle-sim/src/particle_sim/schema.py#L58-L64)); 현재 검사는 landing layer가 stack에 있는지만 확인한다([schema.py:295–300](../../../particle-sim/src/particle_sim/schema.py#L295-L300)). | 새 외부 process config가 마스크층과 무마스크 절연층의 전체 순서·두께·물성을 준다. adapter는 **mask source layer 목록에 있는 층에만** source step을 만들고, 무마스크 절연층에는 만들지 않는다. `lands_after_layer`는 해당 마스크 작업 직후의 nominal surface라는 뜻으로 제안하되 공정 stage 의미를 명시한다. 무마스크 stack row는 layer mask 없이 남는다. |
| CNO 50% | particle-sim core는 홀의 양쪽 전극에 공통으로 닿는 **effective pixels**만 보존([contacts.py:111–135](../../../particle-sim/src/particle_sim/geometry/contacts.py#L111-L135))하고, 현재는 그 픽셀을 **전부** 덮어야 CNO([contact_not_open.py:34–62](../../../particle-sim/src/particle_sim/failure/contact_not_open.py#L34-L62)). 같은 link의 여러 홀은 OR한다. | **particle-sim 외부 의존 작업:** CNO core에서 분모 정책이 확정된 뒤 `covered × 2 >= denominator`를 사용해 정확히 50% 포함, 49% 미달·51% 초과를 검증한다. 전체 물리 홀 분모를 고르면 `ContactHole`에 현재 effective 좌표와 별도로 원래 connected-component 좌표가 필요하다. 분모가 0이거나 유효 접점이 없으면 조용히 정상으로 처리하지 않는다. classification·경고·provenance도 50% 의미로 수정한다. 여러 홀 집계는 아래 미정 결정을 기다린다. |
| ROI/회계 | particle-sim의 CNO 계산은 full image shape의 중심별 맵을 만든다([contact_not_open.py:48–62](../../../particle-sim/src/particle_sim/failure/contact_not_open.py#L48-L62)). 현재 adapter는 주기적 경계조건을 전달하지 않는다. | 외곽 처리 선택 후 평가 중심 영역과 면적 분모를 같은 창으로 제한하는 방안을 검증한다. particle-sim에 평가 창 설정이 없으면 외부 의존 작업 또는 검증 가능한 후처리로 표시한다. |

**stage 의미 제안(아직 공정 확정 아님):** ACTIVE/GAT1/GAT2/OACTIVE/GAT3/METAL1처럼 패턴 도체 마스크가 있는 층은 그 층의 패턴 형성 후 노출된 표면에 유입되는 step을 둔다. CNT1/CNT2는 **개구 마스크 형성·식각 후, 충전 및 METAL1 형성 전** 유입되는 step으로 두어 CNO 적용 후보로 삼는다. METAL1 형성 뒤 step도 METAL1 마스크가 있으므로 유지할 수 있고, 그 단계의 short 등 해당 failure mode를 평가한다. METAL1 뒤 CNO의 적용 가능성은 공정·불량 기전 입력이 없으면 자동으로 긍정하거나 일괄 폐기하지 않는다. 무마스크 절연막은 stack z/topography에는 남지만 유입 step은 0개다. `lands_after_layer`가 개구 후·충전 전 상태를 충분히 표현하지 못한다면 particle-sim schema/공정 단계의 외부 확장이 필요하다([surface 순서](../../../particle-sim/src/particle_sim/io/stack.py#L60-L89)).

## 4. 아직 답변 대기인 세 결정

| 결정 | 선택지 | 잠정 권장과 구현 gate |
| --- | --- | --- |
| 50%의 분모 | A. 각 물리 CNT 홀의 전체 픽셀, B. 양 endpoint가 공통으로 겹치는 유효 픽셀, C. 여러 홀을 합친 면적 | **A를 잠정 권장:** 사용자 표현의 “CNT 영역”과 가장 가깝고 돌출·TR 절단을 숨기지 않는다. 단, raw 물리 홀인지 cut 홀인지도 정해야 한다. B는 현재 simulator 좌표와 맞지만 착지부 밖 픽셀을 제외해 50% 의미가 달라진다. C는 병렬 홀 의미가 섞인다. **사용자 답변 전 core 변경을 Dispatch하지 않는다.** 분모 선택과 raw/cut/effective 픽셀 수를 provenance에 모두 기록하도록 계획한다. |
| 2×2 바깥 경계 | A. 중앙 1-unit 평가+각 변 0.5-unit 여유, B. 유한 2×2 전체 평가, C. 외부 periodic 반복/별도 경계조건 | **A를 잠정 권장:** 중앙 `[300,900)²`의 각 변에서 외곽까지 300 px 여유를 둔다. 입자 footprint뿐 아니라 커널·접점 전체·판정 영향 범위·margin이 이 여유 안에 있는지 입경별로 증명해야 한다. B는 외곽 절단·half-hole 효과를 별도로 보고해야 한다. C는 particle-sim 확장 범위가 크다. **답변 전 ROI 구현 범위를 확정하지 않는다.** |
| 홀 CNO와 회로 단선 | A. 각 홀 50% 가림 사건과 net/회로 단선을 별개로 계산, B. 같은 link의 어느 홀 하나만 가려져도 전체 CNO | **A를 잠정 권장:** 병렬 금속 경로와 다중 홀에서 개별 CNO와 실제 단선을 구분한다. 현재 core는 B이다([OR 집계](../../../particle-sim/src/particle_sim/failure/contact_not_open.py#L58-L62)). **답변 전 link/circuit 집계 구현을 확정하지 않는다.** |

추가 확인이 필요한 입력은 실제 process stack 예시(무마스크 절연막의 순서·두께 포함), 각 mask layer별 이물 분포와 노출 시점, 확정 회로 net mapping, 그리고 위 세 결정이다. 질문은 source chat에서 이미 비동기로 요청 중이므로 중복 질문을 보내지 않는다.

## 5. 이후 구현 Task 초안과 실제 의존성

**이번에는 어떤 Task도 구현 Dispatch하지 않는다.** 결정이 오면 plan v3로 갱신하고, 새 구현 Task를 Orca에 저장한다. 한 편집 worker와 한 read-only worker 한도를 지킨다.

| 초안 | 저장소·파일 소유 범위 | 결과 / 수락 조건 | 선행 |
| --- | --- | --- | --- |
| P0 입력 계약 | extractor `src/layout_electrode_extractor/{schema.py,particle_sim_adapter.py,cli.py}`, 설정 문서·단위 테스트. 필요시 별도 process-config loader. | 외부 전체 process stack의 순서·두께·절연막을 명시 검증. 기존 manifest·CLI 호환 유지. 무마스크 절연층은 stack에는 있고 source stage는 **0**. mask-bearing stage만 생성하고 CNT 개구 단계·METAL 후 단계를 구분. 입력 누락/중복/순서 오류는 출력 전 실패. | 공정 입력 형식과 노출 시점 확정, Opus 계획 검토. |
| P1 접점 export | extractor `particle_sim_adapter.py`, 접점 provenance 관련 테스트. | CNT1 pair별 분할 mask, 고유 row ID와 같은 물리 hole layer, stack 중복 0. `OR(mask row)=원래 cut CNT`·row 간 `AND=0`·각 성분 유일 배정·raw/cut 보존. 최신 fixture `validate-input`에서 100홀, 기존 legacy에서 16홀. 누락 225 px·중복·잘못된 endpoint·빈 row·8연결·금지 ID 반례는 output 생성 전 실패. | 기존 extraction provenance; Opus 계획 검토. P0의 두께 입력과는 독립적으로 합성 모드 검증 가능. |
| P2 net 매핑 | extractor adapter/review 입력·pair 생성·검증 테스트. | 추출 ID/회로 net ID 분리. 같은 gate의 TR 양편은 근거가 있을 때만 같은 net; ACTIVE/OACTIVE S/D 및 비접점 교차는 분리. pair 전수/명시 제외 목록과 변경 사유를 저장. 미확정 net은 확정 short 통계에 섞지 않음. | 확정 net 정책/매핑 입력; P1 뒤 통합. |
| P3 TR·중간층 진단 | extractor `engine.py`, `schema.py`의 필요한 최소 확장, 접점 테스트. | all-layer TR cut 보존. raw 홀 소멸·부분 절단, METAL/CNT TR 겹침, 선언되지 않은 중간 도체 raw 겹침, enclosure 숫자를 issue/provenance로 보고. `hole_in_tr`, `metal_over_tr`, `hole_through_gat2` 반례를 구분. 기하 겹침을 실제 short라고 단정하지 않음. | 허용/거부 정책 결정; P1과 파일 충돌 없이 직렬화. |
| E1 CNO 50% core | **외부 particle-sim** `failure/contact_not_open.py`, `geometry/contacts.py`, `schema.py`의 classification/warning, CNO 테스트. | 확정 분모로 `>=0.5`, 49/50/51% 경계와 odd-pixel 경계, zero denominator/빈 홀, 유효 착지부와 전체 홀 차이, 병렬 홀 사건 및 집계 테스트. 현재 full-cover 규칙과 출력 분류 변경을 명시. | 분모·여러 홀 결정; 해당 저장소 별도 승인·소유자·검토. |
| E2 ROI/단계 지원(필요한 경우) | **외부 particle-sim** source/ROI 계약 및 테스트, 또는 검증된 별도 후처리. | `lands_after_layer`가 CNT 개구 후·충전 전을 표현할 수 있는지 확인; source stage가 mask 없는 ILD에 없음. 선택된 집계 창·입자 footprint·커널·접점 전체·판정 영향 범위·margin·평가 면적을 일치시켜 외곽 half-hole/버스 경계 반례를 검증. 중앙 창을 택해도 300 px 여유만으로 충분하다고 자동 판정하지 않음. | 경계 선택·공정 단계 결정; E1과 독립 가능. |
| I1 end-to-end 확인 | 새 ignored output 디렉터리, extractor+particle-sim CLI·검토 문서. | 최신 fixture export 및 `validate-input` 실제 통과, 홀·전극·TR·pair·step inventory 보존/설명, 기존 fixture 양성 대조군 유지. 사용자 입력 물성/회로 net이 없으면 “합성 기능 시험”으로만 명시. 물리 simulation은 별도 승인과 자료 확인 후. | P0–P3와 E1, 필요시 E2. |

## 6. 정량 반례·명령·재생성 기준

- **CNO 경계:** 100 px 정사각형 유효 시험 홀에 대해 49 px 가림은 false, 50 px는 true, 51 px는 true. 225 px 홀은 112 px false, 113 px true(`2×covered >= denominator`로 정수 비교). 빈 홀·분모 0은 오류 또는 명시적 미적용이고 성공 CNO가 아니다. 분모 정책이 결정되면 같은 물리 홀에 endpoint 유효 면적이 작은 반례를 추가한다.
- **접점:** 정상 분할과 `drop_one_hole` 원본 probe는 [보존됨](../../outputs/opus-practicality-probes-20260924/README.md). 이후 제품 테스트는 정상만 `validate-input`을 통과시키고 누락 225 px는 adapter에서 거부한다. CNT1 분할 row의 물리 합집합이 원본 cut CNT1과 같아야 하며 CNT1/CNT2는 여전히 **두 물리 마스크**다. TR union은 모든 raw layer에서 그대로 절단한다.
- **stage:** 현재 fixture에서 mask-bearing ID는 `ACTIVE,GAT1,GAT2,OACTIVE,GAT3,CNT1,CNT2,METAL1`이다. 외부 입력에 무마스크 ILD 행을 하나 이상 추가해도 그 행의 `particle_source_steps`는 0개, mask-bearing stage의 `lands_after_layer`는 실제 stack에 존재하는 해당 mask ID여야 한다. 없는 마스크를 stage로 지정하면 export 전에 실패한다. 같은 ID의 stage 중복과 단계 순서 역전도 거부한다.
- **net/ROI:** `E00023` 브리지와 독립 전극을 실제 mask로 확인한다. 동일 raw GAT의 TR 양편 40쌍은 확정 매핑 전 물리 short로 단정하지 않는다. 내부 seam과 외곽 경계, 외곽 반쪽 홀, 2×2 밖 연결을 구분하는 테스트를 둔다. 분모가 ROI 전체인지 중앙 평가 창인지는 경계 결정 후 고정한다.

새 산출물은 기존 `outputs/particle-sim-link-check-20260924/`와 `outputs/opus-practicality-probes-20260924/`를 덮지 않는 **새 Git 무시 경로**에 만든다. 한 단계의 실패 시 그 Task와 출력·로그를 보존하고, 후속 Task는 준비 상태로 남긴다. hard reset·전역 stash·기존 결과 삭제로 복구하지 않는다. 입력 process config, 회로 mapping, 마스크, 분모·집계 정책 중 하나라도 변경되면 관련 export·`validate-input`·CNO/ROI 결과를 다시 생성하고 검토 범위를 명시한다. 실제 물리 결과 주장은 입력 물성·공정·net·경계 정의와 독립 검토가 모두 충족된 뒤에만 한다.

**실행 gate:** 사용자 미정 답을 반영한 **plan v3**와 Task 계약을 만든 다음, 구현 Dispatch **전에 새 Claude Opus 5.5 (`--model claude-opus-5-5 --effort high`) 읽기 전용 계획 검토**를 받는다. blocking finding을 해결한 뒤에만 한 편집 worker를 시작한다. schema/core 변경 후보는 계획 검토와 **별개의 새 Opus 5.5 세션**에서 정확한 diff/commit을 독립 검토받는다. 현재 v2 계획은 이 gate를 통과했다고 주장하지 않는다.
