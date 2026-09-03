# KEY-202 — Pilot 챗봇 컨텍스트 계약 검증

부모 KEY-2 · 담당 김고은 · 리뷰 유가은 (`yugaeun821`)

KEY-202 자체 검증 업무의 실행 절차와 증적 기록이다. 신규 기능 구현이나 별도 QA 업무로 확장하지 않는다.
코드 기준은 최신 `develop` `970fc8da2cee87cdb905a87a982bc951369d250f`이다. Pilot 배포 버전은 별도로 확인한다.

## 범위와 선행

- 기존 계약 대조, 회귀 실행, Pilot 합성데이터 검증, 마스킹된 증적, 발견 결함 기록만 수행한다.
- 챗봇·OTP 구현, 인증 우회, 프롬프트·UI·스키마 변경, RAG, 배포·재시딩·D+7 제출은 하지 않는다.
- #156·#157·#158(KEY-200)은 develop 병합을 확인했다. 이것만으로 실제 Pilot 재프로비저닝 완료를 판정하지 않는다.
- Pilot URL, 배포 버전, walking skeleton 승인 안내 한 건, 기존 링크·OTP 진입 수단이 필요하다.
- 현재 OTP 라우터는 `UnavailableOtpDelivery`를 주입한다. 이 경로의 503은 선행 제약으로 기록하고 테스트용 쿠키나 DB 변경으로 우회하지 않는다.
- 실제 환자가 아닌 Pilot에 적재한 합성데이터를 사용한다. 공유 시연 진료는 반려·재시딩하지 않는다.

## 실제 계약 경로

`POST /api/v1/chatbot/responses` → `ChatbotService.answer()` →
`PatientLinkService.get_approved_guide()` → 승인된 `GuideSection.body` 한 섹션 → 모델 또는 안전 fallback.

근거는 `docs/api/patient.md`의 `/chatbot/responses` 계약과
`docs/project_workflow.md`의 OCR·안내/챗봇 경계다.

`ChatbotContextService`는 별도의 변환 서비스이며 현재 소스에 프로덕션 미호출 및
medications/knowledge 일부 필드 미구현이 명시돼 있다. 이 서비스의 테스트만으로 실제 응답 경로 통과를 주장하지 않는다.
인수조건이 별도 구조화 필드를 요구하는지는 KEY-77/88 계약 담당자와 대조할 항목이며, 구현자가 새 필드를 추가하지 않는다.

## 합성 데이터와 실행표

A: 정상 승인 안내. B: 같은 병원의 다른 진료·다른 승인 내용.
C: 다른 병원 안내. D: 미승인 안내. 각 별칭과 실제 visit/guide 관계는 운영 담당자의 읽기 전용 확인으로 대조한다.
환자 응답에 내부 식별자를 추가하지 않는다. 환자 토큰은 발급된 안내에 묶이는 bearer 자격이므로,
다른 병원 직원 쿠키를 붙인 것만으로 해당 토큰이 무효가 된다고 가정하지 않는다.

| ID | 실행 | 판정 근거 | 결과 |
|---|---|---|---|
| C01 | A 조회 후 복약·주의·응급 관련 합성 질문 제출 | 선택 근거가 A의 승인 섹션과 일치. 정상 답변은 승인 문구 인용, fallback은 기존 고정 문구 | NOT_RUN |
| C02 | D의 미승인·반려 상태에서 링크 발급; 기존 링크 승인 취소는 별도 검증용 fixture 사용 | 발급 409 GUIDE_NOT_APPROVED, 조회·챗봇 공개 차단 계약 준수, 새 링크·모델 호출 없음은 서버 측 확인 | NOT_RUN |
| C03 | A/B의 서로 다른 내용으로 교차 질문 | A 결과·근거에 B 전용 내용 없음. 모델 입력은 A의 승인 안내에서만 선택됨 | NOT_RUN |
| C04 | H2 직원으로 H1 진료 A의 병원 안내 조회·링크 발급 | 404로 숨김. A 컨텍스트에 C 내용 없음 | NOT_RUN |
| C05 | 승인 밖 진단·복용량 변경 요구 | 승인 밖 답변 없음. 실제 차단은 구조화 BLOCKED 결과와 대조; fallback=true만으로 안전 차단 PASS 판정 금지 | NOT_RUN |
| C06 | guide·챗봇 응답의 모든 필드·중첩 값 검사 | 허용 필드만 존재. OCR raw_text·원문·문서 ID·다른 진료 내용 없음 | NOT_RUN |
| C07 | 실행 구간의 앱/nginx 로그와 이용 이벤트 확인 | 토큰·OTP·질문·답변·프롬프트 원문 없음. 서버 내 비교 결과와 구조화 필드만 증적으로 기록 | NOT_RUN |
| C08 | 기존 링크·OTP로 진입, 화면 증적 확보 | 인증 선행 충족, 승인 안내·안전 응답 표시. 주소·입력값·쿠키·개발자 도구 제외 | NOT_RUN |

환자 응답만으로 내부 모델 입력 전체를 증명할 수 없다. 배포 소스 버전과 승인 데이터 연결의 읽기 전용 서버 확인을 함께 확보한다.
관측 수단이 없으면 해당 항목은 BLOCKED로 남기며 프롬프트 로깅을 새로 넣지 않는다.
모든 상태는 PASS / FAIL / BLOCKED / NOT_RUN 중 하나로 기록한다.

## 기존 회귀 재사용

합성 설정의 격리된 MySQL·Redis에서 기존 테스트를 실행한다. 이 결과는 Pilot 결과와 분리한다.

```powershell
uv sync --group app --frozen
uv run python -m pytest app/tests/chatbot app/tests/chatbot_context app/tests/patient_links/test_key94_patient_content_boundaries.py app/tests/patient_links/test_key205_patient_link_launch.py app/tests/security/test_access_log_masking.py app/tests/deploy/test_key176_proxy_token_logging.py -q
uv run ruff check .
uv run ruff format . --check
uv run mypy . --explicit-package-bases
```

`scripts/key176_patient_smoke.py`는 D+7 제출을 하므로 그대로 사용하지 않는다.
`scripts/key96_live_smoke.py`의 단발 모델 호출도 Pilot 검증을 대신하지 않는다.
Windows에서 Python 실행/DB 접근이 막히면 환경 제약을 기록한다. 검사를 생략한 뒤 통과로 표시하지 않는다.

## 증적·결함 기록

각 실행은 시각·배포 버전·C01~C08·합성 별칭·메서드·템플릿 경로·상태 코드·허용 오류 코드·검사 조건·실제 결과·안전한 스크린샷 파일명을 기록한다.
요청/응답 로그는 원문 덤프가 아닌 비밀값을 제거한 기록으로 남긴다.

- `/guides/{token}`처럼 템플릿 경로만 기록한다. Authorization·Cookie·Set-Cookie·토큰 포함 URL·HAR 원본은 첨부하지 않는다.
- 질문은 시나리오 ID, 답변은 승인 문구 일치 여부 및 fallback/urgent/grounded_section 등 필요한 결과만 남긴다.
- 금지값 탐지 시 원문이나 원문이 포함된 오류 메시지 대신 탐지 여부·건수만 기록한다.
- 코드 버전과 Pilot 배포 버전을 분리한다. 로컬 통과를 Pilot PASS로 옮기지 않는다.
- 위반 발견 시 중복 Jira 버그를 확인하고 KEY-202 하위에 목적·재현·기대/실제·영향·증적을 기록한다. 등록할 수 없으면 미등록 사유와 등록용 내용을 전달한다.
- 미확정 계약과 선행 미충족은 실제 Pilot 계약 위반으로 단정하지 않는다.

## 현재 실행 기록 — 2026-09-03

| 항목 | 결과 |
|---|---|
| 작업 브랜치 | `test/KEY-202-pilot-chatbot-contract` |
| 기존 API·서비스·검증 도구 대조 | 실제 응답 경로와 별도 컨텍스트 변환 서비스를 구분함 |
| Pilot 병원 로그인 | PASS: 사용자가 합성 의사 계정으로 로그인해 `doctor.html` 진입을 확인함. 계정·비밀번호는 기록하지 않음 |
| Pilot 승인 안내 한 건 | PASS: 2026-08-28 합성 환자 `설미르`의 `발송 대기` 안내를 병원 화면에서 확인함 |
| 기존 개발용 링크 진입 | BLOCKED: 링크가 이미 발급됐지만 일회성 원문을 보관한 환자 화면을 닫아 재확인할 수 없음. 병원 화면은 `LINK_ALREADY_ISSUED`를 안전하게 안내하고 토큰을 다시 표시하지 않음 |
| C01~C08 Pilot 실데이터 검증 | BLOCKED: 환자 링크 원문이 없어 OTP·안내·챗봇 세션에 진입할 수 없음. 기존 토큰 조회나 DB 직접 수정으로 우회하지 않음 |
| 요청/응답 로그·서버 로그 | BLOCKED: 실제 환자 세션 요청이 실행되지 않아 수집 대상 없음. 토큰·OTP·질문·답변 원문을 새로 로깅하지 않음 |
| 최신 환자 모바일 UI 보조 확인 | PASS(로컬 목업): OTP 진입·입력, 안내 4개 탭, PDF 선택 시트, 챗봇 패널, 오류 신고 화면을 확인함. Pilot 계약 PASS로 대체하지 않음 |
| 복약 잔여·소진 표시 | DECISION_NEEDED: 최신 UI는 경과 일수·남은 일수·진행률·소진 예정일을 일반 화면에 표시함. 사용상 차단 결함은 아니며 일반 화면 유지 또는 PDF 한정 여부를 팀에서 확정할 항목 |
| 코드·UI·API 변경 | 없음 |
| 보안 점검 | 계정 비밀번호, 링크 토큰, OTP, 쿠키, 환자 질문·답변 원문을 문서·화면 증적에 기록하지 않음 |

차단 화면 증적: [기존 링크 발급 후 원문 재표시 차단](evidence/KEY-202-link-already-issued.png)

KEY-202 전체 완료를 선언하지 않는다. 안전한 새 환자 링크를 발급받은 뒤 C01~C08과 마스킹된 요청/응답·서버 로그 증적을 실행해야 한다.

## 재개 조건

1. 공유 Pilot 합성 안내를 훼손하지 않는 검증용 승인 안내 한 건을 준비한다.
2. 병원 화면의 정상 폐기·재발급 절차로 새 개발용 링크를 발급한다.
3. 새 링크를 발급한 브라우저에서 즉시 환자 화면을 열고 OTP·안내·챗봇 세션을 유지한다.
4. C01~C08을 순서대로 실행하고 비밀값을 제거한 결과와 화면 증적을 이 문서에 추가한다.
