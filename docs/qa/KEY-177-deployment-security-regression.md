# KEY-177 배포 환경 보안 회귀 설계

> Jira: https://leehee.atlassian.net/browse/KEY-177  
> 실행 선행: KEY-174 Pilot 배포 완료  
> 데이터: 합성 fixture만 사용

## 1. 목적과 판정 경계

Pilot 서버에서 역할 기반 접근통제(RBAC), 병원 데이터 격리, 미승인·원문 데이터 차단,
민감정보 마스킹이 로컬 테스트와 같은 계약을 지키는지 확인한다.

- 신규 권한 정책이나 API를 설계하지 않는다.
- 브라우저 메뉴 숨김만으로 통과시키지 않고 서버 응답을 직접 확인한다.
- 운영 환자, 운영 계정, 실제 토큰·OTP는 사용하지 않는다.
- KEY-174가 끝나기 전에는 아래 절차와 합성 fixture를 검토하고, 실제 PASS 판정은 배포 서버 실행 후 기록한다.

## 2. 준비 데이터

배포 환경에는 서로 겹치지 않는 두 합성 병원과 아래 계정을 준비한다. 비밀번호와 토큰
원문은 증적에 적지 않고 환경의 secret store에서만 주입한다.

| 식별자 | 병원 | 역할 | 용도 |
|---|---|---|---|
| `KEY177_H1_STAFF` | H1 | `staff` | 환자·진료·OCR 일반 허용 |
| `KEY177_H1_DOCTOR` | H1 | `doctor` | 안내 수정·승인 허용 |
| `KEY177_H1_ADMIN` | H1 | `admin` | 병원 운영 허용, 진료 기능 차단 |
| `KEY177_H1_ADMIN_STAFF` | H1 | `admin + staff` | 복수 역할 합집합 확인 |
| `KEY177_H2_STAFF` | H2 | `staff` | H1 자료 접근 차단 확인 |

H1과 H2에 환자·진료·문서·안내를 각각 한 건씩 만들고, H1에는 승인 대기 안내와 승인된
안내를 별도 진료에 둔다. 환자명·전화번호·차트번호는 `docs/data/`의 합성 데이터만 쓴다.

## 3. 실행 매트릭스

### A. 인증·RBAC

| ID | 주체 | 요청 | 기대 결과 |
|---|---|---|---|
| `RBAC-01` | H1 staff | `GET /api/v1/patients` | `200`, H1 자료만 포함 |
| `RBAC-02` | H1 admin | `GET /api/v1/patients` | `403 FORBIDDEN` |
| `RBAC-03` | H1 admin+staff | `GET /api/v1/patients` | `200`, staff 권한 유지 |
| `RBAC-04` | H1 staff | `POST /api/v1/visits/{id}/guide/approve` | `403 FORBIDDEN` |
| `RBAC-05` | H1 doctor | `POST /api/v1/visits/{id}/guide/approve` | `200` |
| `RBAC-06` | 무인증 | 보호 API 대표 1건 | `401`, 리소스 본문 없음 |

### B. 병원 격리

타 병원 리소스는 존재 여부도 노출하지 않도록 `404`를 기대한다. 목록에서는 H1 식별자가
한 건도 포함되지 않아야 한다.

| ID | H2 staff가 H1 식별자로 요청 | 기대 결과 |
|---|---|---|
| `TENANT-01` | `GET /api/v1/patients/{patient_id}` | `404` |
| `TENANT-02` | `GET /api/v1/visits/{visit_id}` | `404` |
| `TENANT-03` | `GET /api/v1/ocr/jobs/{ocr_job_id}/result` | `404` |
| `TENANT-04` | `GET /api/v1/visits/{visit_id}/guide` | `404` |
| `TENANT-05` | `GET /api/v1/visits/{visit_id}/checkin` | `404` |
| `TENANT-06` | 환자·진료 목록 조회 | H1 ID·차트번호·이름 없음 |

### C. 미승인 콘텐츠·원문 차단

| ID | 요청 | 기대 결과 |
|---|---|---|
| `CONTENT-01` | 승인 대기 안내의 환자 링크 발급 | 차단, 환자 링크 원문 없음 |
| `CONTENT-02` | 승인 대기 안내를 환자 공개 API로 조회 | 공개 본문 없음 |
| `CONTENT-03` | 승인된 안내를 환자 공개 API로 조회 | 승인된 섹션만 포함 |
| `CONTENT-04` | 환자 공개 응답 전체 | OCR 원문·내부 후보·직원 메모 없음 |
| `CONTENT-05` | 챗봇 공개 응답 전체 | 미승인 컨텍스트·OCR 원문 없음 |

`CONTENT-05`는 KEY-96 병합 후 실행한다. 그전에는 `SKIP(KEY-96)`으로 기록하며 PASS로
세지 않는다.

### D. 민감정보 비노출

| ID | 관찰 위치 | 금지 값 |
|---|---|---|
| `SECRET-01` | 로그인·refresh 응답 본문 | 비밀번호, refresh token |
| `SECRET-02` | OTP 발급·검증 응답과 오류 | OTP 원문, 환자 링크 토큰 |
| `SECRET-03` | 환자 링크·D+7 오류 응답 | 링크 토큰, 환자 세션 쿠키 |
| `SECRET-04` | access/application/error 로그 | JWT, refresh token, OTP, 링크 토큰 |
| `SECRET-05` | 브라우저 콘솔·네트워크 오류 문구 | 위 금지 값과 환자 전화번호 원문 |

로그 증적은 비밀값 자체를 검색어로 복사하지 않는다. 실행마다 생성한 합성 marker의
SHA-256 앞 12자리만 결과표에 남기고, 원문 부재 여부는 자동 검사 결과로 기록한다.

## 4. 실행 순서

1. 배포 commit SHA와 base URL을 기록하고 `/health`를 확인한다.
2. H1/H2 합성 fixture를 만들고 생성된 리소스 ID만 로컬 임시 결과 파일에 보관한다.
3. `RBAC → TENANT → CONTENT → SECRET` 순서로 실행한다.
4. 각 응답의 상태 코드와 JSON key 목록만 증적으로 남긴다. 토큰·쿠키·환자 원문은 저장하지 않는다.
5. 서버 로그는 같은 요청의 correlation ID로 조회하고 민감정보 자동 검사를 실행한다.
6. 임시 fixture와 로컬 결과 파일을 정리한다.

## 5. 결과 기록 양식

| ID | PASS/FAIL/SKIP | 상태 코드·관찰 결과 | 증적 위치 | 결함 Jira |
|---|---|---|---|---|
| 예: `TENANT-01` | PASS | `404`, 응답에 H1 식별자 없음 | CI artifact 링크 | - |

FAIL이면 아래를 반드시 함께 남긴다.

- 재현 환경과 배포 commit SHA
- 합성 시나리오 ID와 최소 재현 단계
- 기대 결과와 실제 결과(민감정보 제거 후)
- 영향 범위: 역할, 병원, API·화면, 데이터 종류
- 담당자와 별도 Jira 키

## 6. 기존 자동 회귀와 연결

배포 실행 전에 아래 로컬 회귀가 모두 통과해야 한다.

```bash
uv run pytest -q --confcutdir=app/tests/rbac app/tests/rbac
KEY34_SQLITE_TEST=1 uv run pytest -q --confcutdir=app/tests/blocking app/tests/blocking
uv run pytest -q --confcutdir=app/tests/security app/tests/security
uv run pytest -q --confcutdir=app/tests app/tests/patient_links
```

| 배포 매트릭스 | 기존 근거 |
|---|---|
| `RBAC-*` | `app/tests/rbac`, `app/tests/blocking` |
| `TENANT-*` | `app/tests/blocking`, OCR·환자 링크별 격리 테스트 |
| `CONTENT-*` | `test_key94_patient_content_boundaries.py` |
| `SECRET-*` | `app/tests/security` |

## 7. 완료 조건

- KEY-174 배포 서버에서 `SKIP`을 제외한 모든 행이 PASS다.
- KEY-96 미완료로 미룬 행은 후속 실행 주체와 일정을 기록한다.
- 화면·API·로그 어디에도 원문·미승인 콘텐츠와 비밀값이 없다.
- 실패 행은 재현 절차와 담당 Jira 키가 연결돼 있다.
- 결과에 실제 환자정보나 운영 credential이 포함되지 않는다.

## 8. 2026-08-25 설계 단계 선행 확인

| 검사 | 결과 |
|---|---|
| RBAC 계약 | `149 passed` |
| 민감정보·로그 마스킹 | `87 passed` |
| 환자 링크 전체 | 로컬 MySQL 테스트 계정 인증 실패로 미실행, 최신 develop 병합 QA 증적은 `39 passed` |
| Pilot 서버 실행 | `BLOCKED(KEY-174)` |

환자 링크 묶음은 코드 실패가 아니라 로컬 MySQL의 테스트 DB 생성 권한이 없어 실행하지
못했다. 배포 실행 전 CI 또는 권한이 분리된 테스트 DB에서 다시 실행한다.
