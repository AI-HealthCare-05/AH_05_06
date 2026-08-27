# KEY-176 OTP→챗봇→D+7 Pilot 통합 검수

> 부모: KEY-144 · 합성 데이터 전용 · 실제 SMS·RAG·대화 원문 저장은 범위 밖

## 검수 경계

기존 v1 계약을 바꾸지 않는다.

- 안내와 D+7 양식 조회는 72시간 링크로 접근한다.
- OTP 성공 뒤 발급되는 30분 HttpOnly 세션은 D+7 저장에 강제된다.
- 챗봇은 KEY-96의 승인 안내 섹션만 사용하며 외부 검색·벡터 DB·임베딩을 사용하지 않는다.
- 모델 장애는 진단·약물 변경 권고가 없는 고정 응답으로 끝나며 D+7 여정을 막지 않는다.
- KEY-170에는 안내 식별자·이벤트 유형·질문 갈래·결과·근거 섹션·시각만 저장한다.

챗봇 API에 환자 세션을 새로 강제하는 것은 인증 계약 변경이므로 이번 일감에서
임의로 추가하지 않았다. 만료 세션은 계약상 보호 동작인 D+7 저장에서 차단하고,
OTP 재인증 뒤 같은 답을 다시 제출하는 흐름으로 검증한다.

## 자동 검수

`app/tests/e2e/test_key176_pilot_patient_flow.py`가 다음을 한 흐름으로 확인한다.

1. 승인 완료 합성 안내 링크에 OTP를 발급·검증한다.
2. 승인 안내를 열람한다.
3. 챗봇 첫 호출의 합성 외부 장애가 안전한 fallback으로 끝나는지 확인한다.
4. 재시도는 같은 병원의 승인 섹션만 사용하고 정상 답을 내는지 확인한다.
5. 세션을 만료시킨 뒤 D+7 저장이 `401 PATIENT_SESSION_EXPIRED`로 차단되는지 확인한다.
6. OTP를 재발급·검증한 뒤 D+7 한 건을 저장하고 같은 `visit_id`로 병원에서 조회한다.
7. KEY-170 이벤트에는 구조화 값만 있고 질문·답변·링크 토큰 원문이 없는지 확인한다.
8. 미승인 안내는 OTP·챗봇·이용 이벤트 생성 전에 차단되는지 확인한다.

오류 복구 UI는 이미 존재하는 아래 상태 기반 검사로 재사용한다.

```text
frontend/tests/patient-auth-recovery.test.js
frontend/tests/chatbot-streaming-ui.test.js
frontend/tests/chatbot-abort-retry.test.js
```

## 원격 Pilot smoke

전용 합성 승인 안내와 아직 제출하지 않은 D+7 진료 건을 준비한다. 실제 환자나
운영 링크를 사용하지 않는다. 값은 명령행 인자가 아니라 환경변수로만 전달한다.

```bash
export PATIENT_SMOKE_SYNTHETIC_ONLY=1
export PATIENT_SMOKE_LINK_TOKEN=<합성 링크 토큰>
export PATIENT_SMOKE_OTP=<합성 Pilot OTP>
export PATIENT_SMOKE_VISIT_ID=<같은 합성 visit_id>
export SMOKE_LOGIN_ID=<같은 병원의 합성 staff 또는 doctor>
export SMOKE_PASSWORD=<합성 계정 비밀번호>

uv run python scripts/key176_patient_smoke.py https://<Pilot URL>
```

스크립트는 OTP 발급·검증→안내→챗봇→D+7 제출→병원 조회를 순서대로 호출한다.
챗봇은 HTTP 200뿐 아니라 응답의 `fallback` boolean을 확인한다. 정상 생성은
`[PASS]`, 안전 fallback은 `[WARN]`으로 구분하되 환자 여정은 D+7까지 계속한다.
`fallback`이 없거나 boolean이 아니면 응답 계약 위반으로 `[FAIL]` 처리하고 멈춘다.
밖으로 출력하는 것은 단계 이름·허용된 사유·HTTP 상태 코드뿐이다. 응답 본문,
링크·OTP·직원 토큰·비밀번호는 출력하지 않는다. 전용 진료 건은 D+7을 한 번
제출하면 다시 쓸 수 없으므로 실행마다 새 합성 fixture를 준비한다.

## 프록시 로그 경계

애플리케이션의 Uvicorn access log 마스킹과 별개로 Nginx는 기본 설정에서 URL
경로를 기록한다. 링크 토큰이 경로에 있는 `/api/v1/guides/`와
`/api/v1/checkins/`만 HTTP·HTTPS access log를 끄고, 처리시간·실패율 수집에
필요한 일반 `/api/` 로그는 유지한다. 회귀 검사는
`app/tests/deploy/test_key176_proxy_token_logging.py`에 있다.

## 실행 기록

| 검증 | 결과 |
|---|---|
| Ruff·mypy (KEY-176 변경 파일) | 통과 |
| smoke 판정·원문 비노출 단위 검사 | 2 passed |
| Nginx 링크 토큰 로그 경계 | 2 passed |
| 인증 복구·챗봇 실패/중단/재시도 UI | 36 passed |
| MySQL 종단간·전체 회귀 | 게시 전 Docker MySQL 환경에서 실행 |
| 실제 Pilot URL smoke | URL·전용 합성 fixture 제공 뒤 실행 |

실제 Pilot URL과 전용 합성 fixture는 저장소에 없으므로 원격 실행 성공을
기록하지 않는다. 이 항목은 실행 증적이 생기기 전까지 KEY-176의 운영 검수
잔여 항목이며, 코드 검사를 성공으로 꾸며 대신하지 않는다.
