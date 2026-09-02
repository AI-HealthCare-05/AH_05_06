# 환자 피드백 API v1 (KEY-239)

P6 챗봇 답변 평가와 P9 안내 오류 신고를 한 저장 계약으로 받고, 관리자에게는
로그인한 병원 범위의 목록과 상세만 제공한다. 환자에게 의료 답변을 회신하거나
피드백 처리 상태를 변경하는 기능은 이 계약에 포함하지 않는다.

## POST `/api/v1/patient-feedback`

- 인증: `patient_session` HttpOnly 쿠키
- 링크 토큰·OTP·환자 세션 원문은 요청 본문으로 받지 않는다.
- `submission_id`는 클라이언트가 만든 UUID다. 네트워크 재시도는 같은 UUID를
  다시 보내며, 서버는 같은 내용이면 기존 행을 반환하고 내용이 달라지면
  `409 FEEDBACK_SUBMISSION_CONFLICT`로 차단한다.

### P6 챗봇 답변 평가

```json
{
  "submission_id": "00000000-0000-4000-8000-000000000239",
  "target": "CHATBOT_RESPONSE",
  "source_screen": "P6",
  "category": "HELPFUL",
  "response_ref": "일회성-응답-참조값"
}
```

`response_ref`는 챗봇 응답에서 한 번 전달되며 서버에는 SHA-256 digest만
저장된다. 환자 세션이 가리키는 안내의 답변 이벤트만 선택할 수 있다.

### P9 안내 오류 신고

```json
{
  "submission_id": "00000000-0000-4000-8000-000000000240",
  "target": "GUIDE_SECTION",
  "source_screen": "P9",
  "category": "WRONG",
  "section_key": "medication",
  "content_key": "medication.why",
  "detected_tab": "복약지도",
  "details": "합성 안내 피드백"
}
```

`details`는 선택값이며 최대 1,000자다. 서버는 승인 완료 안내의 실제 섹션인지
확인한다.
`section_key`는 서버에서 현재 승인 안내에 실제로 존재하는 섹션인지 검증한다.
`content_key`와 `detected_tab`은 오류 위치를 재현하기 위한 클라이언트 참고
메타데이터이며, 서버의 권한·리소스 소유권 판정에는 사용하지 않는다.
두 필드는 길이와 형식만 검증한다.

### 성공 응답

`201 Created`

```json
{ "feedback_id": 239, "saved": true }
```

### 오류

| HTTP | code | 조건 |
|---|---|---|
| 400 | `INVALID_REQUEST` | 필드 누락·허용하지 않은 필드·형식 오류 |
| 401 | `PATIENT_SESSION_EXPIRED` | 환자 세션 없음 또는 만료 |
| 404 | `FEEDBACK_CONTEXT_NOT_FOUND` | 승인 안내·섹션·챗봇 응답 범위 불일치 |
| 409 | `FEEDBACK_SUBMISSION_CONFLICT` | 같은 제출 ID를 다른 내용에 재사용 |

## GET `/api/v1/admin/patient-feedback`

- 인증: 스탭 Access Token
- 권한: `admin` 역할이 여는 기존 `AUDIT_READ` 권한
- 병원 범위: 토큰의 직원 병원 ID로 서버가 강제
- 쿼리: `page`(기본 1), `page_size`(기본 20, 최대 100), `target`, `category`
- 목록에는 자유 입력 원문 대신 `has_details`만 제공한다.

```json
{
  "items": [
    {
      "feedback_id": 239,
      "visit_id": 120,
      "target": "GUIDE_SECTION",
      "source_screen": "P9",
      "category": "WRONG",
      "has_details": true,
      "created_at": "2026-09-02T10:00:00+09:00"
    }
  ],
  "page": 1,
  "page_size": 20,
  "total": 1
}
```

## GET `/api/v1/admin/patient-feedback/{feedback_id}`

관리자 목록과 같은 인증·권한·병원 범위를 적용한다. 다른 병원의 ID와 없는 ID는
모두 `404 PATIENT_FEEDBACK_NOT_FOUND`로 응답한다.

상세 응답은 목록 필드에 `section_key`, `content_key`, `detected_tab`, `details`를
추가한다. 링크 토큰·OTP·환자 세션·제출 ID digest·챗봇 응답 참조 digest는
응답하지 않는다.
