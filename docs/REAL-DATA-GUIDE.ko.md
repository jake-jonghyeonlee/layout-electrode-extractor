# 실제 데이터 입력 가이드

이 문서는 합성 fixture 대신 실제 레이아웃, 회로, 공정, 이물 데이터를 넣어
추출부터 particle-sim 계산까지 진행하는 방법을 정리합니다. 예시 파일은
[`examples/real-data-template/`](../examples/real-data-template/)에 있습니다.
예시 파일의 숫자, 좌표, 이름은 모두 **형식 예시**이므로 실제 값으로 바꿔야 합니다.

## 전체 흐름

```text
① 레이어 마스크 PNG + manifest.json
        │  layout-electrode-extractor extract
② 추출 결과 (2×2, 전극·TR ID)
        │  review UI에서 이름 붙이기와 회로 대조 (circuit.csv)
③ 전극 ID ↔ 회로 net 대응 확정
        │  process-config.json 작성 (공정 stack, source stage, net_map, open 경로)
④ layout-electrode-extractor export-particle-sim --config
        │  particle-sim validate-input
⑤ particle-sim 계산 (simulate-nominal, analyze-central, analyze-cno-open)
        │  fab-mean.csv
⑥ particle-sim apply-fab → 기대 위험
```

| 입력 | 파일 | 누가 제공 | 필수 여부 |
| --- | --- | --- | --- |
| 레이어 마스크 | `masks/*.png` | 레이아웃 (GDS/OASIS를 래스터화) | 필수 |
| 추출 manifest | `manifest.json` | 레이아웃·공정 담당 | 필수 |
| 회로 표 | `circuit.csv` 또는 `.json` | 회로 담당 | 권장 (review 대조용) |
| 공정·export 설정 | `process-config.json` | 공정 담당 + 검토자 | 혼합 CNT나 `net_map`을 쓰면 필수 |
| Fab 이물 분포 | `fab-mean.csv` | Fab 검사 데이터 | 기대 위험 계산 시 필수 |

## 1. 레이어 마스크 준비

추출기는 GDS를 직접 읽지 않습니다. KLayout 같은 외부 도구로 각 레이어를 래스터화해서
PNG로 넣어야 합니다.

- **범위는 정확히 한 주기(unit)입니다.** 이미지 오른쪽 끝이 왼쪽 끝과, 아래 끝이 위 끝과
  이어지는 반복 단위여야 합니다. 경계에서 배선이 어긋나면 주기 연결이 틀어집니다.
- **해상도는 `pixel_size_um`에 맞춥니다.** 권장값은 0.1 µm/px입니다. 출력은 같은
  해상도의 2×2 이미지입니다.
- **크기는 600×600 px(60×60 µm unit)를 권장합니다.** particle-sim의 E2 중앙 집계
  (`analyze-central`)는 1200×1200 ROI와 0.1 µm/px를 요구합니다. 다른 크기도 추출과
  `validate-input`은 되지만 E2 support 감사는 거부됩니다.
- **형식:** 단일 채널(`L` 또는 `1` 모드) PNG, 값은 0 또는 255만 허용합니다. 안티앨리어싱
  회색값이 있으면 거부됩니다. 모든 레이어는 같은 크기여야 합니다.
- **한도:** unit당 최대 2,000,000 px, 전체 레이어 합계 20,000,000 layer-px입니다.
- **접점 홀(CNT/VIA)** 은 unit 가장자리에 닿으면 안 됩니다. 필요하면 unit 원점을 옮겨
  홀이 경계 안쪽에 오도록 자르세요. 홀은 4-연결 기준으로 하나씩 분리되어야 합니다.
  대각선으로만 닿는 두 홀은 legacy export에서 거부됩니다.
- **TR 영역:** 별도 마스크가 없습니다. `tr_pairs`에 적은 GAT와 채널 레이어가 겹치는
  영역을 TR로 보고, 모든 레이어에서 잘라냅니다. 잘린 부분은 전도하지 않습니다.
  TR과 겹치는 접점 홀은 설정 export에서 거부됩니다.

## 2. `manifest.json` 작성

예시: [`manifest.json`](../examples/real-data-template/manifest.json)

| 필드 | 의미 | 주의 |
| --- | --- | --- |
| `layers[].id` | 레이어 ID | 영문자로 시작하는 ASCII, 최대 64자 |
| `layers[].role` | `GAT`, `ACTIVE`, `OACTIVE`, `METAL`, `CONDUCTOR`, `CNT`, `VIA`, `OTHER` | 역할에 따라 TR, stack, 접점 처리가 달라짐 |
| `layers[].path` | manifest 기준 상대 경로 | 상위 디렉터리로 벗어날 수 없음 |
| `stack` | 도체 레이어만 아래→위 순서로 | 모든 도체 역할 레이어를 정확히 한 번씩 |
| `physical_stack` | 도체와 CNT/VIA를 아래→위 순서로 | 도체 순서는 `stack`과 같아야 함. `--config`를 쓰려면 필수 |
| `tr_pairs` | `{gat, channel}` | channel은 ACTIVE 또는 OACTIVE 역할 |
| `contacts` | 홀 레이어별 lower/upper 도체 | `lower < 홀 < upper` 물리 순서 |
| `connectivity` | 4 또는 8 | 기본값 4 권장 |

**접점 규칙**
- 한 CNT 레이어가 한 종류의 연결만 하면 규칙 하나만 쓰고 `holes`를 생략합니다. 예시의 CNT2가 이 경우입니다.
- 한 CNT 레이어 안에 연결 종류가 섞여 있으면 규칙을 여러 개 쓰고, **모든 규칙에 `holes`** 를 적습니다. 예를 들어 CNT1 안에 ACTIVE–METAL1 홀과 GAT2–METAL1 홀이 섞여 있는 경우입니다.
  - `holes`에는 각 홀 내부의 한 픽셀 좌표를 `[x, y]` 형식으로 적습니다. unit 픽셀 좌표이고 원점은 왼쪽 위입니다.
  - 모든 홀이 정확히 하나의 규칙에 배정되어야 합니다.
- 규칙이 여러 개인 레이어에서 규칙 하나만 `holes`를 생략하면 오류가 납니다.

실행:

```sh
.venv/bin/layout-electrode-extractor extract my-layout/manifest.json outputs/my-extraction
```

출력 `outputs/my-extraction/manifest.json`의 `issues`가 비어 있는지 확인합니다. 전극 수와 TR 수도 예상과 맞는지 확인합니다.

## 3. 전극 확인과 회로 대조 (review)

회로 표 예시: [`circuit.csv`](../examples/real-data-template/circuit.csv)

- CSV 헤더는 `device,terminal,net[,channel_role]`입니다.
- `terminal`은 `G`, `S`, `D`가 필수이고 `B`는 선택입니다. 3단자 TFT는 B를 적지 않습니다.
- `channel_role`은 `ACTIVE` 또는 `OACTIVE`입니다.
- 같은 내용을 JSON(`{"devices": [{"id", "terminals": {...}, "channel_role"}]}`)으로 줄 수도 있습니다.

```sh
.venv/bin/layout-electrode-extractor review outputs/my-extraction \
  --circuit my-layout/circuit.csv --schematic my-layout/schematic.png
```

- 브라우저에서 전극과 TR을 선택해 이름과 회로 단자를 연결하고 저장합니다.
- 회로도 이미지는 사람이 보는 참고 자료입니다. UI가 회로도에서 배선을 인식하지는 않습니다.
- 여기서 확정한 **추출 전극 ID(`E00001` …) → 회로 net** 대응이 다음 단계 `net_map`의 근거가 됩니다.

## 4. `process-config.json` 작성

예시: [`process-config.json`](../examples/real-data-template/process-config.json)

### 4.1 공정 stack (`process_stack`)

모든 공정 층을 **아래→위 순서**로 적습니다. 마스크가 없는 절연막도 포함합니다.

| kind | `mask_layer` | `material_type` | `patterned` |
| --- | --- | --- | --- |
| `conductor` | 자기 ID | `conductor` | `true` |
| `hole` | 자기 ID | `inorganic` | `true` |
| `dielectric` | `null` | `inorganic` 또는 `organic` | `false` |

- `thickness_um`은 양수입니다. `planarization_factor`는 선택이며 0–1 범위입니다.
- 두 가지가 manifest와 정확히 일치해야 합니다.
  - 마스크가 있는 행만 순서대로 뽑으면 extraction의 `physical_stack`과 같아야 합니다.
  - 도체 행만 뽑으면 `stack`과 같아야 합니다.
- **실제 두께와 물성**은 이 표에 넣습니다. 예시 값은 형식 예시일 뿐입니다.

### 4.2 이물 유입 단계 (`source_stages`)

- 마스크가 있는 층 뒤에만 둘 수 있고, `process_stack` 순서를 따라야 합니다.
- `semantics`:
  - `after_pattern`: 도체 패턴 형성 후 유입
  - `cnt_open_before_fill_approximation`: CNT 개구 후, 충전 전 유입. 홀 행 뒤에만 둘 수 있습니다.
- `surface_model`은 `flat`, `conformal`, `partial`을 지원합니다. `after_pattern`에는 `conformal`을 기본 권장하며 CNT open 단계는 의도적인 flat-film 근사로 `flat`을 유지합니다. `partial`은 landing 단계까지 모든 비도체 stack 행에 `planarization_factor`가 필요합니다. `flat`과 0 contact margin을 함께 쓰면 short CA가 구조적으로 0이 되며 particle-sim이 `STRUCTURAL_ZERO_SHORT` 경고를 냅니다.
- `fab_distribution_layer`(Fab 이물 밀도를 가져올 layer)는 **착지 layer 바로 위 마스크 layer**입니다(2026-09-30 결정). 도체 행과 접점이 있는 홀 행이 마스크 layer이고, 마스크 없는 절연막과 접점 없는 홀 행은 건너뜁니다. 생략하면 export가 자동으로 채우며, 다른 이름을 적으면 거부합니다. 위에 마스크 layer가 없을 때(예: 최상부 METAL1)만 직접 적습니다.
- 예시 템플릿: `SRC_AFTER_GAT2` → `OACTIVE`, `SRC_CNT1_OPEN` → `CNT2`, `SRC_CNT2_OPEN` → `METAL1`, `SRC_AFTER_METAL1` → 직접 적은 `METAL_PHOTO`.
- 이 이름은 6단계 Fab 이물 표의 같은 열 값과 일치해야 합니다.
- `contact_applicable_stages`에는 접점이 있는 홀 레이어마다 그 홀의 CNT 개구 stage를 정확히 하나 적습니다.

### 4.3 입경 (`particle_sizes_um`)

1–30 µm, 40 µm, 50 µm의 32개 값 중에서 **오름차순 부분집합**을 적습니다. E2
`analyze-central`은 32개 전체를 요구합니다.

### 4.4 회로 net 대응 (`net_map`)

- 추출 manifest의 **모든** 전극 ID를 확정 net ID로 대응시켜야 합니다. 하나라도 빠지면 오류입니다.
- 여러 전극을 같은 net으로 묶을 수 있습니다. 예를 들어 자기 TR에 잘려 나뉜 같은 gate 조각들입니다. 이렇게 묶어도 전극 마스크와 ID는 따로 유지되고, 같은 net끼리는 short 후보에서 빠집니다.
- 뼈대는 아래처럼 만들고, review 결과대로 오른쪽 값을 고칩니다.

```sh
.venv/bin/python - <<'PY'
import json
from pathlib import Path
extraction = json.loads(Path("outputs/my-extraction/manifest.json").read_text())
config_path = Path("my-layout/process-config.json")
config = json.loads(config_path.read_text())
config["net_map"] = {e["id"]: "TODO_" + e["id"] for e in extraction["electrodes"]}
config_path.write_text(json.dumps(config, indent=2) + "\n")
PY
```

`TODO_`가 남아 있으면 확정되지 않은 것입니다. 모두 실제 net 이름으로 바꾼 뒤 export하세요.

### 4.5 제외 쌍, open 경로, CNO/open 관계 (선택)

- **`excluded_pairs`:** 서로 다른 net의 전극 쌍 중 계산에서 뺄 쌍입니다.
  - 전극 이름은 레이어별 export ID로 적습니다. 예: `E00004_GAT1`.
  - 사유(`reason`)는 필수입니다. 같은 net 쌍은 자동으로 제외되므로 적으면 오류입니다.
- **`open_paths`:** open 판정 대상입니다. 완전한 `net_map`이 있어야 쓸 수 있습니다.
  - 두 단자 좌표 `terminal_a_yx_px`, `terminal_b_yx_px`는 **1200×1200 export 좌표**이고 형식이 `[y, x]`입니다. manifest의 `holes`는 `[x, y]`이므로 순서가 반대입니다.
  - 두 단자는 같은 전극 마스크 위에 있고 서로 연결되어 있어야 합니다.
  - ROI 경계를 단자로 자동 추정하지 않습니다.
- **`cno_open_relations`:** 같은 연결의 CNO와 open을 중복 제거할 때 씁니다.
  - `cno_link_id`는 한 번 export한 뒤 `adapter-provenance.json`에 나온 정확한 `cno:<contact_id>:<lower>__<upper>` 값을 복사합니다.
  - 같은 net이라는 이유로 관계가 자동 추정되지 않습니다.

## 5. export와 입력 검증

```sh
.venv/bin/layout-electrode-extractor export-particle-sim \
  outputs/my-extraction outputs/my-export --config my-layout/process-config.json
/Users/jonghyeonlee/git/particle-sim/.venv/bin/particle-sim validate-input \
  --product-config outputs/my-export/product.yaml
```

export는 검증을 모두 통과해야 출력 폴더를 만듭니다. 실패하면 폴더가 생기지 않고 오류 메시지만 나옵니다.

확인할 것:
- `validate-input`이 `status: ok`이고 미해결 쌍이 0개인지
- `adapter-report.json`의 `declared_circuit_nets`가 0이 아닌지. 0이면 `net_map`이 빠진 것입니다.
- `adapter-provenance.json`의 `physical_hole_diagnostics`에서 홀별 enclosure와 교차 기록

자주 나오는 오류:

| 메시지 | 원인 |
| --- | --- |
| `pixels must be exactly 0 or 255` | 래스터화할 때 안티앨리어싱이 들어감 |
| `physical hole touches unit edge` | 홀이 unit 경계에 걸림. unit 원점을 옮겨야 함 |
| `hole_in_tr` | 접점 홀이 TR 영역과 겹침 |
| `hole_through_intermediate_conductor` | 홀이 선언되지 않은 중간 도체를 관통 |
| `process_stack projection must match` | config 층 순서가 manifest의 `physical_stack`, `stack`과 다름 |
| `missing raw hole seed` / seed 관련 오류 | 혼합 CNT 규칙의 `holes` 좌표가 실제 홀과 맞지 않음 |
| `measured CNT open stage/contact physics is unsupported` | 아래 제약 참고 |

## 6. particle-sim 계산과 Fab 이물 분포

이물 분포는 extractor가 아니라 particle-sim `apply-fab`에 넣습니다.
예시: [`fab-mean.csv`](../examples/real-data-template/fab-mean.csv)

- 평균 형식 열: `fab_id, product_family, fab_distribution_layer, size_bin_left_um,
  size_bin_right_um, size_representative_um, mean_particle_count,
  inspection_area_per_sample_mm2, measurement_period, particle_type`
- 선택 열: `sample_count`, `source_id`, `source_hash`
- `fab_distribution_layer` 값은 export된 `product.yaml`의 source step 값(착지 layer 바로 위 마스크 layer)과 같아야 합니다.
- 같은 (`fab_id`, `product_family`, 단계) 안에서 bin 구간이 겹치면 안 됩니다.
- `--bin-method`에는 기본값이 없어서 직접 골라야 합니다: `exact_point`, `piecewise_constant`, `piecewise_linear`, `empirical_samples`.

```sh
PS=/Users/jonghyeonlee/git/particle-sim/.venv/bin/particle-sim
$PS simulate-nominal --product-config outputs/my-export/product.yaml --output outputs/my-run
$PS apply-fab --run outputs/my-run --fab-data my-layout/fab-mean.csv \
  --product-config outputs/my-export/product.yaml --bin-method piecewise_constant \
  --output outputs/my-risk
```

각 명령의 정확한 옵션은 `particle-sim <command> --help`로 확인하세요.

**계산량 주의.** 전극 쌍 수가 수천–수만 개로 늘어날 수 있습니다. 긴 버스에서 open 커널은
메모리를 20 GB 이상 쓴 사례가 있습니다. 처음에는 `particle_sizes_um`을 몇 개로 줄이거나
`excluded_pairs`로 대표 쌍만 남겨 소규모로 돌린 뒤 넓히세요. 이런 소규모 실행 결과는 전체 쌍에 대한 결과가 아닙니다.

## 현재 제약 (실제 데이터에서도 그대로 적용)

1. **`profile: "measured"`는 접점이 있으면 거부됩니다.** particle-sim이 아직 열린 CNT
   표면을 모델링하지 못하기 때문입니다. 실제 두께와 물성을 넣더라도 CNT가 있는 레이아웃은
   `profile: "synthetic"`으로 export해야 합니다. 이 경우 CNT open 단계는 평면 근사입니다.
2. **open 연결성은 인증되지 않습니다.** CNT open stage의 open은 비국소 문제로 표시되며,
   긴 배선에서의 실제 open 커널은 비용 문제가 남아 있습니다.
3. **경계 효과가 있습니다.** particle-sim은 2×2 이미지를 유한 ROI로 계산하고 주기 경계조건을
   쓰지 않습니다. 집계는 중앙 `[300,900)²` 영역을 기준으로 해석하세요.
4. **CNO 판정은 기하 규칙입니다.** 홀 전체 cut 면적의 50% 이상이 가려지면 CNO로 봅니다.
   실제 식각, liner, fill 현상을 검증한 것이 아닙니다.
5. **검토는 사람의 몫입니다.** `net_map`, `excluded_pairs`, `open_paths`는 사람이 확정한
   선언입니다. 도구가 회로를 추론하지 않으므로 잘못 선언하면 결과도 틀립니다.

## 체크리스트

- [ ] 모든 레이어 PNG가 같은 크기, 0/255, 한 주기, 0.1 µm/px(권장 600×600)
- [ ] 접점 홀이 unit 경계와 TR에 닿지 않음
- [ ] `manifest.json`의 `stack`, `physical_stack`, `tr_pairs`, `contacts` 작성 (혼합 CNT는 모든 규칙에 `holes`)
- [ ] `extract` 결과의 `issues`가 0개, 전극·TR 수가 예상과 일치
- [ ] review에서 전극 ↔ 회로 대응 확인
- [ ] `process-config.json`에 실제 두께·물성, source stage, 입경, 완전한 `net_map` 작성
- [ ] `export-particle-sim --config` 성공, `validate-input`이 `ok`에 미해결 0
- [ ] `fab-mean.csv`의 `fab_distribution_layer`가 착지 layer 바로 위 마스크 layer 이름과 일치
- [ ] 소규모 실행 후 전체 계산으로 확대
