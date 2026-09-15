# KEY-154 — OCR 중단 복구 검증

기준: 2026-09-15, develop `61f958b` 반영 후 재검증. Jira: https://leehee.atlassian.net/browse/KEY-154

## 구현 및 정책

- 워커 시작 직후 및 60초 주기로 `PROCESSING` 작업을 확인한다.
- `started_at`, 없으면 `created_at`에서 10분 이상 지난 작업만 `FAILED / PROCESSING_TIMEOUT`으로 전환한다.
- 기본 CLOVA 제한 10초 × 최대 3회 및 재시도 간격보다 충분히 긴 10분을 사용한다. 사용자 지정 CLOVA 제한을 크게 늘릴 때는 이 기준도 함께 검토해야 한다.
- 후보 조회 이후에도 상태와 시각 조건을 다시 적용한다. 다른 워커가 새로 시작하거나 완료한 작업을 덮지 않는다.
- 완료 저장은 작업 행 잠금 안에서 상태를 확인한다. 시간 초과 후 늦은 성공·실패 응답은 종료된 상태를 되살리지 않는다.
- 신규 정리 로그는 작업 ID·코드만 기록한다. 정리 루프 오류 원문은 기록하지 않는다.
- 자동 재큐잉, CLOVA API·필드 추출, 상태 enum 및 DB schema 변경 없음. 재업로드는 사람이 기존 화면에서 수행한다.

### 확정 필드 해석

Jira의 “확정 필드 수정 차단”은 현재 KEY-273과 충돌한다. 2026-09-15 사용자 확인 **“기존 KEY-273 정책 유지”**에 따라 수정 허용 및 수정 시 확정 해제·재확정 흐름을 검증했다. 서버 정책을 변경하지 않았다. 목업에도 같은 확정 해제를 적용했다.

## 인수조건별 근거

| 조건 | 근거 |
|---|---|
| 시작·주기 정리 | `TestRecoveryLoop`: 워커 진입점에서 기존 루프와 함께 실행, 시작 직후 실행, 오류 후 다음 주기 재실행 |
| 오래된 작업만 실패 | `TestProcessingTimeout`: 경계 시각, started_at 누락, 최신 시작/생성, 기존 FAILED·COMPLETED 유지 |
| 정상 완료·시작 경쟁 보호 | 후보 조회 뒤 완료 또는 시작 시각 갱신을 끼워 넣어 조건부 UPDATE 확인 |
| 늦은 성공·오류 보호 | 실제 DB에서 시간 초과 후 성공·실패 응답 도착, 결과 미생성 및 실패 코드·진행률 보존 |
| 재업로드 후 생성 가능 | 합성 재업로드 작업 완료 후 `assert_ocr_jobs_ready` 통과, 이전 실패 작업은 유지 |
| 빠른 환자 전환 | `ocr-review-async.test.js`: 작업 목록·상태·결과·폴링 각각 늦은 성공/오류, A→B→A 재선택 |
| 확정 후 수정 정책 | 실제 DB에서 수정·확정 해제·재확정, 목업 PATCH 회귀 |
| 실패 안내 | `PROCESSING_TIMEOUT` 한국어 문구와 기존 FAILED 재업로드 경로 테스트 |

## 기존 테스트 재사용

- `ocr-review-transitions.test.js`: “환자를 바꾸면 앞 환자의 편집·충돌·저장 표시가 하나도 안 남는다”, “판독 실패는 화면을 막지 않는다 — 재업로드로 되돌아갈 수 있다”, “판독 중이면 기다리는 화면에 머문다”, “판독 완료면 결과 화면으로 넘어간다”.
- `shell-template.test.js`: 공통 shell·필수 DOM.
- `ocr-review-state-weight.test.js`: “warn 이면 반드시 다음 행동이 있다”.

## 실행 결과

- `pytest -q app/tests/ocr app/tests/document_apis --tb=short`: **171 passed**, 기존 422 상수 폐기 예정 경고 1건.
- `node --test frontend/tests/*.test.js`: **1,317 passed**, 실패·skip 없음.
- `ruff check .`: 통과.
- `ruff format . --check`: **472 files already formatted**.
- `mypy app ai_worker`: **459 source files**, 오류 없음.
- `git diff --check`: 통과.

백엔드는 전용 로컬 MySQL 테스트 DB를 사용했다. 외부 CLOVA 응답은 합성 fixture이며 실제 API 호출·SMS 발송·운영 데이터 사용 없음.

## 브라우저 검증 범위

로컬 변경 파일을 제공하는 `127.0.0.1:18384`에서 실제 Chrome으로 실행했다. 저장소의 OCR 화면 및 이벤트·렌더러를 사용하고 API 응답만 합성 데이터로 제어했다. 운영 사이트 QA 또는 실제 CLOVA 호출 E2E로 간주하지 않는다.

- 시간 초과 안내, 기존 작업 영역 유지, 재업로드 버튼 활성 및 업로드 패널 열림 확인.
- 이전 환자 요청을 지연시킨 뒤 마지막 선택 환자의 필드가 덮이지 않음을 확인.
- 확정된 혈색소 필드의 수정 버튼 → 값 입력 → 저장 → 재조회에서 값 변경 및 확정 해제를 확인. 구형 목업의 표시용 필드명은 테스트 데이터에서 실제 API의 `HEMOGLOBIN` 형식으로 맞췄으며, 운영 데이터·화면 코드를 우회하지 않았다.
- 실제 워커 강제 종료/OOM 실험 대신 오래된 PROCESSING DB 상태와 시작·주기 루프 테스트로 복구 조건을 재현했다.

로컬 시각 증거: `/private/tmp/key154-timeout.png`, `/private/tmp/key154-current-patient.png`, `/private/tmp/key154-confirmed-edit.png`. 실행 스크립트는 `/private/tmp/key154-browser-check.cjs`에 있으며 로컬 Playwright/Chrome 설치 경로를 사용한다. 이 임시 경로들은 커밋 산출물이 아니다.

커밋·푸시·PR 및 병합 후 통합 환경 QA는 별도 단계다. `qa-required`와 이희진·한금준 리뷰를 유지한다.

## PR #328 후속 리뷰 반영 — 2026-09-15

- 일반 댓글 3개 및 인라인 댓글 없음 확인. 한금준님의 재시도 개선 의견을 이희진님 요청대로 같은 PR에서 반영했다.
- CLOVA 재시도 backoff 이후, 재호출 직전에 DB의 PROCESSING 여부를 조회한다. 이미 종료됐거나 삭제된 작업이면 기존 ALREADY_PROCESSED 종료 경로를 사용하며 종료 상태·실패 코드를 덮지 않는다.
- HTTP 동안 DB 잠금을 유지하지 않는다. 조회 직후 상태가 바뀌는 짧은 경쟁 구간까지 없앤다고 주장하지 않으며, 늦은 결과 저장의 기존 행 잠금·상태 재확인을 유지한다.
- 세 가지 재시도 가능 오류(timeout/network/server) × 오류 반환 중 정리/대기 중 정리 6개 시나리오를 DB와 합성 CLOVA로 검사한다. CLOVA 호출은 최초 1회뿐이고 PROCESSING_TIMEOUT·완료 시각·진행률이 유지되며 결과가 생기지 않는다. 정상 재시도 성공/소진/재시도 불가 오류의 기존 테스트도 유지한다.
- 최종 helper 코드에서 백엔드 전체 `pytest -n 4 -q app ai_worker` 재실행: 2,823 passed / 기존 xfailed 1 / subtests 14 passed, 168.26초. 기존 HTTP 422 상수 폐기 예정 경고 10건이며 실패 없음.
- 전체 프런트 1,317 passed, Ruff check/format 및 mypy 472개 파일 통과. 테스트 기대값 완화·migration·외부 서비스 호출·화면 변경 없음. 최초 보완의 Ruff 복잡도/루프 변수 경고는 helper 분리와 명시적 변수 바인딩으로 해결했다.
- 실제 CLOVA/운영 DB/배포 및 새 브라우저 시연은 실행하지 않았다. 잘못된 추가 테스트 경로로 1회 수집 없이 종료한 뒤 경로를 바로잡았으며, 최종 검증은 위 전체 백엔드 재실행 결과를 기준으로 한다.
