# Mock 계약 대조 범위

기준 정본은 `docs/api/openapi.json`에 생성된 서버 Pydantic DTO다. 브라우저 mock은
로컬 화면 확인용이며 서버보다 성공 조건이 느슨하거나 다른 응답 필드를 만들 수 없다.

## 자동 대조 대상

- 직원 로그인: `POST /api/v1/auth/login`
- OCR 필드 수정·확정: `PATCH /api/v1/ocr/fields/{field_id}`
- 안내 제출·승인: `POST /api/v1/visits/{visit_id}/guide/submit`, `/approve`
- 환자 링크 발급: `POST /api/v1/visits/{visit_id}/guide/link`
- OTP 발급·검증: `POST /api/v1/patient-auth/otp/issue`, `/verify`
- 환자 안내 조회: `GET /api/v1/guides/{token}`

`frontend/tests/key232-mock-contract.test.js`가 mock 응답의 필수 필드, 타입, enum을
OpenAPI와 직접 대조한다. `additionalProperties: false`인 DTO는 추가 필드도 금지하고,
그 설정이 없는 직원 로그인·내 정보 응답은 OpenAPI의 필드 목록과 정확히 같은지
별도로 검사한다. 서버 계약이 바뀌고 기준선을 갱신하면 mock이 함께 바뀌지 않은
경우 이 검사가 실패한다.

## 자동 대조 밖의 mock

아래 기능도 mock을 사용하지만 KEY-232의 확정 범위 밖이므로 차이만 기록한다.

- 환자·진료 목록/상세: 화면 상태 시연을 위한 합성 날짜와 이력 항목이 추가된다.
- 처방 세트·검사 기준선·문구 설정: 브라우저 메모리에만 저장되며 서버 영속성과 트랜잭션을 흉내 내지 않는다.
- 문자 발송 예정/이력: 실제 발송기와 재시도 작업 없이 합성 상태만 제공한다.
- 챗봇: 완성 응답을 짧은 조각으로 나눠 스트리밍 UI만 검증한다.
- D+7 신호: 브라우저 메모리에서 순서·정정 규칙을 검증하며 다중 프로세스 동시성은 흉내 내지 않는다.

이 목록의 mock도 배포/Pilot에서는 활성화되지 않는다. 서버 DTO 결함으로 보이는
차이는 mock에서 우회하지 않고 KEY-217 계약 변경으로 먼저 제기한다.
