# KEY-230 clean clone 검증 — 2026-09-15

상태: **16:58 Jira 댓글의 두 결함 수정 및 로컬 재검증 완료. GitHub CI 실제 실행·최종 인수는 미완료.** 아래 최초 QA의 실패 기록은 당시 결과로 보존한다.

## 16:58 댓글 반영 후 보완

### 대조 실패 원인 재현 및 해소

새 QA DB `key230_upgrade_0915d`로 62→63을 재현했다. migration 전부터 유지한 asyncmy 연결은 기본 autocommit=False 상태였다. 이 연결에서 `guide_message.hold_reason`을 조회하면 clean DB는 `varchar(22)`, upgrade DB는 이전 `varchar(19)`로 반환됐다. 같은 연결에서 `rollback()`으로 읽기 트랜잭션을 끝낸 뒤 재조회하자 `varchar(22)`로 일치했다. 이어 새 독립 연결에서도 컬럼 483개·인덱스 구성 행 200개가 완전히 일치했다. 이번 실패 원인은 검증 연결의 오래된 트랜잭션 조회였다. migration을 추가하거나 DB 구조를 수동 보정하지 않았다. 이전 61→62 실패의 행은 확보하지 못했으므로 그것까지 동일 원인으로 단정하지 않는다.

실행 종료 0, 실제 DB 양방향 drift 종료 1 세 경우 통과, 기존 서비스 복구 확인. 최종 배포 회귀 **350 passed (40.59초)**, 전체 Ruff/format 및 mypy 476개 파일 통과.

- 이희진님이 KEY-230 안에서 유가은에게 최종 수정을 요청했다. 아래 과거 기록의 ‘영역 오너에게 이관’은 현재 작업 방침이 아니다.
- 최신 develop `06807b9`로 fast-forward한 후 `check_schema_drift.py`에 DB-only 표·컬럼 역방향 비교와 종료 1을 추가했다. DB는 변경하지 않으며 Aerich 모델도 정상 비교한다. 타입·인덱스 비교는 명시적 제한사항이다.
- `checks.yml`에 실제 이미지 빌드 → Compose bootstrap → 반복 bootstrap/환경파일 체크섬 확인 job을 추가했다. 각 단계 오류는 job 실패로 전파하며 종료 시 일회용 CI 프로젝트만 정리한다. 대역 테스트로 실제 job 실행을 대신하지 않는다.
- 배포 회귀 전체 **350 passed (39.81초)**, 저장소 전체 Ruff check/format **476개 파일 통과**. mypy 초기 잘못된 호출의 모듈 중복 오류 후 CI 동일 명령으로 재검사했으며, 새 테스트의 YAML import는 기존 공통 읽기 도구를 재사용하도록 수정했다.
- 새 격리 프로젝트 `key230fixed0915`에서 실제 이미지 빌드, 새 DB에 migration 0~63 적용, seed 및 양방향 drift 검사, health/auth/core smoke **통과(27초)**. 반복 실행에서 upgrade 없음·seed 생성 0·환경파일 내용 동일 확인. 실제 Chrome 로그인 → `/patients.html` 성공. 종료 0으로 기존 서비스 복구.
- 이번 새 DB 실행은 이전에 bootstrap이 생성한 합성 로컬 환경파일을 재사용했다. 환경파일 없는 최초 생성/보존 검증은 아래 최초 QA 기록과 구분한다. 운영 비밀값 복사·실제 SMS 발송은 하지 않았다.
- CI와 같은 `mypy . --explicit-package-bases`: **476개 파일 통과**. YAML stub 추가 없이 기존 테스트 공통 도구 재사용으로 해결했다.
- 별도 `key230_upgrade_0915c` DB에 정식 migration 0~62 및 합성 seed를 적용한 뒤 migration 63 하나를 적용했다. 직원 건수 보존 통과. 직후 동일 연결 대조는 컬럼 불일치 assertion으로 종료했으나 새 독립 연결 조회에서는 컬럼 483개·인덱스 구성 행 200개가 모두 일치하고 양쪽 차집합이 비었다. 최초 assertion 세부 행을 확보하지 못해 원인은 확정하지 않는다. 실패와 후속 성공을 모두 남긴다.
- 실제 DB를 변경하지 않는 모델 메타데이터 probe: model-only 컬럼 / DB-only 컬럼 / DB-only 표를 각각 주입하여 실제 checker `main()` **모두 종료 1** 확인. 정상 스키마는 실제 bootstrap에서 종료 0. 표·컬럼 자동 삭제는 하지 않는다.
- 재검증 보조 파일: `/private/tmp/key230-fixed-verify.sh`, `/private/tmp/key230-fixed-isolation.yml`, `/private/tmp/key230-db-qa.py`. 검사 컨테이너는 중지하고 기존 서비스를 복구했으며 모든 기존 볼륨과 QA 볼륨을 보존했다.
- **미실행:** GitHub Actions의 새 bootstrap job 실제 실행. 로컬 성공을 CI green으로 표시하지 않는다. 최종 인수자는 이희진이다.

## 최초 QA 기록 (보완 전)

- 기준: 최신 develop `61f958be8b3ba9feab8c7aac6864f0d4970d1dba`를 원격에서 새 clone.
- 경로: `/private/tmp/AH-key230-verification`, 브랜치 `codex/KEY-230-bootstrap-verification`.
- Jira 최신 계약: https://leehee.atlassian.net/browse/KEY-230 (2026-09-15 16:00 수정).
- 운영/기존 환경파일 복사 없이 bootstrap이 로컬 임의 자격증명을 생성했다. 값은 출력하거나 커밋하지 않았다.

## 실행 및 관찰

1. README 기본 명령 `./dev.sh start` 실행.
2. `.env`, `.bootstrap.local.env` 생성 후 `포트 검사`에서 3306 사용 중으로 **종료 1**. 컨테이너 기동·migration 전에 중단됨.
3. 같은 명령 재실행도 같은 포트 검사에서 실패. 재실행 실측 1.05초. 두 로컬 파일의 mtime·크기 변화 없음(내용 동일성/전체 bootstrap 멱등성 검증과는 구분).
4. 기존 mysql/redis/fastapi/nginx가 3306/6379/8000/80을 사용 중이었다. 최초 검사는 서비스 변경 없이 중단했다.
5. 사용자 승인 후 기존 mysql/redis/fastapi/nginx/ai-worker를 일시 중지했다. 별도 Compose 프로젝트 `key230verification0915`, 컨테이너 이름, 이미지 태그, DB/static/upload 볼륨을 사용했다. 기존 볼륨은 삭제하지 않았다.
6. 실제 clean DB 전체 Aerich upgrade(최종 migration 62), seed, 현재 drift checker, health/auth/core smoke: **통과, 108초**. 별도 `./dev.sh check`도 통과했다.
7. 첫 nginx 기동 직후 curl은 종료 56이었다. 검증 스크립트의 종료 처리로 기존 컨테이너를 복구했고, Docker 조회에서 기존 서비스 실행 및 MySQL/Redis healthy를 확인했다.
8. 같은 검증 DB로 재실행: **18초**, `No upgrade items found`, smoke 통과. 이어서 전체 bootstrap을 한 번 더 실행해 통과했다. seed 로그: 병원 total=2/created=0, 직원 total=15/created=0/updated=15, 처방 세트 created=0/skipped=4, 주의사항 created=0/skipped=16. 직원 갱신은 있으므로 모든 DB 값이 불변이라는 의미는 아니다.
9. 반복 실행 전후 `.env`와 `.bootstrap.local.env`의 파일 체크섬 일치를 검사했다. 비밀값 및 체크섬은 로그에 출력하지 않았다.
10. nginx 기동 후 재시도를 허용한 `/login.html` HTTP 검사가 통과했다. 이는 브라우저에서 실제 로그인 조작을 수행한 증거와는 구분한다. 두 번째 검증 스크립트 종료 0, 기존 서비스 복구 명령 성공. 검증 컨테이너는 중지하고 검증 볼륨은 보존했다.

로컬 원본 로그: `/private/tmp/key230-real-bootstrap.log`, `/private/tmp/key230-repeat-bootstrap.log`. 격리 override는 원본 Compose의 기본 명령/마이그레이션 경로를 유지하되 자원 이름과 업로드 볼륨만 분리했다. 따라서 override 없는 기본 Compose와 완전히 동일한 실행으로 주장하지 않는다.

`docker-compose.yml`은 컨테이너 이름과 Redis/API/웹 포트를 고정한다. 프로젝트 이름만 변경해도 격리되지 않는다. bootstrap의 HTTP 검사 주소도 localhost:8000으로 고정되어 있어서 임의 포트 override만으로 기존 서비스와 안전하게 분리했다고 볼 수 없다.

## 추가 확인

- 기존 `app/tests/deploy/test_key228_bootstrap_local.py`: **12 passed**, 13.46초. 가짜 Docker 경계의 셸 계약 검증이며 실제 Docker 부트스트랩 성공 증거가 아니다.
- 현행 `check_schema_drift.py`에 합성 메타데이터를 주입한 읽기 전용 probe:
  - 모델에만 있는 컬럼: DETECTED.
  - DB에만 있는 컬럼·테이블: NOT_DETECTED.
- `.github/workflows/checks.yml`은 MySQL/Redis 테스트 서비스를 사용하지만 실제 `dev.sh start` / bootstrap 명령을 실행하는 job은 없다.

## 추가 QA 실행 결과

- 실제 Chrome(headless, 설치된 Chrome 채널)에서 `/login.html`의 ID/비밀번호 입력 및 로그인 버튼 클릭 → 로그인 API 200 → `/patients.html` 전환 성공. 합성 직원 표시 및 빈 환자 목록 화면을 스크린샷으로 직접 확인했다. 비밀번호/JWT/환자 링크는 출력하지 않았다.
- 기존 DB 경로: 기존 설정 DB와 이름이 다른 `key230_upgrade_0915b`를 격리 MySQL에 새로 만들고, 저장소의 정식 migration 0~61만 별도 폴더로 복사하여 적용했다(실제 파일 60개). 합성 seed 후 나머지 migration 62 하나를 적용했다. 직원 15명 건수 유지 확인. 앱 스키마 생성이나 수동 테이블 SQL로 migration을 우회하지 않았다. 기존 DB가 있으면 덮어쓰지 않고 중단하도록 했다.
- 깨끗한 DB와 61→62 업그레이드 DB를 독립 연결로 두 차례 비교: 컬럼 483개 및 인덱스 구성 행 200개 모두 일치. 컬럼은 타입/null/default/extra, 인덱스는 이름/유일성/컬럼 순서/부분 길이를 포함한다. 재차 bootstrap을 실행한 후에도 같은 결과였다. 인덱스 200은 고유 인덱스 개수가 아니라 `information_schema.STATISTICS` 행 수다.
- 실제 DB drift probe: DB를 변형하지 않고 프로세스 내 `staff` 모델 필드 집합만 변경하여 현행 `_gaps()`와 실제 DB를 비교했다. 가상 필드 추가(model-only)는 탐지, `login_id`를 모델 필드 집합에서 제외(DB-only)하면 미탐지. 종료 시 모델 메타데이터 복구. 이는 실제 DB 구조를 ALTER한 실험과는 구분한다.
- 추가 QA 회귀 `test_key230_failure_propagation.py`: Docker up/migration/seed/drift/smoke 각각 종료 43을 주입했을 때 실제 bootstrap 셸도 종료 43, 이후 단계 및 완료 메시지 없음. Docker 경계는 대역이며 실제 서비스 장애 실험이나 실제 CI 실행 증거로 주장하지 않는다.
- 기존 bootstrap 12개 + 새 실패 전파 5개: **17 passed (19.40초)**.
- 배포 회귀 전체: **342 passed (39.68초), skip 없음**. 프로젝트 DB 초기화 fixture, 별도 테스트 MySQL 포트 18377, Redis 포트 16379, `TEST_SLOT=3`, `NO_COLOR=`로 실행. 테스트 framework의 격리 DB 초기화는 별도 단위/회귀 검사이며 migration 검증을 대체하지 않는다.
- 새 QA 테스트 Ruff check/format 통과. 제품 코드·CI·migration은 수정하지 않았다. 커밋/푸시/PR 및 Jira 완료 전환은 하지 않았다.

### 실패 시도도 함께 보존

- 기존 DB QA 첫 시도는 검사 스크립트의 `SEED_STAFF_PASSWORD` 누락으로 종료했다. 새 합성 비밀번호를 메모리에서 생성하고 새 검사 DB에서 재실행했다. 제품 bootstrap 결함으로 분류하지 않는다.
- 업그레이드 직후 첫 컬럼 대조는 불일치 assertion으로 종료했다. 이후 독립 연결 조회 두 차례는 컬럼/인덱스 모두 일치했다. 최초 불일치의 세부 행과 원인은 확보하지 못했으므로 원인을 확정하거나 최초 실패를 삭제하지 않는다.
- 배포 전체 첫 실행은 `--confcutdir`로 프로젝트 DB fixture를 제외하고 sandbox 내 실행해 331 passed/10 failed/1 skipped였다. 정상 DB fixture와 로컬 실행 권한으로 재실행 후 341 passed/1 failed, 남은 실패는 실행 환경 `NO_COLOR=1`과 색상 기대값 충돌이었다. 이를 해제한 최종 전체 실행은 342 passed이며 테스트 코드를 완화하지 않았다.
- 모든 서비스 일시 중단 실행은 종료 trap으로 기존 mysql/redis/fastapi/nginx/ai-worker를 다시 시작했다. 마지막 검사 종료 0 및 복구 명령 성공. 기존 데이터/볼륨은 삭제하지 않았고, 검사 DB/볼륨도 진단을 위해 남겨뒀다.

추가 로컬 증적: `/private/tmp/key230-browser-login.png`, `/private/tmp/key230-upgrade-retry.log`, `/private/tmp/key230-schema-diagnostic.log`, `/private/tmp/key230-final-db-evidence.log`, `/private/tmp/key230-deploy-final.log`. 실행 보조 파일은 `/private/tmp/key230-run-bootstrap.sh`, `/private/tmp/key230-db-qa.py`, `/private/tmp/key230-browser.cjs`에 보존했다.

## 인수조건별 결과와 이관

- [x] 승인된 기존 서비스 임시 중단과 격리 Docker 환경에서 실제 clean bootstrap 및 API 로그인 smoke, 시간 기록.
- [x] 기존 검증 DB 반복 upgrade(no-op)·seed 중복 없음·환경파일 내용 보존 확인.
- [x] 로그인 페이지 HTTP 응답 확인.
- [x] 실제 브라우저 로그인 조작 및 화면 검증.
- [x] migration 61 기반 합성 seed DB → 62 upgrade, 직원 건수 보존 확인. 모든 과거 버전·임의 데이터에 대한 보장을 뜻하지 않는다.
- [x] clean/upgrade DB의 컬럼·인덱스 전체 메타데이터 독립 대조, 반복 bootstrap 후 재대조.
- [x] Docker/migration/seed/drift/smoke 실패 전파 셸 계약 검증.
- [ ] **불합격:** DB-only drift 미탐지. 수정 대상 `scripts/check_schema_drift.py`, 영역 오너 확인/수정 필요. 모델의 필드 집합에서 실제 DB의 `staff.login_id`만 제외해도 빈 gaps가 반환된다. 보완 후 양방향 재검증이 필요하다.
- [ ] **불합격:** `.github/workflows/checks.yml`에 실제 bootstrap 핵심 계약 실행 job 부재. CI 영역 오너가 편입한 후 실제 CI 실행 결과를 확인해야 한다. 로컬 Docker 성공이나 대역 테스트 통과로 대체하지 않는다.

실행·QA 담당은 유가은, 발견 파일 수정은 영역 오너, 최종 인수는 이희진이다. 위 두 결함의 영역 담당자를 임의로 지정하거나 코드 변경/완료 승인하지 않았다. 담당자 전달용 결과이며 아직 Jira에 게시하지 않았다.

Jira 계약에 따라 결함 수정은 발견 파일의 영역 오너, 최종 인수는 이희진이다. 임시 SQL/앱 스키마 생성으로 migration을 우회하지 않았으며, 이 기록은 KEY-230 완료·CI 통과를 의미하지 않는다.
