# KEY-36 테스트 계정·역할·환자 fixture 명세

> 상태: 구현 초안
> 적용 범위: QA용 합성 데이터와 권한 테스트 계약
> 주의: 이 문서는 테스트 계약이며 현재 모델·API 구현 완료를 의미하지 않는다.

## 1. 목적

인증, 역할 기반 접근 제어, 병원별 데이터 격리, OCR·안내문 흐름을 반복해서 검증할 수 있도록 공통 테스트 계정과 합성 환자 fixture를 정의한다.

이 문서에 포함된 이름, 병원, 연락처, 진료 및 검사 정보는 모두 테스트 전용 가상 데이터다. 실제 환자정보, 실제 직원정보, 비밀번호, JWT, OTP 및 운영용 링크 토큰을 저장소에 커밋하지 않는다.

## 2. 확정된 인증·계정 계약

- `ADMIN`, `DOCTOR`, `STAFF`는 모두 role이다.
- 한 직원은 두 개 이상의 role을 가질 수 있다.
- 직원 ID와 환자 ID를 포함한 주요 식별자는 UUID를 사용한다.
- `login_id`는 직원 생성 후 변경할 수 없다.
- 공개 회원가입 API인 `/api/v1/auth/signup`은 사용하지 않는다.
- 직원 계정은 권한 있는 관리자가 생성한다.
- Refresh Token은 JavaScript에 노출하지 않는 HttpOnly 쿠키로 관리한다.
- 브라우저는 토큰 재발급 요청에 Refresh Token 쿠키를 자동으로 포함한다.
- 프론트엔드 요청은 쿠키 전달이 필요한 경우 `credentials: "include"`를 사용한다.
- 운영 환경 쿠키는 `HttpOnly`, `Secure`, 적절한 `SameSite` 정책을 적용한다.
- 퇴사 직원은 삭제하지 않고 비활성 상태로 보존해 과거 작업 기록의 작성자를 유지한다.

## 3. 구현 전제와 현재 차이

현재 저장소의 `User` 모델과 인증 API는 이메일·정수 ID·`is_admin`을 사용하는 초기 템플릿이다. KEY-36은 다른 인증·환자 기능 티켓의 운영 모델을 선행 구현하지 않고, 해당 모델이 병합될 때 바로 연결할 수 있는 독립 테스트 데이터 팩토리로 제공한다.

- 직원 UUID 모델
- `login_id` 기반 로그인
- 복수 role 저장과 서버 측 권한 판정
- 관리자 전용 직원 생성 API
- 최초 비밀번호 변경
- HttpOnly Refresh Token 쿠키
- 공개 `/auth/signup` 제거

## 4. 테스트 환경 원칙

### 병원 격리

최소 두 병원을 생성한다.

| fixture | UUID 예시 | 용도 |
|---|---|---|
| `clinic_alpha` | `10000000-0000-4000-8000-000000000001` | 정상 기능 테스트의 기본 병원 |
| `clinic_beta` | `20000000-0000-4000-8000-000000000001` | 타 병원 접근 차단 테스트 |

UUID 예시는 테스트에서만 사용하는 고정값이다. 운영 데이터에는 사용하지 않는다.

### 비밀번호와 토큰

- 비밀번호 원문은 fixture 파일에 넣지 않는다.
- 테스트 비밀번호는 환경변수 또는 테스트 실행 중 생성한다.
- 예: `TEST_STAFF_PASSWORD`, `TEST_ADMIN_PASSWORD`
- JWT, Refresh Token, OTP, 환자 링크 토큰은 테스트 실행 중 발급한다.
- 실패 로그와 assertion 메시지에 토큰 원문을 출력하지 않는다.

## 5. 직원 계정 fixture

| fixture | 소속 | roles | 상태 | 주 검증 목적 |
|---|---|---|---|---|
| `alpha_admin` | Alpha | `ADMIN` | active | 직원 생성·수정과 병원 설정 |
| `alpha_doctor` | Alpha | `DOCTOR` | active | 안내문 검토·최종 승인 |
| `alpha_staff` | Alpha | `STAFF` | active | 환자·진료 등록과 문서 업로드 |
| `alpha_admin_staff` | Alpha | `ADMIN`, `STAFF` | active | 복수 role 합집합 권한 |
| `alpha_doctor_staff` | Alpha | `DOCTOR`, `STAFF` | active | OCR 확인 후 의사 승인 흐름 |
| `alpha_left_staff` | Alpha | `STAFF` | left | 퇴사 계정 로그인 차단과 기록 보존 |
| `beta_admin` | Beta | `ADMIN` | active | 타 병원 관리자 접근 차단 |
| `beta_doctor` | Beta | `DOCTOR` | active | 타 병원 의사 접근 차단 |
| `beta_staff` | Beta | `STAFF` | active | 타 병원 스탭 접근 차단 |

### 직원 공통 필드

```text
id: UUID
clinic_id: UUID
login_id: 영문 소문자와 숫자로 구성된 테스트 전용 값
name: 명백한 가상 이름
roles: ADMIN | DOCTOR | STAFF 중 하나 이상
status: active | left
must_change_password: boolean
```

### 최초 로그인 전용 fixture

`alpha_new_staff`는 `must_change_password=true`로 생성한다.

- 일반 Access/Refresh Token을 발급하지 않아야 한다.
- 비밀번호 변경 전용 단기 토큰만 발급해야 한다.
- 비밀번호 변경 완료 후 해당 단기 토큰은 재사용할 수 없어야 한다.
- 변경 완료 후 정상 로그인이 가능해야 한다.

## 6. 합성 환자 fixture

| fixture | 소속 | 시나리오 | 포함 조건 |
|---|---|---|---|
| `alpha_patient_pcos` | Alpha | PCOS 정상 흐름 | OCR 판독 가능, 처방·안내 생성 가능 |
| `alpha_patient_ems` | Alpha | 자궁내막증 정상 흐름 | 복수 처방과 주의 문구 포함 |
| `alpha_patient_unreadable` | Alpha | 일부 OCR 판독 불가 | 최소 한 필드가 `unreadable` |
| `alpha_patient_conflict` | Alpha | 동일 항목 값 충돌 | 서로 다른 문서에서 같은 항목의 다른 값 |
| `alpha_patient_unconfirmed` | Alpha | 미확정 OCR | 확정 전 안내 생성 차단 검증 |
| `alpha_patient_no_drug` | Alpha | 약 이름·일수 누락 | 안내 생성 실패·fallback 검증 |
| `alpha_patient_deleted_source` | Alpha | 승인 후 원본 삭제 | 삭제 뒤 원본 URL 접근 차단 |
| `beta_patient_isolation` | Beta | 병원 격리 | Alpha 직원의 조회·수정·다운로드 차단 |

### 합성 데이터 작성 규칙

- 주민등록번호를 만들거나 저장하지 않는다.
- 전화번호는 실제 발송이 불가능한 테스트 전용 값 또는 문자 발송 mock을 사용한다.
- 환자명은 `QA환자A`, `QA환자B`처럼 가상임이 드러나게 한다.
- 검사값은 명세에서 허용한 항목만 최소한으로 작성한다.
- OCR 원문 전체를 DB fixture로 저장하지 않는다.
- 진단이나 처방 변경을 유도하는 문장을 넣지 않는다.
- 의료 안전 문구는 승인된 component fixture를 사용한다.

## 7. 역할별 권한 검증표

| 행위 | ADMIN | DOCTOR | STAFF | 타 병원 계정 |
|---|---:|---:|---:|---:|
| 직원 계정 생성·수정 | 허용 | 차단 | 차단 | 차단 |
| 병원 설정 변경 | 허용 | 차단 | 차단 | 차단 |
| 환자·진료 등록 | 정책에 따라 허용 | 정책에 따라 허용 | 허용 | 차단 |
| 의료문서 업로드 | 정책에 따라 허용 | 정책에 따라 허용 | 허용 | 차단 |
| OCR 결과 수정·확정 | 정책 확인 필요 | 정책 확인 필요 | 허용 | 차단 |
| 안내문 승인 요청 | 정책 확인 필요 | 정책 확인 필요 | 허용 | 차단 |
| 안내문 최종 승인 | 차단 | 허용 | 차단 | 차단 |
| 감사로그 조회 | 허용 | 차단 | 차단 | 차단 |

`정책에 따라 허용` 및 `정책 확인 필요` 항목은 API 명세의 최종 권한표가 확정된 뒤 기대 결과를 고정한다. 역할별 화면 노출과 관계없이 서버가 동일한 권한 검사를 수행해야 한다.

## 8. 필수 인증·보안 테스트

### 인증

- 정상 `login_id`와 비밀번호로 로그인할 수 있다.
- 존재하지 않는 아이디와 틀린 비밀번호가 동일한 오류 형태를 반환한다.
- 비활성·퇴사 계정은 로그인할 수 없다.
- 최초 로그인 계정은 비밀번호 변경 전 일반 기능에 접근할 수 없다.
- Access Token 누락·만료·변조 요청은 `401`이다.
- Refresh Token은 응답 JSON과 JavaScript에서 읽을 수 없다.
- 유효한 HttpOnly 쿠키로만 Access Token을 재발급할 수 있다.
- 로그아웃 후 기존 Refresh Token을 재사용할 수 없다.

### 역할·소유권

- 단일 role 계정은 허용된 기능만 실행할 수 있다.
- 복수 role 계정은 보유 role의 권한 합집합을 적용받는다.
- 화면에서 버튼을 숨겨도 직접 API를 호출하면 서버가 권한을 다시 검사한다.
- Alpha 직원은 Beta 환자·진료·문서·안내문에 접근할 수 없다.
- 타 병원 리소스 차단 응답은 환자 존재 여부를 불필요하게 노출하지 않는다.

### 민감정보

- 응답과 로그에 비밀번호, JWT, Refresh Token, OTP 및 환자 링크 토큰 원문이 없다.
- 원본 저장소 키와 프리사인드 URL이 권한 없는 응답에 포함되지 않는다.
- 승인 후 삭제된 의료문서 URL은 재사용할 수 없다.
- 실패 응답에 OCR 원문이나 다른 병원의 식별정보가 포함되지 않는다.

## 9. fixture 구현 위치

```text
app/tests/
├── fixtures/
│   ├── __init__.py
│   ├── models.py
│   └── key36.py
├── auth_apis/
├── permission_apis/
└── security_apis/
tests/
└── test_key36_fixtures.py
```

- `build_key36_fixture_set()`이 결정적인 UUID를 가진 병원·직원·환자·진료 데이터를 반환한다.
- 현재 운영 모델과 분리된 dataclass이므로 인증·환자 모델 변경 전에도 계약 테스트에서 사용할 수 있다.
- 실제 모델 병합 후에는 반환된 fixture를 DB 모델로 저장하는 어댑터만 추가한다.
- 테스트 간 데이터가 누출되지 않도록 테스트별 트랜잭션 또는 초기화를 적용한다.
- 외부 OCR, 문자 발송, S3는 실제 서비스 대신 mock/fake를 사용한다.

### 실행 방법

비밀번호는 저장소에 커밋하지 않고 테스트 프로세스에만 주입한다.

```bash
APP_ENV=test KEY36_TEST_PASSWORD='<개발 전용 값>' uv run python -m pytest tests/test_key36_fixtures.py
```

- `KEY36_TEST_PASSWORD`가 없으면 fixture 생성을 거부한다.
- `APP_ENV=prod` 또는 `APP_ENV=production`이면 fixture 생성을 거부한다.
- 반환된 `test_password`는 로그인 요청용 테스트 어댑터에서만 사용하고 로그나 assertion 메시지에 출력하지 않는다.

## 10. 단계별 적용

### 1단계 — 현재

- 병원, 역할별 직원, 합성 환자와 진료 연결 fixture를 제공한다.
- UUID, 복수 역할, 병원 격리, 퇴사·최초 로그인 계정과 운영 실행 차단을 계약 테스트로 검증한다.
- 미확정 API 권한과 운영 모델을 임의로 구현하지 않는다.

### 2단계 — 직원·환자 모델 병합 후

- 병원과 직원 fixture를 구현한다.
- UUID, 복수 role, 퇴사 상태 테스트를 작성한다.
- 공개 `/auth/signup`이 제거됐는지 확인한다.

### 3단계 — 인증 API 병합 후

- 로그인, 최초 비밀번호 변경, Refresh Token 쿠키, 로그아웃 테스트를 작성한다.
- 브라우저 쿠키 속성과 재발급 흐름을 확인한다.

### 4단계 — 환자·OCR API 병합 후

- 합성 환자와 진료·문서 fixture를 구현한다.
- 타 병원 접근 차단, 미확정 OCR 사용 차단, 원본 삭제 회귀 테스트를 작성한다.

## 11. KEY-36 완료 조건

- [x] 역할별 테스트 계정 목록이 확정됐다.
- [x] 두 병원을 사용하는 데이터 격리 시나리오가 포함됐다.
- [ ] 정상·예외 OCR 합성 환자 시나리오가 포함됐다.
- [x] 실제 개인정보와 비밀값을 사용하지 않는다.
- [x] UUID와 복수 role 정책이 반영됐다.
- [ ] HttpOnly Refresh Token 검증 방법이 포함됐다.
- [ ] 공개 `/auth/signup` 제거 검증이 포함됐다.
- [ ] 담당자와 리뷰어가 미확정 권한 항목을 결정했다.
- [ ] 구현된 fixture와 관련 테스트가 통과했다.
- [ ] 실행하지 못한 테스트와 제한사항을 PR에 기록했다.

## 12. 검토가 필요한 항목

1. `ADMIN`이 환자·진료 업무 권한도 자동으로 가지는지
2. `DOCTOR`가 환자 등록·문서 업로드·OCR 수정까지 할 수 있는지
3. `STAFF`와 `DOCTOR` 중 누가 OCR 결과를 최종 확정하는지
4. `roles`와 세부 `permissions`를 함께 사용할지
5. 타 병원 리소스 접근 시 `403`과 `404` 중 어떤 상태를 사용할지
6. Refresh Token 쿠키의 `SameSite` 값과 개발 환경의 `Secure` 적용 방식
7. 테스트용 문자번호와 SMS mock의 공통 형식
