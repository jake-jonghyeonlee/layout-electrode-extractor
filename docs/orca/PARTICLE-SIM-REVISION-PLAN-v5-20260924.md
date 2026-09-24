# particle-sim 연계 수정계획 v5 — 2026-09-24

**상태:** 확정 입경을 계획에 반영한 문서 수정만 수행. 구현·simulation·새 worker Dispatch 없음. 기존 Orca Run `run_5463d205f39d`, 기준 `d163c46`(제품 `79a4d68`). [v4 계획](PARTICLE-SIM-REVISION-PLAN-v4-20260924.md), [현황 시험](PARTICLE-SIM-LINK-CHECK-20260924.md), [Opus 검토](OPUS-PRACTICALITY-REVIEW-20260924.md)을 최신 사용자 답으로 갱신한다. `/Users/jonghyeonlee/git/particle-sim`은 읽기 전용이며 그 저장소의 변경은 **외부 의존 작업 제안**으로만 적는다.

## 1. 확정 규칙과 보존할 계약

| 주제 | 확정 내용 |
| --- | --- |
| 공정 stack | 층 두께와 절연막의 위치·물성은 추후 외부 입력으로 받는다. 마스크가 없는 절연층도 전체 공정 순서에는 포함한다. 임의의 두께·ILD를 실제값으로 확정하지 않는다. |
| 이물 유입 | **마스크가 있는 물리 층만** source stage 후보로 만든다. 마스크 없는 절연층의 source stage 수는 0이다. CNT1/CNT2는 도체 전극이 아니어도 접점 마스크가 있는 물리 층이다. |
| CNO | **개별 CNT 홀의 전체 면적**을 분모로 가림률 **50% 이상**이면 해당 홀의 CNO 사건이다. 50%는 포함한다. 홀끼리 면적을 합산하지 않는다. |
| 계산 입경 | **지름 µm**로 `diameters_um = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 40, 50]`의 정확히 **32개** 이산값을 계산한다. 31–39 및 41–49 µm는 추가하지 않는다. 입경별 확률 가중치·밀도는 아직 입력되지 않았으며 균등분포로 가정하지 않는다. |
| 불량 집계 | 홀 CNO와 회로 open을 **독립 계산**한다. **동일 이물 조건**(동일 sample/위치/크기·형상/source step)에서 **동일 연결**의 CNO와 open이 함께 참일 때만 최종 open을 제거하고 CNO를 우선한다. 다른 연결의 open과 모든 short는 유지한다. 원시 결과와 중복 제거 후 통계를 모두 보존한다. |
| 추출 | 600×600 unit, 0.1 µm/px, 20 px 배선, 1200×1200 2×2 출력. TR 10개/unit·40개/2×2, **모든 층 TR 절단**, 두 물리 CNT 마스크, ACTIVE→CNT1→METAL1→CNT1→GAT2 브리지 두 개, RGB GAT 버스·수직 METAL trunk·주기적 인스턴스 정체성을 유지한다. |
| 연락·소유권 | extractor 저장소만 이후 승인된 구현 대상이다. particle-sim core의 CNO·ROI 변경은 해당 저장소 소유자의 별도 구현/검토가 필요하다. 구독 외 결제나 원격 게시를 전제하지 않는다. |

현재 extractor `physical_stack`은 **마스크가 있는 도체와 CNT/VIA ID만** 허용한다([schema.py:140–155](../../src/layout_electrode_extractor/schema.py#L140-L155)). 따라서 외부 입력의 **전체 process stack**에는 무마스크 절연층을 포함하고, 기존 `physical_stack`은 그중 마스크 층의 순서 투영으로 유지하는 안을 권장한다. 이를 동일 필드에 무리하게 섞지 않아 기존 manifest를 깨뜨리지 않는다. 전체 process stack의 conductor 투영은 현재 `stack`과 같아야 한다. 실제 절연층의 수·순서·두께는 입력 전까지 미정이다.

## 2. 사용자가 물은 “2×2 경계”의 정확한 뜻

원본 unit 600×600을 가로·세로 두 개씩 놓은 계산 이미지는 좌표 `x,y=0…1199`이다. **내부 이음선**은 `x=599/600`, `y=599/600`; **2×2 외곽 경계**는 `x=0/1199`, `y=0/1199`이다. 추출기는 반복 배선이 내부 이음선을 지날 때도 별도 반복 인스턴스 ID를 보존한다. particle-sim은 이 1200×1200 이미지를 유한한 ROI로 받아 바깥쪽을 자동으로 주기 연결하지 않는다. 그러므로 외곽에서 잘린 CNT 홀이나 배선에 대해 원래 unit 밖의 다음 반복 복사본을 particle-sim이 보지 못할 수 있고, ROI 경계를 단자로 쓰는 open 판정도 별도 선택이다([auto_open.py:1–7](../../../particle-sim/src/particle_sim/failure/auto_open.py#L1-L7), [terminal 구성](../../../particle-sim/src/particle_sim/failure/auto_open.py#L43-L65)). 현재 fixture의 `open_applicable_steps_by_layer`는 빈 목록이라 자동 open을 켜지 않는다. **확정된 집계 창은 중앙 `[300,900)×[300,900)` 600 px**이다. 이 창의 각 변에서 1200 px ROI 외곽까지의 여유는 **300 px = 30 µm = 0.5 unit**이다. 입자 footprint·커널 지원 범위, 접점 홀 전체와 endpoint 유효 영역, CNO/open/short 판정이 참조하는 공간 범위, 추가 margin을 합쳐 외곽의 영향이 중앙 집계에 들어오지 않는지 입력별로 검증한다. 입자 반지름만 `≤300 px`라는 조건이나 여유 자체만으로 정확성을 주장하지 않는다. 검증 범위를 초과하는 입력은 자동 정확성 주장을 금지하고 거부하거나 명시적으로 미지원 처리한다. 집계 위치·면적 분모는 이 중앙 창으로 고정하되 영향 범위 계산법은 구현 전 검토한다.

### 2.1 경계 영향과 계산 비용: 읽기 전용 조사

**기하적으로 경계가 영향을 줄 수 있다.** 현재 CNO는 홀 좌표에서 입자 stamp 반경만큼 확장한 국소 창을 계산하며, 창을 이미지 경계에서 자른다([contact_not_open.py:35–60](../../../particle-sim/src/particle_sim/failure/contact_not_open.py#L35-L60)). 현재 규칙은 full-effective-hole cover이므로 이 코드를 새 50% CNO의 측정치로 해석하지 않는다. 이후에는 cut CNT **홀 전체** bbox, 입자 footprint/커널 및 contact margin, endpoint 유효 영역을 함께 고려해야 한다. Short는 전극까지 XY 거리와 입자 반경+margin을 비교하므로([contact.py:32–55](../../../particle-sim/src/particle_sim/geometry/contact.py#L32-L55)), 중심이 중앙 창 안이라도 영향받는 전극·표면 정보가 ROI 밖에 있으면 유한 ROI와 확장 ROI 결과가 달라질 수 있다. Open은 입자 손상이 국소라도 양 단자 사이의 **전체 연결성** 판정이다([open_failure.py:41–73](../../../particle-sim/src/particle_sim/failure/open_failure.py#L41-L73)); 국소 타일 최적화도 타일 밖 연결 성분을 사용한다([open_fast.py:1–17](../../../particle-sim/src/particle_sim/failure/open_fast.py#L1-L17)). 따라서 open에는 `반경+margin ≤ 30 µm`만으로 충분하다는 보장이 없다. 실제 회로 net/단자·ROI 밖 대체 경로의 정의가 필요하다.

아래 수치는 **120 µm 정사각 전체 ROI**에서 바깥 경계까지 거리 `r` 이내인 중심의 면적 비율 `1-(1-2r/120)^2`이다. 균일한 중심 분포일 때 경계 근처에 놓일 *기하학적 기회*를 나타낼 뿐, 실제 경계 오차율·CNO 확률·입경 분포가 아니다. 표의 `r`은 기하학적 경계 띠 폭 예시이며 **확정 입경의 지름이 아니다**. 확정 최대 지름은 50 µm, 최대 반지름은 25 µm다. 입경별 확률 가중치·밀도는 아직 없다.

| 예시 `r` (µm) | 전체 120 µm ROI의 경계 띠 비율 | 중앙 집계창에 대한 해석 |
| ---: | ---: | --- |
| 1 | 3.3% | 이 값 자체는 영향 확률이 아님; 30 µm 여유와 총 support 비교 필요 |
| 5 | 16.0% | 동일 |
| 10 | 30.6% | 동일 |
| 30 | 75.0% | 반경만 여유와 같아도 홀 크기·커널·margin 때문에 충분하지 않을 수 있음 |

**확정 지름의 픽셀 환산:** 0.1 µm/px에서 1–30 µm 지름은 반지름 0.5–15 µm = 5–150 px, 40 µm는 20 µm = 200 px, 50 µm는 25 µm = 250 px다. 중앙 집계창 각 변의 300 px 여유에서 **최대 입자 footprint 반지름만 빼면 50 px = 5 µm가 남는다**. 이 값은 contact margin·커널 지원 범위·CNT 홀 전체 span·endpoint 범위가 차지할 수 있는 여유를 보증하지 않으며, 회로 open의 비국소적 우회 연결도 해결하지 않는다. 1·30·40·50 µm 지름을 대표 경계 반례로 보고, 실제 지원 여부는 **32개 지름 각각**의 전체 support와 open 연결성에 대해 판정한다.

**계산량:** 현재 nominal 경로는 전체 `grid.shape_yx` 크기로 CNO·pair·union map을 만들고 모든 source step·입경·pair를 평가한다([pipeline.py:248–365](../../../particle-sim/src/particle_sim/pipeline.py#L248-L365)); 현재 critical area는 전체 map을 합산하고 ROI 전체 면적으로 정규화한다([critical_area.py:10–28](../../../particle-sim/src/particle_sim/aggregation/critical_area.py#L10-L28)). 1200 ROI 계산 뒤 중앙 결과만 집계하면 **기존 map 계산량은 대체로 그대로**지만 중앙 crop의 면적·정규화·중복 회계 구현은 필요하다. ROI 자체를 키우면 1200²=144만, 1800²=324만, 2400²=576만 픽셀로, **단일 map 픽셀·메모리 비율은 1:2.25:4**다. 예를 들어 float32 map 하나는 약 5.76/12.96/23.04 MB(십진)다. 전체 실행 시간은 pair/step/입경 수, distance transform, open 연결성·캐시 때문에 이 비율과 같다고 단정하지 않는다. 현행 CNO full-cover core를 대상으로 한 probe는 새 50% 규칙의 검증이 아니므로 이번에는 시간 benchmark를 만들지 않았다.

**권장:** 입력별 총 국소 support와 전체 홀/endpoint 범위가 각 변 300 px 안에 있고, 확정 net·단자의 연결성도 유한 ROI와 바깥 반복 경로의 차이를 일으키지 않음이 검증되면 **기존 2×2 계산+중앙 집계**를 유지한다. 하나라도 초과하면 조용히 정확하다고 보고하지 않는다. 영향받은 failure mode/입경만 대상으로 stable periodic instance ID와 net 매핑을 유지한 **선택적 추가 halo**를 생성해 중앙 결과를 원래 2×2와 비교하거나, 비용·정체성 검증이 안 되면 해당 조건을 미지원으로 표시한다. 이미 label된 전극 mask를 단순 타일 복사해 큰 ROI를 만들지 않는다. 실제 halo 후보는 같은 중앙 좌표·동일 홀 ID·동일 연결 ID의 CNO/short/open map과 집계값을 비교해 수렴 여부를 확인한다. 이 비교도 시험한 조건의 증거일 뿐 일반적인 안정화 증명은 아니다.

## 3. 코드상 현재 상태와 필요한 변화

| 범위 | 현재 코드·출력 사실 | 계획된 변경 또는 외부 의존 |
| --- | --- | --- |
| 접점 export | 같은 CNT1 물리 mask의 두 endpoint pair는 adapter가 출력 전에 거부한다([adapter:150–157](../../src/layout_electrode_extractor/particle_sim_adapter.py#L150-L157)). 임시 분할은 particle-sim `validate-input`을 통과했지만 누락 홀도 통과했다([재현 증거](../../outputs/opus-practicality-probes-20260924/README.md)). | extractor adapter에서 홀별 provenance로 **물리 CNT1 mask를 endpoint pair별 비중첩 export mask로 분할**하고 두 row는 고유 ID·동일 `hole_layer=CNT1`을 사용한다. CNT1/CNT2 원본 raw·TR-cut mask와의 union·누락·중복·빈 성분 검사를 출력 생성 전에 한다. |
| 출력 net | 현재 `net_id=추출 전극 ID`([adapter:163–178](../../src/layout_electrode_extractor/particle_sim_adapter.py#L163-L178)); 자기 TR에 의해 분리된 같은 gate 40쌍이 다른-net short 후보가 됐다. | **추출 전극 ID와 회로 net ID를 분리**한 확인된 대응표를 입력받는다. 전층 TR cut/전극 mask는 바꾸지 않는다. 원본 gate 연결과 확정 회로 annotation만 근거로 같은 net을 묶고, S/D나 비접점 층간 교차는 자동 병합하지 않는다. 미확정 pair는 불확실 상태/명시 제외 사유로 남긴다. |
| 공정 입력·source 단계 | adapter는 역할 기반 가정 ILD·두께를 만들고 단일 `SOURCE_AFTER_TOP_CONDUCTOR`에 모든 contact를 붙인다([adapter:17–138](../../src/layout_electrode_extractor/particle_sim_adapter.py#L17-L138), [contact row](../../src/layout_electrode_extractor/particle_sim_adapter.py#L193-L210)). particle-sim `ParticleSourceStep`는 `lands_after_layer`와 분포층 이름을 가진다([schema.py:58–64](../../../particle-sim/src/particle_sim/schema.py#L58-L64)); 현재 검사는 landing layer가 stack에 있는지만 확인한다([schema.py:295–300](../../../particle-sim/src/particle_sim/schema.py#L295-L300)). | 새 외부 process config가 마스크층과 무마스크 절연층의 전체 순서·두께·물성을 준다. adapter는 **mask source layer 목록에 있는 층에만** source step을 만들고, 무마스크 절연층에는 만들지 않는다. `lands_after_layer`는 해당 마스크 작업 직후의 nominal surface라는 뜻으로 제안하되 공정 stage 의미를 명시한다. 무마스크 stack row는 layer mask 없이 남는다. |
| CNO 50% | particle-sim core는 홀의 양쪽 전극에 공통으로 닿는 **effective pixels**만 보존([contacts.py:111–135](../../../particle-sim/src/particle_sim/geometry/contacts.py#L111-L135))하고, 현재는 그 픽셀을 **전부** 덮어야 CNO([contact_not_open.py:34–62](../../../particle-sim/src/particle_sim/failure/contact_not_open.py#L34-L62)). 같은 link의 여러 홀은 OR한다. | **particle-sim 외부 의존 작업:** 현재 all-layer TR cut을 거친 simulation 입력 CNT mask의 **개별 연결 성분 전체 픽셀**을 홀별 분모로 보존하고, 그 성분과 입자 가림 영역의 픽셀 교집합을 분자로 `2×covered >= full_cut_hole_area`를 판정한다. effective endpoint 공통 면적은 분모가 아니다. raw/cut/effective 성분 ID·면적·좌표 대응을 provenance로 기록한다. TR 부분 절단·외곽 절단·성분 분리 또는 사라짐이 원래 홀 분모를 조용히 축소하지 않도록 진단하고 정책에 따라 거부한다. 빈 홀/유효 접점 없음도 조용히 정상 처리하지 않는다. |
| CNO/open 중복 | 현재 CNO는 link별 OR 결과를 만들며 독립적인 회로 open 결과와 동일 사건 대조용 식별자 계약이 없다. | **particle-sim 외부 의존 작업:** 홀별 CNO와 확정 net mapping 기반 회로 open을 각각 계산·보존한 뒤, 동일 이물 조건·동일 연결의 CNO/open만 CNO 우선으로 후처리한다. sample/위치/크기·형상/source step과 확정 연결 ID를 같은 키 공간으로 매핑하고, 동일 사건의 여러 가림 footprint는 먼저 픽셀 union을 만들어 각 홀과 교차시켜 중복 픽셀을 한 번만 센다. 다른 연결의 open과 short는 유지한다. raw CNO/open/short 결과, 중복 대응표, 최종 사건/통계를 별도 저장한다. |
| ROI/회계 | particle-sim의 CNO 계산은 full image shape의 중심별 맵을 만든다([contact_not_open.py:48–62](../../../particle-sim/src/particle_sim/failure/contact_not_open.py#L48-L62)). 현재 adapter는 주기적 경계조건을 전달하지 않는다. | 평가 중심과 통계 면적 분모를 중앙 `[300,900)²`로 제한한다. 전체 영향 support·margin이 각 변 300 px 안에 있음을 검증하고, 초과 시 자동 정확성 주장을 금지한다. particle-sim에 평가 창 설정이 없으면 외부 의존 작업 또는 검증 가능한 후처리로 표시한다. |

**stage 의미 제안(아직 공정 확정 아님):** ACTIVE/GAT1/GAT2/OACTIVE/GAT3/METAL1처럼 패턴 도체 마스크가 있는 층은 그 층의 패턴 형성 후 노출된 표면에 유입되는 step을 둔다. CNT1/CNT2는 **개구 마스크 형성·식각 후, 충전 및 METAL1 형성 전** 유입되는 step으로 두어 CNO 적용 후보로 삼는다. METAL1 형성 뒤 step도 METAL1 마스크가 있으므로 유지할 수 있고, 그 단계의 short 등 해당 failure mode를 평가한다. METAL1 뒤 CNO의 적용 가능성은 공정·불량 기전 입력이 없으면 자동으로 긍정하거나 일괄 폐기하지 않는다. 무마스크 절연막은 stack z/topography에는 남지만 유입 step은 0개다. `lands_after_layer`가 개구 후·충전 전 상태를 충분히 표현하지 못한다면 particle-sim schema/공정 단계의 외부 확장이 필요하다([surface 순서](../../../particle-sim/src/particle_sim/io/stack.py#L60-L89)).

## 4. 중복 범위 확정

이전 네 질문은 답변 완료다. (1) CNO 분모는 **각 CNT 홀 전체 면적**이다. 구현 좌표계에서는 all-layer TR cut 후 **simulation 입력 mask의 물리 CNT 연결 성분**을 한 홀로 삼는다. raw 마스크·cut 마스크·endpoint 공통 effective 면적을 구분하며, 부분 TR 절단이나 유한 ROI 바깥으로 잘린 조각을 원래 홀의 축소된 분모로 조용히 받아들이지 않는다. 성분 단절·소실·경계 접촉을 진단하고 허용/거부 정책을 정해, 정상 홀만 계산한다. (2) 중앙 `[300,900)²`만 집계한다. (3) 홀 CNO와 회로 open을 독립 계산하고 중복 제거 시 CNO를 우선한다. (4) 중복 제거는 **동일 이물 조건과 동일 연결의 CNO/open**에만 적용한다.

중복 키는 좌표만으로 만들지 않고 sample/step/입자 크기·형상과 **확정 회로 연결 ID**를 함께 사용한다. 동일 이물이 같은 연결의 여러 홀에 CNO를 만들면 홀별 원시 사건은 모두 남기고, 그 연결의 회로 open 원시 사건과 비교해 최종 중복 제거를 한다. 같은 이물이 만든 **다른 연결의 open 및 모든 short는 제거하지 않는다**. 병렬 홀이 가려져도 회로 open은 별도 계산한다. 동일 사건의 가림 footprint가 여러 개면 union 후 **각 홀과 따로** 교차시켜 동일 픽셀을 한 홀 안에서 중복 가산하지 않는다. 회로 연결 ID가 미확정이면 동일 연결이라고 추측해 제거하지 않고 미분류로 남긴다.

추가 입력으로 실제 process stack 예시(무마스크 절연막의 순서·두께 포함), 각 mask layer별 이물 분포와 노출 시점, 확정 회로 net mapping이 필요하다. **입경 목록과 최대 반경은 확정**됐지만 입경별 가중치·밀도, contact margin 및 kernel의 추가 지원 범위가 미입력이므로 경계 영향 판단은 여전히 조건부다.

## 5. 이후 구현 Task 초안과 실제 의존성

**이번에는 어떤 Task도 구현 Dispatch하지 않는다.** process/net/입경 입력을 반영해 구현 Task를 저장한다. 한 편집 worker와 한 read-only worker 한도를 지킨다.

| 초안 | 저장소·파일 소유 범위 | 결과 / 수락 조건 | 선행 |
| --- | --- | --- | --- |
| P0 입력 계약 | extractor `src/layout_electrode_extractor/{schema.py,particle_sim_adapter.py,cli.py}`, 설정 문서·단위 테스트. 필요시 별도 process-config loader. | 외부 전체 process stack의 순서·두께·절연막을 명시 검증. 기존 manifest·CLI 호환 유지. 무마스크 절연층은 stack에는 있고 source stage는 **0**. mask-bearing stage만 생성하고 CNT 개구 단계·METAL 후 단계를 구분. 입력 누락/중복/순서 오류는 출력 전 실패. | 공정 입력 형식과 노출 시점 확정, Opus 계획 검토. |
| P1 접점 export | extractor `particle_sim_adapter.py`, 접점 provenance 관련 테스트. | CNT1 pair별 분할 mask, 고유 row ID와 같은 물리 hole layer, stack 중복 0. `OR(mask row)=원래 cut CNT`·row 간 `AND=0`·각 성분 유일 배정·raw/cut 보존. 최신 fixture `validate-input`에서 100홀, 기존 legacy에서 16홀. 누락 225 px·중복·잘못된 endpoint·빈 row·8연결·금지 ID 반례는 output 생성 전 실패. | 기존 extraction provenance; Opus 계획 검토. P0의 두께 입력과는 독립적으로 합성 모드 검증 가능. |
| P2 net 매핑 | extractor adapter/review 입력·pair 생성·검증 테스트. | 추출 ID/회로 net ID 분리. 같은 gate의 TR 양편은 근거가 있을 때만 같은 net; ACTIVE/OACTIVE S/D 및 비접점 교차는 분리. pair 전수/명시 제외 목록과 변경 사유를 저장. 미확정 net은 확정 short 통계에 섞지 않음. | 확정 net 정책/매핑 입력; P1 뒤 통합. |
| P3 TR·중간층 진단 | extractor `engine.py`, `schema.py`의 필요한 최소 확장, 접점 테스트. | all-layer TR cut 보존. raw 홀 소멸·부분 절단, METAL/CNT TR 겹침, 선언되지 않은 중간 도체 raw 겹침, enclosure 숫자를 issue/provenance로 보고. `hole_in_tr`, `metal_over_tr`, `hole_through_gat2` 반례를 구분. 기하 겹침을 실제 short라고 단정하지 않음. | 허용/거부 정책 결정; P1과 파일 충돌 없이 직렬화. |
| E1 CNO 50% core | **외부 particle-sim** `failure/contact_not_open.py`, `geometry/contacts.py`, `schema.py`의 classification/warning, CNO 테스트. | cut CNT 연결 성분 전체 면적을 분모로 `>=0.5`; 49/50/51%·odd-pixel·빈 홀·유효 착지부와 전체 홀 차이·TR 부분 절단/소실·ROI 외곽 조각·병렬 홀 반례. raw/cut/effective provenance 보존, 조용한 분모 축소 거부. 현재 full-cover 규칙과 출력 분류 변경 명시. | 해당 저장소 별도 승인·소유자·검토; 접점 진단 정책은 P3와 맞춤. |
| E2 ROI/단계 지원(필요한 경우) | **외부 particle-sim** source/ROI 계약 및 테스트, 또는 검증된 별도 후처리. | `lands_after_layer`가 CNT 개구 후·충전 전을 표현할 수 있는지 확인; source stage가 mask 없는 ILD에 없음. 중앙 `[300,900)²` 집계·평가 면적을 고정하고 32개 지름 각각 입자 footprint·커널·접점 전체·판정 영향 범위·margin이 각 변 300 px 안에 있는지 검증. 특히 지름 1·30·40·50 µm와 최대 50 µm의 footprint 후 남는 50 px를 확인. open 연결성은 별도 검증; 초과 시 자동 정확성 주장 금지. | 공정 단계 결정; E1과 독립 가능. |
| E3 CNO/open 중복 회계 | **외부 particle-sim** CNO/open 결과 집계·출력·테스트; 필요시 extractor의 명시 net/link map 연계. | 독립 원시 CNO/open/short 사건을 유지하고 동일 이물 조건·동일 연결 키로 대응표를 만든 뒤 해당 open만 CNO 우선 제거. 다른 연결 open·모든 short 보존. raw와 dedup 후 건수·확률/면적 분모를 별도 보고; 한 입자 두 홀, 병렬 경로, 같은 입자의 다른 연결, 같은 위치 다른 step/크기의 반례. | P2 확정 net map, E1; 외부 저장소 별도 승인·검토. |
| I1 end-to-end 확인 | 새 ignored output 디렉터리, extractor+particle-sim CLI·검토 문서. | 최신 fixture export 및 `validate-input` 실제 통과, 홀·전극·TR·pair·step inventory 보존/설명, 기존 fixture 양성 대조군 유지. CNO/open 독립 원시 및 dedup 통계, 중앙 ROI 영향 검증을 확인. 사용자 입력 물성/회로 net이 없으면 “합성 기능 시험”으로만 명시. 물리 simulation은 별도 승인과 자료 확인 후. | P0–P3와 E1/E3, 필요시 E2. |

## 6. 정량 반례·명령·재생성 기준

- **CNO 경계:** cut CNT 연결 성분 전체 면적이 100 px인 홀에 대해 49 px 가림은 false, 50 px는 true, 51 px는 true. 225 px 홀은 112 px false, 113 px true(`2×covered >= denominator`로 정수 비교). 같은 전체 홀에서 endpoint effective 면적만 작은 반례를 추가해 분모 혼동을 막는다. raw 225 px 홀이 TR/외곽 때문에 cut 200 px 조각이 된 경우 100 px 가림을 곧바로 50% CNO로 처리하지 않고 먼저 절단 진단·거부 정책을 적용한다. 빈 홀·분모 0·유효 endpoint 없음은 조용한 정상 판정이 아니다.
- **접점:** 정상 분할과 `drop_one_hole` 원본 probe는 [보존됨](../../outputs/opus-practicality-probes-20260924/README.md). 이후 제품 테스트는 정상만 `validate-input`을 통과시키고 누락 225 px는 adapter에서 거부한다. CNT1 분할 row의 물리 합집합이 원본 cut CNT1과 같아야 하며 CNT1/CNT2는 여전히 **두 물리 마스크**다. TR union은 모든 raw layer에서 그대로 절단한다.
- **stage:** 현재 fixture에서 mask-bearing ID는 `ACTIVE,GAT1,GAT2,OACTIVE,GAT3,CNT1,CNT2,METAL1`이다. 외부 입력에 무마스크 ILD 행을 하나 이상 추가해도 그 행의 `particle_source_steps`는 0개, mask-bearing stage의 `lands_after_layer`는 실제 stack에 존재하는 해당 mask ID여야 한다. 없는 마스크를 stage로 지정하면 export 전에 실패한다. 같은 ID의 stage 중복과 단계 순서 역전도 거부한다.
- **net/ROI:** `E00023` 브리지와 독립 전극을 실제 mask로 확인한다. 동일 raw GAT의 TR 양편 40쌍은 확정 매핑 전 물리 short로 단정하지 않는다. 내부 seam과 외곽 경계, 외곽 반쪽 홀, 2×2 밖 연결을 구분한다. 통계 집계 창과 그 면적 분모는 중앙 `[300,900)²`로 고정한다. 정확히 32개 지름 `1..30,40,50` 각각의 support gate와 1·30·40·50 µm 경계 반례를 확인한다. 국소 support가 각 변 300 px를 넘거나 open 연결성에 ROI 밖 경로가 필요하면 정확성을 주장하지 않고 선택적 halo 비교 또는 미지원 처리를 한다.
- **중복 회계:** 동일 이물 조건·동일 연결에서 CNO와 open이 함께 검출되면 두 원시 결과를 모두 보존하고 최종 open만 제거한다. 다른 sample·step·입자 크기·형상, 다른 연결의 open, 모든 short는 보존한다. 동일 입자가 두 홀을 덮는 경우 픽셀 union으로 홀별 가림률을 구하고 병렬 경로의 회로 open은 별도 계산한다. raw 건수, 매칭 키/대응표, dedup 후 건수와 확률 분모가 재현되어야 한다.

새 산출물은 기존 `outputs/particle-sim-link-check-20260924/`와 `outputs/opus-practicality-probes-20260924/`를 덮지 않는 **새 Git 무시 경로**에 만든다. 한 단계의 실패 시 그 Task와 출력·로그를 보존하고, 후속 Task는 준비 상태로 남긴다. hard reset·전역 stash·기존 결과 삭제로 복구하지 않는다. 입력 process config, 회로 mapping, 마스크, 홀/ROI 판정 또는 중복 키 정책 중 하나라도 변경되면 관련 export·`validate-input`·CNO/open 원시/중복제거·ROI 결과를 다시 생성하고 검토 범위를 명시한다. 실제 물리 결과 주장은 입력 물성·공정·net·경계 정의와 독립 검토가 모두 충족된 뒤에만 한다.

**실행 gate:** 확정 32개 입경과 필요한 process/net/가중치 입력, 위 경계 영향 정책을 구현 Task 계약에 반영한 다음, 구현 Dispatch **전에 새 Claude Opus 5.5 (`--model claude-opus-5-5 --effort high`) 읽기 전용 계획 검토**를 받는다. blocking finding을 해결한 뒤에만 한 편집 worker를 시작한다. schema/core 변경 후보는 계획 검토와 **별개의 새 Opus 5.5 세션**에서 정확한 diff/commit을 독립 검토받는다. 현재 v5 계획은 이 gate를 통과했다고 주장하지 않는다.
