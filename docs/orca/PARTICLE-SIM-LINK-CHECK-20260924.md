# Particle-sim 연계 확인 — 2026-09-24

대상은 `f01d0d5` (`79a4d68` 브리지 fixture)이며, Orca Run `run_5463d205f39d`의 직접 수행 Task `task_4add686708cd`에서 확인했다. 생성물은 모두 Git 무시 경로 `outputs/particle-sim-link-check-20260924/`에 있다. `/Users/jonghyeonlee/git/particle-sim`은 읽기 전용으로 조사했고 코드를 변경하지 않았다. 검사 시 그 저장소의 HEAD는 `aae492a`였다.

## 재현 명령과 실제 결과

```sh
.venv/bin/layout-electrode-extractor make-synthetic outputs/particle-sim-link-check-20260924/source
.venv/bin/layout-electrode-extractor extract outputs/particle-sim-link-check-20260924/source/manifest.json outputs/particle-sim-link-check-20260924/extraction
.venv/bin/layout-electrode-extractor export-particle-sim outputs/particle-sim-link-check-20260924/extraction outputs/particle-sim-link-check-20260924/mixed-export
.venv/bin/pytest -q
.venv/bin/ruff check .
```

생성은 600×600 px, 추출은 1200×1200 px·0.1 µm/px였다. 실제 추출 manifest에는 전극 **101개**, TR **40개**(단위당 GAT1/ACTIVE 4, GAT2/OACTIVE 2, GAT3/OACTIVE 4), 추출 issue **0개**가 있다. 접점 원본은 단위당 CNT1 14개(ACTIVE–METAL1 11, GAT2–METAL1 3)와 CNT2 11개(OACTIVE–METAL1 11)이며 2×2에는 유효 홀 인스턴스 100개가 기록됐다. 그래프는 node 75개, edge 150개, component 25개다. 실제 추출 마스크는 이전 검토 후보의 source/raw/cut/TR 마스크와 각각 byte hash가 같고, 모든 층의 `cut = raw − TR` 검증도 통과했다. 두 브리지는 각각 서로 다른 CNT1 두 홀, 네 명시적 그래프 edge, 연속된 cut METAL1을 갖는다. 세부 ID와 원본 경로는 [inventory.json](../../outputs/particle-sim-link-check-20260924/inventory.json), [verification.json](../../outputs/particle-sim-link-check-20260924/verification.json), [추출 manifest](../../outputs/particle-sim-link-check-20260924/extraction/manifest.json)에 있다.

원본 layer 합성만 보여주는 오버레이와 달리 [실제 전극 마스크 sheet](../../outputs/particle-sim-link-check-20260924/images/actual-electrode-mask-sheet.png)는 `extraction/electrodes/E00023/{ACTIVE,CNT1,GAT2,METAL1}.png`를 직접 합성하고 E00056(ACTIVE 직접 패드), E00085(OACTIVE/금속 trunk), E00003(R bus)와 나란히 놓았다. 각 패널은 1200×1200 실제 마스크를 600×600으로 축소한 미리보기다. [접점 안내 이미지](../../outputs/particle-sim-link-check-20260924/images/contact-routing-guide.png)와 [추출 오버레이](../../outputs/particle-sim-link-check-20260924/images/extracted-overlay-1200.png)도 새 추출에서 다시 생성하고 육안 확인했다. RGB 수평 seam과 METAL1 수직 seam의 추출 전극 ID는 `inventory.json`에 있다.

최신 fixture의 `export-particle-sim`은 **exit 2**로 종료했다: `unsupported contact topology: particle-sim export requires one endpoint pair per physical CNT/VIA layer; per-hole rules need separate validated masks`. `mixed-export/`는 생성되지 않았다. 이는 adapter가 같은 CNT1에 대한 두 `contact_rules`를 출력 작성 전에 막기 때문이다([adapter](../../src/layout_electrode_extractor/particle_sim_adapter.py#L145-L158)); [실행 로그](../../outputs/particle-sim-link-check-20260924/logs/mixed-export.log)를 보라. 따라서 최신 fixture로 particle-sim `validate-input`이나 물리 simulation을 통과했다고 주장할 수 없다.

별도 **positive control**로 기존 단일 endpoint-pair/CNT fixture `outputs/task-final-default/input`을 새 경로 `legacy-source/`에 복사해 최신 CLI로 재추출·export했다. 추출은 전극 88개·TR 32개, export는 particle-sim 전극 98개·net 88개·contact row 2개·분류 pair 4,743개였다. 실제 명령은 다음과 같았다.

```sh
.venv/bin/layout-electrode-extractor extract outputs/particle-sim-link-check-20260924/legacy-source/manifest.json outputs/particle-sim-link-check-20260924/legacy-extraction
.venv/bin/layout-electrode-extractor export-particle-sim outputs/particle-sim-link-check-20260924/legacy-extraction outputs/particle-sim-link-check-20260924/legacy-export
/Users/jonghyeonlee/git/particle-sim/.venv/bin/particle-sim validate-input --product-config outputs/particle-sim-link-check-20260924/legacy-export/product.yaml
```

`validate-input`은 exit 0, `status: ok`, 1200×1200·0.1 µm/px, 98 전극, 4,743 pair, 16 contact hole, 미해결 pair 0이었다([전체 검증 출력](../../outputs/particle-sim-link-check-20260924/logs/legacy-validate-input.log), [export manifest](../../outputs/particle-sim-link-check-20260924/legacy-export/product.yaml)). 이는 **옛 fixture에 대한 양성 대조군**이며 현재 브리지 fixture의 particle-sim 지원 증거가 아니다. pytest 53개와 Ruff도 통과했다([pytest 로그](../../outputs/particle-sim-link-check-20260924/logs/pytest.log), [Ruff 로그](../../outputs/particle-sim-link-check-20260924/logs/ruff.log)).

## 실제 연계에 필요한 변경

1. **Adapter에서 CNT1을 hole endpoint별로 분리해 export해야 한다.** 현재 adapter는 `contact_rules`의 물리 layer 중복을 거부하고, 허용 경로에서도 접점 row 하나에 CNT 전체 cut mask 하나를 사용한다([adapter](../../src/layout_electrode_extractor/particle_sim_adapter.py#L150-L157), [mask 작성](../../src/layout_electrode_extractor/particle_sim_adapter.py#L193-L210)). 추출의 `contact_holes` provenance를 사용해 CNT1 ACTIVE–METAL1 홀과 GAT2–METAL1 홀을 서로 겹치지 않는 별도 이진 마스크로 만들고, CNT2 OACTIVE–METAL1은 그대로 둬야 한다. 각 분할 마스크의 union이 원래 cut CNT1과 정확히 같고 누락·중복 홀 또는 TR 픽셀이 없음을 검사해야 한다. 출력 contact ID는 고유해야 하지만 `hole_layer`는 물리 CNT1을 유지해야 한다.
2. **particle-sim 입력 계약에 맞게 명시적 endpoint·net을 검증해야 한다.** 현재 particle-sim `Contact`는 각 row에 고유 `contact_id`, 경로, `hole_layer`, 명시적 `lower_layer`/`upper_layer`를 받는다([schema](../../../particle-sim/src/particle_sim/schema.py#L120-L155), [고유 ID·층 위치 검사](../../../particle-sim/src/particle_sim/schema.py#L422-L450)). 동일 `hole_layer`를 여러 contact row에서 쓰는 것을 금지하는 검사는 이 코드에서 찾지 못했으므로 schema 변경 필요성은 아직 입증되지 않았다. 그러나 실제 분할 export를 만든 뒤 반드시 `validate-input`으로 확인해야 한다. loader는 각 분할 mask의 connected component마다 **정확히 하나의 lower 및 upper 전극**, 양쪽 **동일 net**, 공통 유효 픽셀을 요구한다([contacts](../../../particle-sim/src/particle_sim/geometry/contacts.py#L75-L135)). 기존 adapter처럼 추출 전극 ID를 층별 mask의 공통 `net_id`로 전달하고([adapter](../../src/layout_electrode_extractor/particle_sim_adapter.py#L163-L178)), 특히 브리지 두 홀의 endpoint와 E00023 전극 provenance를 보존해야 한다. contact ID가 바뀌면 CNO failure-unit 그룹도 바뀌므로 그 의미를 검토해야 한다.
3. **공정 순서와 물리 가정을 별도로 검토해야 한다.** 현재 source의 `physical_stack`은 `ACTIVE,GAT1,GAT2,OACTIVE,GAT3,CNT1,CNT2,METAL1`이고 추출에 보존된다. 하지만 adapter는 conductor-only `stack`과 역할 기반 가정 ILD·접점 위치로 particle-sim `process_order`를 새로 만든다([adapter](../../src/layout_electrode_extractor/particle_sim_adapter.py#L17-L133)); `physical_stack`을 직접 읽지 않는다. 분할 contact row가 동일 CNT1 `hole_layer`를 참조하면서 ACTIVE 또는 GAT2보다 위, METAL1보다 아래에 놓이는지 확인해야 한다. particle-sim은 홀 층이 명시 endpoint 사이에 있는지만 검사한다([schema](../../../particle-sim/src/particle_sim/schema.py#L430-L449)). 이 순서와 2-D 마스크 겹침은 깊은 홀 식각, liner/fill, 중간층 통과 가능성을 검증하지 않는다. 가정 ILD 두께·source step·CNO 기준은 실제 공정 자료 없이는 확정할 수 없다.
4. **검증 범위를 구분해야 한다.** particle-sim mask loader는 단일 채널 이진 PNG/TIFF를 그대로 읽고 resize·threshold를 허용하지 않는다([loader](../../../particle-sim/src/particle_sim/io/masks.py#L57-L100)); 모든 마스크 shape와 ROI 크기도 검사한다. 현재 adapter의 raw layer mask(지형용), cut 전극 mask, cut 접점 mask 사용 의도를 유지하고, 분할 export에 대해 mask union·endpoint·stack·pair inventory와 실제 `validate-input`을 별도 회귀 테스트로 확인해야 한다. particle-sim 입력은 유한 2×2 ROI이며 추출의 주기적 연결성 자체를 simulation 경계조건으로 전달하지 않는다. 물리 simulation은 별도 요청과 물성 확인 후 수행해야 한다.

이번 Task는 필요한 변경 사항 정리와 실제 현행 상태 시험에 한정했다. Adapter·schema 구현은 변경하지 않았다.
