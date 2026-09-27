# Layout electrode extractor

[English README](README.md)

이 패키지는 주기적으로 반복되는 레이아웃 unit의 이진 레이어 마스크에서 전극 연결을
추출합니다. 결과는 원래 픽셀 해상도의 2×2 unit 이미지로 저장하며, 이름과 회로 대응을
붙이는 로컬 검토 UI와 particle-sim 입력 export를 제공합니다. 이 도구는 기하 처리
워크플로입니다. 합성 예시 값과 particle-sim export가 실제 공정의 물리적 타당성을
보장하지는 않습니다.

실제 레이아웃, 회로, 공정, Fab 데이터를 넣는 방법은
[실제 데이터 입력 가이드](docs/REAL-DATA-GUIDE.ko.md)와
`examples/real-data-template/`을 참고하세요.

## 핵심 동작

- **모든 레이어를 TR로 절단합니다.** `tr_pairs`에 선언한 GAT와 채널(ACTIVE/OACTIVE)이
  겹치는 영역을 TR로 보고, 접점 레이어를 포함한 모든 레이어에서 그 합집합을 제거한 뒤
  추출합니다. 제거된 부분은 전도하지 않습니다.
- **주기 연결을 정확히 계산합니다.** 2차원 격자 전체에서 연결 성분과 인스턴스 정체성을
  보존합니다. 이미 라벨링된 전극을 단순히 타일링하지 않으며, 유한한 주변 타일에서
  결과가 안정되었다는 사실을 정확성의 근거로 쓰지 않습니다.
- **출력은 2×2 이미지입니다.** 해상도는 그대로 유지되므로 600×600 px(0.1 µm/px) 입력은
  1200×1200 px(120×120 µm) 출력이 됩니다.

## 합성 예시 재현

Python 3.11 이상이 필요합니다. 저장소 루트에서 실행합니다.

```sh
python -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/layout-electrode-extractor make-synthetic outputs/demo/input
.venv/bin/layout-electrode-extractor extract outputs/demo/input/manifest.json outputs/demo/extraction
.venv/bin/layout-electrode-extractor review outputs/demo/extraction --circuit examples/circuit.csv
```

마지막 명령은 `http://127.0.0.1:8765`에 로컬 검토 페이지를 엽니다. TR과 전극을 선택해
이름과 회로 연결을 입력하고 UI에서 저장하세요. 저장한 뒤 다른 터미널에서, 또는 서버를
멈춘 뒤 검토 결과를 내보냅니다.

```sh
.venv/bin/layout-electrode-extractor export-reviewed outputs/demo/extraction outputs/demo/reviewed --circuit examples/circuit.csv
```

### 합성 fixture 구성

생성기는 0.1 µm/px, 600×600 px unit을 만들며 배선 폭은 약 20 px(2 µm)입니다.

- **레이어:** GAT 3개, ACTIVE, OACTIVE, 접점 레이어 2개(CNT1, CNT2), METAL1
- **버스:** 수평 GAT1 버스 2개가 R과 B, GAT2 버스가 G를 나타냅니다.
- **TR:** unit당 10개(GAT1/ACTIVE 4, GAT2/OACTIVE 2, GAT3/OACTIVE 4), 2×2 전체로 40개입니다.
- **물리 순서(아래→위):** ACTIVE, GAT1, GAT2, OACTIVE, GAT3, CNT1, CNT2, METAL1.
  도체만 적는 `stack`에서는 CNT1과 CNT2가 빠집니다.
- **CNT1:** 한 물리 마스크에 홀 14개가 있습니다. ACTIVE–METAL1이 11개, GAT2–METAL1이 3개입니다.
  이 중 네 홀이 METAL1 브리지 두 개(ACTIVE→CNT1→METAL1→CNT1→GAT2)를 이룹니다.
- **CNT2:** OACTIVE–METAL1 홀 11개입니다.
- **METAL1:** 왼쪽과 오른쪽 METAL1 trunk가 각각 unit 세로 전체를 가로지릅니다.

층 순서, endpoint, 기하는 fixture 가정이며 측정된 공정 자료가 아닙니다. 원래 계약의
"GAT 2개"는 이후 GAT 3개 생성기로 대체되었습니다.

## particle-sim export와 검증

혼합 CNT1 합성 추출은 설정 파일과 함께 export하고 검증합니다.

이물 유입 단계의 `surface_model`은 `flat`, `conformal`, `partial`을 지원합니다.
`after_pattern`에는 `conformal`을 기본 권장합니다. `partial`은 landing 단계까지
모든 비도체 stack 행에 명시적인 `planarization_factor`가 필요합니다.
`flat`과 0 contact margin을 함께 쓰면 short CA가 구조적으로 0이 되어 particle-sim이
`STRUCTURAL_ZERO_SHORT` 경고를 냅니다. CNT open 단계는 CNO의 의도적인 flat-film 근사로
`flat`을 유지합니다.

```sh
.venv/bin/layout-electrode-extractor export-particle-sim \
  outputs/demo/extraction outputs/demo/particle-sim \
  --config examples/synthetic-particle-config.json
<particle-sim 경로>/.venv/bin/particle-sim validate-input \
  --product-config outputs/demo/particle-sim/product.yaml
```

- **설정 없이 export(legacy):** `--config`를 빼면 CNT 레이어마다 endpoint 쌍이 하나인
  기존 방식으로 export합니다. 이 경우 혼합 CNT1은 출력을 만들기 전에 거부됩니다.
- **설정 파일(version 1 JSON)에 들어가는 것:**
  - 마스크가 없는 절연막을 포함한 공정 stack(`process_stack`)
  - 이물 유입 단계(`source_stages`)
  - 입경 목록: 1–30 µm, 40 µm, 50 µm의 32개 값 중 오름차순 부분집합
  - 선택 항목: `net_map`(추출 전극 ID → 확정 회로 net), `excluded_pairs`, `open_paths`,
    `cno_open_relations`
  - 필드별 설명은 [실제 데이터 입력 가이드](docs/REAL-DATA-GUIDE.ko.md) 4절에 있습니다.
- **출력:**
  - 도체는 원본(raw) 반복 마스크를 지형용으로 씁니다. CNT/VIA는 TR로 절단된 홀 마스크를 씁니다.
  - 서로 다른 net의 전극 쌍을 모두 분류합니다. 같은 레이어 쌍은 `lateral_short`,
    다른 레이어 쌍은 `vertical_short`입니다.
  - 조용히 빠지는 쌍은 없습니다. 제외된 쌍에는 모두 사유가 기록됩니다.
- **`adapter-provenance.json`:**
  - 모든 레이어의 raw/cut/TR 픽셀 수, 단계별 마스크 수, raw 도체 겹침(관찰로만 기록)을 담습니다.
  - 홀별 진단(`physical_hole_diagnostics`)과 `product.yaml`의 SHA-256도 기록합니다.
- **설정 export가 출력 전에 거부하는 경우:**
  - `hole_in_tr`: TR에 걸린 홀
  - `hole_through_intermediate_conductor`: 선언되지 않은 중간 도체를 관통하는 홀
  - `metal_over_tr`는 관찰로만 기록하고 허용합니다.
- **홀 seed 규칙:**
  - 명시된 seed는 자기 raw 컴포넌트와 일치해야 하고, 선언된 규칙의 `holes`에도 들어 있어야 합니다.
  - `seed: null`은 legacy와 설정 모드 모두에서, 레이어에 규칙이 정확히 하나이고 그 규칙에
    `holes`가 없을 때만 허용합니다.
  - 각 행이 가리키는 규칙은 같은 레이어의 규칙이어야 합니다.
- **legacy 호환 범위:** 4-연결이고 `contact_holes` provenance가 완전한 추출만 받습니다.
  대각선으로만 이어진 홀을 하나로 합치는 8-연결 마스크와 provenance가 없는 예전 폴더는 거부합니다.

## 현재 particle-sim 연계 상태 (2026-09-26)

| 대상 | 상태 |
| --- | --- |
| extractor 제품 | `77b335a`, 독립 Opus 5.5 high 검토 PASS |
| particle-sim 격리 복사본 | `7213deb`, 독립 검토 PASS, 복사본 테스트 369개 통과 |
| 누적 패치 | `aae492a..7213deb`, SHA-256 `e715b36910ac57577d927496a067fab98584e6890d5d453101836c7f859936f4` |
| 원본 particle-sim | 사용자 승인으로 **로컬 브랜치 `v5-extractor-integration`** 에 적용, 커밋 `fca4806`. 원본 pytest 369개, Ruff, I1 `validate-input` 통과 |

particle-sim 쪽 변경은 다음과 같습니다.
- **E1:** 홀 전체 cut 면적의 50% 이상이 가려지면 CNO로 판정합니다.
- **E2:** 중앙 `[300,900)²` 영역의 support를 감사합니다.
- **E3:** 동일 이물·동일 연결의 CNO/open 중복을 제거합니다.
- CNO 계산을 정수 sparse 누적 방식으로 바꿔 빠르게 했습니다.

원본의 기존 브랜치 `schema2-contacts-cno`는 `aae492a` 그대로입니다. 원격에는 게시하지 않았습니다.
경위와 근거는 [체크포인트](docs/orca/CHECKPOINT.md)와 [한국어 최종 보고서](docs/orca/FINAL-REPORT.ko.md)에 있습니다.

## particle-sim 호환 버전

두 레포는 따로 관리합니다([particle-sim](https://github.com/jake-jonghyeonlee/particle-sim)). 서로의 Python 코드를 import하지 않고 파일로만 연결됩니다.
연결 파일은 schema 2.0 `product.yaml`, 레이어별 마스크, 그리고 particle-sim이
`analyze-cno-open --adapter-sidecar`로 읽는 `adapter-provenance.json`입니다.

| layout-electrode-extractor | particle-sim | 상태 |
| --- | --- | --- |
| `main`의 `77b335a` 이후 | 브랜치 `v5-extractor-integration`, 커밋 `fca4806` | 지원. 설정 export, 50% 홀 CNO(E1), 중앙 support 감사(E2), sidecar 해시 결합 CNO/open 중복 제거(E3) |
| `--config` 없는 legacy export | `aae492a` (`schema2-contacts-cno`) | P2 점검에서 `validate-input` 통과. `fca4806`에서는 다시 확인하지 않음 |

`fca4806`의 Git tree는 독립 검토를 통과한 복사본 커밋 `7213deb`와 같습니다. 두 레포를
게시한 뒤에는 커밋 ID 대신 릴리스 태그로 이 표를 갱신하세요.

## 한계

- 합성 회로, stack 두께, 유전 특성, 입자 설정은 예시용 가정입니다.
- 추출은 주기 정체성을 쓰지만, particle-sim 입력은 유한한 2×2 이미지이고 주기 경계조건이
  없습니다. 바깥 경계가 결과에 영향을 줄 수 있으므로 중앙 영역 기준으로 해석하세요.
- 2×2 출력은 unit 면적의 4배이지만, critical area나 불량 수가 정확히 4배가 되지는 않습니다.
- `profile: "measured"`는 접점이 있으면 거부됩니다. CNT open 단계는 평면 근사입니다.
- 회로 open 연결성은 비국소 문제라 인증되지 않습니다. 긴 배선에서 open 커널 비용이 큽니다.
- 전체 쌍×입경×단계 시뮬레이션과 물리적 불량률은 검증하지 않았습니다.

## 명령과 출력

```sh
.venv/bin/layout-electrode-extractor --help
.venv/bin/pytest
.venv/bin/ruff check .
```

`outputs/`, 가상환경, 캐시, 빌드 산출물은 Git에서 제외됩니다. 생성기와 예시 입력만
버전 관리하고, 생성된 마스크나 시뮬레이션 결과는 커밋하지 마세요.
