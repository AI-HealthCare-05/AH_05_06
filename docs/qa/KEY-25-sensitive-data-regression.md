# KEY-25 민감정보 노출 회귀 테스트·보안 체크리스트

## 1. 목적

정상·오류 응답과 애플리케이션 로그에 인증정보나 환자 식별정보가 불필요하게
남지 않는지 PR마다 반복 확인한다. 이 문서는 새로운 마스킹 정책을 정의하지 않고
`KEY-11`·`KEY-28`에서 구현한 공통 마스킹과 오류 처리기를 검수하는 기준이다.

## 2. 적용 범위

| 경로 | 차단 대상 | 허용 범위 |
|---|---|---|
| 정상 인증 응답 | 비밀번호, OTP, Refresh Token | 로그인·갱신 성공의 `access_token`, `must_change_password` |
| 검증 오류 `422` | 요청 원문의 `input` | 필드 위치·검증 규칙·최소 길이 |
| HTTP 오류 | JWT, 링크 토큰, OTP, 비밀번호, 전체 전화번호·주민번호 | 오류 의미, 전화번호 뒤 4자리 |
| 처리되지 않은 오류 `500` | 예외 내부값·DB 접속정보 | 일반 오류 문구 |
| 애플리케이션 로그 | JWT, 링크 토큰, OTP, 비밀번호, 전화번호 중간자리·주민번호 뒷자리 | 요청·환자·진료 내부 ID, 전화번호 뒤 4자리 |

환자 이름·생년월일 등 구조화 개인정보를 통째로 로그에 기록하는 코드는 마스킹에
의존하지 않고 호출부에서 제거한다. 현재 공통 마스킹은 임의 문자열만 보고 사람의
이름이나 날짜를 정확히 판별할 수 없기 때문이다.

## 3. 자동 회귀 테스트

`app/tests/security/test_sensitive_data_regression.py`가 다음 경로를 한 번에 확인한다.

- 정상 응답이 요청의 비밀번호·OTP를 되돌려 주지 않음
- 로그인·갱신 응답 모델에 계약 외 필드가 추가되지 않음
- `422` 응답에 Pydantic의 요청 원문 `input`이 포함되지 않음
- HTTP 오류의 비밀번호·OTP·JWT·링크 토큰·전체 전화번호·주민번호가 제거됨
- 일반 로그와 예외 traceback 렌더링에 동일한 차단 규칙이 적용됨
- 추적에 필요한 내부 `patient_id`와 전화번호 뒤 4자리는 유지됨

세부 정규식과 오탐 방지는 기존 테스트가 담당한다.

- `app/tests/security/test_masking.py`
- `app/tests/security/test_error_responses.py`
- `app/tests/security/test_secrets_not_committed.py`
- `app/tests/auth_apis/test_staff_login_api.py`
- `app/tests/auth_apis/test_staff_session_api.py`

## 4. 실행 방법

```bash
ENV=local uv run pytest app/tests/security/test_sensitive_data_regression.py -q
ENV=local uv run pytest app/tests/security -q
uv run ruff check app/tests/security/test_sensitive_data_regression.py
uv run ruff format app/tests/security/test_sensitive_data_regression.py --check
```

`app/tests/conftest.py`가 MySQL 테스트 DB를 초기화하므로 전체 `app/tests` 실행에는
테스트 DB 생성 권한이 필요하다. DB와 무관한 KEY-25 단위 회귀만 로컬에서 빠르게
확인할 때는 다음과 같이 공통 DB fixture를 제외한다.

```bash
ENV=local uv run pytest app/tests/security/test_sensitive_data_regression.py -q \
  --confcutdir=app/tests/security
```

## 5. PR 리뷰용 체크리스트

### 응답

- [ ] 정상 응답이 요청 본문을 그대로 echo하지 않는다.
- [ ] 로그인·갱신 외 응답 본문에 Access Token이 포함되지 않는다.
- [ ] Refresh Token은 본문이나 JavaScript 저장소가 아닌 HttpOnly 쿠키로만 전달된다.
- [ ] 오류 응답에 비밀번호·OTP·토큰·전체 전화번호가 포함되지 않는다.
- [ ] `422` 오류의 `detail` 항목에 `input`이 포함되지 않는다.
- [ ] `500` 응답이 예외 메시지·DB 주소·계정 정보를 노출하지 않는다.

### 로그

- [ ] 요청 본문, Authorization 헤더, 쿠키 전체를 로그로 남기지 않는다.
- [ ] `logger.*(..., exc_info=...)`의 예외 문자열도 마스킹된다.
- [ ] 환자 이름·생년월일·전체 전화번호를 한 문장에 함께 기록하지 않는다.
- [ ] 필요하면 내부 식별자와 전화번호 뒤 4자리만 사용한다.
- [ ] 외부 OCR·문자·AI 서비스 요청/응답 원문을 그대로 기록하지 않는다.

### 저장소

- [ ] 실제 `.env`와 운영 비밀값 파일이 Git 추적 대상이 아니다.
- [ ] 예시 환경파일에는 `your-...` 형태의 자리표시자만 있다.
- [ ] 테스트 데이터는 합성값이며 실제 환자정보·토큰·비밀번호가 아니다.
- [ ] 비밀값처럼 보이는 신규 상수가 커밋에 포함되지 않았다.

## 6. 실패 사례와 조치 방법

| 실패 | 원인 | 조치 |
|---|---|---|
| `422`에 비밀번호·OTP가 보임 | 기본 FastAPI 검증 응답이 `input`을 반환 | `register_error_handlers()` 등록 여부와 `masked_validation_handler` 확인 |
| HTTP 오류에 토큰이 보임 | `HTTPException.detail`에 원문 삽입 | 오류 코드·일반 문구만 사용하고 공통 핸들러 등록 확인 |
| 일반 로그에 원문이 보임 | `setup_logger()`가 아닌 별도 로거/핸들러 사용 | 공통 로거를 사용하고 `MaskingFilter`가 붙었는지 확인 |
| 예외 traceback에 비밀값이 보임 | 예외 메시지·소스 코드에 원문 포함 | 예외에는 식별용 코드만 넣고 소스의 실제 값을 즉시 교체·폐기 |
| 전화번호가 전부 보임 | 마스킹 경로를 거치지 않음 | 공통 로거·`scrub()`를 사용하고 전체 개인정보 로깅 제거 |
| 내부 ID까지 전부 사라짐 | 토큰 정규식이 너무 넓음 | 오탐 회귀 테스트를 추가하고 토큰 형식 조건을 좁힘 |

비밀값이 실제로 커밋되었다면 단순 삭제 커밋으로 끝내지 않는다. 해당 키·비밀번호를
먼저 폐기하고 재발급한 다음, 저장소 이력 정리는 `KEY-110` 담당자와 조율한다.

## 7. 현재 제한사항과 후속 검증

- 환자 링크·OTP API가 병합되면 실제 발급·오류·잠금 응답을 이 회귀 테스트에 연결한다.
- 환자·진료 API가 병합되면 목록·상세·오류 응답의 최소 필드 노출을 추가 검증한다.
- 외부 OCR·SMS·AI 연동은 실제 비밀값 대신 fake를 사용해 요청·응답 로그를 검증한다.
- `KEY-110`의 저장소 이력 비밀값 교체는 이 티켓에서 수정하지 않는다.

## 8. 완료 조건 대응

- 토큰·OTP·비밀번호·환자 식별정보 노출: 자동 회귀 테스트와 5절 체크리스트로 확인
- 실패 사례와 조치 방법: 6절에 원인별 대응 절차 기록
