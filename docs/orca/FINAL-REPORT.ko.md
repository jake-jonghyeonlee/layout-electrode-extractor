# 첫 로컬 릴리스 최종 보고서

[영문 원본](FINAL-REPORT.md)

> 이 문서의 뒷부분 「완료 결과」 이하는 첫 로컬 릴리스(Run `run_3cf905a17b81`, 제품
> `6b8bd68`)의 번역입니다. 그 뒤 Run `run_5463d205f39d`에서 진행한 fixture 고도화와
> particle-sim v5 연계 결과를 먼저 정리합니다.

## 2026-09-25 v5 연계 현황 요약

### 기준 커밋과 검토

| 대상 | 커밋 | 독립 검토 |
| --- | --- | --- |
| extractor 제품 | `6893fe6` | Opus 5.5 high PASS ([검토](FINAL-OPUS-CODE-REVIEW-20260925.md)), 권고 A1–A10 |
| particle-sim 격리 복사본 E1–E3 | `9a7cc2b` | 위 검토와 함께 PASS |
| particle-sim 격리 복사본 sparse CNO | `3bedd08` | Opus 5.5 high PASS ([검토](CNO-SPARSE-OPUS-REVIEW-20260925.md)) |
| 누적 simulator 패치 | `aae492a..3bedd08` | SHA-256 `14b5f6701fb54365905e21d847a1005df8a8f8c722a082adf0d1daf342e97bb4`, 원본에 `git apply --check` 통과, **미적용** |

원본 `/Users/jonghyeonlee/git/particle-sim`은 `aae492a`에서 변경되지 않았습니다.
모든 E-stage 구현은 Git 무시 경로 `outputs/v5-integration-20260924/particle-sim-copy`에서만
수행했습니다.

### 추가된 기능

- **합성 fixture:** GAT1/GAT2/GAT3 R/G/B 수평 버스, 전체 높이 METAL1 trunk,
  ACTIVE→CNT1→METAL1→CNT1→GAT2 브리지 2개. unit당 TR 10개(2×2에서 40개), 모든 층 TR 절단,
  CNT1 14개·CNT2 11개 홀, 20 px 배선, 600→1200 px, 0.1 µm/px. `physical_stack`에
  합성 층 순서 `ACTIVE,GAT1,GAT2,OACTIVE,GAT3,CNT1,CNT2,METAL1`을 기록합니다.
  원래 계약의 “GAT 2개”는 최신 생성기(GAT 3개)로 대체되었습니다.
- **P0/P1 명시적 공정 입력:** 마스크 없는 절연층을 포함한 process stack, 마스크 층에만 두는
  source stage, 32개 입경(1–30, 40, 50 µm) 설정을 검증합니다. 같은 CNT1 안의
  ACTIVE–METAL1과 GAT2–METAL1 홀을 서로 겹치지 않는 별도 contact row로 분할하며,
  분할 마스크의 합집합이 원래 cut CNT1과 정확히 같은지 검사합니다.
- **P2 회로 선언:** 추출 전극 ID와 회로 net ID를 분리하는 완전한 `net_map`(다대일 허용),
  모든 전극 쌍의 안정 ID와 제외 사유, 명시적 open 경로(`fallback: error`, 자동 open 없음),
  CNO/open 관계 선언을 지원합니다.
- **P3 홀 단위 진단:** 홀별 raw/cut/TR 제거/유효 픽셀 수, 상·하부 enclosure, 다른 도체와의
  교차를 `adapter-provenance.json`에 기록합니다. 설정 모드는 `hole_in_tr`과
  `hole_through_intermediate_conductor`를 출력 전에 거부하고, `metal_over_tr`는 관찰로만 기록합니다.
- **particle-sim 복사본 E1–E3와 sparse CNO:** E1 홀 전체 cut 면적 대비 50% 이상(포함) 가림 시
  CNO, E2 중앙 `[300,900)²` 집계 영역의 국소 support 감사, E3 동일 이물·동일 연결의
  CNO/open 중복 제거(원시·제거·최종 분할 보존). 이후 CNO 상관 계산을 정수 sparse 누적으로 바꿔
  약 20 GB RSS가 필요하던 계산을 수 초·1 GB 미만으로 줄였습니다.

### particle-sim 연결성 검증

| 단계 | 결과 |
| --- | --- |
| [연계 점검](PARTICLE-SIM-LINK-CHECK-20260924.md) (`f01d0d5`) | 브리지 fixture는 CNT1 endpoint 혼합 때문에 어댑터가 exit 2로 거부. 옛 fixture 양성 대조군은 `validate-input` 통과. 필요한 변경 4가지 도출 |
| [P2/P3](P2-ADAPTER-REPORT-20260924.md) | 전극 행 155, 홀 100, contact row 3, 포함 쌍 11,879. mapped·exclusion·legacy 출력 모두 원본 `validate-input` `ok`, 미해결 0 |
| [I1 통합](I1-INTEGRATION-REPORT-20260924.md) | 최신 생성·추출·설정 export를 원본과 복사본 모두 `validate-input` `ok`(1200×1200, 155 전극, 11,879 쌍). E2 96행: 국소 reach 최대 257 px < 300 px, `SOURCE_CNT1_OPEN` 32행은 비국소 open으로 미지원 표시 |
| sparse 재측정 | 실제 short 맵 12개와 CNO 맵 12개(1/30/40/50 µm), 6.81 s, 약 844 MB RSS. 실제 open 커널 맵은 0개이며 E3 open 관계는 2픽셀 합성 맵으로만 확인 |

이 결과는 입력 계약 호환성과 선택한 기하 계산의 재현성을 보여줍니다. net 매핑은 합성
항등 매핑이고, stack 두께·물성·입경 분포는 가정 또는 미입력 상태입니다. 전체
쌍×입경×단계 시뮬레이션, 회로 open 연결성, 물리적 불량률은 입증하지 않았습니다.
particle-sim은 2×2 이미지를 유한 ROI로 받으며 주기적 경계조건을 적용하지 않습니다.

### 후속 작업 우선순위

**P0 — 원본 particle-sim에 패치를 적용하기 전에 필요한 작업**

1. **A2 수정:** E3가 늦은 검증 실패 시 0으로 채워진 `derived/dedup_open.zarr`를 남깁니다.
   모든 맵을 먼저 검증하거나 staging 후 rename으로 게시하도록 고칩니다. 같은 작업에서 **A3**
   (검토자가 확인한 14개 잘못된 입력 거부의 단위 테스트)를 추가합니다.
2. **A1 결정:** legacy export가 대각선으로만 이어진 CNT 픽셀(8-연결)을 이제 거부합니다.
   진단 코드로 기록할지, 좁아진 legacy 계약을 문서화할지 정합니다.
3. **A9·A7·A8 보강:** sidecar에 `product.yaml` SHA-256을 기록해 E3에서 결합을 확인하고,
   홀 seed 좌표를 재검증하며, 게시 시 빈 디렉터리 경쟁 조건과 선행 `mkdir`를 정리합니다.
4. **최종 후보 재검토:** 위 수정을 포함한 extractor와 복사본 커밋 조합으로 fresh Opus high
   독립 검토 PASS를 다시 받습니다. 기존 PASS는 이전 커밋에만 유효합니다.
5. **원본 적용(사용자·저장소 소유자 결정):** 검토된 누적 패치를 원본에 적용하고 그 저장소에서
   pytest, Ruff, `validate-input`을 다시 실행합니다. 원본 적용은 이 레포의 작업 범위 밖이므로
   명시적 승인이 필요합니다.

**P1 — 실제 의미 있는 결과를 위해 외부 입력이 필요한 작업**

6. **확정 회로 netlist:** 현재 합성 항등 매핑을 실제 회로 연결로 바꿉니다. 자기 TR로 나뉜
   같은 gate가 서로 다른 net의 short 후보로 잡히는 문제를 해소합니다.
7. **실제 공정 stack·물성·입경 분포:** 층 두께, 절연막 위치·물성, 입경별 가중치 없이 불량률을
   산정할 수 없습니다.
8. **open 커널 비용과 비국소 open:** 긴 버스에서 실제 open 커널이 약 21 GB RSS로 중단됐습니다.
   CNO처럼 경계가 있는 구현이 필요하며, `SOURCE_CNT1_OPEN`의 비국소 연결성 인증 방법도 정해야
   합니다.

**P2 — 범위 확장과 품질 정리**

9. 비용 측정 후 제한된 전체 쌍×입경×단계 시뮬레이션을 실행합니다. 현재는 선택한 쌍만 계산했습니다.
10. 실제 레이아웃 unit으로 추출과 검토 UI를 검증합니다. 지금까지는 합성 fixture만 사용했으며,
    최종 fixture의 브라우저 검토는 시각 확인에 그쳤습니다.
11. 남은 권고를 처리합니다: A4 ROI 가장자리 홀 동작 문서화, A5 비볼록 홀에 전체 span 사용,
    A6 CNT1/CNT2 홀 겹침 진단·`CONDUCTOR`의 `metal_over_tr`·enclosure 임계값, A10 입경 부분집합과
    E2 요구의 차이 문서화.
12. 문서를 정리합니다: 계약 문서의 “GAT 2개” 문구 갱신, `docs/orca/REVIEW.md` Python 코드 블록의
    `ruff format` 지적 해소.

## 완료 결과

첫 로컬 릴리스의 구현과 검증을 `main` 브랜치에서 완료했습니다. 검증 대상 제품 커밋은
`6b8bd682f9d1dfaf4df4d1e84e9027c09c016b04`이며, 기준 커밋은
`439372f5897ffcb9175a0d330f6990d12ff1d0b7`입니다. 독립적인 Claude Sonnet high 검토에서
해당 제품 SHA에 대해 조건 없는 PASS를 받았습니다. 근거는 [REVIEW.md](REVIEW.md)에
기록되어 있습니다. 원격 저장소에 게시하지 않았습니다. 영문 보고서와 체크포인트는 검토된
제품 SHA 이후의 문서 커밋으로, 제품 코드를 변경하지 않습니다. 이 한글판은 해당 보고서의 번역입니다.

Orca Run `run_3cf905a17b81`의 조정 및 수명주기는 코디네이터 터미널
`term_2b2539fe-3275-42de-8d69-008f8559c7d7`이 관리했습니다. 저장된 Task 8개를 모두
완료했습니다. 종료된 모든 worker에 Orca release 결정을 적용하고 결과 전달 확인을
완료했습니다. 마지막 `worker-list --terminal-state reclaimable` 조회 결과는 0개였습니다.
명시적으로 생성한 터미널은 Orca의 외부 리소스로 남아 있지만, 활성 편집 또는 검토
Dispatch는 없습니다.

| 작업 | 저장된 Task ID | 결과 |
| --- | --- | --- |
| T1 정확한 주기적 연결 추출 | `task_b92fb0d783ae` | `723efc5`, 완료 승인 |
| T2 검토 UI, 이름 지정, 회로 연결 | `task_64d014d8fc4c` | `153f8e2`, 완료 승인 |
| T3 합성 데이터 및 particle-sim 어댑터 | `task_4a52361c281a` | `1b96df6`, 완료 승인 |
| T4 독립 검토 | `task_693c45297d8e` | 지적 사항 기록, PASS 없음 |
| T5 역할 및 접점 처리 어댑터 수정 | `task_81b3de404c06` | `23f7196`, 완료 승인 |
| T6 독립 재검토 | `task_904c4294584e` | 범위를 좁힌 지적 사항 2 기록, PASS 없음 |
| T7 CONDUCTOR 역할 처리 수정 | `task_bc341f6eee99` | `6b8bd68`, 완료 승인 |
| T8 독립 최종 검토 | `task_dfe47171b5f3` | `6b8bd68`에 대해 조건 없는 PASS |

검토 worker의 시작 실패도 Orca 이력에 보존했습니다. T4의 `ctx_44bee5c8742b`는
작업 공간 신뢰 확인 단계에서 멈췄으며, 터미널에서 상태를 확실히 확인한 후 실행 권한을
차단했습니다. T4의 `ctx_1da55f0d22ba`와 T6의 `ctx_96cf7be3dfa2`는
`agent_readiness`/실행 주체 식별 정보 변경 단계에서 실패했고, 실제 리소스는 생성되지
않았습니다. 새로 명시적으로 생성한 Claude 터미널에서 T4, T6, T8을 성공적으로
완료했습니다. 실패한 시도를 삭제하거나 제품 검토 PASS로 처리하지 않았습니다.

## 구현된 기능

- 엄격한 manifest 검증과 설치 가능한 CLI를 제공합니다. 접점 레이어를 포함한 모든 선언된
  레이어에서 TR 영역의 합집합을 제거한 뒤 추출합니다. 정확한 주기적 연결 계산으로 2차원
  격자 전체에서 연결 성분과 개별 인스턴스의 식별 관계를 보존합니다. 유한한 주변 타일 범위에서
  결과가 안정되었다는 사실을 정확성의 근거로 사용하지 않습니다.
- 출력은 0.1 µm/px 해상도를 유지하는 2×2 이미지입니다. 제공된 600×600 합성 유닛은
  1200×1200 이미지로 출력됩니다. 배선 폭은 약 20 px(2 µm)이며, GAT 2개, ACTIVE,
  OACTIVE, CNT 2개, METAL1 레이어를 사용합니다.
- 로컬 검토 UI에서 전극/TR 선택, 이름 지정, 주석 저장, 회로 연결, 지정된 이름을 반영한
  마스크 내보내기를 지원합니다. JSON/CSV 회로 표는 G/S/D 단자를 갖는 TFT와 선택적인
  B 단자를 지원하므로, 3단자 TFT에 없는 body 연결을 임의로 만들지 않습니다. 4단자 MOS도
  지원합니다. SPICE 직접 가져오기는 지원하지 않습니다. 회로도 이미지는 사람이 연결 관계를
  확인하는 시각적 참고 자료로 사용하며, UI가 배선 그래프를 추론하거나 OCR을 수행하지는 않습니다.
- particle-sim 어댑터는 스키마 2.0 입력, 명시적인 쌍 분류, stack 행, 접점 연결의 출처 정보,
  레이어별 마스크를 출력합니다. 가정에 따른 유전체 배치는 선언된 역할을 기준으로 계산하며,
  METAL과 CONDUCTOR를 유효한 상부 도체로 취급합니다. 지원하지 않거나 모호한 stack은
  출력 생성 전에 `ManifestError`를 발생시킵니다.

## 최종 제품 SHA 검증

코디네이터가 `.venv/bin/pytest -q`를 재실행하여 26개 테스트 통과를 확인했습니다.
`.venv/bin/ruff check .`도 통과했고, `.venv/bin/ruff format --check src tests`에서는
14개 파일의 형식이 이미 올바름을 확인했습니다.
`node --check src/layout_electrode_extractor/static/app.js`도 통과했습니다.
독립 검토자는 테스트를 다시 실행하고, 수정된 CONDUCTOR 역할의 유전체 배치와 상부
METAL/CONDUCTOR 역할이 없을 때의 명시적인 오류 진단을 모두 재현했습니다.

코디네이터는 인접한 실제 particle-sim 저장소를 수정하지 않고 해당 저장소의
`validate-input` CLI를 실행하여 다음 최종 출력을 독립적으로 검증했습니다.
이 생성물들은 Git 추적에서 제외되어 있습니다.

| 제품 manifest | 크기 및 해상도 | 마스크 수 | 쌍 수 | 결과 |
| --- | --- | ---: | ---: | --- |
| `outputs/task-final-default/particle-sim/product.yaml` | 1200×1200, 0.1 µm/px | 98 | 4,743 | `ok`, 미해결 항목 0개 |
| `outputs/task-final-renamed/particle-sim/product.yaml` | 1200×1200, 0.1 µm/px | 120 | 7,130 | `ok`, 미해결 항목 0개 |
| `outputs/task-final-conductor/particle-sim/product.yaml` | 1200×1200, 0.1 µm/px | 98 | 4,743 | `ok`, 미해결 항목 0개 |

범위를 제한한 대표 particle-sim 실행 결과는 `outputs/t3-final/smoke-run-final`에
있습니다. 한 쌍만 시뮬레이션했고, 나머지 4,742쌍은 해당 기본 동작 확인용 manifest에서
명시적으로 제외했습니다. 따라서 이 결과는 선택한 한 쌍에 대한 실행만 입증합니다.

원래 사용자 대화 세션에서는 후보 커밋 `153f8e2`에 대해 Aside Playwright를 사용했습니다.
Git 추적에서 제외된 `outputs/browser-smoke.json`에 1200×1200 렌더링, E00001 선택,
`Browser_Gate` 저장 및 새로고침 후 유지, GAT1 전환, TR00001 선택, `Browser_T1` 저장,
선택적 B 단자를 포함한 G/S/D 입력 폼, `outputs/t1-smoke/extracted-reviewed`의
이름 반영 내보내기 경로를 기록했습니다. 별도의 브라우저 시각 검토에서는 최종 2 µm 합성
데이터의 반복되는 굴곡·분기·루프와 전극 인스턴스 88개, TR 인스턴스 32개가 표시됨을
확인했습니다. 스크린샷은 `outputs/layout-review-final.png`입니다. 첫 브라우저 기본 동작
검증에는 이전의 가는 배선 데이터를 사용했으며, 최종 데이터의 브라우저 검토는 시각 확인만 수행했습니다.

## 로컬 실행

환경 설정, 데이터 생성, 추출, 검토 결과 내보내기 및 particle-sim 명령은
[README.md](../../README.md)를 참고하세요. 이미 생성된 최종 데이터를 확인하려면 다음을 실행합니다.

```sh
.venv/bin/layout-electrode-extractor review outputs/t3-final/extraction --port 18876
```

브라우저에서 `http://127.0.0.1:18876/`을 엽니다. 위 명령으로 서버를 다시 시작해야 하며,
릴리스용 서버가 백그라운드에서 계속 실행 중이라는 의미는 아닙니다. 브라우저 검증 당시에는
다른 프로세스가 18765 포트를 사용하고 있어 임시로 18769 포트를 사용했습니다.

## 제한사항

합성 회로, stack 두께, 유전 특성 및 입자 설정은 예시용 가정입니다. particle-sim은 유한한
2×2 이미지를 입력받으며 주기적 경계 조건을 적용하지 않으므로, 바깥쪽 경계가 시뮬레이션
결과에 영향을 줄 수 있습니다. 쌍 수와 임계 면적이 물리적 불량률의 4배 증가를 의미하지는
않습니다. 출력된 모든 쌍은 입력 검증을 통과했지만, 실제 시뮬레이션은 한 쌍에 한정했습니다.
검토 후 이름을 반영한 내보내기는 사용자가 지정한 주석에 의존합니다. 저장소 전체에 대한
`ruff format --check .`는 검토자가 작성한 `docs/orca/REVIEW.md`의 Python 코드 블록을
지적합니다. 소스와 테스트 파일의 형식 검사는 통과했습니다.

## 2026-09-25 P0 보강 진행 상황

새 Orca Run `run_5ebf21e5c7f7`에서 E3 원자적 출력과 입력 오류 14종 테스트, 레거시
8-연결 CNT 진단, 접점 seed 확인, 경합 없는 출력 게시, `product.yaml` SHA-256 출처 결합을
구현했습니다. 추출기 제품 커밋은 `4410ec3`, 격리된 particle-sim 복사본은 `7213deb`입니다.
누적 패치의 SHA-256은 `e715b36910ac57577d927496a067fab98584e6890d5d453101836c7f859936f4`이며
원본에 대한 읽기 전용 `git apply --check`를 통과했습니다. 코디네이터 검증에서 추출기 테스트
109개, 복사본 테스트 369개가 통과했고, 원본 `validate-input`은 전극 155개·쌍 11,879개·
미해결 쌍 0개를 보고했습니다. 원본 저장소에는 패치를 적용하지 않았습니다.

레거시 단일 규칙의 `seed: null` 허용 여부는 사용자 결정 대기 중입니다. 그 결정에 따라
제품 후보를 확정한 뒤 별도의 Opus 5.5 high 검토를 진행해야 하므로, 현재 P0 완료 판정이나
독립 검토 PASS는 없습니다.
