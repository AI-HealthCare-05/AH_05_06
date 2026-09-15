# KEY-230 clean clone·bootstrap 검증 — 2026-09-15

상태: **MySQL 1419 보완 커밋 `c6871a2`의 원격 CI bootstrap·lint·test 모두 통과. 후속 리뷰의 조회 실패 시 연결 정리 테스트를 로컬에서 보완했으며 이 추가 변경은 아직 푸시 전이다. 최종 인수는 대기한다.**

## 조회 실패 연결 정리 리뷰 보완 — 2026-09-16

- 기존 테스트는 초기화 예외를 주입하므로 이름을 `test_connection_closed_on_init_failure`로 바로잡았다.
- 초기화 성공 후 첫 DB 이름 조회 실패와 두 번째 스키마 조회 실패를 각각 추가했다. 두 경우 모두 원래 예외를 그대로 전파하고 `close_connections()`를 정확히 한 번 await하는지 검증한다. 실제 제품 코드·DB 구조는 변경하지 않았다.
- 관련 회귀 15개, 전체 배포 회귀 **353 passed (36.92초)**, 전체 Ruff check/format 및 mypy 476개 파일 통과. 테스트 대역으로 실패를 주입했으며 운영 DB나 외부 서비스 호출은 없다.
- [수정 후 CI 34983276935](https://github.com/AI-HealthCare-05/AH_05_06/actions/runs/34983276935): `c6871a2` 기준 bootstrap 1분20초, lint 35초, test 4분47초 모두 PASS. 이번 추가 테스트의 원격 CI 결과와는 구분한다.

## 후속 MySQL 1419 보완

- [후속 CI 34954192543](https://github.com/AI-HealthCare-05/AH_05_06/actions/runs/34954192543): lint/test는 통과했지만 첫 migration이 1419(SUPER privilege / binary logging)로 종료해 반복 실행에 도달하지 못했다. 아래 기존 CI 성공 기록과 구분한다.
- 로컬 `docker-compose.yml`의 MySQL 시작 옵션에 `--log-bin-trust-function-creators=1`을 추가했다. CI bootstrap도 이 Compose를 사용하므로 동일하게 적용된다. 앱 계정 SUPER 권한 부여, migration 우회, 운영 Compose/RDS 설정 변경은 하지 않았다.
- 바이너리 로그가 켜진 서버에서 함수·트리거 작성자에 대한 추가 신뢰 설정이므로 로컬/CI에 한정한다. 일반 생성 권한은 여전히 필요하다.
- 새 격리 Compose 프로젝트에서 기존 검증 이미지(제품 기준 `06807b9`)와 수정된 MySQL 시작 설정으로 실제 실행했다. 일반 앱 계정 조회에서 `@@log_bin=1`, `@@log_bin_trust_function_creators=1` 확인. 정식 migration 0~63, seed, drift, health/auth/core 모두 통과했다.
- 두 번째 bootstrap은 upgrade 없음, seed 신규 생성 0, smoke 통과, 환경파일 체크섬 동일. 기존 볼륨은 삭제하지 않았고 격리 QA 볼륨은 보존했다. 종료 코드 0과 기존 실행 서비스 복구를 확인했다.
- 당시 시작 옵션 회귀 및 관련 실패 전파 테스트 13개, 전체 배포 회귀 **351 passed (37.17초)**, 전체 Ruff check/format 476개 파일 통과. 이후 원격 CI 성공은 위 `c6871a2` 실행에서 확인했다.

## 기존 검증 기준 및 기록

- 계약: [KEY-230](https://leehee.atlassian.net/browse/KEY-230)의 AC1~7 및 2026-09-15 16:58 댓글.
- 실행·QA 및 요청된 결함 보완: 유가은. 최종 인수: 이희진.
- 최초 clean clone 기준 `61f958b`, 최종 제품 기준 develop `06807b9`, 보완 검증 커밋 `1b68860`.
- 수정 범위: `scripts/check_schema_drift.py` 양방향 비교, `.github/workflows/checks.yml` 실제 bootstrap job, 관련 회귀 테스트·README·QA 기록. migration 파일은 변경하지 않았다.
- 공유 증적: [GitHub Actions 실행 34949707907](https://github.com/AI-HealthCare-05/AH_05_06/actions/runs/34949707907). 원본 로컬 로그·스크린샷·보조 스크립트는 **작성자 로컬 보관**이며 다른 사람이 접근 가능한 공유 산출물로 간주하지 않는다.

## 인수조건별 결과

아래 표는 기존 `1b68860` 검증 기록이다. 후속 MySQL 실패를 보완한 **AC6 원격 CI도 `c6871a2`에서 통과**했으며, 추가 테스트 보완은 위 후속 리뷰 절을 따른다.

| 조건 | 현재 결과 | 검증 근거와 범위 |
|---|---|---|
| AC1 단일 절차로 새 환경에서 로그인 도달 | 로컬 통과 | README의 `./dev.sh start` 경로로 실제 Docker bootstrap·health/auth/core smoke 성공. 실제 Chrome에서 합성 직원 로그인 API 200 → `patients.html` 도달. 최초 clean 실행 108초, 보완 후 새 DB 실행 27초. |
| AC2 clean/기존 DB migration 및 구조 확인 | 검증한 경로 통과 | clean DB 정식 migration 0~63, 기존 합성 seed DB 62→63 성공 및 직원 건수 보존. 새 독립 연결에서 컬럼 483개·인덱스 구성 행 200개 일치. 과거 61→62 경로도 독립 연결 대조 성공. 모든 과거 버전·임의 데이터에 대한 보장은 아니다. |
| AC3 두 번째 실행의 멱등성 | 로컬 및 CI 로그 확인 | 반복 upgrade `No upgrade items found`, seed `created=0`, 환경파일 체크섬 동일. 직원 seed의 `updated=15`는 정상 갱신이므로 모든 DB 값이 불변이라는 뜻은 아니다. 파괴적 스키마 변경 없이 반복 bootstrap 성공. |
| AC4 DB↔모델 양방향 drift 탐지 | 수정 후 통과 | 모델에만 있는 표·컬럼과 DB에만 있는 표·컬럼을 비교하고 차이가 있으면 종료 1. 실제 DB 조회와 프로세스 내 모델 메타데이터 probe로 model-only 컬럼 / DB-only 컬럼 / DB-only 표를 각각 탐지. 정상 bootstrap은 종료 0. Aerich 모델도 비교 대상이며 DB 구조를 수정하지 않는다. |
| AC5 단계 실패를 전체 실패로 전파 | 통과 | Docker up·migration·seed·drift·smoke 각 단계에 종료 43을 주입하면 bootstrap도 43으로 종료하고 후속 단계·완료 메시지를 실행하지 않음. Docker 대역 기반 실패 전파 회귀이며 실제 서비스 장애 실험과 구분한다. |
| AC6 실제 bootstrap CI | 원격 CI 통과 | PR 코드로 `key230/bootstrap:app-ci` 이미지 빌드 → 실제 Compose bootstrap → 반복 실행. migration 0~63·seed·drift·smoke 성공, 반복 환경파일 체크섬 확인. 단계 실패를 job 실패로 전파하고 종료 시 해당 일회용 CI 프로젝트 볼륨만 정리. |
| AC7 안전한 증적 기록 | 문서 보완 완료 | 위 커밋·환경·소요시간·결과와 아래 실패 이력·제한사항 기록. 합성 데이터·로컬 임의 자격증명만 사용하고 실제 환자정보·운영 자격증명·비밀값은 문서/커밋/로그에 남기지 않음. 공유 증적은 위 CI 링크, 원본 로컬 증적은 작성자 보관. |

## 환경과 최종 검증 결과

- 새 clone 및 격리 Compose 프로젝트의 MySQL·Redis·FastAPI·Nginx 사용. 기존 컨테이너를 승인하에 일시 중지하고 종료 trap으로 복구했으며 기존 데이터·볼륨은 삭제하지 않았다. 로컬 QA DB/볼륨도 진단용으로 보존했다.
- Compose는 고정 컨테이너 이름·포트를 사용하므로 프로젝트 이름만 바꿔서는 격리되지 않는다. 검수 override로 자원 이름·볼륨을 분리하되 원본 bootstrap/migration 경로를 유지했다. override 없는 실행과 완전히 동일하다고 주장하지 않는다.
- 최초 실행은 운영 환경파일 복사 없이 bootstrap이 로컬 임의 자격증명을 생성했다. 보완 후 27초 실행은 이 합성 로컬 환경파일을 재사용했으므로 최초 파일 생성 검증과 구분한다. 실제 SMS 발송 없음.
- migration은 정식 Aerich upgrade만 사용했다. 수동 SQL 스키마 보정이나 앱의 임시 스키마 생성으로 우회하지 않았다. 검사용 DB는 별도 이름이며 이미 존재하면 덮어쓰기 대신 중단했다.
- 최종 배포 회귀: **350 passed (40.59초)**. 같은 350개를 실행한 이전 중간 측정값은 최종 결과로 중복 기재하지 않는다.
- CI 이벤트 루프 보완 후 배포·timeline 병렬 회귀: **401 passed (22.10초)**. 전체 Ruff check/format 및 `mypy . --explicit-package-bases` **476개 파일 통과**.
- 커밋 `1b68860`의 실제 원격 CI: **bootstrap 1분20초 / lint 41초 / test 4분58초 모두 PASS**. 이 결과는 해당 커밋의 실행 증거이며 이후 변경이나 다른 배포 환경까지 보장하지 않는다.

## 실패 이력과 해결

1. 최초 포트 3306 점유로 bootstrap이 migration 전 종료 1. 기존 서비스를 보호한 채 중단했고, 승인된 일시 중지·격리 실행 후 통과했다. 최초 Nginx 기동 직후 HTTP 실패는 준비 대기 후 재실행해 해소했다.
2. 초기 checker의 DB-only drift 미탐지와 실제 bootstrap CI job 부재를 발견했다. Jira 16:58 요청에 따라 이번 PR에서 양방향 비교와 실제 job을 추가했고 로컬·원격 CI로 검증했다. 현재 미해결 결함이 아니다.
3. 62→63 직후 대조 불일치는 오래 유지한 asyncmy 읽기 트랜잭션에서 `hold_reason`이 이전 `varchar(19)`로 조회되는 현상으로 재현했다. 같은 연결의 `rollback()` 후 `varchar(22)`로 일치했고 새 독립 연결도 컬럼·인덱스 구성 일치. migration/스키마 보정은 하지 않았다. 더 이전 61→62 첫 불일치는 세부 행을 확보하지 못했으므로 동일 원인으로 단정하지 않는다.
4. 최초 전체 CI는 새 테스트의 `asyncio.run()`이 후속 Tortoise 테스트의 이벤트 루프를 제거해 704 failed였다. pytest-asyncio의 `async def`/`await`로 수정했고 위 최종 전체 CI가 통과했다. 테스트 제외·기대값 완화 없음.
5. 초기 검수 스크립트의 seed 비밀번호 누락, DB fixture 제외, `NO_COLOR` 및 mypy 호출 방식 오류는 검수 환경/호출을 바로잡아 재검증했다. 제품 결함과 구분하며 위 최종 결과로 정리한다.

## 제한사항과 인수 경계

- **drift checker는 표·컬럼 이름만 비교한다. 타입·인덱스 비교는 제외한다.** AC2의 별도 DB 메타데이터 대조는 컬럼 타입/null/default/extra와 인덱스 이름/유일성/컬럼 순서/부분 길이를 포함했지만 checker 기능은 아니다. 인덱스 200은 고유 인덱스 수가 아닌 `information_schema.STATISTICS` 행 수다.
- 반복 upgrade no-op 및 seed `created=0`은 현재 CI 로그에서 확인한 결과이며 별도 assertion으로 고정하지 않았다. 환경파일 체크섬은 CI에서 검사한다.
- PR 빌드 이미지는 job의 `DOCKER_USER`/`DOCKER_REPOSITORY`/`APP_VERSION` 설정으로 선택한다. 빌드 태그와 이 조합의 일치를 고정하는 추가 회귀는 이번 필수 문서 정리 범위에서 추가하지 않았다.
- 현재 M2M 모델은 없으며, 향후 자동 연결 표가 생기면 DB-only 탐지 범위 보완이 필요할 수 있다.
- 커밋 작성자 GitHub 연결 설정은 별도 관리 항목이다. 이 문서 수정은 기존 커밋의 작성자나 전역 Git 설정을 변경하지 않는다.
- QA 실행·결함 수정·CI 통과와 최종 인수는 구분한다. 이 기록만으로 Jira 완료나 PR 병합을 승인하지 않는다. 최종 인수자는 이희진이다.
