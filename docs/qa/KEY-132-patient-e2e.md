# KEY-132 환자 모바일 E2E 검수

## 범위와 기준

- Jira: https://leehee.atlassian.net/browse/KEY-132 (2026-09-15 갱신 설명 확인)
- 실행·QA 유가은 / 요구사항·의료안전 검수 이희진 / 기술 확인 권일준.
- 기준 develop `06807b9` (PR #326 KEY-351 grounding 포함).
- 브랜치 `codex/KEY-132-patient-e2e`, 제품 코드 변경 없음.
- D+7, KEY-176 Pilot 여정, KEY-237 병원 전체 E2E는 중복 실행 범위에서 제외.
- 현재 상태: **로컬 실제 서버·모바일·실제 LLM·회귀 QA 실행 완료, 담당 검수자의 최종 인수 대기. 운영 SMS/인증 종단 검수를 완료했다는 의미는 아님.**

## 환경

- 원본 FastAPI 라우터/서비스, MySQL 및 Redis 연결. 프런트는 동일 프로세스의 검수 전용 StaticFiles 마운트로 제공.
- AC1 서빙 방식의 알려진 차이: 운영은 Nginx의 정적 파일 서빙과 API reverse proxy를 사용하지만 이번 QA는 FastAPI 프로세스의 StaticFiles로 프런트를 제공했다. 따라서 운영과 동일한 서빙 방식이 아니며 Nginx 경유 라우팅·HTTPS·프록시 헤더·로그 동작까지 검증한 것으로 보지 않는다.
- `127.0.0.1:18432`, Chrome headless, 모바일 390×844 / touch.
- 새 DB `key132_qa0915`, MySQL 포트 18377, Redis 포트 16379 / DB 12. 정식 Aerich upgrade로 생성. 기존 DB가 있으면 덮어쓰기 거부.
- 합성 환자/의원, 승인·미승인·만료·회전된 이전 링크 시나리오. 원문 링크는 로컬 권한 0600 상태 파일에만 보관하고 문서/출력에 남기지 않음.
- 프런트 `?mock=1` 사용 안 함. **백엔드 개발용 고정 OTP 발송 어댑터 사용**, 실제 SMS 미발송. 실제 휴대폰 수신/운영 발송 승인 검수는 아님.
- `OPENAI_API_KEY`는 빈 값. 정상 외부 LLM 생성 검수 아님. `Config`의 빈 SecretStr은 모델 어댑터를 만들며 호출 실패 fallback 경로로 진행됨. 따라서 모델 없는 분기와 동일하다고 주장하지 않음. 유료 정상 생성은 수행하지 않음.

## 실행 결과

| 검증 | 관찰 | 판정 |
|---|---|---|
| OTP 전 Guide API | 401 | 통과 |
| 잘못된 OTP | 401, 안내 진입 안 됨 | 통과 |
| 올바른 개발 OTP | 실제 API 검증 후 `/guide.html` 도달 | 로컬 통과 |
| P2 현황/P3 복약/P4 주의/P5 생활 | 실제 모바일 탭 렌더링 | 통과 |
| 승인 문구 일치 | 복약·주의·생활 edited_body 문구가 각 탭에 표시됨 | 통과 |
| 미승인 생성 원문 | 4개 탭에서 노출 없음 | 통과 |
| P6 챗봇 UI | 실제 `/chatbot/responses` 200, 안전 fallback | fallback 경로 통과 |
| 네트워크 실패 복구 | 브라우저에서 첫 챗봇 요청 abort → 다시 시도 표시 → 실제 API 200 | 통과 |
| 같은 submission_id 재요청 | 200 fallback, 답변 내용 동일, response_ref만 변경 | 모델 실패 재시도 허용 경로 |
| 미승인 링크 context | 410 | 통과 |
| 만료 링크 context | 410 | 통과 |
| 회전 전 링크 context | 404 | 통과 |
| 브라우저 미처리 JS 예외 | 0 | 통과 |

모델 실패 분기는 `ChatbotService._answer_from()`에서 `_record(..., keep=False)`로 요청 잠금을 풀고 영구 멱등 완료 표식을 남기지 않는다. 재시도 시 새 response_ref가 나오는 것은 이 경로와 일치한다. **정상 생성의 동일 요청 재생 검증과 혼동하지 않는다.**

### 자동 회귀

- `app/tests/patient_links`, `app/tests/chatbot`, `app/tests/patient_usage`: **234 passed, 22.56초**.
- `node --test frontend/tests/*.test.js`: **1,306 passed, skip 0**, 약 3.48초.
- API 회귀는 별도 `TEST_SLOT=4` 테스트 DB/Redis를 사용. 일부 서비스 경계와 외부 모델은 테스트 대역이므로 운영/실제 외부 모델 E2E 성공 증거가 아니다.
- 잠금·세션 만료·링크 회전·승인 컨텍스트·정상 답변 멱등성에 대한 자동 회귀는 위 묶음에 포함된다. 각각을 이번 실제 브라우저에서 모두 재현했다고 주장하지 않는다.
- AC4 폐기 경로: `app/tests/patient_links/test_key219_patient_auth.py::test_revoked_link_returns_410_link_revoked`는 승인된 안내의 상태를 `SCHEDULED_TO_SEND`에서 `APPROVAL_PENDING`으로 변경한 뒤 context 응답이 410 / `LINK_REVOKED`인지 검증한다. 위 **234 passed** 스위트에 포함되며, 실행 결과 표의 회전 전 링크 404와 별개의 폐기 검증 근거다.
- AC2 P2(현황) 콘텐츠 일치: `app/tests/patient_links/test_key241_patient_guide_contract.py::test_v3_contract_uses_available_models_and_keeps_approved_sections`는 저장한 합성 Prescription/OCR 데이터를 기준으로 `stat` 카드의 `drugName`, `prescribed`, `dayOn`, `remaining`, `pct` 등을 기대값과 비교하고 승인 섹션 보존도 검증한다. 이 역시 위 **234 passed** 스위트에 포함되며, 브라우저의 복약·주의·생활 승인 문구 대조와 구분되는 P2 콘텐츠 검증 근거다.

## QA 보조 스크립트의 수정 이력

- 초기 Visit import 위치를 바로잡은 뒤 서버 실행. 제품 결함 아님.
- 초기 폐기 fixture에 모델에 없는 revoked_at을 전달하여 정상 링크가 만들어졌다. 이를 폐기로 판정하지 않고 실제 digest 회전으로 수정하여 이전 링크 404 재확인.
- 초기 수동 챗봇 요청은 UUID가 아닌 submission_id라 400이었다. UUID로 바로잡아 200 확인.
- 중복 응답은 JSON 문자열 순서 비교 대신 필드별 깊은 비교로 확인. 실제 차이는 response_ref뿐임을 검증.

## 추가 완료 검증

- 저장된 로컬 OpenAI 자격증명을 값 노출 없이 별도 QA 서버(`18433`, Redis DB13)에 적용. 합성 질문만 사용. 실제 모바일 챗봇 200, `fallback=false`, `grounded_section=medication` 확인. 현재 서비스는 승인 섹션에 대한 추출 근거 검사를 통과한 응답만 이 성공 경로로 반환한다.
- 실제 LLM 정상 생성 후 동일 UUID의 submission_id로 같은 질문 재전송: 200/200, `fallback=false`, **동일 response_ref**. 앞서 빈 키 모델 장애의 재시도와 구분된다.
- 합성 링크 소유의 Redis 세션 TTL만 1ms로 줄여 만료시킴: Guide API 401. 토큰이 제거된 URL의 단순 새로고침은 '안내 링크 정보가 없어요'를 표시하며, 원래 링크를 새 문서로 열면 OTP 화면으로 자동 이동. 올바른 OTP 재인증 후 안내 재진입 성공.
- 실제 모바일 OTP 확인 화면에서 잠금 상태 검증: API에 잘못된 코드 5회 제출 → 401/401/401/401/429. 화면에서 올바른 코드를 입력해도 429. 잠금 중 OTP 재발급도 429. 미처리 브라우저 예외 0.
- 실제 세션 쿠키 `HttpOnly=true`, `SameSite=Lax`, `Path=/api/v1` 확인. 로컬 HTTP이므로 운영 Secure 속성 확인과는 구분.
- `https://care-on.site/login.html` 읽기 전용 HEAD: 인증서 검증을 끄지 않은 curl로 HTTPS 200 확인. 운영 로그인·환자 OTP·Nginx 토큰 로그 검수는 아님.
- 추가 LLM 유료 호출은 정상 응답 검수에 필요한 소수 호출로 제한했다. 실제 SMS 미발송, 기존 제품 코드/운영 데이터 수정 없음.

추가 증적: `/private/tmp/key132-final.log`(LLM 정상/동일 요청 및 최초 이동 timeout), `/private/tmp/key132-auth-complete.log`(인증 전체 통과), `/private/tmp/key132-locked.png`.

### 추가 QA 시행착오

처음에는 토큰이 지워진 안내 URL을 reload하여 OTP로 자동 이동할 것이라고 잘못 기대했다. 또한 동일 페이지에서 fragment만 바꾸면 새 페이지 로드가 발생하지 않았다. 기존 구현의 토큰 비저장 계약에 맞춰 빈 페이지를 거쳐 원래 링크를 여는 방식으로 재실행했고 재인증 경로를 확인했다. 제품 코드 변경이나 테스트 조건 완화는 하지 않았다.

## 최종 인수와 적용 범위

1. 정상 LLM 응답·정상 요청 재생·잠금·세션 만료와 재인증의 로컬 실제 서버 검증은 위 추가 결과로 완료했다.
2. 고정 OTP 개발 어댑터이므로 서로 다른 문자 인증번호의 교체·이전 코드 무효화는 자동 회귀 근거이며 실제 문자 수신 검증이 아니다. 링크 회전도 합성 DB의 digest를 회전하여 이전 링크 차단을 검증했으며 운영 발송 이력 화면 조작은 하지 않았다.
3. Jira는 현재 develop의 실제 서버 연결을 요구하고 운영/Pilot 지정은 없다. 따라서 로컬 실제 서버 결과로 제출하되, 운영 Secure 쿠키·프록시 로그·실제 문자 수신을 별도 미검증 범위로 명시한다. 앞서 나열한 운영 HTTPS 전체 검수를 이번 로컬 검수와 혼동하지 않는다.
4. 최종 인수는 Jira의 요구사항·의료안전 검수자에게 남긴다. QA 실행을 완료했더라도 담당자 승인 없이 Jira 완료 상태로 전환하지 않았다.

## 로컬 증적

- `/private/tmp/key132-browser-final.log`, `/private/tmp/key132-regression.log`, `/private/tmp/key132-frontend.log`
- `/private/tmp/key132-guide.png`, `/private/tmp/key132-chat.png`
- 검수 보조: `/private/tmp/key132-server.py`, `/private/tmp/key132-browser.cjs`

이 문서는 QA 결과 제출용이다. 위 원본 로그·스크린샷·보조 스크립트는 실행자의 로컬 증적이며 저장소에 포함하지 않았다. 인증 상태 파일과 실제 자격증명은 PR에 포함하지 않는다. Jira 최종 인수 및 완료 전환은 별도다.
