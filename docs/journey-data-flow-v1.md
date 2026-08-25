# 전체 서비스 여정의 1차 데이터 흐름 정의 v1 (`KEY-146`)

> 상위: [`KEY-140`](https://leehee.atlassian.net/browse/KEY-140) · 관련: [`KEY-148`](https://leehee.atlassian.net/browse/KEY-148) · 기준 커밋 `develop`(2026-08-21, `b6c2f55`)
> 8/27 종단간 최소 동작본을 구현하기 전에, 합성 시나리오 한 건이 서비스 처음부터 끝까지 이동할 때 필요한 데이터 계약과 연결 기준을 정의한다. 전체 여정 실행이나 통합 QA는 이 문서의 범위가 아니다 — `KEY-152`(E2E)·`KEY-141`이 담당한다.
>
> 모든 상태 표기는 `develop`의 실제 코드와 GitHub PR 이력을 직접 대조해 판정했다.

---

## 1. 기준 시나리오

`KEY-148`이 고정한 `SYN-EMS-01`을 그대로 쓴다. 같은 환자를 문서마다 다르게 가리키면 추적이 성립하지 않는다.

| | 값 |
|---|---|
| 병원 | H1 · 기준의원 (`hospital_id`) |
| 스탭 / 의사 | `staff01` 한소영 / `doctor01` 박연 |
| 환자 | 차트 `12401` 윤지아 (`patient_id`) |
| 진료 | 2026-07-29 · 담당의 박연 (`visit_id`) |

---

## 2. 연결 규칙 — `patient_id`·`visit_id`를 어떻게 유지하는가

인수조건 "동일한 `patient_id`·`visit_id`가 전체 여정에서 유지됨"을 코드가 지킬 수 있는 형태로 정의한다.

| 규칙 | 내용 | 근거 |
|---|---|---|
| **R1 — 값 복사 금지, FK만 사용** | 진료에 종속된 모든 데이터(`medical_document`, `ocr_job`, `guide_document`, 향후 `checkin`)는 생성 시점에 부모 `visit_id`를 FK로 받는다. 문자열이나 다른 필드로 값을 다시 옮겨 적지 않는다 | `app/models/documents.py`(`visit` FK), `app/models/ocr.py`(`OcrJob.visit`), `app/models/visits.py`(`GuideDocument.visit`, 1:1) |
| **R2 — `patient_id`는 `visit`을 거쳐서만 얻는다** | `guide_document`·`ocr_job`은 `patient_id` 칼럼을 직접 갖지 않는다. 환자를 알아야 하면 `visit.patient`를 조회한다 — 중복 저장하면 두 값이 갈라질 수 있다 | `GuideDocument`에 `patient_id` 칼럼 없음(`app/models/visits.py`) |
| **R3 — 병원 격리는 항상 `visit.hospital_id`가 최종 근거** | 각 테이블의 `hospital_id`는 목록 조회용 인덱스 사본일 뿐, 격리 판정에는 쓰지 않는다 | `docs/api/hospital.md` §5 "`guide_document.hospital_id`는 목록 조회용 인덱스 사본이라 격리 판정에는 쓰지 않는다" |
| **R4 (설계) — D+7·환자 링크도 같은 체인을 따른다** | `check_in_id`(PK) → `CHECKIN.guide_document_id`(FK) → `GUIDE_DOCUMENT.visit_id` → `Visit.patient_id`. 새 테이블이 생기면 `visit_id`를 직접 복제하지 않고 `guide_document_id`를 거쳐 파생한다 | `docs/api/hospital.md` §8 "`CHECKIN.guide_document_id` → `GUIDE_DOCUMENT.visit_id/patient_id`로 추적" |

---

## 3. 안전 게이트 정의

### 게이트 A — OCR 확정 게이트

> **규칙**: 안내 섹션(`guide_section.generated_body`)을 만드는 입력값은 `ocr_field.is_confirmed = true`인 값만 쓴다. 미확정 필드가 안내 생성 입력에 섞이면 위반이다.

| 항목 | 상태 |
|---|---|
| 확정 여부 저장 | **구현완료** — `OcrField.is_confirmed`, `PATCH /ocr/fields/{id}`가 `confirm` 플래그로 설정 |
| 확정값과 미확정값 분리 | **구현완료** — `extracted_value`(예측) / `corrected_value`(수정) / `is_confirmed`(확정) 3단 분리 |
| 게이트를 실제로 강제하는 코드 | **미구현** — 안내 생성 자체가 없어 이 규칙을 지킬 대상이 아직 없다 |
| 강제 책임 | `KEY-150`(안내 생성 구현 시 입력 검증으로 반영) |
| 회귀 검증 책임 | `KEY-153`("미확정 OCR 사용 차단") |

### 게이트 B — 승인 전 비노출 게이트

> **규칙**: 환자용 조회 API는 `guide_document.status == SCHEDULED_TO_SEND`인 건만 반환한다. `STAFF_REVIEW` · `APPROVAL_PENDING` · `APPROVAL_RETURNED` 상태의 안내와 원본 의료문서·미확정 OCR 결과는 어떤 환자 API도 반환하지 않는다.

| 항목 | 상태 |
|---|---|
| 상태값 자체 | **구현완료** — `GuideStatus` 4종, 승인 시 `SCHEDULED_TO_SEND`로 전환 |
| 병원측 조회에서 상태 노출 | **구현완료** — `GET /visits/{id}/guide` 응답에 `status` 포함 |
| 환자용 조회 API의 게이트 적용 | **미구현** — 환자 API 자체가 없다 |
| 계약상 원칙 | `docs/api/common.md` §3 "승인 전 안내, 미확정 OCR 결과와 원본 의료문서는 환자 API에 제공하지 않는다" |
| 강제 책임 | `KEY-151`(환자용 안내 조회 API 구현 시 서버 쿼리 조건으로 반영) |
| 회귀 검증 책임 | `KEY-153`("승인 전 환자 안내 조회를 차단") |

### 게이트 C — 병원 간 격리 게이트

타 병원 리소스는 `403`이 아니라 `404`로 감춘다(`docs/api/common.md` §3). **구현완료** — `KEY-153`이 회귀로만 검증한다.

---

## 4. 여정 9단계 — 화면 → API → DB → 다음 단계

| # | 단계 | 화면 | API | 입력 ID | 출력 ID / DB 행 | 생성 주체 | 다음 단계가 읽는 것 | 상태 | 담당 일감 |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 병원 로그인 | `login.html` | `POST /api/v1/auth/login` | `login_id`, `password` | 액세스 토큰 + Redis `idle:{refresh_token_id}` | 서버(인증) | 이후 모든 API의 `Staff.hospital_id`·`roles` | **구현완료** | — |
| 2 | 환자·진료 등록 | `patients.html` | `POST /patients`, `POST /patients/{patient_id}/visits` | (신규 생성) | `patient_id`, `visit_id` | 스탭/의사 | 이후 모든 단계의 FK | **구현완료** | — |
| 3 | 문서 업로드 | `patients.html`(upload) | `POST /front-desk/visits/{visit_id}/documents` | `visit_id` | `document_id`(`medical_document`) | 스탭 | 4단계 소유권 검증 대상 | **구현완료** | — |
| 4 | OCR 작업 생성 | `patients.html`(upload) | `POST /documents/{document_id}/ocr` | `document_id`, `visit_id` | `ocr_job_id`(`PROCESSING`) | 스탭 | 판독을 끝낼 워커 | **확인 필요** — 작업 생성은 구현완료, 완료 처리자 없음(§6) | `KEY-149` |
| 4' | OCR 수정·확정 | `ocr-review.html` | `GET /ocr/jobs/{ocr_job_id}`, `/fields`, `/result`, `PATCH /ocr/fields/{ocr_field_id}` | `ocr_job_id`, `ocr_field_id` | `ocr_field.corrected_value`, `is_confirmed`(`confirm: bool` 플래그) | 스탭/의사 | 5단계 안내 생성 입력(게이트 A) | 코드 **구현완료** / 입력 데이터 **확인 필요** | `KEY-149` |
| 5 | 안내 생성 | — | 없음 | `visit_id`, 확정 `ocr_field` 값들 | `guide_document_id`, `guide_section` | (설계상 서버) | 6단계 검토·승인 대상 | **미구현**(§6) | `KEY-150` |
| 6 | 의사 승인·반려 | `doctor.html` | `POST /visits/{visit_id}/guide/approve`, `/return` | `visit_id` | `guide_document.status→SCHEDULED_TO_SEND`, `guide_event` | 의사 | 7단계 발송 대상(게이트 B) | **구현완료** — 입력 행이 있으면 정상 동작 | — |
| 7 | 환자 링크·OTP 발급/조회 | `guide.html` | 없음 | `guide_document_id` | (설계) 링크 토큰, `patient_session` | (설계) | 8단계 인증 컨텍스트 | **미구현** | `KEY-90` |
| 8 | D+7 복약·통증 응답 | `checkin.html` | 없음 | (설계) `check_in_id` | (설계) `checkin_response.guide_document_id` | 환자 | 9단계 | **미구현** | `KEY-151` |
| 9 | 병원에서 D+7 확인 | — | 없음 | `visit_id` | — (조회만) | 스탭/의사 | — | **미구현** | `KEY-99` |

`api.js`·`patients-api.js`·`ocr-api.js`·`doctor-api.js`·`guide-api.js`·`checkin-api.js`는 각각 `?mock=1` 경로를 갖고 있다(`docs/qa/KEY-148-walking-skeleton.md` §3). 이 표는 `?mock=1`이 아닌 실제 서버 호출 기준이다.

---

## 5. 데이터별 생성 주체·목적·저장 위치

| 데이터 | 생성 주체 | 목적 | 저장 위치 | 상태 |
|---|---|---|---|---|
| `patient` | 스탭/의사 | 환자 신원 | MySQL `patient` | 구현완료 |
| `visit` | 스탭/의사 | 진료 한 건 | MySQL `visit` | 구현완료 |
| `medical_document` | 스탭 업로드 | OCR 원본 임시 보관 | MySQL `medical_document` + `LocalFileStorage` | 구현완료 |
| `ocr_job` / `ocr_job_document` | 스탭 | OCR 실행 단위 | MySQL `ocr_job`, `ocr_job_document` | 생성 구현완료 / 완료 처리 미구현 |
| `ocr_result` / `ocr_field` / `ocr_field_candidate` | 설계상 AI worker 또는 `KEY-149` fixture | 판독 예측·수정·확정값 | MySQL `ocr_result`, `ocr_field`, `ocr_field_candidate` | 확인 필요 |
| `ocr_document_text.raw_text` | 설계상 AI worker | 판독용 전체 텍스트 | MySQL `ocr_document_text` | 확인 필요 — 파기 호출부 미연결 |
| `guide_document` / `guide_section` | 설계상 `KEY-150` | 환자에게 나갈 안내문 4갈래 | MySQL `guide_document`, `guide_section` | 미구현 |
| `guide_event` | 승인/반려/수정 시 서비스가 같은 트랜잭션에서 기록 | 감사 이력 | MySQL `guide_event` | 구현완료 |
| 환자 링크·OTP·세션 | 설계상 `KEY-90` | 환자 인증 | (없음) | 미구현 |
| D+7 응답 | 설계상 `KEY-151` | 복약·통증 확인 | (없음) | 미구현 |

---

## 6. 미구현 구간 상세

### 6-1. OCR 작업 완료 처리

`POST /api/v1/documents/{document_id}/ocr`(`app/ocr/api.py`)는 `TortoiseDocumentOwnershipVerifier`로 `medical_document` 소유권을 검증하고 `ocr_job` 행을 `PROCESSING` 상태로 만든다. 이 작업을 `COMPLETED`로 옮기고 `ocr_result`·`ocr_field`를 채우는 코드는 `ai_worker/tasks/`가 비어 있어 존재하지 않는다. API로 작업을 만들면 그 행은 `PROCESSING`에 머문다. `PATCH /ocr/fields/{id}`는 코드상 동작하지만 `ocr_field` 행 자체가 없으면 호출할 대상이 없다.

### 6-2. 안내 생성

`app/services/guides.py`의 `GuideService`는 `get`·`edit_section`·`approve`·`return_to_staff`만 갖는다. `guide_document`·`guide_section` 행을 만드는 메서드가 없다. `GuideDocument.create(...)` 호출은 테스트 셋업(`app/tests/guide_apis/test_guide_approval.py`) 안에만 있고, `scripts/`나 `app/tests/fixtures/`에는 재사용 가능한 생성 경로가 없다. 6단계(승인)는 코드로는 정상 동작하지만, 그 앞에 놓일 행을 만드는 정식 경로가 아직 없다.

### 6-3. 환자 링크·OTP·D+7

`app/apis/v1/__init__.py`에 등록된 라우터는 `health·staff_auth·user·patient·visit·document·ocr·guide` 여덟 개뿐이다. 환자 링크·OTP·세션·D+7 응답을 다루는 모델·라우터는 저장소에 없다.

---

## 7. 저장하지 않을 원본·토큰·불필요한 대화 정보

| 무엇 | 원칙 | 코드 근거 | 상태 |
|---|---|---|---|
| 의료문서 원본 파일 | 승인·발송 뒤 삭제 대상 | `docs/project_workflow.md` §2 | 삭제 트랜잭션 미연결 |
| OCR 원문 텍스트(`ocr_document_text.raw_text`) | 확정 뒤 파기 | `OcrDocumentText.purge_raw_text()`(`app/models/ocr.py`) | 메서드는 있으나 승인 트랜잭션과 미연결(`KEY-59`) |
| 리프레시 토큰 | 응답 본문에 넣지 않고 `HttpOnly` 쿠키로만 | `docs/api/hospital.md` §2 | 구현완료 |
| 환자 링크·OTP 토큰 원문 | 쿼리스트링·로그·커밋에 남기지 않음 | `docs/api/common.md` §3 | 대상 기능 자체 미구현 |
| 챗봇 대화 원문 | 조회·다운로드 기능 제공 안 함, 예외 추출만 `event_log.action=chat_export`로 감사 | `docs/api/hospital.md` §9 | 원칙 확정, 챗봇 자체가 별도 범위(`KEY-2`) |
| 환자 이용 이벤트 | 질문 갈래·응답 결과·근거 섹션만 남기고 **원문 칸을 두지 않음**. 돌려주는 API도 없음 | `PatientUsageEvent`(`app/models/visits.py`), `docs/api/patient.md` §2.4 | 구현완료(`KEY-170`) — 챗봇 호출 지점은 `KEY-95`·`KEY-96` 대기 |
| 승인 전 안내·미확정 OCR | 환자 API에 제공 금지 (게이트 B) | `docs/api/common.md` §3 | 대상 API 미구현 |

---

## 8. 구현완료·미구현·확인필요 종합 — 후속 일감 연결

| # | 구간 | 분류 | 확인·구현 책임 |
|---|---|---|---|
| 1 | 병원 로그인·환자/진료·문서 업로드 | **구현완료** | — |
| 2 | OCR 작업 완료 처리(AI worker 또는 fixture) | **확인 필요** | `KEY-149` |
| 3 | OCR 필드 수정·확정(행이 있다는 전제) | **확인 필요** | `KEY-149` |
| 4 | OCR 원문 파기·승인 트랜잭션 연결 | **미구현** | `KEY-59`(선행), 승인 흐름은 `KEY-150`/`KEY-111` 후속 |
| 5 | 안내 생성(고정 템플릿) | **미구현** | `KEY-150` |
| 6 | 의사 승인·반려 | **구현완료** | — |
| 7 | 환자 링크·OTP·세션 | **미구현** | `KEY-90` |
| 8 | D+7 응답 제출 | **미구현** | `KEY-151` |
| 9 | 병원측 D+7 조회 | **미구현** | `KEY-99` |
| 10 | 게이트 A·B 실제 강제 코드 | **미구현** | `KEY-150`(A), `KEY-151`(B) |
| 11 | RBAC·격리·게이트 회귀 테스트 | 착수 전 | `KEY-153` |

### `KEY-152` E2E 검증 지점

`KEY-152`(전체 여정 원클릭 E2E)는 `KEY-149`·`KEY-150`·`KEY-151`·`KEY-99`가 모두 연결된 뒤 실행하는 것이 선행 조건이다. 이 문서 기준으로 그 실행이 통과하려면 아래가 먼저 채워져야 한다.

1. 4단계 — OCR 작업이 `PROCESSING`에서 실제로 벗어나는 경로 (`KEY-149`)
2. 5단계 — `guide_document`를 만드는 최소 한 가지 경로 (`KEY-150`)
3. 7·8단계 — 환자 링크 발급과 D+7 제출 엔드포인트 (`KEY-90`, `KEY-151`)
4. 9단계 — 병원 화면에서 같은 `visit_id`로 D+7 응답 조회 (`KEY-99`)
5. 게이트 A·B가 최소 한 번은 "차단 동작"으로도 검증됨 (`KEY-153`과 결과를 서로 참조하며 중복 구현하지 않는다)

---

## 9. 리뷰 체크리스트

- [ ] 4장 흐름표의 입력·출력 ID가 실제 모델 FK와 일치하는가
- [ ] 3장 게이트 A·B의 규칙 문장이 팀이 합의한 안전 요건과 같은가
- [ ] `KEY-149`~`KEY-153`에 이 문서의 담당 일감 연결이 실제로 반영됐는가 (Jira 쪽 업데이트는 별도 작업)
- [ ] 실제 환자정보 없이(`SYN-EMS-01` 합성값만으로) 문서를 이해할 수 있는가

---

## 10. 참고

- 시나리오 정본: [`docs/qa/KEY-148-walking-skeleton.md`](qa/KEY-148-walking-skeleton.md)
- API 계약: [`docs/api/README.md`](api/README.md), [`docs/api/common.md`](api/common.md), [`docs/api/hospital.md`](api/hospital.md), [`docs/api/patient.md`](api/patient.md)
- 모델 배치: [`docs/models-layout.md`](models-layout.md)
