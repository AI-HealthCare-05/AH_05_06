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
- [x] Aerich migration 63: clean/기존 DB upgrade·재실행·기존 응답 보존·append-only 검증
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
