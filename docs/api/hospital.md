# 병원용 API

> 인증 주체: 병원 직원
> 상세 근거: [로그인·세션 계약](../auth-contract.md), [환자·진료 API v1](../contracts/patient-visit-api-v1.md), [OCR API 계약](../key-60-ocr-api.md)

## 1. 기능 범위

```text
직원 로그인
→ 환자·진료 등록 및 조회
→ 의료문서 업로드·OCR 확인·확정
→ 안내 생성·검토·승인
→ 환자 링크 발급
→ D+7 응답 조회
```

모든 API는 직원 역할과 병원 범위를 서버에서 검증한다. 공통 오류·민감정보 규칙은 [API 공통 규칙](common.md)을 따른다.

## 2. 직원 인증

| Method | Path | 용도 |
|---|---|---|
| `POST` | `/api/v1/auth/login` | 직원 로그인 |
| `GET` | `/api/v1/auth/me` | 현재 직원·권한 조회 |
| `POST` | `/api/v1/auth/refresh` | 직원 세션 갱신 |
| `POST` | `/api/v1/auth/logout` | 로그아웃 |
| `PATCH` | `/api/v1/auth/password` | 최초 로그인·비밀번호 변경 |

상세 요청·응답과 예외는 [로그인·세션 상세 계약](../auth-contract.md)을 따른다.

## 3. 환자·진료

| Method | Path | 용도 |
|---|---|---|
| `POST` | `/api/v1/patients` | 환자 생성 |
| `GET` | `/api/v1/patients` | 환자 목록·검색 |
| `GET` | `/api/v1/patients/{patient_id}` | 환자 상세 조회 |
| `PATCH` | `/api/v1/patients/{patient_id}` | 환자정보 수정 |
| `POST` | `/api/v1/patients/{patient_id}/visits` | 진료 생성 |
| `GET` | `/api/v1/patients/{patient_id}/visits` | 진료 이력 조회 |
| `GET` | `/api/v1/visits/{visit_id}` | 진료 상세 조회 |
| `PATCH` | `/api/v1/visits/{visit_id}` | 진료 수정 |
| `GET` | `/api/v1/front-desk/visits` | 날짜별 병원 업무 목록 |

필드, 페이지네이션, 권한과 오류 계약은 [환자·진료 API v1 상세 계약](../contracts/patient-visit-api-v1.md)을 따른다.

## 4. OCR

| Method | Path | 용도 |
|---|---|---|
| `POST` | `/api/v1/documents/{document_id}/ocr` | OCR 작업 생성 |
| `GET` | `/api/v1/ocr/jobs/{ocr_job_id}` | 처리 상태 조회 |
| `GET` | `/api/v1/ocr/jobs/{ocr_job_id}/result` | OCR 결과 조회 |
| `GET` | `/api/v1/ocr/jobs/{ocr_job_id}/fields` | 구조화 필드·후보 조회 |
| `PATCH` | `/api/v1/ocr/fields/{ocr_field_id}` | 필드 수정·확정 |

상세 계약과 현재 통합 제한은 [OCR API 구현 계약](../key-60-ocr-api.md)에 기록한다.

## 5. 아직 연결 중인 영역

아래 영역은 Jira 인수조건과 병합된 구현을 기준으로 엔드포인트·DTO가 확정될 때 이 문서에 추가한다.

- 의료문서 업로드·임시 저장
- 안내 생성·승인·반려
- 환자 링크 발급 관리
- D+7 응답 병원 조회
- 관리자·감사로그

확정되지 않은 경로와 필드를 문서에서 먼저 만들어 구현 범위를 넓히지 않는다.
