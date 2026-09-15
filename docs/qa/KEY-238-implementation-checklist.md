# KEY-238 구현·검증 체크리스트

기준: 2026-09-15 10:24 수정 Jira KEY-238. 이전 MVP 제외 설명은 적용하지 않는다.
선행 PR #310(KEY-335): 2026-09-15 01:19:02 UTC 병합 확인.
최종 통합 기준 develop: 7654419 (2026-09-15 재조회). 실제 SMS, D+15/D+30, 챗봇 변경은 범위 밖이다.

## 구현 및 검증 (체크되지 않은 항목은 미완료)

- [x] append-only 선택 신호 모델·DTO·POST /checkins/{token}/signals
- [x] 같은 client_id의 sequence 비교, 다른 client_id의 수신 순서, 동일 요청 재시도
- [x] 최종 저장의 현재 신호 보정 및 KEY-335 멱등성 유지 (실제 독립 DB connection 경쟁 검사 포함)
- [x] stopped_side_effect/stopped_improved만 서버가 확인 대상으로 판정
- [x] staff/doctor 병원 범위 조회·확인 처리, actor·확인 시각 저장
- [x] 저장 전 이탈 신호를 병원 목록·상세에 표시
- [x] 실제/목업 notify·ask 정합성 및 승인 섹션만 의료 문구로 사용
- [x] 선택 메모 길이·빈 값 처리, 최종 저장·병원 조회·이력만 노출
- [x] 완료 화면 fragment 복귀 (실제 브라우저에서 승인 안내 표시까지 확인)
- [x] 신호 실패를 성공으로 표시하지 않되 폼·최종 저장은 유지
- [x] OTP 세션·만료·회전·타 병원·admin 단독 접근 차단 회귀
- [x] 신호에 메모/토큰/OTP 미저장, 토큰 비반환, 기존 로그·오류 마스킹 보안 회귀 유지
- [x] Aerich migration 64: clean/기존 DB upgrade·재실행·기존 응답 보존·append-only 검증 (아래 최초 63번 결과는 당시 기록)
- [x] OpenAPI·API 문서 갱신
- [x] Ruff/mypy/백엔드·프론트 전체 관련 회귀 및 실제 브라우저 검증

## 실행 증거 — 2026-09-15 로컬 합성 데이터

- `pytest -q app/tests/patient_links app/tests/patient_manage app/tests/migrations app/tests/security`: **478 passed**, 63.10초.
- `node --test frontend/tests/*.test.js`: **1,304 passed**, 실패·skip 0.
- `mypy . --explicit-package-bases`: **474 source files**, 오류 0.
- `ruff check .`, `ruff format --check .`, `git diff --check`: 통과.
- `scripts/generate_openapi.py --check`: 현재 DTO와 일치.
- `scripts/ci/key238_migration_check.py`: 전용 MySQL의 `key238_v63_clean`·`key238_v63_existing` 모두 통과. 기존 DB 경로는 0~62 적용 → 기존 CheckIn 삽입 → 63 적용 → 기존 답/메모 null 유지 확인. 두 DB 모두 재실행은 빈 적용 목록이고 이벤트 UPDATE/DELETE가 차단됨.
- `scripts/check_schema_drift.py`: migration 63 적용 DB와 모델 드리프트 없음.
- 최신 develop 통합 중 62번이 KEY-328에 사용되어 **63번으로 이동**, 현재 모델 전체에서 MODELS_STATE를 재생성하고 위 검증 재실행. upstream 변경 파일은 보존.

### 실제 브라우저 (API mock 아님, SMS만 로컬 mock)

1. 새 합성 환자 링크에서 OTP 입력 → D+7 실제 폼 표시.
2. 최종 저장 전 ‘불편해서 중단했어요’ 선택 → 의료진 관리 ‘챙겨주세요 1명’, ‘복약 선택 확인 필요’ 표시.
3. 전체 이력에서 선택 상태 OPEN 표시 → ‘확인 완료’ 클릭 → 확인 직원 ID·시각 표시, 진료 완료/안전 해소가 아니라는 설명 유지.
4. 환자가 ‘잘 먹고 있어요’·통증 없음·합성 메모를 최종 저장 → 완료 화면 표시.
5. 의료진 이력 재조회에서 메모와 ‘확인 대상 아님’ 표시 확인.
6. 완료 화면 ‘복약지도 다시 보기’ → 토큰 fragment를 통해 승인 안내 정상 표시.

## 주의

이 증거는 로컬 구현 검증이며 운영 배포·팀 최종 승인·GitHub CI 통과를 의미하지 않는다.
운영 서버·기존 서비스 DB를 변경하거나 실제 문자를 발송하지 않았다. 최종 저장된 배지는 KEY-320 범위를
보존하며 선택 신호 확인 완료를 진료 완료·안전 해소로 표현하지 않는다.

## PR #323 리뷰 보완 — 2026-09-15

검토: 이희진의 [같은 답 재발생 시 확인 상태 미해제 지적](https://github.com/AI-HealthCare-05/AH_05_06/pull/323#issuecomment-5675136012). 조회 시 일반 댓글 1건, 인라인 리뷰·제출 리뷰 없음.

- 새 signal_id가 현재 상태가 되면 answer_key가 같아도 확인자·확인 시각을 해제한다. 기존 append-only 확인 이력은 보존한다.
- 중단 답 두 종류 모두 새 발생 → 병원 목록 CHECKIN_SIGNAL 재표시 → 환자 이력 OPEN → 새 발생 건 확인 및 확인 이력 추가를 실제 DB/API에서 검증한다.
- 동일 요청 재시도와 이전 순번은 확인 상태를 유지하며, 다른 기기에서 온 같은 답의 새 현재 신호는 재오픈한다.
- 이전 signal_id로 새 발생을 확인하려 하면 409. 최종 저장 이후의 늦은 신호는 이력만 남긴다.
- 최종 저장은 새 선택 이벤트가 아니라 현재 답 보정이다. 같은 답은 기존 확인을 유지하고 다른 답은 해제하는 기존 정책을 보존했다.
- DTO·schema·migration·화면 렌더러 변경 없음. API 문서에 재오픈/보존 기준을 명시했다. 이번 보완은 병원 목록·이력 API 응답까지 검증하며 위 최초 구현의 브라우저/실제 migration 실행을 다시 수행한 것으로 표시하지 않는다.
- 최종 재검증: `pytest -q app/tests/patient_links app/tests/patient_manage app/tests/migrations app/tests/security --tb=short` **482 passed** (63.83초), 전체 프런트 **1,304 passed**, mypy **474 files**, Ruff check/format·OpenAPI `--check`·`git diff --check` 통과. 실제 SMS·운영 데이터 사용 없음.

## PR #323 후속 전체 리뷰 반영 — 2026-09-15

- 일반 댓글 4개와 인라인 댓글 없음 확인. 기존 같은 답 재발생 재오픈 수정은 리뷰어 확인 완료이며 기존 회귀를 유지했다.
- `NOTIFIES.uncomfortable=False` 및 새 신호 조회·확인 라우트 2개의 소유 모듈 등록 누락을 수정했다. 계약·라우팅·환자 링크 회귀 621개 통과.
- 공용 서버 적용 여부는 SSH 권한 거부로 직접 확인하지 못했다. 사용자의 공용 서버 미적용 추정 및 재생성 진행 승인을 전제로 진행했다. 운영 DB/장부는 변경하지 않았다.
- develop `06807b9`를 통합하고 PR의 기존 63번을 제거한 뒤 Python 3.13/Aerich offline으로 `64_20260915181415_key238_checkin_signals.py`를 새로 생성했다. 파일명만 변경하지 않았다. 기존 append-only 트리거와 FK 역순 downgrade는 유지했다. KEY-338의 hold_reason 22자 확장을 새 MODELS_STATE에 포함하며 해당 변경 SQL을 중복하지 않는다.
- 실제 격리 MySQL `key238_v64_clean` 0→64 / `key238_v64_existing` 0→63·기존 CheckIn 삽입→64 모두 통과. 재실행 추가 적용 없음, 기존 응답·note null 보존, append-only UPDATE/DELETE 차단, hold_reason 실제 길이 22 확인. 기존 v63 QA DB는 삭제하지 않았다.
- 후속 `aerich migrate --offline`: **No changes detected**. 최초 실행은 app 의존성 누락, 다음 실행은 엔진 버전 조회용 DB 인증 부족으로 실패했으며 app 그룹·전용 QA DB 설정 후 재실행 성공. offline은 비교 기준을 파일로 삼지만 MySQL 버전 조회는 연결이 필요했다.
- 전체 프런트 **1,309 passed**, Ruff check/format 및 OpenAPI 일치 통과. 새 최소 venv mypy는 AI 선택 의존성이 없어 실패했으나, 해당 의존성이 설치된 공유 Python 3.13 환경에서 **478 files 통과**. 애플리케이션 코드/의존성 잠금 파일을 완화하지 않았다.
- 이번 수정은 테스트 레지스트리·migration 재생성이며 화면 변경/실제 SMS/운영 배포는 하지 않았다. GitHub CI 재실행은 푸시 후 별도 확인 필요.
- 최종 백엔드 전체 `pytest -n 4 -q app ai_worker`: **2,888 passed / 1 xfailed / 14 subtests passed (173.93초)**, skip·fail 0. 기존 HTTP 422 deprecation 경고 9건은 유지했다. 충돌 파일 없음 및 diff 공백 검사 통과. develop 통합과 보완 변경은 커밋 전 로컬 상태로 보존한다.
