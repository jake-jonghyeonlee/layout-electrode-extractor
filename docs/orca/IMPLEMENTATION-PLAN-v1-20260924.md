# v5 particle-sim 연계 구현 실행계약 v1

기준 `762a239`, 기존 Run `run_5463d205f39d`. [제품 규칙 v5](PARTICLE-SIM-REVISION-PLAN-v5-20260924.md)을 구현한다. 이 문서는 **Opus 5.5 high 계획 검토 전 초안**이다. `/Users/jonghyeonlee/git/particle-sim` 원본은 끝까지 읽기 전용이며, 외부 simulator 변경은 무시되는 독립 복사본/patch와 증거로만 전달한다. `docs/orca/FINAL-REPORT.ko.md`는 건드리지 않는다.

## 입력·실패 계약

- Extractor 기존 schema/CLI는 유지한다. 새 particle-sim export 설정은 명시 JSON 파일로 받으며 `--config`가 없을 때 기존 legacy 단일 pair 합성 export 동작을 유지한다. mixed CNT1의 기본 export는 오류 대신 **명시적인 synthetic test profile**을 호출했을 때만 가능하다. 외부 두께·절연막·입경별 가중치·회로 net은 실제 자료가 없으므로 실제값을 만들지 않는다. synthetic profile의 숫자는 가정이라고 manifest/report에 표시한다.
- Process config에는 full bottom→top stack row(ID, 역할, mask source 여부, 두께/물성 등 simulator 필수값), source stage 정의, 회로 net mapping, 필요시 pair/open-path 정책을 둔다. 기존 `physical_stack`은 masked projection, `stack`은 conductor projection으로 대조한다. maskless ILD는 full process stack에 있으며 source stage는 **0개**다. mask-bearing ACTIVE/GAT/OACTIVE/CNT/METAL만 source 단계 후보이며 CNT는 개구 후·충전 전이라는 nominal 의미를 기록한다. simulator의 표현 능력 밖 단계는 거부/미지원으로 명시한다. 누락된 실물 입력은 실제물성 검증을 막지만, 명시 synthetic profile의 기능 시험을 막지 않는다.
- 확정 회로 net ID 없이는 추출 ID로 **합성/임시 net**을 만들 수 있지만 확정 short 통계라 주장하지 않는다. 명시 net map에서 다수 추출 전극→한 회로 net을 허용하고 원본 전극 ID/물리 mask는 바꾸지 않는다. 같은 raw GAT TR 양편, ACTIVE/OACTIVE S/D를 자동 병합하지 않는다. pair는 전수 분류 또는 검증 가능한 명시 제외 이유를 남긴다. open-path는 단자·net 근거 없으면 생성하지 않고 `unsupported/unconfigured`라고 보고한다.
- Contact export는 물리 CNT1/CNT2 두 mask만 소유한다. 각 raw CNT 연결 성분은 유일한 선언 endpoint pair와 raw→cut provenance를 가져야 한다. export row는 endpoint pair별 분할 mask, 고유 contact ID, 원래 `hole_layer`를 사용한다. row 간 비중첩, 행 union=cut physical CNT, 빈/누락/중복/잘못된 endpoint/부분 TR 절단/외곽 잘림을 출력 전 진단한다. 부분 절단 홀은 조용히 작은 분모로 바꾸지 않고 기본 거부한다. 두 브리지의 graph-edge/두 홀/연속 METAL 근거와 100 CNT 홀/2×2를 검증한다. 기존 raw/cut/TR40/전극 periodic ID는 불변이다.
- 확정 지름은 `1..30,40,50` µm **32개만**. CNO는 all-layer TR cut 후 simulation 입력의 **개별 온전한 CNT 홀 연결 성분 전체 픽셀** 중 입자 가림이 `2*covered>=hole_pixels`인 경우다. effective endpoint 면적은 분모가 아니다. raw/cut/effective 픽셀 수를 각각 보존한다. source step/입경/입자 중심/형상/sample과 확정 연결이 모두 같은 CNO/open만 CNO 우선 중복 제거한다. 다른 연결 open과 모든 short, 원시 사건은 남긴다.
- 중앙 `[300,900)²` 600px 창만 통계 집계한다. 1200 ROI 각 변 300px halo, 최대 지름 50µm의 반경 250px 뒤 입자 footprint만 50px 여유. 32개 지름 각각 footprint·커널·margin·전체 홀/endpoint/short support를 계산해 여유 초과면 거부 또는 명시 미지원. 회로 open은 비국소 연결이므로 반경 비교만으로 안전 판정하지 않는다. 큰 halo를 만들 때 추출 전극 label을 단순 타일링하지 않고 periodic instance ID를 재계산한다.

## 직렬 Task와 수락 증거

1. **P0/P1 (Sol high 편집):** 이 repo adapter의 명시 config/stack/stage/mixed CNT1 분할 및 검증. 소유 `particle_sim_adapter.py`, 필요한 config/schema/CLI와 관련 단위 tests/docs. 기존 legacy export `validate-input` 양성 유지, mixed 최신 fixture export가 100 홀·155 layer mask·101 extracted net baseline을 재현하거나 net map으로 바뀐 수를 설명. 누락/중복/부분 TR/금지 endpoint는 출력 폴더 생성 전에 실패. 이 Task는 P2/P3와 파일 소유가 겹치므로 단독 편집.
2. **P2/P3 (Sol high 또는 명확히 분리되면 Luna high 편집):** 명시 net map, pair/open-path 상태, full-hole/raw-cut/TR·중간층 진단과 regressions. P0/P1 뒤 같은 파일을 직렬 소유. 정해지지 않은 net을 실제 net으로 가장하지 않음. 모든 층 TR cut 및 40 TR/2×2 동일. 실제 raw geometry overlap은 물리 short로 단정하지 않음.
3. **E1/E2/E3 (외부 변경 시안):** 원본 particle-sim을 편집하지 않는 무시 경로의 독립 복사본에서 최소 적용 가능 patch를 만들고 그 복사본에서만 테스트한다. 범위: full-cut physical-hole 50% CNO, 중앙 ROI 및 support gate, 동일 연결 CNO/open 중복 회계·raw 보존. 49/50/51%, 225px 홀 112/113, effective/whole 차이, 1/30/40/50 및 전 32 입경, 다른 연결/short 반례. 원본과 복사본 SHA/status를 기록. patch가 실제 원본에 적용·검증된 것으로 주장하지 않는다. E1의 full hole에 필요한 P1 provenance와 E3의 net map은 실제 의존이다. 원본 적용은 추후 사용자 최종 확인 단계.
4. **I1 통합·검증 (코디네이터):** fixture 재생성→추출→export→원본 particle-sim `validate-input` (지원되는 schema 범위)과 복사본 E1/E2/E3 실행/검증을 분리해 기록. Legacy 양성 대조군, 53개 이상 관련 pytest/Ruff, raw/cut/TR/bridge/seam 검증, 32 size 입력과 중앙 집계, 1/30/40/50 경계, bounded runtime/memory probe. 새 ignored output 디렉터리·정확한 CLI/로그/이미지 링크·제약을 남긴다. 전체 pair×32×step 물리 simulation은 입력 물성/net/분포 없이 수행하지 않는다.

## 검토·복구 gate

- 새 **`claude-opus-5-5` high 읽기 전용 계획 검토**가 이 문서와 v5, 관련 source/schema/test를 검토하고 blocking finding을 해결한 뒤에만 첫 편집 Dispatch를 시작한다. source/project `AGENTS.md`의 옛 Sonnet 규정은 최신 사용자 명시 Opus 규정보다 뒤선다.
- 구현 후보의 public schema/core/adapter 변경은 **별개의 fresh Opus 5.5 high 읽기 전용 코드 검토**가 정확한 commit/diff를 PASS해야 한다. 수정 후 stale PASS를 재사용하지 않는다.
- 하나의 편집 worker와 하나의 읽기 전용 worker만 허용한다. 모든 Task는 기존 Run에 저장한다. 이전 산출물과 partial diff를 보존하며 Orca의 positive settlement/release/ack/checkpoint 순서를 따른다. 원본 particle-sim은 읽기 전용, 추가 결제·원격 게시 없음.
