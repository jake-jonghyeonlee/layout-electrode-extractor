# E-stage 실행계약 보정, 2026-09-24

기준: [구현 계획 v2](IMPLEMENTATION-PLAN-v2-20260924.md), [Opus 5.5 high 읽기 전용 검토](IMPLEMENTATION-E-GATE-REVIEW-20260924.md). 이 문서는 검토의 X1/X2/X3 필수 조건을 채택한다. 제품 코드 리뷰 PASS는 아니다.

## P2와 P3 소유권

- P2는 adapter/config의 net map, 전체 pair 분류, 명시 open path 및 CNO/open 관계 sidecar를 소유한다. 관계 키는 particle-sim의 `cno:{contact_id}:{lower_electrode}__{upper_electrode}` **link unit ID**다. 동일 net만으로 관계를 만들지 않는다. 중복/없는 link 또는 path, 적용 source step이 한 개도 겹치지 않는 관계를 출력 전에 거부한다. 관계가 없는 기본 export는 P0/P1과 동일하다.
- 명시 open path는 실제 점/마스크 단자를 검증하고 `fallback=error`만 허용한다. ROI 외곽을 단자로 대용하지 않는다. `open_applicable_steps_by_layer`는 비워 auto-open을 활성화하지 않는다.
- P3는 extractor 진단만 별도 직렬 Task로 소유한다. 새로운 진단 필드 밖의 fixture raw/cut 마스크, TR 40, contact 100, 각 225px 홀, 주기 instance ID, export 입력은 동일해야 한다. 중간 도체 raw 겹침은 검출 사실로만 기록하고 물리 short로 판정하지 않는다. P2가 sidecar만으로 충족한다면 engine/schema 수정을 강제하지 않는다.

## E1/E2/E3 독립 복사본

- **E1:** 현재 `ContactHole.ys/xs`는 유효 endpoint 겹침 및 auto-open 단자에서 계속 사용한다. 별도의 온전한 TR-cut physical hole 좌표와 raw/cut/effective 픽셀 수를 추가한다. 기본 CNO 입자 disc margin은 0이며 manifest `contact_margin_um`을 가져오지 않는다. 각 홀에 `2*covered >= full_cut_hole_pixels`; link는 홀 CNO의 OR. 기존 full-cover 명칭은 50% 규칙으로 갱신한다. 49/50/51%, 225px의 112/113, margin 0.5와 유효 면적이 작은 반례, auto-open 결과의 기존 버전 대비 동일성 검증이 필요하다. `auto_open.py`는 수정하지 않는다.
- **E2:** 중앙 `[300,900)²` 집계와 32개 확정 지름별 support gate. radius + 명시 margin + 전체 홀 half-span + short reach가 300px 이내임을 조건별 확인한다. 통과해도 회로 open의 비국소 연결성은 증명되지 않았다고 명시한다. CNT open-before-fill은 현재 flat-film 근사이며 물리 공정 재현 검사는 이 Task의 범위 밖이다.
- **E3:** P2 sidecar의 관계표와 E1의 margin-0 link CNO map을 사용해 각 `(source step, diameter, y, x, shape[, sample])`별로 `removed=open_raw & OR(related_link_CNO)`와 `open_final=open_raw & ~OR(...)`를 계산한다. 적용 불가 source step에서는 removed=0이다. 원시 CNO/open/short, `ca.parquet`, `ca_union.parquet`와 기존 raw allocated/unique 열은 그대로 두고 별도 dedup 결과를 낸다. `open_final | removed == open_raw`, dedup 전후 any-union map 픽셀 동일, 관련 없는 open 및 모든 short 원시 map 동일을 검증한다. `auto_open:` unit이 있으면 dedup 통계 보고를 거부한다.

## X3 복사/실행 보호

원본 `/Users/jonghyeonlee/git/particle-sim`의 HEAD, `git --no-optional-locks status --porcelain=v1 -uall`, `.git/index` SHA-256, editable `.pth` 내용의 전후 동일성을 기록한다. 원본 Python import를 피한다. `git archive <recorded SHA>`를 extractor의 ignored `outputs/`에 푼 뒤 **복사본 안에서 `git init` 및 baseline commit**을 만들어 Git 탐색이 extractor로 올라가지 않도록 한다. 복사본 전용 cwd에서 `GIT_OPTIONAL_LOCKS=0`, `PYTHONDONTWRITEBYTECODE=1`, `GIT_CEILING_DIRECTORIES=<copy parent>`, `PYTHONPATH=<copy>/src`로 실행한다. 사용 가능한 원본 venv의 `.pth`는 읽기만 하고, 같은 실행 환경에서 `particle_sim.__file__`이 복사본 아래인지 assert한다. 테스트 cache provider는 비활성화한다. 복사본 patch는 그 복사본 Git으로 만든다. 원본 repo와 venv에는 설치·편집·출력하지 않는다.

한 시점에 편집자는 하나다. E1은 X3 보호를 검증한 뒤 시작하고, E3는 P2 관계표와 E1 판정이 검증된 뒤 시작한다. E단계 결과는 독립 복사본의 적용 가능한 시안이며 원본 적용·물리 시뮬레이션 완료를 뜻하지 않는다.
