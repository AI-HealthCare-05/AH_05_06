# 환자·진료 API 계약 v1 동결 후보

> KEY-12 · 하위 KEY-26 · 구현 후속 KEY-31
> 상태: `v1.0-rc1` — 한금준 최종 검수와 PR 승인 시 `v1.0-frozen`으로 전환
> 기준일: 2026-08-19

이 문서는 새 API 범위를 제안하는 문서가 아니다. 기존 환자 관리 API 문서, ERD v11, 요구사항, 정본 와이어프레임 사이의 충돌을 해소하고 KEY-31 구현이 따라야 할 이름과 관계를 고정한다.

## 1. 검수 근거와 우선순위

충돌 시 아래 순서로 판단한다.

1. 이슈 #19·#20의 인수조건과 확정 댓글
2. Notion `API 명세서` 내보내기와 저장소 정본 `docs/wireframes/wireframe-medic-2.3.1.html`, `wireframe-patient-2.3.1.html`
3. ERD v11 테이블·컬럼 정의서와 테이블별 상세 설명
4. 기존 `5일차 환자 관리 및 진료기록 API 설계`
5. 현재 코드 골격

검수에 사용한 외부 파일은 수정하지 않았으며 SHA-256으로 식별한다.

| 자료 | SHA-256 | 판정 |
|---|---|---|
| `5일차_환자관리_API_설계.md` | `66704F3690B65160C2ED09304C6BEDFE5E1641885948BC94D71B87C2A56BD190` | 기존 API 계약 |
| `ERD_v11_테이블별_상세설명.md` | `DA033DC04FCEAF25D86F1A2AF121C674B88F9F1363F1A539DEECCFA66A148605` | 최신 관계·업무 규칙 |
| `ERD_v11_테이블_컬럼_정의서_MySQL.md` | `483B95355ABF8DC225B0F0B5111F7F860074B6C25BA478E19554ADA0467436C0` | 최신 필드·인덱스 |
| Notion `API 명세서` HTML/CSV 내보내기 | `D09A80DA11178C2D3784C2BD78EAA1696D34DF147600FDC8F59BEA35506A46EF` | 사용자 제공 원본 링크의 2026-08-19 내보내기. 91개 API와 상세 요청·응답을 대조 |
| `API명세서 Template.xlsx` | `63A5C531333E64432ED8ADB786B81F6C43EA82F410A43171E5EA9D851405F19A` | 다른 프로젝트 회원가입 예시 1행뿐인 스텁으로 판정, 동결 근거에서 제외 |

Notion 원본은 [API 명세서](https://app.notion.com/p/API-da8e237b905d829d902b8111d01120a1?source=copy_link)다. 브라우저 연결 대신 사용자가 직접 내보내 첨부한 HTML/CSV를 읽었으며, 위 해시는 이번 대조에 사용한 정확한 내보내기 파일을 식별한다.

## 2. 동결 결정

| 항목 | v1 결정 | 근거 |
|---|---|---|
| 환자 PK | `patient_id: bigint` | ERD v11 및 현재 `User` PK와 정합 |
| 진료 PK | `visit_id: bigint` | ERD v11 |
| 병원 범위 | `hospital_id: bigint`, 클라이언트 입력 금지 | 모든 접근에서 로그인 직원의 병원으로 서버가 결정 |
| 차트번호 | `hospital_patient_no`, `(hospital_id, hospital_patient_no)` 유일 | S1-2·S1-3, ERD v11 |
| 환자 나이 | 저장하지 않고 `birth_date`로 계산 | 본인확인 및 시간이 지나면 변하는 `age` 제거 |
| 성별 | `gender`를 PATIENT에 추가, `FEMALE/MALE/OTHER/UNKNOWN`, 기본 `UNKNOWN` | Notion S2-1 응답에는 네 값이 있으나 ERD v11에서 누락됨. 합성 데이터는 `FEMALE`을 명시 |
| 진료 리소스명 | `visits` | 환자 1:N 진료 관계와 OCR·안내·발송 연결 기준 |
| 환자 삭제 | v1 API에서 제공하지 않음 | S2-1의 “의료 기록은 삭제하지 않습니다” |
| 진행 상태 | Patient/Visit에 별도 업무 진행 상태를 저장하지 않음 | `EVENT_LOG` 최신 이벤트에서 파생. 단 `visit.status`는 방문 자체의 `SCHEDULED/COMPLETED/CANCELED`만 표현 |
| 계획 중단 | `visit.planned_stop: boolean`, 기본 `false` | 의사가 계획적으로 처방을 중단한 경우 확인·소진·재진 알림 및 이탈 판정에서 제외 |
| 역할 | `roles jsonb`의 `staff`, `doctor`, `admin` 중 하나 이상, 중복 허용 | KEY-9 확정 |
| `staff.is_owner` | 컬럼 유지, v1 권한 판정에서는 사용하지 않음 | KEY-11 확정 |
| `event_log.action=chat_export` | 값 유지 | KEY-9·KEY-11 결정사항. 앱의 대화 원문 조회·내려받기는 제공하지 않으며, 예외적 운영 추출은 승인된 감사 절차를 통해 이 값을 기록해야 함 |

## 3. 데이터 관계

```text
HOSPITAL 1 ── N PATIENT 1 ── N VISIT
    │               │              ├── N MEDICAL_DOCUMENT / OCR_JOB
    │               │              ├── N PRESCRIPTION / LAB_RESULT
    │               │              └── N GUIDE_DOCUMENT ── N CHECKIN
    └── N STAFF_USER ───────────────┘ doctor_id
```

- `patient_id`는 사람을 식별한다.
- `visit_id`는 그 환자의 한 진료 건을 식별하며 OCR·안내 생성의 직접 연결 키다.
- 발송과 D+7 응답은 `guide_document_id`를 직접 사용하되 `GUIDE_DOCUMENT.visit_id`를 통해 진료로 추적할 수 있어야 한다.
- 환자 본인확인에는 `hospital_patient_no`, `name`, `birth_date`, `phone`을 사용한다. 외부 응답에는 목적에 필요한 최소값만 노출한다.
- URL의 `patient_id` 또는 `visit_id`와 요청 본문에 같은 ID를 중복해서 받지 않는다.

## 4. 모델 필드

### PATIENT

| API 필드 | DB 필드 | 타입 | 필수 | 규칙 |
|---|---|---|---:|---|
| `patient_id` | `patient_id` | bigint | 응답 | PK |
| — | `hospital_id` | bigint | 서버 | 로그인 직원의 병원, 요청 본문에서 거부 |
| `hospital_patient_no` | `hospital_patient_no` | string(50) | 요청 | 병원 내 유일, 생성 후 변경 불가 |
| `name` | `name` | string(50) | 요청 | trim 후 1~50자, 한 글자 검색 허용 |
| `birth_date` | `birth_date` | date | 요청 | 나이 및 본인확인 원천 |
| `gender` | `gender` | `FEMALE/MALE/OTHER/UNKNOWN` | 선택 | 미입력은 `UNKNOWN`. 합성 산부인과 데이터는 `FEMALE`을 명시 |
| `phone` | `phone` | string(20) | 요청 | 숫자로 정규화, 검색·발송·재발급에 사용 |
| `sms_consent` | `sms_consent` | boolean | 요청 | 발송 전제 조건 |
| `sms_consented_at` | `sms_consented_at` | datetime | 응답 | 동의 시 서버 기록 |
| `sms_opted_out_at` | `sms_opted_out_at` | datetime | 응답 | 거부 시 서버 기록 |
| — | `sms_consent_updated_by` | bigint | 서버 | 로그인 직원 ID |
| `created_at` | `created_at` | datetime | 응답 | UTC 저장, ISO 8601 응답 |
| `updated_at` | `updated_at` | datetime | 응답 | UTC 저장, ISO 8601 응답 |

`age`는 API·DB 필드가 아니다. 응답의 `age`가 필요한 화면에서는 `birth_date`와 조회 기준일로 서버가 계산한 읽기 전용 값을 제공할 수 있다.

### VISIT

| API 필드 | DB 필드 | 타입 | 필수 | 규칙 |
|---|---|---|---:|---|
| `visit_id` | `visit_id` | bigint | 응답 | PK |
| — | `hospital_id` | bigint | 서버 | 환자 병원과 로그인 직원 병원이 모두 같아야 함 |
| `patient_id` | `patient_id` | bigint | 경로/응답 | POST에서는 경로로만 입력 |
| `doctor_id` | `doctor_id` | bigint/null | 요청 | 같은 병원, `doctor` 역할 보유자만 |
| `department` | `department` | string(100)/null | 요청 | 진료 당시 스냅샷 |
| `visited_at` | `visited_at` | datetime | 요청 | 오늘 진료와 시간순 이력의 정렬 기준 |
| `visit_summary` | `visit_summary` | string/null | 요청·응답 | 환자용 승인 안내와 분리된 진료 요약 원천 |
| `doctor_note` | `doctor_note` | string/null | 요청·응답 | 승인 데이터 생성의 선택 입력, 환자 API에는 원문 노출 금지 |
| `status` | `status` | `SCHEDULED/COMPLETED/CANCELED` | 요청·응답 | 방문 자체 상태만 표현 |
| `planned_stop` | `planned_stop` | boolean | 요청·응답 | `true`이면 확인·소진·재진 문자와 이탈 판정을 중단 |
| `created_at` | `created_at` | datetime | 응답 | UTC 저장 |
| `updated_at` | `updated_at` | datetime | 응답 | UTC 저장 |

동일 병원·환자·진료일의 중복 등록은 서비스 계층에서 `409 VISIT_ALREADY_REGISTERED`로 막는다.

## 5. 엔드포인트

| Method | Path | 용도 | 권한 |
|---|---|---|---|
| POST | `/api/v1/patients` | 신규 환자 생성 | `patient:write` |
| GET | `/api/v1/patients` | 이름·차트·전화 검색, 관리 목록, 오늘 진료 필터 | `patient:read` |
| GET | `/api/v1/patients/{patient_id}` | 환자 카드 기본정보 | `patient:read` |
| PATCH | `/api/v1/patients/{patient_id}` | 차트번호를 제외한 환자정보 수정 | `patient:write` |
| POST | `/api/v1/patients/{patient_id}/visits` | 환자에 진료 건 추가 | `patient:write` |
| GET | `/api/v1/patients/{patient_id}/visits` | 지난 방문 시간순 조회 | `patient:read` |
| GET | `/api/v1/visits/{visit_id}` | 진료 건 상세 및 후속 기능 연결 | `patient:read` |
| PATCH | `/api/v1/visits/{visit_id}` | 진료 기본정보 수정 | `patient:write` |

`patient:read`와 `patient:write`는 `staff` 또는 `doctor` 역할이 연다. `admin`만 가진 사용자는 진료 데이터에 접근할 수 없다.

Notion의 화면 조합 API(`/front-desk/visits`, `/front-desk/patients/search`, `/front-desk/visits/{visit_id}/patient-card`, `/patients/{patient_id}/care-summary`, `/patients/{patient_id}/care-history`)는 삭제하지 않는다. 이 API들은 위 여덟 리소스 계약과 후속 도메인의 구조화된 읽기 모델을 조합한다. 단, 중복된 `PATCH /front-desk/patients/{patient_id}`는 `PATCH /patients/{patient_id}`로 통합한다.

모든 단건 조회·수정은 다음 순서로 검증한다.

1. 리소스를 로그인 직원의 `hospital_id`와 함께 조회한다.
2. 없거나 타 병원 소유이면 모두 `404`를 반환한다.
3. Visit 경로에서는 `visit.hospital_id == visit.patient.hospital_id`도 확인한다.
4. 수정 권한은 역할 검사 후 적용한다.

타 병원 리소스에 `403`을 반환하지 않는다. 존재 여부를 감추기 위해 없는 리소스와 같은 `404`를 사용한다.

## 6. 요청·응답 핵심 계약

### 환자 생성

```json
{
  "hospital_patient_no": "12501",
  "name": "조은비",
  "birth_date": "1994-07-22",
  "gender": "FEMALE",
  "phone": "01039457702",
  "sms_consent": true
}
```

`hospital_id`, `patient_id`, `age`, `sms_consent_updated_by`를 본문에 보내면 `400 INVALID_REQUEST`다.

### 환자 목록·검색

```text
GET /api/v1/patients?category=NEEDS_ATTENTION&keyword=김&cursor=patient_102&limit=20
```

- `category`: `ALL/IN_TREATMENT/NEEDS_ATTENTION/SMS_OPT_OUT/INACTIVE_6_MONTHS`, 기본 `ALL`.
- `keyword`: 이름, 차트번호, 정규화된 휴대폰에서 검색한다. 이름은 한 글자부터 허용한다.
- `cursor`: 서버가 발급한 불투명 다음 페이지 커서. 임의 조립하지 않는다.
- `limit` 기본 20, 최대 100.
- 응답은 `{counts, selected_category, items, page: {next_cursor, has_next}}`다.
- 목록 항목은 환자 기본정보와 `latest_visit` 요약을 포함한다. 동명이인 구분을 위해 생년월일, 차트번호, 전화번호 뒤 4자리, 최근 진료일을 모두 제공한다.
- S1 날짜별 업무 목록은 기존 `GET /front-desk/visits?date=YYYY-MM-DD`가 담당하며 `visit.visited_at`을 날짜로 묶고 업무 상태를 파생한다.

### 환자 수정

- 수정 가능: `name`, `birth_date`, `gender`, `phone`, `sms_consent`.
- 수정 불가: `patient_id`, `hospital_id`, `hospital_patient_no`, 생성·수정 메타데이터.
- 빈 본문은 `400 EMPTY_UPDATE_FIELDS`다.
- 전화번호 또는 동의 변경은 예정 발송에 반영하고 감사 이벤트를 남기는 서비스 계층 작업이다.

### 진료 생성

```json
{
  "doctor_id": 12,
  "department": "산부인과",
  "visited_at": "2026-08-13T10:32:00+09:00",
  "visit_summary": null,
  "doctor_note": null,
  "status": "COMPLETED",
  "planned_stop": false
}
```

`patient_id`, `hospital_id`, `visit_id`를 본문에 중복 입력하지 않는다.

### 진료 목록

```text
GET /api/v1/patients/{patient_id}/visits?cursor=visit_501&limit=20
```

- `visited_at DESC, visit_id DESC`로 안정 정렬한다.
- 응답은 `{items, page: {next_cursor, has_next}}`다.
- 안내·발송·D+7 요약은 각 도메인의 구조화된 요약만 결합하며 원문 의료문서나 챗봇 대화 원문을 포함하지 않는다.

### 진료 수정

- 수정 가능: `doctor_id`, `department`, `visited_at`, `visit_summary`, `doctor_note`, `status`, `planned_stop`.
- OCR 또는 승인 안내가 이미 연결된 뒤 식별 관계를 바꾸는 수정은 `409 visit_locked`다.
- `patient_id`, `hospital_id`, `visit_id`는 수정할 수 없다.

## 7. 오류 계약

모든 오류는 같은 모양을 사용한다.

```json
{
  "code": "PATIENT_NOT_FOUND",
  "message": "환자를 찾을 수 없습니다.",
  "field_errors": null
}
```

| HTTP | code | 조건 |
|---:|---|---|
| 401 | `UNAUTHORIZED` | 인증 없음·만료 |
| 403 | `FORBIDDEN` | `staff`·`doctor` 역할 없음 |
| 404 | `PATIENT_NOT_FOUND` | 환자 없음 또는 타 병원 환자 |
| 404 | `VISIT_NOT_FOUND` | 진료 없음 또는 타 병원 진료 |
| 409 | `DUPLICATE_HOSPITAL_PATIENT_NO` | 같은 병원 차트번호 중복 |
| 409 | `VISIT_ALREADY_REGISTERED` | 같은 환자의 같은 날짜 진료 중복 |
| 409 | `VISIT_LOCKED` | 후속 데이터 연결 뒤 관계 변경 시도 |
| 400 | `INVALID_REQUEST` | 필드 형식·enum·범위 오류 |
| 400 | `EMPTY_UPDATE_FIELDS` | PATCH 본문에 수정 가능 필드 없음 |

## 8. 화면 데이터 추적

| 화면 | 계약 필드 |
|---|---|
| S1-1 | `/front-desk/visits?date`, `visit_id/visited_at/doctor`, 이벤트에서 파생한 업무 상태 |
| S1-2 | `name`, `birth_date`, `phone`, `hospital_patient_no`, `latest_visit.visited_at` |
| S1-3 | 환자 생성 필드 + 생성 후 반환된 `patient_id` |
| S1-4 | 환자 상세 + 오늘 진료 + `GET /patients/{id}/visits` |
| S1-5~S1-14 | `visit_id`를 OCR·안내·발송 계약에 전달 |
| S2-1 | 환자 목록 + `latest_visit` + 구조화된 진행 상태 요약 |
| S2-2 | 진료 목록 + 발송·열람·체크인 구조화 요약 |
| S2-3·S2-4 | `patient_id`, `visit_id`, `guide_document_id`로 발송 추적 |
| P7-1~P7-6 | `check_in_id`를 경로로 사용하고 `CHECKIN.guide_document_id` → `GUIDE_DOCUMENT.visit_id/patient_id`로 추적 |

## 9. 기존 명세 불일치 처리

| 기존 값 | v1 처리 | 상태 |
|---|---|---|
| `age` 저장 | `birth_date` 저장, 나이 파생 | 수정 |
| 환자 `gender`는 API에 있으나 ERD에 없음 | ERD·모델에 `gender` 추가 | 수정 |
| Notion `gender=FEMALE/MALE/OTHER/UNKNOWN`, rc1은 두 값만 명시 | 네 값과 `UNKNOWN` 기본값으로 통일 | 수정 |
| `chart_number`가 MedicalRecord에 있고 전역 유일 | `patient.hospital_patient_no`, 병원 내 유일 | 수정 |
| Notion `chart_no` | 리소스 API는 `hospital_patient_no`; 화면 조합 응답도 같은 이름으로 수정 | 수정 |
| Notion `sms_consent_at` | `sms_consented_at`으로 수정 | 수정 |
| Notion `visit_date` | 저장·리소스 API는 `visited_at`; 화면 표시에서는 날짜를 파생 | 수정 |
| Notion `department_id`, ERD `department` | 화면 명령은 `department_id`를 받아 활성·의사 소속을 검증하고, VISIT에는 당시 명칭을 `department` 스냅샷으로 저장 | 매핑 확정 |
| Notion 화면 API의 `RECORD_MISSING` 등 업무 상태 | `visit.status`에 저장하지 않고 OCR·안내·발송 이벤트에서 파생 | 매핑 확정 |
| Notion offset/cursor 혼재, rc1 offset | 기존 명세의 cursor+limit로 통일 | 수정 |
| Notion 오류 코드 대문자·400, rc1 소문자·422 | 전체 기존 API 규칙에 맞춰 대문자 코드와 400 사용 | 수정 |
| Notion care-history의 UUID 예시, 다른 환자 API와 ERD는 integer | 환자·진료·안내 식별자는 bigint로 통일 | 수정 |
| `/medical-records` | `/visits`로 교체 | 수정 |
| 환자 DELETE와 cascade | v1에서 삭제 API 제거 | 수정 |
| `PENDING/STAFF/ADMIN` + department 권한 | `roles jsonb`의 staff/doctor/admin 매트릭스 | 수정 |
| 본문과 경로의 `patient_id` 중복 가능성 | 경로에서만 입력 | 수정 |
| 환자 목록 name/gender/age 필터 | `category`, `keyword`, cursor/limit로 통일 | 수정 |
| ERD `visit.status`와 이벤트 파생 상태 충돌 | 방문 상태만 저장, 업무 진행 상태는 이벤트 파생 | 구분 확정 |
| ERD v11의 `STAFF_USER_ROLE`·`HOSPITAL.super_admin_user_id` | v1에서는 `staff.roles jsonb`와 미사용 `is_owner` 유지 | 사용자 확정사항 우선 |

### 처방 계약 경계

처방을 VISIT의 JSON 필드로 추가하지 않는다. ERD v11의 `PRESCRIPTION(visit_id)` 1:N `PRESCRIPTION_ITEM(duration_days 포함)`이 실제 처방과 약·용법·처방일수를 소유한다. `PRESCRIPTION_SET_VERSION`은 템플릿 출처이고 `GUIDE_DOCUMENT.prescription_id/prescription_set_version_id`가 승인 스냅샷을 연결한다. KEY-26/31은 이 테이블의 상세 구현 범위가 아니지만, 소진 예정일과 D+7 판정은 확정된 `PRESCRIPTION_ITEM.duration_days`만 사용한다.

### 별도 확인 항목

- Notion의 P7 상세는 `P7-1~P7-5`로 표기되어 있으나 정본 와이어프레임에는 저장 완료 `P7-6`이 있다. 구현·테스트 범위는 정본의 `P7-1~P7-6`으로 유지한다.
- `chat_export`는 사용자의 KEY-9·KEY-11 확정사항에 따라 유지한다. 통제되지 않은 DB 직접 조회는 애플리케이션이 자동 기록할 수 없으므로, 운영 추출은 별도 승인 도구/절차가 `event_log`를 남기는 경우만 허용한다.

## 10. 동결 절차와 변경 규칙

- 한금준이 전체 API 규칙, 공통 오류 모양, ID 타입, 페이지네이션을 검수한다.
- 승인 전 상태는 `v1.0-rc1`이며 KEY-31은 필드명·관계를 이 문서와 다르게 구현하지 않는다.
- 승인 시 이 문서의 상태를 `v1.0-frozen`으로 바꾸고 승인자·승인일을 기록한다.
- 동결 뒤 변경은 같은 PR에서 이 문서, 관련 모델·마이그레이션, 화면 영향 ID를 함께 수정한다.
- OCR·안내·챗봇 상세 본문은 이 계약의 범위 밖이며 `patient_id`, `visit_id` 연결 규칙만 공유한다.
