# Opus 5.5 검토의 coordinator 채택·보류 — 2026-09-24

독립 보고서: [OPUS-PRACTICALITY-REVIEW-20260924.md](OPUS-PRACTICALITY-REVIEW-20260924.md). 현재 상태와 제약: [CURRENT-STATE-OPUS-REVIEW-20260924.md](CURRENT-STATE-OPUS-REVIEW-20260924.md). 검토는 Run `run_5463d205f39d`의 Task `task_e317341a234d`, Dispatch `ctx_bdbd92049991`에서 `d8d80a1` 코드와 particle-sim `aae492a`를 대상으로 했다. 이후 제품 구현은 하지 않았다.

## 채택한 사실과 의미

- **입력 계약 수준의 가능성:** 별도 endpoint mask 두 개가 동일 물리 `hole_layer=CNT1`을 공유하고 고유 `contact_id`를 쓰는 임시 export는 particle-sim `validate-input`에서 `ok`였다. 이는 현재 제품 adapter의 기능이 아니다. 현 adapter는 중복 물리 CNT1 규칙을 exit 2로 거부한다. [보존한 probe와 재실행 요약](../../outputs/opus-practicality-probes-20260924/README.md)에는 정상 split **100홀·54 CNO link·전극 155개·pair 11,879개·미해결 0개**가 기록돼 있다.
- **필수 adapter 정합성:** 한 홀을 제거한 probe도 `validate-input`에서 `ok`였지만, 원본 cut CNT1과의 비교에서는 단위당 **225픽셀이 누락**됐다(2×2 hole 수 100→96). 따라서 홀별 분할 마스크의 비중첩, 전체 union 일치, 성분별 유일 규칙 배정, 빈 row·금지 issue 검사는 export 전에 필요하다. particle-sim의 성공 상태만으로 누락을 검출했다고 해석하면 안 된다.
- **전층 TR 절단 계약 유지:** `raw & ~TR` 규칙이나 추출 전극의 주기적 인스턴스 ID는 이번 검토에서 변경하지 않는다. Opus가 제시한 `hole_in_tr`, `metal_over_tr`, `hole_through_gat2`는 현재 fixture의 실패가 아니라 **추가 fixture 반례**다. 진단 또는 export 제한을 설계할 근거로 채택한다. 이때 raw 홀과 cut 홀의 소멸·분할, 비소자층의 TR 교집합, 선언되지 않은 중간 도체 겹침을 각각 기록해야 한다.

## 별도 결정이 필요한 부분

1. **회로 net 대응(B3).** 전층 TR 절단으로 동일한 원본 GAT 배선도 추출 전극 여러 개가 된다. `net_id = 추출 전극 ID`를 그대로 쓰면 임시 export에서 자기 TR을 사이에 둔 gate 조각 40쌍이 서로 다른 net의 short pair로 분류됐다. 전층 절단을 유지하면서, **추출 전극 ID와 물리·회로 net ID를 별도 필드/매핑으로 관리**하는 방향을 채택한다. 확정된 회로 연결표·사용자 annotation 또는 TR 이전 원본 GAT 연속성의 근거로만 같은 gate net을 부여해야 한다. ACTIVE/OACTIVE의 S/D를 TR을 넘어 합치거나, 층간 기하 교차를 접점 없이 합치거나, RGB의 독립 버스를 이름만으로 합쳐서는 안 된다. 회로 net 대응이 미확정이면 해당 pair는 물리 short 판정에 쓰지 말고 미확정으로 보존하는 정책이 필요하다. 구체적 자동화 범위와 승인 방식은 후속 설계 결정이다.
2. **접점·금속의 TR 교차 처리(B5).** 사용자 규칙은 모든 층 절단으로 유지한다. 비소자층에 TR이 겹칠 때 경고만 할지, particle-sim export를 거부할지, 어떤 설계 의도로 예외를 승인할지는 결정이 필요하다. 현재 fixture는 해당 raw 교집합이 0이므로 이번 출력에는 영향을 주지 않는다.
3. **공정·이물 단계(B4)와 물리 검증.** 현 adapter가 모든 contact를 METAL1 뒤 한 step에 연결한다는 것은 코드 사실이다. 그 단계에서 CNO가 물리적으로 유효한지, CNT 식각·채움과 이물 유입을 어떤 단계로 나눌지는 공정 흐름 자료 없이는 확정할 수 없다. 사용자 physical order는 순서 제약이지 식각 깊이·절연막·충전의 증거가 아니다.

## 물리 추론으로 보류한 표현

- `hole_through_gat2` probe는 **선언 endpoint가 아닌 중간 GAT2의 2-D raw 겹침을 extractor가 issue 없이 통과시킨다**는 사실을 입증한다. 실제 전기적 short 여부는 식각 정지, 절연막, liner/fill, 깊이에 달려 있다. 검출을 필수로 보되 실제 short라고 단정하지 않는다.
- 홀 10개/unit의 lower landing 밖 돌출은 관찰된 기하 사실이다. DRC 위반 여부와 CNO 유효 면적의 물리 의미는 공정별 enclosure 규칙을 받아야 결정된다.
- Opus의 한 주기 회계 창 `[300,900)²`은 이물 반지름과 particle-sim의 평가 창 지원 여부가 미검증인 조건부 아이디어다. 이를 현재 계산의 경계 오차 해결책으로 채택하지 않는다. 유한 2×2 ROI와 정확한 주기적 추출 정체성의 차이는 계속 명시한다.
- `validate-input` 통과는 mask/manifest 계약 확인이다. 실제 particle-sim simulation 및 제조 가능성 검증은 아직 없다.

## 최소 후속 우선순위 (이번에는 착수하지 않음)

1. **입력 연결 최소 기능:** adapter에서 CNT1을 endpoint별 mask/row로 분리하고 동일 물리 hole layer를 stack에 한 번만 배치한다. 누락·중복·잘못된 endpoint·8연결 차이·ID 문자 반례를 포함한 partition 검증을 넣는다. 현재 fixture와 기존 단일 pair fixture 양쪽을 실제 `validate-input`으로 확인한다.
2. **추출 진단:** raw contact의 TR 소멸·부분 절단, 비소자층의 TR 겹침, 미선언 중간 도체 겹침을 진단한다. all-layer cut은 유지한다. enclosure는 공정 규칙이 없으면 수치와 가정으로 먼저 보고한다.
3. **물리 분석 정책:** 확정 회로 net mapping, TR 교차 예외 정책, 공정별 이물 유입 단계·CNO 기준을 결정한 뒤 pair와 step을 재생성한다. 현재의 11,879 pair와 54 CNO link는 synthetic 계약 출력 수치로만 취급한다.
4. **simulation 진입 조건:** 실제 두께·절연막·식각/충전, 입자 분포·전도성·매립 깊이, enclosure/DRC, CNO 부분 가림·병렬 경로 기준, 유한 ROI 경계 회계가 정해지고 새 manifest의 `validate-input`과 대표 반례가 통과한 뒤 물리 simulation을 검토한다.

이번 요청의 범위는 정리와 독립 질의다. 위 후속 구현을 시작하지 않았고, particle-sim 저장소를 변경하지 않았다.
