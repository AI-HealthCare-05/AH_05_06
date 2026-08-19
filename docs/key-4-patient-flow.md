# KEY-4 환자 이용 흐름

관련 이슈: [#15](https://github.com/AI-HealthCare-05/AH_05_06/issues/15)

## 흐름

1. 병원 사용자가 승인 완료된 `care_episode_id`로 링크를 즉시 또는 예약 발급한다.
2. 발송 시각부터 72시간 동안 링크가 유효하며, 토큰은 URL fragment에만 담긴다.
3. 환자는 3분 동안 유효한 6자리 OTP로 본인 확인을 하고 30분 세션을 받는다.
4. 환자는 승인된 처방·복약·주의·생활관리 정보와 근거가 표시되는 챗봇만 이용한다.
5. 상태 탭(P5)은 승인된 복약 기간을 기준으로 현재 복약 진행률과 남은 기간을 조회한다.
6. D+7 전용 링크(P7)에서는 복약 상태 선택 즉시 P7-2~P7-5 안내를 펼치고, 중단 선택은 저장 전에도 병원에 구조화 알림을 생성한다. 통증 여부·정도·유형은 마지막 단계에서 한 번 제출한다.

## API 경계

- 병원 인증 필요: `POST /api/v1/patient-links`, `POST /api/v1/patient-links/dispatch-due`, `POST /api/v1/patient-links/{id}/revoke`, `GET /api/v1/patient-links/{id}/follow-up`, `GET /api/v1/patient-links/{id}/follow-up-alerts`
- 환자 링크 인증: `POST /api/v1/patient/auth/link`, `POST /api/v1/patient/auth/otp`, `POST /api/v1/patient/auth/verify`, `POST /api/v1/patient/auth/reissue`
- 환자 세션 필요: `GET /api/v1/patient/guidance`, `GET /api/v1/patient/medication-status`, `POST /api/v1/patient/chat/stream`, `POST /api/v1/patient/follow-up/adherence-selection`, `GET|POST /api/v1/patient/follow-up`

`PATIENT_PUBLIC_URL`은 환자에게 전달할 공개 URL로 설정한다. 환자 세션은 `HttpOnly`, `SameSite=Strict` 쿠키이고 운영 환경에서는 `Secure`가 적용된다.

## 데이터 안전 규칙

- `ApprovedGuidanceBundle`은 `status=approved`만 허용하고 정의되지 않은 필드를 거부한다.
- 원문 의료문서, OCR 결과, 초안 필드는 환자 계약과 응답에 포함하지 않는다.
- 챗봇 검색 대상은 번들 안의 승인된 `knowledge`뿐이며 각 답변에 근거와 한계를 반환한다.
- 챗봇 질문과 답변 원문은 저장하지 않는다. 병원 API에도 대화 원문 조회 기능이 없다.
- 병원은 D+7 구조화 응답만 조회할 수 있다.
- 링크·세션 토큰, OTP, 생년월일은 평문으로 저장하지 않는다. 발송 대기 중인 전화번호와 토큰은 암호화한다.
- 환자는 생년월일 `YYMMDD` 6자리를 그대로 전송한다. 세기 추론은 하지 않고 서버에 저장된 해시와만 비교한다.

## 운영 연결 지점

현재 `InMemoryApprovedGuidanceProvider`, `PatientFlowStore`, `InMemoryPatientMessageGateway`는 KEY-2 및 인프라 연동을 위한 경계 구현이다. 실제 운영 전에는 각각 KEY-2 승인 데이터 저장소, 영속 DB/Redis, SMS 발송사 어댑터로 교체하고 `dispatch-due`를 스케줄러에서 호출해야 한다. 여러 프로세스에서 동일한 실패 횟수·잠금·재발급 제한을 공유하도록 원자적 저장이 필요하다. 환자 정적 파일은 애플리케이션에서 마운트하지 않고 nginx가 제공한다.

화면 정본은 `docs/wireframes/wireframe-patient-2.3.1.html`이며 이번 구현은 화면 ID·문구·상태 범위를 변경하지 않는다.
