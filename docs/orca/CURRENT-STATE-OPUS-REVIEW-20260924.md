# 현재 상태와 Opus 5.5 실용성 검토 자료 — 2026-09-24

## 구현과 관찰

- 제품 코드는 `79a4d68`, 검토·문서 기준은 `f01d0d5`와 `2f000f0`이다. 기존 Orca Run은 `run_5463d205f39d`이며 이 검토에서 구현 변경이나 particle-sim 저장소 변경은 하지 않는다.
- 합성 unit은 600×600 px·0.1 µm/px·약 20 px 배선, 출력은 1200×1200 px(2×2)이다. RGB 수평 버스는 R/B=GAT1, G=GAT2이고 수직 METAL1 trunk가 있다. 물리 순서는 `ACTIVE,GAT1,GAT2,OACTIVE,GAT3,CNT1,CNT2,METAL1`; conductor-only `stack`은 CNT1/CNT2를 뺀 투영이다. CNT1은 ACTIVE–METAL1 또는 GAT2–METAL1, CNT2는 OACTIVE–METAL1만 갖는다.
- 각 ACTIVE→GAT2 경로는 서로 다른 CNT1 홀 둘과 연속 METAL1을 거친다. 브리지 1은 기존 직접 GAT2/METAL1 trunk 경로와 병렬이고 브리지 2는 분할에 필수다. TR은 GAT1/ACTIVE 4, GAT2/OACTIVE 2, GAT3/OACTIVE 4개/단위이며 TR union은 **모든 층**에서 제거한다. 주기적 전극 판정은 반복 인스턴스 ID를 보존한다. 2×2 유한 ROI를 별도의 particle-sim 주기 경계조건으로 취급하지 않는다.
- 최신 CLI 재실행은 전극 101개·TR 40개·유효 CNT 홀 100개/2×2·issue 0개였다. [실제 전극 마스크 sheet](../../outputs/particle-sim-link-check-20260924/images/actual-electrode-mask-sheet.png), [inventory](../../outputs/particle-sim-link-check-20260924/inventory.json), [추출 manifest](../../outputs/particle-sim-link-check-20260924/extraction/manifest.json), [상세 시험 문서](PARTICLE-SIM-LINK-CHECK-20260924.md)를 참조한다. pytest 53개와 Ruff가 통과했다.
- 최신 fixture의 `export-particle-sim`은 같은 CNT1 mask에 두 endpoint pair가 있어 exit 2로 선제 거부했고 출력 폴더는 없다. 기존 단일 endpoint-pair fixture를 **별도 양성 대조군**으로 실행한 particle-sim `validate-input`만 `status: ok`, 전극 98개·pair 4,743개·미해결 pair 0개였다. 최신 fixture의 particle-sim 입력 검증이나 물리 simulation은 아직 수행하지 않았다.

## 현재 제약

1. Adapter는 하나의 물리 CNT/VIA mask에 하나의 endpoint pair만 허용한다. 추출은 홀별 pair와 그래프 provenance를 갖지만, adapter는 분할 접점 mask/행을 아직 만들지 않는다.
2. particle-sim schema는 contact row마다 `contact_id`, `path`, 물리 `hole_layer`, 명시적 lower/upper 도체층을 받는다. 같은 `hole_layer`를 여러 row가 참조하는 안은 코드상 가능해 보이나 현재 fixture로 `validate-input`한 증거는 없다. 홀의 각 연결 성분은 정확히 하나의 아래·위 전극에 겹치고 양쪽 net이 같아야 한다.
3. `physical_stack`은 추출 provenance이지만 adapter는 conductor stack에서 가정 ILD·두께·접점 위치를 다시 만든다. 2-D 순서와 마스크 교집합은 중간층 관통, 식각·충전, 실제 두께·물성의 제조 가능성을 증명하지 않는다.
4. 전체 이종 net 전극 pair를 분류하는 기본 정책은 규모가 크다. CNO는 contact ID와 endpoint 전극별로 묶이므로 CNT1 분할 시 failure-unit 의미를 확인해야 한다. 유한 2×2 ROI의 외곽은 반복 simulation 경계가 아니다.

## Opus 5.5에 요청할 판단

좁은 범위로 `src/layout_electrode_extractor/{schema.py,engine.py,particle_sim_adapter.py,synthetic.py}`, 관련 contact/adapter 테스트, 위 output 증거, 읽기 전용 `particle-sim/src/particle_sim/{schema.py,io/masks.py,geometry/contacts.py}`를 보라. 각 판단은 현재 코드/출력 근거와 함께 **검증된 사실**, **추론**, **아직 미검증**을 구분해 달라.

1. 현행 extractor와 제안된 adapter의 홀별 분할로 현재 fixture를 particle-sim에 실제 적용할 수 있는가? 필수 blocker와 선택적 개선을 구분하라.
2. CNT1의 endpoint별 비중첩 mask, 동일 물리 `hole_layer`를 공유하는 여러 contact row, 고유 `contact_id`, 명시 endpoint, 공통 `net_id`가 충분한가? 누락 홀·합쳐진 홀·다른 net·주기 인스턴스·TR-cut 경계 등 반례를 제시하라.
3. 물리 stack과 중간 도체층 관통, 2×2 유한 ROI와 주기 연결의 차이, 전층 TR 절단, 이종 net pair 전수 분류, CNO grouping 및 물리 가정은 실제 적용을 어디까지 제한하는가?
4. 구현을 시작한다면 최소 작업 순서와 단계별 acceptance 명령/구체적 반례는 무엇인가? `validate-input` 이후 실제 물리 simulation을 주장하기 전에 필요한 공정 자료와 확인은 무엇인가?

이 문서는 질의·현황 자료다. Opus 판단을 받은 뒤 coordinator가 채택 여부와 후속 필수 작업을 별도로 기록한다.
