# 병원용 API

> 인증 주체: 병원 직원
> 문서 상태: 직원 인증, 환자·진료, OCR의 기존 상세 계약과 구현 기록을 통합한 저장소 정본

## 1. 적용 원칙

병원 직원이 사용하는 API는 아래 흐름을 지원한다.

```text
직원 로그인
→ 환자·진료 등록 및 조회
→ 의료문서 업로드·OCR 확인·확정
→ 안내 생성·검토·승인
→ 환자 링크 발급
→ D+7 응답 조회
```

모든 API는 직원 역할과 병원 범위를 서버에서 검증한다. 인증 주체, 민감정보, 공통 식별자, 오류 코드와 변경 관리는 [API 공통 규칙](common.md)을 우선 적용한다. 이 문서 안의 과거 구현 기록과 공통 규칙이 충돌하면 공통 규칙이 우선한다.

### 1.1 KEY-151 D+7 최소 환류

`GET /api/v1/visits/{visit_id}/checkin`은 같은 병원의 `staff` 또는 `doctor`가
해당 진료에 연결된 D+7 복약·통증 응답 한 건을 조회하는 Walking Skeleton
계약이다. 응답은 `check_in.guide_document_id`에서 `GuideDocument.visit_id`를
파생하며 환자 링크 토큰, 환자정보, OCR·의료문서 원문을 포함하지 않는다.

아직 응답하지 않은 진료·없는 진료·타 병원 진료는 모두
`404 CHECKIN_NOT_FOUND`로 감춘다. 별도 병원 화면을 새로 만드는 것은 정본
와이어프레임과 KEY-99 범위이므로 KEY-151에서는 서버 조회 경계까지만 연결한다.

## 2. 직원 인증


> `KEY-10` · 하위 `KEY-22`(화면) · `KEY-24`(통합 테스트)
> 근거 — 와이어프레임 `L-1`·`L-2`·`L-3` (`docs/wireframes/wireframe-medic-2.3.1.html`) · `spec-medical.md` staff 표
> 2026-08-19

**이 문서는 `KEY-8`(API 계약 v1 동결)을 대신하지 않는다.** 화면이 요구하는 것을 정리해
계약 확정에 넣을 입력물이다. 확정 권한은 `KEY-8` 담당(이희진)에게 있다.

---

### 1. 지금 코드가 화면과 어긋난다

현재 `app/`은 부트캠프 예시 골격이다. 화면이 요구하는 것과 **여덟 군데**가 다르다.

| 화면이 요구하는 것 | 지금 코드 | 어디 |
|---|---|---|
| **아이디**로 로그인 (`staff01`) | `email`로 로그인 | `L-1` · `app/dtos/auth.py` |
| 계정은 **어드민이 만든다** | `POST /auth/signup` 회원가입이 열려 있다 | `A1-2` · `app/apis/v1/auth_routers.py` |
| `roles` 배열 (staff·doctor·admin) | `is_admin` bool 하나 | `A1-2` · `app/models/users.py` |
| **첫 로그인 비밀번호 변경 강제** | 없음 | `L-3` |
| **5회 실패 → 10분 잠금** · 시도 횟수 표시 | 없음 | `L-2` |
| 퇴사자(`status='left'`)는 못 들어온다 | 없음 | `A1-3` |
| `GET /auth/me` · `POST /auth/logout` · `POST /auth/refresh` · `PATCH /auth/password` | `GET /users/me`만 있다 | `KEY-22` |
| 리프레시 토큰을 **`HttpOnly` 쿠키**로 | 본문에 담아 준다 | 4절 |

`spec-medical.md`의 `staff` 표에는 **이미 다 있다** — `login_id` · `must_change_password` ·
`roles` · `status`. 명세와 코드가 갈려 있는 것이지, 정할 것이 없어서 못 만든 것이 아니다.

---

### 2. 화면이 정한 것

#### `L-1` 로그인

| | |
|---|---|
| 입력 | **아이디** · 비밀번호 |
| 아이디 규칙 | `^[a-z0-9]{4,}$` · **생성 후 변경 불가** (`staff.login_id`) |
| 로그인 유지 | `☐ 이 컴퓨터에서 로그인 유지` — **기본 해제.** 공용 컴퓨터를 쓴다 |
| 역할 선택 | **없다.** 「의사로 로그인 / 스탭으로 로그인」을 두면 처음 쓰는 사람이 멈춘다 |
| 로그인 후 | 스탭 → `S1` · 의사 → `D1` · 관리자 권한 보유 시 `A1` 메뉴가 보인다 |
| 의원 이름 | 카드 아래에 표시 — 어느 의원 화면인지 알려준다 |

#### `L-2` 오류

> **어느 쪽이 틀렸는지 쓰지 않는다.** 아이디가 있는지 없는지가 드러나면 안 된다.

| | |
|---|---|
| 문구 | `⚠ 아이디 또는 비밀번호가 맞지 않습니다` |
| 횟수 | `5회 오류 시 일시 잠금 (2회)` — 지금까지 몇 번 틀렸는지 함께 보여준다 |
| 잠금 | 5회 실패 → **10분** · `잠시 뒤 다시 시도해 주세요. (10분)` |

#### `L-3` 첫 로그인 — 비밀번호 바꾸기

> **건너뛸 수 없다.** 이 화면을 지나야 `S1` 또는 `D1`로 간다.

| | |
|---|---|
| 왜 | 어드민이 정해준 첫 비밀번호를 그대로 쓰면 **정해준 사람이 계속 알고 있게 된다** |
| 입력 | 새 비밀번호 + 확인 (두 번) |
| 규칙 | `영문 · 숫자 · 기호를 섞어 8자 이상` |
| 불일치 | `두 번 넣으신 비밀번호가 달라요` |

---

### 3. 화면 둘이 부딪히는 곳 — 횟수를 보여주면 아이디가 새어 나간다

`L-2`는 두 가지를 동시에 요구한다.

1. **아이디 존재 여부를 감춘다** — 어느 쪽이 틀렸는지 쓰지 않는다
2. **실패 횟수를 보여준다** — `(2회)`

그런데 실패 횟수를 **아이디 기준으로** 세면 1번이 깨진다.
없는 아이디로 다섯 번 두드렸을 때 횟수가 안 올라가면, **횟수가 안 오른다는 사실 자체가
「그런 아이디는 없다」는 답이 된다.**

**해결 — 없는 아이디도 똑같이 센다.** 계정이 아니라 **입력된 문자열**을 키로 삼는다.

```
key = f"login_fail:{입력된_login_id}"     계정이 있든 없든 똑같이 오른다
```

없는 아이디도 5회에서 잠기고 같은 문구가 나온다. 공격자가 얻는 정보가 없다.
Redis TTL 10분을 그대로 잠금 시간으로 쓴다 — 잠금 해제를 따로 관리하지 않아도 된다.

> 참고 — IP 기준으로만 세면 의원 하나가 공인 IP를 공유하는 경우 **한 사람의 오타로
> 의원 전체가 잠긴다.** 진료 중에 그런 일이 생기면 안 된다.

---

### 4. 엔드포인트 — v1 확정 (`KEY-8` · 2026-08-19)

> 이 절은 **이희진 님이 확정한 v1 계약**이다. 바꾸려면 `KEY-8`을 거친다.

| | |
|---|---|
| `POST` | `/api/v1/auth/login` |
| `GET` | `/api/v1/auth/me` |
| `POST` | `/api/v1/auth/refresh` |
| `POST` | `/api/v1/auth/logout` |
| **`PATCH`** | `/api/v1/auth/password` |

#### `POST /api/v1/auth/login`

```jsonc
// 요청
{ "login_id": "staff01", "password": "…", "remember": false }

// 200 — 본문에는 액세스 토큰만 온다
{ "access_token": "…", "must_change_password": false }

// 응답 헤더
Set-Cookie: refresh_token=…; HttpOnly; Secure; SameSite=Lax; Path=/api/v1/auth
```

**리프레시 토큰은 본문에 담지 않는다.** `HttpOnly` 쿠키로만 내려간다 —
스크립트가 읽지 못하므로 XSS로 새어 나가도 훔쳐 갈 것이 없다.

`remember`는 **발급 여부가 아니라 쿠키가 얼마나 남는지**를 정한다.
리프레시 토큰은 두 경우 모두 발급된다.

| `remember` | 쿠키 | 언제 사라지나 |
|---|---|---|
| **거짓** (기본) | 세션 쿠키 (`Max-Age` 없음) | **브라우저를 닫으면** |
| 참 | `Max-Age` = 리프레시 수명 | 그 기간이 지나면 |

> **쿠키가 남아 있는 것과 세션이 살아 있는 것은 다르다.** 세션 쿠키는 브라우저를
> 닫아야 사라지는데 접수대는 하루 종일 켜 둔다. 그래서 **유휴 30분**이 함께 간다 —
> `refresh` 절 참고. 로그인 유지를 켜도 30분 가만히 있으면 끊긴다.

#### `GET /api/v1/auth/me`

세션 복원과 화면 분기의 근거다. 새로고침할 때마다 부른다.

```jsonc
{ "id": "…", "name": "박연", "login_id": "doctor01",
  "roles": ["doctor"], "must_change_password": false,
  "clinic_name": "여성의원" }
```

`roles`로 FE가 초기 화면(`S1`/`D1`)과 어드민 메뉴 노출을 정한다.
**노출 여부는 편의일 뿐이고 실제 차단은 서버가 한다** (`KEY-9`).

#### `POST /api/v1/auth/refresh`

요청 본문이 없다. **쿠키로 온 리프레시 토큰만 본다.**

```jsonc
// 200
{ "access_token": "…" }
// Set-Cookie: refresh_token=…   ← 새 토큰으로 갈아 끼운다
```

**Rotation** — 쓸 때마다 새 리프레시 토큰을 발급하고 **쓴 것은 즉시 폐기**한다.
이미 폐기된 토큰이 다시 오면 **훔친 것이 쓰였다는 뜻**이므로, 그 계정의 세션을 전부 끊는다.

##### 유휴 30분 — 여기서 끊는다

접수대는 브라우저를 하루 종일 켜 둔다. 쿠키만으로는 **탭만 닫고 자리를 떠도
다음 사람이 그대로 들어간다.** 그래서 「가만히 있으면 끊긴다」가 필요하다.

```
로그인 · refresh 성공  →  Redis  idle:{refresh_token_id}  TTL 30분으로 갱신
refresh 요청           →  이 키부터 확인
                          없으면  401 token_expired + 그 리프레시 토큰 폐기
                          있으면  정상 rotation
```

**`refresh` 시점에만 본다.** 매 요청마다 확인하지 않는다 — 새 미들웨어 없이
로그인·`refresh` 핸들러만 고치면 되고, 요청마다 Redis를 두드리지 않는다.

**`remember`와 무관하다.** 로그인 유지를 켜도 30분 가만히 있으면 `refresh`가 막힌다.
쿠키가 남아 있는 것과 세션이 살아 있는 것은 다르다.

> **최악의 경우** 액세스 토큰 잔여 수명(최대 60분)만큼은 살아 있을 수 있다.
> 매 요청 검사를 하지 않기로 한 대가다. 그래도 **「브라우저를 닫을 때까지」보다는 크게 짧다.**

환자 세션도 30분이라 **직원과 환자가 같은 기준**을 쓴다.
(`KEY-8` 확정 · 2026-08-19)

#### `POST /api/v1/auth/logout`

액세스 토큰과 리프레시 토큰을 함께 무효로 만들고 쿠키를 지운다.
이후 보호 API는 `401`.

#### `PATCH /api/v1/auth/password`

**두 경우가 요청 조건이 다르다.**

| | 언제 | 요청 | 왜 다른가 |
|---|---|---|---|
| **최초 로그인** (`L-3`) | `must_change_password = true` | `{ "new_password": "…" }` | 방금 그 비밀번호로 로그인했다. **한 화면에서 같은 값을 두 번 넣게 하면 거기서부터 막힌다** |
| 일반 변경 | 평소 | `{ "current_password": "…", "new_password": "…" }` | 자리를 비운 사이 남이 바꾸는 것을 막는다 |

서버가 `must_change_password`로 갈라 판정한다. **참인데 `current_password`가 오면 무시하고,
거짓인데 없으면 `422`다.**

성공하면 `must_change_password`를 내리고 **기존 세션을 전부 폐기한다** — 리프레시 토큰 포함.
비밀번호를 바꾸는 이유가 「남이 알고 있다」이므로 그 남의 세션도 같이 끊어야 한다.
FE는 로그인 화면으로 돌아가 새 비밀번호로 다시 들어온다.

---

### 5. 서버가 지키는 것 — 화면이 뭘 하든

`KEY-9`와 같은 원칙이다. **프론트 표시 여부와 무관하게 서버가 최종 판정한다.**

#### 상태 코드는 셋으로 통일한다

| | 언제 |
|---|---|
| **`401`** | 미인증 · 만료 — **다시 로그인해야 한다** |
| **`403`** | 인증은 됐는데 권한이 부족하다 — 로그인해도 안 된다 |
| **`422`** | 요청 형식·검증 오류 |
| `429` | 잠금 — 아래 |

`401`과 `403`을 섞으면 화면이 「다시 로그인하세요」와 「권한이 없습니다」 중
무엇을 낼지 정하지 못한다.

#### 규칙

| 규칙 | 응답 | 인수조건 |
|---|---|---|
| 아이디·비밀번호 불일치 | `401 invalid_credentials` — **어느 쪽인지 말하지 않는다** | 「잘못된 인증정보와 만료 세션이 구분되어 안내됨」 |
| 만료·로그아웃된 토큰 | `401 token_expired` | 위와 **다른 코드여야 한다.** 화면 문구가 다르다 |
| **5회 초과** | **`429 ACCOUNT_LOCKED`** + **`Retry-After: 600`** 헤더 | `L-2` |
| 퇴사자(`status='left'`) | `401 invalid_credentials` | **없는 계정과 같게 답한다** — 누가 그만뒀는지 알려줄 이유가 없다 |
| `must_change_password`인 채 보호 API 호출 | `403 password_change_required` | 「최초 로그인 사용자는 `L-3` 완료 전 다른 보호 화면에 접근할 수 없음」 |
| 로그아웃 뒤 보호 API 호출 | `401 token_expired` | 「로그아웃 후 보호 API와 화면에 접근할 수 없음」 |
| 폐기된 리프레시 토큰 재사용 | `401` + **그 계정의 세션 전부 폐기** | Rotation |
| **30분 무활동 뒤 `refresh`** | `401 token_expired` + **그 리프레시 토큰 폐기** | 유휴 만료 — 4절 |

`Retry-After`는 **표준 헤더**라 프록시와 클라이언트가 그대로 이해한다.
본문에도 `retry_after_seconds`를 함께 담아 화면이 「(10분)」을 계산하게 한다.

`403 password_change_required`의 예외는 **자기 자신을 벗어나는 것뿐**이다 —
`GET /auth/me` · `PATCH /auth/password` · `POST /auth/logout` **셋만** 통과시킨다.
그 셋까지 막으면 비밀번호를 바꿀 방법이 없어 계정이 잠긴다.

#### 토큰을 어디에도 남기지 않는다

`AGENTS.md` 규칙이다. URL 쿼리 · 화면 · 로그 · 커밋 어디에도 원문을 넣지 않는다.
로그인 실패 로그에 **입력된 비밀번호를 남기지 않는다** — 오타는 대개 다른 계정의 진짜 비밀번호다.

---

### 6. 정해진 것과 남은 것

| 무엇 | 지금 상태 |
|---|---|
| ~~토큰 수명 · 리프레시 회전~~ | **정해졌다** — 액세스 60분 · 리프레시 14일(`envs/example.local.env`) · Rotation 적용 |
| ~~`remember` 켰을 때 유지 기간~~ | **정해졌다** — 쿠키 `Max-Age` = 리프레시 수명 |
| ~~FE 저장 위치와 스택~~ | **정해졌다** — `frontend/` 정적 구조 (PR #11 병합 후 확정) |
| ~~유휴 만료~~ | **정해졌다** — 30분 sliding window · `refresh` 시점 확인 (4절) |
| `signup` 제거 시점 | 제품에 회원가입이 없다. 다만 지금 지우면 기존 테스트 9개가 깨지므로 `A1-2` 직원 등록이 생길 때 함께 옮긴다 |

---

### 7. 어디에 무엇이 있나

| | |
|---|---|
| 화면 정본 | `docs/wireframes/wireframe-medic-2.3.1.html` — `L-1` `L-2` `L-3` |
| `staff` 표 | 기획 저장소 `spec-medical.md` |
| 권한 매트릭스 | `app/tests/rbac/matrix.py` (`KEY-23`) |
| 직원 계정 픽스처 | `docs/data/synthetic-staff.csv` — 14계정 (`KEY-10` · PR #12) |
| 로그인 화면 | `frontend/login.html` · `password.html` (`KEY-22` · PR #14) |

## 3. 환자·진료


> KEY-12 · 하위 KEY-26 · 구현 후속 KEY-31
> 상태: `v1.0-rc1` — 한금준 최종 검수와 PR 승인 시 `v1.0-frozen`으로 전환
> 기준일: 2026-08-19

이 문서는 새 API 범위를 제안하는 문서가 아니다. 기존 환자 관리 API 문서, ERD v11, 요구사항, 정본 와이어프레임 사이의 충돌을 해소하고 KEY-31 구현이 따라야 할 이름과 관계를 고정한다.

### 1. 검수 근거와 우선순위

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

### 2. 동결 결정

| 항목 | v1 결정 | 근거 |
|---|---|---|
| 환자 PK | `patient_id: bigint` | ERD v11 및 현재 `User` PK와 정합 |
| 진료 PK | `visit_id: bigint` | ERD v11 |
| 병원 범위 | `hospital_id: bigint`, 클라이언트 입력 금지 | 모든 접근에서 로그인 직원의 병원으로 서버가 결정 |
| 차트번호 | `hospital_patient_no`, `(hospital_id, hospital_patient_no)` 유일. 진료 전에는 감사 사유를 남기는 제한적 정정 허용 | S1-2·S1-3, ERD v11 |
| 환자 나이 | 저장하지 않고 `birth_date`로 계산 | 본인확인 및 시간이 지나면 변하는 `age` 제거 |
| 성별 | `gender`를 PATIENT에 추가, `FEMALE/MALE/OTHER/UNKNOWN`, 기본 `UNKNOWN` | Notion S2-1 응답에는 네 값이 있으나 ERD v11에서 누락됨. 합성 데이터는 `FEMALE`을 명시 |
| 진료 리소스명 | `visits` | 환자 1:N 진료 관계와 OCR·안내·발송 연결 기준 |
| 환자 삭제 | v1 API에서 제공하지 않음 | S2-1의 “의료 기록은 삭제하지 않습니다” |
| 진행 상태 | Patient/Visit에 별도 업무 진행 상태를 저장하지 않음 | `EVENT_LOG` 최신 이벤트에서 파생. 단 `visit.status`는 방문 자체의 `SCHEDULED/COMPLETED/CANCELED`만 표현 |
| 계획 중단 | `visit.planned_stop: boolean`, 기본 `false` | 의사가 계획적으로 처방을 중단한 경우 확인·소진·재진 알림 및 이탈 판정에서 제외 |
| 역할 | `roles jsonb`의 `staff`, `doctor`, `admin` 중 하나 이상, 중복 허용 | KEY-9 확정 |
| `staff.is_owner` | 컬럼 유지, v1 권한 판정에서는 사용하지 않음 | KEY-11 확정 |
| `event_log.action=chat_export` | 값 유지 | KEY-9·KEY-11 결정사항. 앱의 대화 원문 조회·내려받기는 제공하지 않으며, 예외적 운영 추출은 승인된 감사 절차를 통해 이 값을 기록해야 함 |

### 3. 데이터 관계

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

### 4. 모델 필드

#### PATIENT

| API 필드 | DB 필드 | 타입 | 필수 | 규칙 |
|---|---|---|---:|---|
| `patient_id` | `patient_id` | bigint | 응답 | PK |
| — | `hospital_id` | bigint | 서버 | 로그인 직원의 병원, 요청 본문에서 거부 |
| `hospital_patient_no` | `hospital_patient_no` | string(50) | 요청 | 병원 내 유일. 일반 수정 불가; 진료가 없는 환자에 한해 `admin`과 임상 역할을 함께 가진 사용자가 정정 가능 |
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

#### VISIT

| API 필드 | DB 필드 | 타입 | 필수 | 규칙 |
|---|---|---|---:|---|
| `visit_id` | `visit_id` | bigint | 응답 | PK |
| — | `hospital_id` | bigint | 서버 | 환자 병원과 로그인 직원 병원이 모두 같아야 함 |
| `patient_id` | `patient_id` | bigint | 경로/응답 | POST에서는 경로로만 입력 |
| `doctor_id` | `doctor_id` | bigint/null | 요청 | 같은 병원, `doctor` 역할 보유자만 |
| `department_id` | — | bigint/null | 요청 | 같은 병원의 활성 진료과. 저장 전 담당 의사의 소속을 검증하는 명령 필드 |
| `department` | `department` | string(100)/null | 응답 | 검증된 진료과 명칭을 저장한 진료 당시 스냅샷. 클라이언트가 직접 입력하지 않음 |
| `visited_at` | `visited_at` | datetime | 요청 | 오늘 진료와 시간순 이력의 정렬 기준 |
| `visit_summary` | `visit_summary` | string/null | 요청·응답 | 환자용 승인 안내와 분리된 진료 요약 원천 |
| `doctor_note` | `doctor_note` | string/null | 요청·응답 | 승인 데이터 생성의 선택 입력, 환자 API에는 원문 노출 금지 |
| `status` | `status` | `SCHEDULED/COMPLETED/CANCELED` | 요청·응답 | 방문 자체 상태만 표현 |
| `planned_stop` | `planned_stop` | boolean | 요청·응답 | `true`이면 확인·소진·재진 문자와 이탈 판정을 중단 |
| `created_at` | `created_at` | datetime | 응답 | UTC 저장 |
| `updated_at` | `updated_at` | datetime | 응답 | UTC 저장 |

날짜 기반 규칙의 기준은 병원 표시 시간대다. v1은 `Asia/Seoul`로 고정하고, `visited_at`은 UTC로 저장한 뒤 표시 시간대로 변환한다. 동일 병원·환자·현지 진료일의 중복 등록은 서비스 계층에서 `409 VISIT_ALREADY_REGISTERED`로 막는다. 향후 병원별 시간대 설정을 추가하더라도 저장 형식은 UTC로 유지한다.

### 5. 엔드포인트

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
| GET | `/api/v1/front-desk/visits` | S1-1 날짜별 업무 목록 읽기 모델 | `patient:read` |

`patient:read`와 `patient:write`는 `staff` 또는 `doctor` 역할이 연다. `admin`만 가진 사용자는 진료 데이터에 접근할 수 없다.

Notion의 화면 조합 API(`/front-desk/visits`, `/front-desk/patients/search`, `/front-desk/visits/{visit_id}/patient-card`, `/patients/{patient_id}/care-summary`, `/patients/{patient_id}/care-history`)는 삭제하지 않는다. 이 API들은 위 여덟 리소스 계약과 후속 도메인의 구조화된 읽기 모델을 조합한다. 단, 중복된 `PATCH /front-desk/patients/{patient_id}`는 `PATCH /patients/{patient_id}`로 통합한다.

모든 단건 조회·수정은 다음 순서로 검증한다.

1. 리소스를 로그인 직원의 `hospital_id`와 함께 조회한다.
2. 없거나 타 병원 소유이면 모두 `404`를 반환한다.
3. Visit 경로에서는 `visit.hospital_id == visit.patient.hospital_id`도 확인한다.
4. 수정 권한은 역할 검사 후 적용한다.

타 병원 리소스에 `403`을 반환하지 않는다. 존재 여부를 감추기 위해 없는 리소스와 같은 `404`를 사용한다.

### 6. 요청·응답 핵심 계약

#### 환자 생성

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

#### 환자 목록·검색

```text
GET /api/v1/patients?category=NEEDS_ATTENTION&keyword=김&cursor=patient_102&limit=20
```

- `category`: `ALL/IN_TREATMENT/NEEDS_ATTENTION/SMS_OPT_OUT/INACTIVE_6_MONTHS`, 기본 `ALL`.
- 현재 계산 가능한 `ALL`, `SMS_OPT_OUT`, `INACTIVE_6_MONTHS`만 조회할 수 있다. 이벤트 기반 `IN_TREATMENT`, `NEEDS_ATTENTION`을 선택하면 후속 계약이 연결되기 전까지 `400 INVALID_REQUEST`로 명시적으로 거부하며, 빈 검색 결과처럼 응답하지 않는다.
- `keyword`: 이름, 차트번호, 정규화된 휴대폰에서 검색한다. 이름은 한 글자부터 허용한다.
- `cursor`: 서버가 발급한 불투명 다음 페이지 커서. 임의 조립하지 않는다.
- `limit` 기본 20, 최대 100.
- 응답은 `{counts, selected_category, items, page: {next_cursor, has_next}}`다.
- 목록 항목은 환자 기본정보와 `latest_visit` 요약을 포함한다. 동명이인 구분을 위해 생년월일, 차트번호, 전화번호 뒤 4자리, 최근 진료일을 모두 제공한다.

#### S1-1 날짜별 업무 목록

```text
GET /api/v1/front-desk/visits?date=2026-08-13&categories=IN_PROGRESS,NEEDS_ATTENTION&cursor=visit_501&limit=50
```

- `date`는 필수 `YYYY-MM-DD`이며 v1 병원 표시 시간대인 `Asia/Seoul`의 현지 날짜다.
- `categories`는 쉼표로 구분한 업무 카테고리다. 미입력 시 전체 카테고리를 조회한다.
- `cursor`는 서버가 발급한 불투명 커서다. `limit`은 기본 50, 최대 100인 cursor pagination을 사용한다.
- `NEEDS_ATTENTION`은 해결될 때까지 날짜와 무관하게 포함한다. 나머지 카테고리는 `visited_at`을 `Asia/Seoul`로 변환한 날짜가 요청한 `date`와 같은 진료만 포함한다.
- `age`는 저장값이 아니라 요청한 현지 날짜와 `birth_date`로 계산한다. 동명이인 확인과 계산 근거를 위해 응답에 두 값을 함께 제공한다.
- `diagnosis_name`은 확정된 구조화 진단명이 있을 때만 제공하며 미확정이면 `null`이다. 원문 의료문서는 포함하지 않는다.

업무 카테고리는 서버가 OCR·안내·승인·발송의 최신 이벤트를 읽어 다음 값으로 파생한다.

| 화면 탭 | `work_category` | 포함하는 `detail_status` |
|---|---|---|
| 작성 중 | `IN_PROGRESS` | `NO_DOCUMENT`, `OCR_REVIEW`, `GUIDE_GENERATING`, `STAFF_REVIEW` |
| 보완 | `NEEDS_ATTENTION` | `GENERATION_FAILED`, `INVALID_PHONE`, `SMS_OPT_OUT`, `APPROVAL_RETURNED` |
| 승인 요청 | `APPROVAL_REQUESTED` | `APPROVAL_PENDING` |
| 발송 대기 | `SEND_PENDING` | `SCHEDULED_TO_SEND` |
| 완료 | `COMPLETED` | `SENT`, `VIEWED` |

여러 이벤트가 동시에 존재하면 `NEEDS_ATTENTION → APPROVAL_REQUESTED → SEND_PENDING → IN_PROGRESS → COMPLETED` 순으로 하나의 `work_category`를 선택한다. `detail_status`는 해당 카테고리에서 가장 최근에 발생한 미해결 상태다.

- **카테고리 사이 우선순위가 먼저다.** 더 최근에 생긴 일이라도 위 순서를 뒤집지 않는다. 방금 승인 요청이 걸린 진료라도 보낼 곳이 없으면 `NEEDS_ATTENTION`이다.
- 「발생 시각」은 상태마다 이렇게 읽는다.
  - `APPROVAL_RETURNED` 등 안내문 상태 — 안내문이 마지막으로 움직인 시각
  - `SMS_OPT_OUT` — 환자가 수신을 거부한 시각
  - `INVALID_PHONE` — **시각이 없다.** 사건이 아니라 상태라 언제 그렇게 됐는지를 남기지 않는다. 시각을 아는 상태가 같은 카테고리에 있으면 그쪽을 보여 준다
- 같은 시각이면 위 표의 차례를 따른다. 같은 데이터에 화면이 흔들리지 않게 하기 위한 것이다.

```json
{
  "date": "2026-08-13",
  "timezone": "Asia/Seoul",
  "counts": {
    "IN_PROGRESS": 2,
    "NEEDS_ATTENTION": 1,
    "APPROVAL_REQUESTED": 1,
    "SEND_PENDING": 0,
    "COMPLETED": 3
  },
  "selected_categories": ["IN_PROGRESS", "NEEDS_ATTENTION"],
  "items": [
    {
      "visit_id": 501,
      "patient_id": 101,
      "name": "김서연",
      "hospital_patient_no": "12345",
      "birth_date": "1990-01-01",
      "age": 36,
      "diagnosis_name": null,
      "doctor": {"doctor_id": 12, "name": "박연"},
      "visited_at": "2026-08-13T10:32:00+09:00",
      "work_category": "IN_PROGRESS",
      "detail_status": "OCR_REVIEW"
    }
  ],
  "page": {"next_cursor": null, "has_next": false}
}
```

#### 환자 수정

- 수정 가능: `name`, `birth_date`, `gender`, `phone`, `sms_consent`.
- 일반 수정 불가: `patient_id`, `hospital_id`, `hospital_patient_no`, 생성·수정 메타데이터.
- 차트번호 오타 정정은 같은 `PATCH`에서 `hospital_patient_no`와 필수 `correction_reason`을 함께 보낸다. 요청자는 `admin`과 `staff` 또는 `doctor` 역할을 함께 가져야 하며, 해당 환자에게 진료가 한 건도 없어야 한다. 성공 시 변경 전후 값, 사유, 수행자, 시각을 감사 이벤트로 남긴다.
- 진료가 이미 있으면 `409 PATIENT_NUMBER_LOCKED`, 중복 번호면 `409 DUPLICATE_HOSPITAL_PATIENT_NO`다. 진료 이후의 정정·병합은 v1에서 제공하지 않는다.
- 빈 본문은 `400 EMPTY_UPDATE_FIELDS`다.
- 전화번호 또는 동의 변경은 예정 발송에 반영하고 감사 이벤트를 남기는 서비스 계층 작업이다.

#### 진료 생성

```json
{
  "doctor_id": 12,
  "department_id": 7,
  "visited_at": "2026-08-13T10:32:00+09:00",
  "visit_summary": null,
  "doctor_note": null,
  "status": "COMPLETED",
  "planned_stop": false
}
```

`patient_id`, `hospital_id`, `visit_id`, `department`를 본문에 입력하지 않는다. v1 목표 계약은 `department_id`가 같은 병원의 활성 진료과인지, 지정 의사가 그 진료과 소속인지 검증한 뒤 현재 명칭을 `visit.department`에 스냅샷으로 저장하는 것이다. 현재는 진료과 기준 모델과 직원-진료과 관계가 없어 `department_id`의 non-null 입력을 `400 INVALID_DEPARTMENT`로 거부하며, 미검증 스냅샷을 저장하지 않는다.

`doctor_id`는 같은 병원의 재직 중인 `doctor` 역할 직원만 허용한다. `null`은 담당의 미지정이며 수정에서는 담당의 해제로 해석한다. 존재하지 않음·타 병원·퇴사·비의사 조건은 직원 정보 노출을 피하기 위해 모두 `400 INVALID_REQUEST`로 응답한다.

#### 진료 목록

```text
GET /api/v1/patients/{patient_id}/visits?cursor=visit_501&limit=20
```

- `visited_at DESC, visit_id DESC`로 안정 정렬한다.
- 응답은 `{items, page: {next_cursor, has_next}}`다.
- 안내·발송·D+7 요약은 각 도메인의 구조화된 요약만 결합하며 원문 의료문서나 챗봇 대화 원문을 포함하지 않는다.

#### 진료 수정

- 수정 가능: `doctor_id`, `department_id`, `visited_at`, `visit_summary`, `doctor_note`, `status`, `planned_stop`.
- 현재 `department_id` 변경은 진료과 기준 모델이 없어 `400 INVALID_DEPARTMENT`로 거부한다. 기준 모델 연결 뒤 생성과 같은 활성 진료과·의사 소속 검증 및 `department` 스냅샷 갱신을 적용한다.
- `department_id: null`은 담당 진료과 해제로 해석하여 `department` 스냅샷을 삭제한다. 단, OCR 또는 승인 안내가 연결되어 `VISIT_LOCKED`가 된 진료에는 같은 잠금 규칙을 적용해 삭제도 차단한다.
- OCR 처리(`PROCESSING`·`COMPLETED`) 또는 승인 안내(`APPROVAL_PENDING`·`SCHEDULED_TO_SEND`) 연결 뒤 `department_id`, `doctor_id`, `visited_at`의 실제 변경은 `409 VISIT_LOCKED`다. `FAILED` OCR만 연결된 진료는 잠그지 않는다.
- 잠금된 진료에도 `visit_summary`, `doctor_note`, `status`, `planned_stop`은 수정할 수 있다. 잠금 대상 필드를 본문에 포함하더라도 저장된 값과 같으면 관계 변경이 아니므로 허용한다.
- `patient_id`, `hospital_id`, `visit_id`는 수정할 수 없다. 특히 `patient_id`는 요청 DTO에 없고 추가 필드 입력이 금지되어 공통 `400 INVALID_REQUEST`로 거부된다.

### 7. 오류 계약

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
| 409 | `PATIENT_NUMBER_LOCKED` | 진료가 연결된 환자의 차트번호 정정 시도 |
| 409 | `VISIT_ALREADY_REGISTERED` | 같은 환자의 같은 날짜 진료 중복 |
| 409 | `VISIT_LOCKED` | 후속 데이터 연결 뒤 관계 변경 시도 |
| 400 | `INVALID_DEPARTMENT` | 진료과가 없거나 비활성 또는 타 병원 소속 |
| 400 | `DOCTOR_DEPARTMENT_MISMATCH` | 직원-진료과 관계 연결 뒤 적용할 예약 코드. 현재 구현은 반환하지 않음 |
| 400 | `INVALID_REQUEST` | 필드 형식·enum·범위 오류 |
| 400 | `EMPTY_UPDATE_FIELDS` | PATCH 본문에 수정 가능 필드 없음 |

환자·진료 도메인의 오류 `code`는 `UPPER_SNAKE_CASE`로 고정한다. 직원 인증의 기존 소문자 코드는 [공통 오류 호환 규칙](common.md#5-오류와-변경-관리)에 따라 별도 변경 작업 전까지 유지한다.

### 8. 화면 데이터 추적

| 화면 | 계약 필드 |
|---|---|
| S1-1 | `/front-desk/visits?date`, 이름·차트번호·생년월일·파생 나이·확정 진단명·담당의·업무 카테고리, cursor pagination |
| S1-2 | `name`, `birth_date`, `phone`, `hospital_patient_no`, `latest_visit.visited_at` |
| S1-3 | 환자 생성 필드 + 생성 후 반환된 `patient_id` |
| S1-4 | 환자 상세 + 오늘 진료 + `GET /patients/{id}/visits` |
| S1-5~S1-14 | `visit_id`를 OCR·안내·발송 계약에 전달 |
| S2-1 | 환자 목록 + `latest_visit` + 구조화된 진행 상태 요약 |
| S2-2 | 진료 목록 + 발송·열람·체크인 구조화 요약 |
| S2-3·S2-4 | `patient_id`, `visit_id`, `guide_document_id`로 발송 추적 |
| P7-1~P7-6 | `check_in_id`를 경로로 사용하고 `CHECKIN.guide_document_id` → `GUIDE_DOCUMENT.visit_id/patient_id`로 추적 |

### 9. 기존 명세 불일치 처리

| 기존 값 | v1 처리 | 상태 |
|---|---|---|
| `age` 저장 | `birth_date` 저장, 나이 파생 | 수정 |
| 환자 `gender`는 API에 있으나 ERD에 없음 | ERD·모델에 `gender` 추가 | 수정 |
| Notion `gender=FEMALE/MALE/OTHER/UNKNOWN`, rc1은 두 값만 명시 | 네 값과 `UNKNOWN` 기본값으로 통일 | 수정 |
| `chart_number`가 MedicalRecord에 있고 전역 유일 | `patient.hospital_patient_no`, 병원 내 유일 | 수정 |
| Notion `chart_no` | 리소스 API는 `hospital_patient_no`; 화면 조합 응답도 같은 이름으로 수정 | 수정 |
| Notion `sms_consent_at` | `sms_consented_at`으로 수정 | 수정 |
| Notion `visit_date` | 저장·리소스 API는 `visited_at`; 화면 표시에서는 날짜를 파생 | 수정 |
| Notion `department_id`, ERD `department` | 화면·리소스 명령 모두 `department_id`를 받아 활성·의사 소속을 검증하고, VISIT에는 당시 명칭을 `department` 스냅샷으로 저장 | 매핑 확정 |
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
| S1-1 탭 이름만 있고 서버 상태값·응답·페이지네이션 없음 | 다섯 `work_category`, 상세 상태 매핑, 응답 필드, cursor pagination 확정 | 수정 |
| UTC 저장과 날짜별 화면·중복 판정의 시간대 불명확 | v1 병원 표시 시간대 `Asia/Seoul` 기준으로 날짜 그룹화·중복 판정 | 수정 |
| 차트번호 생성 후 영구 불변 | 진료가 없고 `admin`+임상 역할인 경우 감사 사유를 남겨 제한 정정 | 수정 |

#### 처방 계약 경계

처방을 VISIT의 JSON 필드로 추가하지 않는다. `PRESCRIPTION(visit_id)` 1:N `PRESCRIPTION_ITEM(duration_days 포함)`이 실제 처방과 약·용법·처방일수를 소유한다. 소진 예정일과 D+7 판정은 확정된 `PRESCRIPTION_ITEM.duration_days`만 사용한다.

**세트 출처는 표가 아니라 스냅샷 문자열이다** — [KEY-137](https://leehee.atlassian.net/browse/KEY-137)에서 확정했다. ERD v11이 적어 둔 `PRESCRIPTION_SET_VERSION` 템플릿 표는 저장소 어디에도 없고, 합성 정본이 그 자리에 담고 있는 값은 id가 아니라 **사람이 읽는 이름**이다(8종 · 최대 17자). 그래서 칸 이름도 담고 있는 것대로 `prescription.prescription_set`(`varchar(100)`)이다. `..._id`라는 이름을 두면 다음 사람이 조인할 표를 찾게 된다.

세트가 개정돼도 그 진료가 무엇을 근거로 했는지는 바뀌면 안 되므로, 템플릿 표가 생기더라도 이 칸은 `visit.department`처럼 **그때의 이름을 남기는 스냅샷**으로 유지하고 FK를 따로 더한다.

#### 별도 확인 항목

- Notion의 P7 상세는 `P7-1~P7-5`로 표기되어 있으나 정본 와이어프레임에는 저장 완료 `P7-6`이 있다. 구현·테스트 범위는 정본의 `P7-1~P7-6`으로 유지한다.
- `chat_export`는 사용자의 KEY-9·KEY-11 확정사항에 따라 유지한다. 통제되지 않은 DB 직접 조회는 애플리케이션이 자동 기록할 수 없으므로, 운영 추출은 별도 승인 도구/절차가 `event_log`를 남기는 경우만 허용한다.

### 10. 동결 절차와 변경 규칙

- 한금준이 전체 API 규칙, 공통 오류 모양과 `UPPER_SNAKE_CASE` 전환, ID 타입, 페이지네이션을 검수한다.
- S1-1 구현은 이 문서의 `work_category/detail_status` 매핑과 `Asia/Seoul` 날짜 규칙을 공통 상태 파생 모듈로 한 번만 구현한다.
- 승인 전 상태는 `v1.0-rc1`이며 KEY-31은 필드명·관계를 이 문서와 다르게 구현하지 않는다.
- 승인 시 이 문서의 상태를 `v1.0-frozen`으로 바꾸고 승인자·승인일을 기록한다.
- 동결 뒤 변경은 같은 PR에서 이 문서, 관련 모델·마이그레이션, 화면 영향 ID를 함께 수정한다.
- OCR·안내·챗봇 상세 본문은 이 계약의 범위 밖이며 `patient_id`, `visit_id` 연결 규칙만 공유한다.

## 4. OCR


### 엔드포인트

| Method | Path | 용도 |
| --- | --- | --- |
| `GET` | `/api/v1/visits/{visit_id}/ocr-job` | 진료의 현재 OCR 작업 조회 (KEY-133) |
| `GET` | `/api/v1/ocr/jobs/{ocr_job_id}` | 처리 상태·진행률 조회 |
| `GET` | `/api/v1/ocr/jobs/{ocr_job_id}/result` | 전체 텍스트와 구조화 결과 조회 |
| `GET` | `/api/v1/ocr/jobs/{ocr_job_id}/fields` | 구조화 필드·신뢰도·후보 조회 |
| `PATCH` | `/api/v1/ocr/fields/{ocr_field_id}` | 수정값 또는 후보 선택과 확정 |

`GET /visits/{visit_id}/ocr-job`은 해당 진료의 현재 OCR 작업을 반환합니다.
`PROCESSING` 상태 작업이 있으면 그것을 우선 반환하고, 없으면 `created_at` 내림차순
최신 작업을 반환합니다. 작업이 없으면 `404 NOT_FOUND`를 반환합니다.

수정 API는 `base_version`을 요구하고 버전이 달라지면 `409 VERSION_CONFLICT`를
반환합니다. 이미 확정된 필드는 다시 수정하지 않습니다. 타 병원 식별자는 존재
여부를 숨기기 위해 `404 NOT_FOUND`로 통일합니다.

OCR 도메인 오류는 동결 계약의 `code`, `message`, `field_errors` 응답 구조를
사용합니다. 요청 검증 오류는 KEY-11로 `develop`에 병합된 공통 마스킹 처리기를
그대로 사용하며 OCR 라우터가 별도로 가로채지 않습니다. 공통 검증 오류를 동결
계약의 400 응답으로 전환하는 작업은 전체 API 계약 변경에서 일괄 적용합니다.

### 판독 항목의 상태 어휘 — `field_status`

> 결정 2026-08-21 · [KEY-109](https://leehee.atlassian.net/browse/KEY-109) · 담당 권일준 · 리뷰어 이희진
> 근거: `#40`(KEY-62) 검수 · 와이어프레임 `S1-7`
>
> **결정 완료 · 서버 미구현.** 모델·마이그레이션·`PATCH` 구현 전까지 화면은 목업으로 돕니다.

지금은 「값이 없다」가 한 덩이라 스탭이 무엇을 해야 하는지 알 수 없습니다. 넷으로 가릅니다.

| 상태 | 뜻 | 누가 판정하나 | 스탭이 할 일 |
|---|---|---|---|
| `READ` | 읽었고 값이 있다 | 기계 | 맞는지 본다 |
| `UNREADABLE` | 문서에 있는데 못 읽었다 | 기계 | **채워야 한다** |
| `PENDING_REPORT` | 문서가 「추후 보고 예정」이라 한다 | 기계 | 없다 — 기다린다 |
| `NOT_PERFORMED` | 이번엔 검사를 안 했다 | **사람** | 표시하고 넘어간다 |

`OcrJob.status = FAILED`는 **작업 전체**의 상태입니다. 항목 상태와 층이 다르므로 같은 목록에 넣지 않습니다 — 섞으면 「한 항목이 실패」와 「판독이 실패」가 구별되지 않습니다.

**「누가 말했는지」를 위한 칸은 새로 두지 않습니다.** `OcrField`가 이미 `extracted_value`·`confidence`(기계)와 `corrected_value`·`modified_by`(사람)를 갖고 있습니다. 두 곳에 같은 뜻을 두면 어긋날 자리도 함께 생깁니다.

#### 「확인할 항목」 계수

```text
UNREADABLE       센다     값이 있는데 못 읽었다 — 사람이 넣어야 한다
PENDING_REPORT   뺀다     기다리는 것 말고 할 일이 없다
NOT_PERFORMED    뺀다     비어 있는 게 맞다
```

`PENDING_REPORT`를 세면 스탭이 영원히 막힙니다 — AMH 결과가 두 주 뒤에 나오는데 그때까지 안내문을 못 만듭니다. `submit` 잠금은 `UNREADABLE`과 값 충돌만 막습니다.

#### 계약 변경

```text
OcrField
  + field_status  READ | UNREADABLE | PENDING_REPORT | NOT_PERFORMED   기본 READ

PATCH /api/v1/ocr/fields/{ocr_field_id}
  + field_status  선택. 사람이 보낼 수 있는 값은 NOT_PERFORMED 와 READ 뿐이다.
                  UNREADABLE · PENDING_REPORT 은 기계가 판정한다 — 사람이 보내면 400.
  기존 규칙 유지 — corrected_value 와 candidate_id 는 함께 못 보낸다.
                  field_status=NOT_PERFORMED 이면 값도 함께 보낼 수 없다.
```

되돌리기는 `field_status: "READ"`로 보냅니다. 빠져나갈 길이 없으면 스탭은 새 판독을 올립니다.

#### 하지 않기로 한 것

- **「이전 값 유지」** — 앞 진료의 검사값을 이번 판독에 복사하지 않습니다. 옛 측정치가 이번 측정치의 자리에 앉고, 안내문은 그 자리를 「지금」이라고 말합니다. 의무기록이라 되짚을 근거도 남지 않습니다. 대신 안내문이 출처와 날짜를 함께 말합니다(「지난 검사 (05-20) 10.2」) — [KEY-75](https://leehee.atlassian.net/browse/KEY-75) 몫이고, 지난 값을 담을 `lab_result` 표는 [KEY-136](https://leehee.atlassian.net/browse/KEY-136)이 계획으로 두었습니다.
- **OCR 전체 실패 뒤 직접 입력** — v1 범위 밖입니다. 작업이 `FAILED`면 결과가 없고, 결과가 없으면 채워 넣을 항목 목록 자체가 없습니다. 재업로드가 1순위입니다 — 실패는 대개 사진이 흐리거나 잘린 것이고, 손으로 넣은 오타는 그대로 의무기록이 됩니다.

#### 남은 몫

- `PENDING_REPORT`를 **서버가 내려주는 것** — [KEY-134](https://leehee.atlassian.net/browse/KEY-134). 지금은 목업만 `pending_report`를 줍니다.
- `field_status` **모델·마이그레이션·`PATCH` 구현** — 서버 몫.

### 권한·개인정보

- `staff` 또는 `doctor` 역할만 접근할 수 있습니다. `admin` 단독 사용자는 차단합니다.
- 모든 ORM 조회에 인증 사용자의 `hospital_id` 범위를 적용합니다.
- 문서 소유권은 문서·진료·병원이 모두 일치하는 권위 있는 업로드 저장소에서
  검증합니다. 해당 저장소가 연결되기 전에는 작업 생성을 기본 차단합니다.
- 작업 생성은 진료 행을 잠근 트랜잭션 안에서 소유권과 기존 `PROCESSING` 작업을
  확인해 동시 요청의 중복 생성을 막습니다.
- 원문과 필드값을 로그에 기록하지 않습니다.
- 테스트 데이터는 `합성 추출값`, `합성 수정값`만 사용합니다.
- 승인 이후 원문 파기는 KEY-59의 `purge_raw_text`와 승인 트랜잭션을 연결해야 합니다.

### 현재 통합 제한

현재 `develop`의 `User` 모델에는 KEY-9/KEY-21의 `hospital_id`와 `roles`가 아직
병합되지 않았습니다. 이 값이 없으면 서버는 기본 차단합니다. 직원 모델이 병합될
때 `get_ocr_actor`를 실제 직원 컨텍스트에 연결해야 합니다. KEY-73의 직원 PK인
`staff_id`와 기존 `User.id`를 모두 인식하되 최종 통합 후 직원 컨텍스트 하나로
고정합니다.

KEY-53의 권위 있는 문서 모델·저장소가 아직 없으므로 기본 소유권 검증기는 작업
생성을 `404`로 차단합니다. KEY-53 통합 시 문서의 `document_id`, `visit_id`,
`hospital_id`를 같은 트랜잭션에서 검증하고 잠그는 구현을 주입해야 합니다.

OCR 엔진 실행은 AI worker가 `ocr_job`의 `PROCESSING` 작업을 가져가 결과를 쓰는
경계입니다. 본 API는 작업 생성과 결과 검수 계약을 담당하며 OCR 추론 구현이나
문서 업로드 저장소는 포함하지 않습니다.

최신 Notion에서 삭제 상태인 재판독 API와 일괄 결과 수정 API는 구현하지 않았습니다.
KEY-60에 명시된 필드 단위 조회·수정 계약만 유지했습니다.

### 응답 스키마 — OcrFieldResponse

`GET /ocr/jobs/{id}/result` · `GET /ocr/jobs/{id}/fields` · `PATCH /ocr/fields/{id}` 의 필드 항목.

| 필드 | 타입 | 설명 |
|---|---|---|
| `ocr_field_id` | `int` | 필드 PK |
| `field_type` | `string` | 필드 구분자 (예: `DIAGNOSIS`, `HB`) |
| `extracted_value` | `string \| null` | OCR 엔진 추출값 |
| `corrected_value` | `string \| null` | 사람이 수정한 값 |
| `value` | `string \| null` | 표시값 — `corrected_value` 우선, 없으면 `extracted_value` |
| `unit` | `string \| null` | 검사값 단위 (예: `mg/dL`, `cm`) |
| `confidence` | `float \| null` | OCR 신뢰도 0–1 |
| `is_low_confidence` | `bool` | 서버 판정 저신뢰 여부 — 임계값 0.75, 화면이 임의로 정하지 않는다 |
| `version` | `int` | 낙관적 잠금 버전 — PATCH 요청 시 `base_version`으로 전달 |
| `is_confirmed` | `bool` | 확정 여부 — `true`이면 수정 불가 |
| `is_pending_report` | `bool` | "별도 보고 예정" 상태 (예: AMH 추후 보고) |
| `document_id` | `int \| null` | 출처 문서 ID — 원문 파기 후에는 `null` |
| `source_line` | `int \| null` | 출처 줄 번호 — 원문 해당 줄 이동에 사용 |
| `modified_by` | `int \| null` | 수정한 직원 PK |
| `modified_at` | `datetime \| null` | 수정 시각 |
| `confirmed_by` | `int \| null` | 확정한 직원 PK |
| `confirmed_at` | `datetime \| null` | 확정 시각 |
| `candidates` | `OcrCandidateResponse[]` | 복수 후보 목록 (없으면 빈 배열) |

### 응답 스키마 — OcrCandidateResponse

같은 필드에 복수 판독값이 있을 때 `candidates` 배열 항목.

| 필드 | 타입 | 설명 |
|---|---|---|
| `ocr_field_candidate_id` | `int` | 후보 PK |
| `value` | `string` | 후보값 |
| `confidence` | `float \| null` | 후보 신뢰도 0–1 |
| `rank` | `int` | 순위 (1이 기본 선택) |
| `source_date` | `date \| null` | 후보값의 검사일 |
| `source_line` | `int \| null` | 후보값 출처 줄 번호 |
| `document_id` | `int \| null` | 후보값 출처 문서 ID — 원문 파기 후에는 `null` |
| `is_selected` | `bool` | 현재 선택된 후보 여부 |

> `document_id`·`source_line`은 원문 파기 후 항상 `null`을 반환합니다.
> 줄 번호만으로는 원문에 접근할 수 없으므로 `document_id=null`이면 출처 이동 버튼을 비활성화합니다.

## 5. 안내 생성·승인·반려

> 상위 일감: `KEY-111`(`KEY-76` 인수조건, 와이어프레임 D1-1~D1-5), `KEY-150`(확정 OCR→고정 안내→의사 승인 연결)

### 엔드포인트

| Method | Path | 용도 | 권한 |
|---|---|---|---|
| POST | `/api/v1/visits/{visit_id}/guide/generate` | 확정 OCR로 고정 안내 생성 — 201 | `staff`·`doctor` |
| GET | `/api/v1/visits/{visit_id}/guide` | 안내문 조회 — 다섯 갈래 + ⚠ 표시 | `staff`·`doctor` |
| PATCH | `/api/v1/visits/{visit_id}/guide/sections/{key}` | 한 갈래만 수정 | `doctor` |
| POST | `/api/v1/visits/{visit_id}/guide/approve` | 승인 — 발송 예약 | `doctor` |
| POST | `/api/v1/visits/{visit_id}/guide/return` | 스탭에 되돌림 (사유 필수) | `doctor` |
| POST | `/api/v1/visits/{visit_id}/guide/link` | 72시간 개발용 환자 링크 1회 발급 (`demo_only`) | `staff`·`doctor` |

`admin` 단독 사용자는 승인·반려·수정을 할 수 없다 — `admin`은 역할이 아니라 권한이며, 의료 판단을 한다는 뜻이 아니다.

### 상태값

| 상태 | 의미 | 화면 탭 |
|---|---|---|
| `STAFF_REVIEW` | 스탭 확인 중 | 작성 중 |
| `APPROVAL_PENDING` | 승인 요청 | 승인 요청 |
| `SCHEDULED_TO_SEND` | 발송 예약됨 | 발송 대기 |
| `APPROVAL_RETURNED` | 승인 반려 | 보완 |

새 이름을 만들지 않는다 — 위 값은 `docs/contracts/patient-visit-api-v1.md` §6의 `detail_status`와 같은 어휘다. **승인의 결과는 `APPROVED`가 아니라 `SCHEDULED_TO_SEND`다** — 승인이 곧 발송 예약이며, 승인과 발송 사이에 사람이 다시 손대는 자리를 두지 않는다(D1-5).

### 안내문 조회 응답

```json
{
  "visit_id": 501,
  "patient": {
    "name": "김서연",
    "birth_date": "1990-01-01",
    "age": 36,
    "gender": "FEMALE",
    "hospital_patient_no": "SYN-12345"
  },
  "summary": "자궁내막증 · 비잔 (계속) · 84일 · 지난 방문 05-20",
  "status": "APPROVAL_PENDING",
  "version": 3,
  "approved_at": null,
  "scheduled_at": null,
  "returned_reason": null,
  "sections": [
    {"key": "medication", "body": "...", "edited": false, "locked": false, "warn": "AMH 결과가 아직 안 나왔습니다 — 값이 빠진 자리입니다"},
    {"key": "caution", "body": "...", "edited": false, "locked": false, "warn": null},
    {"key": "emergency", "body": "...", "edited": false, "locked": true, "warn": null},
    {"key": "life", "body": "...", "edited": false, "locked": false, "warn": null},
    {"key": "messages", "body": "...", "edited": false, "locked": false, "warn": null}
  ]
}
```

- `patient`·`summary`는 승인 화면이 「누구 것인지」를 알아야 하므로 응답에 포함한다. `phone`은 포함하지 않는다 — 승인할 때마다 전화번호가 화면과 로그를 지날 이유가 없다.
- `age`는 저장값이 아니라 조회 시점의 현지 날짜와 `birth_date`로 계산한다. 동명이인 확인과 계산 근거를 위해 `birth_date`와 `age`를 함께 제공한다(계약 §4).
- `sections[]`은 다섯 갈래(`medication`/`caution`/`emergency`/`life`/`messages`) 고정이며 각 항목은 `body` 문자열 하나다. 8/27 여정에서 안내문은 고정 텍스트라(`KEY-150` — 「확정 OCR→고정 안내→의사 승인」), 제목·표·목록으로 나눈 구조화 콘텐츠 모델(`blocks`)은 이번 계약에 포함하지 않는다. 실제 LLM 생성이 붙을 때 다시 정한다.
- `warn`·`locked`는 섹션 단위다. `warn`은 AI가 자신 없는 곳·지난 진료와 달라진 곳·값이 빠진 곳에만 서버가 판정해 채운다 — 화면은 판정하지 않는다. `locked`는 🚨 응급 문장(식약처 의약품정보 기준)이라는 뜻의, 이유 문자열이 없는 boolean이다. 다른 이유로 잠기는 섹션이 생기면 이유 필드를 추가하는 계약 변경이 필요하다.
- `edited`는 사람이 고쳤는지를 말한다. 생성 원문은 서버에 별도로 보관하며 이 응답에는 포함하지 않는다.

### 안내 생성

```text
POST /api/v1/visits/{visit_id}/guide/generate
→ 201 Created
```

- `staff`·`doctor` 역할 모두 호출할 수 있다.
- 진료에 연결된 OCR 필드 중 `is_confirmed=True`인 것이 하나 이상 있어야 한다 — 미확정 값으로 안내를 만들면 스탭이 수정한 사실이 사라지고, 의사는 OCR 원본인지 사람이 고친 것인지 알 수 없는 글을 승인하게 된다.
- 안내는 `APPROVAL_PENDING` 상태로 생성된다 — W1 고정 안내 경로는 스탭 검토(`STAFF_REVIEW`) 단계를 거치지 않는다. LLM 생성 안내가 붙는 시점에 이 흐름을 다시 정한다.
- 섹션은 `medication`·`caution`·`emergency`·`life`·`messages` 5개 고정이며, **응답 차례가 곧 화면 차례**다(`emergency`는 `caution` 바로 뒤).
- **`emergency`만 `locked=true`다.** 식약처 의약품정보 기준 응급 문장이라 사람이 고칠 수 없다(D1-2). `caution`은 일반 주의 문구이고 `locked=false`이므로 의사가 환자에 맞춰 고칠 수 있다.
  - 나눈 까닭은 잠금 단위 때문이다. `locked`는 섹션 단위라 한 갈래에 두면 응급 문장을 지키려다 일반 문구까지 잠긴다(`KEY-161`).
  - **화면은 새 탭을 만들지 않는다.** 두 갈래를 같은 「주의사항」 탭 안에 이어서 그린다 — 따로 탭이면 열지 않고 승인할 수 있다.
- 같은 진료에 안내가 이미 있으면 `409 GUIDE_ALREADY_EXISTS`다.
- 응답은 안내문 조회와 같은 전체 모양이다.

### 섹션 수정

```text
PATCH /api/v1/visits/{visit_id}/guide/sections/{key}
{"body": "..."}
```

- `doctor` 역할만 호출할 수 있다.
- `locked`인 섹션은 `409 SECTION_LOCKED`다.
- 안내문이 `APPROVAL_PENDING` 상태가 아니면 `409 GUIDE_NOT_PENDING`이다 — 승인 요청 상태에서만 고칠 수 있다.
- 응답은 수정된 섹션 하나(`{key, body, edited, locked, warn}`)만 돌려준다.

### 승인

```text
POST /api/v1/visits/{visit_id}/guide/approve
```

- `doctor` 역할만 호출할 수 있다.
- 승인은 상태를 `SCHEDULED_TO_SEND`로 바꾸고 `scheduled_at`을 함께 채운다 — 두 동작을 나누지 않는다.
- `scheduled_at`은 병원 표시 시간대(`Asia/Seoul`) 기준 그날 18:00이며, 이미 지났으면 다음 날 18:00이다. 계산은 받은 시각이 어느 시간대든 `Asia/Seoul`로 옮긴 뒤 판단한다 — 저장 모드(`use_tz`)와 무관하게 같은 순간을 가리켜야 한다.
- 이미 `SCHEDULED_TO_SEND`면 `409 ALREADY_APPROVED`, `APPROVAL_PENDING`이 아니면 `409 GUIDE_NOT_PENDING`이다.
- 응답은 안내문 조회와 같은 전체 모양이다. 수신번호(`phone`)는 포함하지 않는다 — 이 화면은 「누구인지」만 알면 되고 발송 번호는 서버가 안다.

### 반려

```text
POST /api/v1/visits/{visit_id}/guide/return
{"reason": "검사 결과지를 다시 올려 주세요"}
```

- `doctor` 역할만 호출할 수 있다.
- `reason`은 필수이며 최대 200자다. 비어 있으면 `422 REASON_REQUIRED`, 초과하면 `422 REASON_TOO_LONG`이다.
- 이 문장은 스탭 알림에 그대로 뜬다(D1-7 「승인 반려 — 진료기록 재업로드 필요」). **최신 상태 표시는 `GuideDocument.returned_reason`을 쓰고, 감사 이력 조회는 `GuideEvent.reason`을 쓴다** — 같은 문장을 각자의 용도로 보관하며, 알림 API는 이 역할 구분을 따른다.

### 동시성·격리

- 상태 확인·변경과 이력 기록은 한 트랜잭션 안에서 행을 잠그고(`select_for_update`) 수행한다. 동시에 들어온 승인·반려·수정 요청이 모두 `APPROVAL_PENDING`을 읽고 함께 통과하는 경합을 막는다 — 의사가 승인한 내용과 실제 발송 내용이 달라지면 안 된다.
- 병원 격리는 `visit.hospital_id`를 타고 판단한다. `guide_document.hospital_id`는 목록 조회용 인덱스 사본이라 격리 판정에는 쓰지 않는다. 타 병원 안내문은 존재 여부를 감추기 위해 `404 GUIDE_NOT_FOUND`다.

### 오류 계약

| HTTP | code | 조건 |
|---:|---|---|
| 403 | `FORBIDDEN` | 승인·반려·수정에 `doctor` 역할 없음 |
| 404 | `VISIT_NOT_FOUND` | 진료 없음 또는 타 병원 진료 (generate) |
| 404 | `GUIDE_NOT_FOUND` | 안내문 없음 또는 타 병원 안내문 |
| 404 | `SECTION_NOT_FOUND` | 없는 섹션 키 |
| 409 | `GUIDE_ALREADY_EXISTS` | 같은 진료에 안내가 이미 있는데 generate 재시도 |
| 409 | `SECTION_LOCKED` | 잠긴(🚨 응급) 섹션 수정 시도 |
| 409 | `GUIDE_NOT_PENDING` | 승인 요청 상태가 아닌데 수정·승인·반려 시도 |
| 409 | `ALREADY_APPROVED` | 이미 승인된 안내문 재승인 시도 |
| 422 | `OCR_NOT_CONFIRMED` | 확정된 OCR 항목 없이 generate 시도 |
| 422 | `EMPTY_BODY` | 섹션 수정 본문 빈 값 |
| 422 | `REASON_REQUIRED` | 반려 사유 빈 값 |
| 422 | `REASON_TOO_LONG` | 반려 사유 200자 초과 |

### 남은 결정

- `generate`는 W1 고정 안내 경로로 `STAFF_REVIEW` 단계 없이 바로 `APPROVAL_PENDING`으로 만든다. LLM 생성 안내가 붙을 때 `STAFF_REVIEW` 단계와 스탭 편집 경로를 다시 정한다.
- 승인 전 환자 조회 차단(`APPROVAL_PENDING` 상태에서 환자 모바일 API 접근 불가)은 환자 링크·OTP·모바일 영역(KEY-4)에서 구현한다. `generate`는 DB 상태를 `APPROVAL_PENDING`으로 설정하는 것으로 이 게이트의 전제를 만든다.
- `locked`가 이유 문자열 없는 boolean인 것은 지금 유일하게 잠기는 `emergency` 섹션(🚨 응급 문장)에는 맞지만, 다른 이유로 잠기는 섹션이 생기면 이유 필드를 추가하는 계약 변경이 필요하다.

#### 구조화된 문자 설정은 이 계약의 범위가 아니다

`messages`는 다른 섹션과 **같은 평문 `body`**다. 와이어프레임 `S1-14`·`D1-4`가 그리는 회차 체크박스(D+7·D+15·D+30·소진 임박), 템플릿 이름, 미리보기 같은 **구조화된 설정은 `GuideResponse`에 없다.**

```text
있는 것   sections[] 안의 { key: "messages", body: "…" } 평문 한 덩이
없는 것   schedule · send_at · template_name · preview · preview_meta
          그 설정을 저장할 자리 · 실제 SMS 발송 · 예약 실행기 · 발송 이력
```

**승인은 `scheduled_at`을 채우는 데까지다.** 그 뒤에 문자를 보내는 것은 아무것도 없다. 화면이 「자동 발송됩니다」라고 말하면 안 되는 이유이고, 의사 승인 화면은 그 자리에 `[demo]` 표시를 둔다([KEY-160](https://leehee.atlassian.net/browse/KEY-160) · `docs/qa/KEY-148-walking-skeleton.md` §6).

구조화된 문자 설정은 **스탭과 의사가 같은 설정을 공유하는 별도 메시지 자원**으로 `S1-14` 후속 계약에서 다룬다. 신규 엔드포인트·DTO·권한·모델이 KEY-2(안내 승인)와 KEY-4(환자 전달)에 걸치는 계약 변경이라, 구현 전에 합의하고 별도 일감으로 만든다.

## 6. 환자·진료 구현 기록


> 상위 일감: KEY-16

### 구현 범위

- `POST/GET /api/v1/patients`
- `GET/PATCH /api/v1/patients/{patient_id}`
- `POST/GET /api/v1/patients/{patient_id}/visits`
- `GET/PATCH /api/v1/visits/{visit_id}`
- 병원 범위 조회, `staff`·`doctor` 역할 검사, 중복·404·403 오류 계약
- 서명된 cursor pagination과 `Asia/Seoul` 현지 날짜 기준 중복 진료 검사

요청 본문의 `hospital_id`, `patient_id`, `visit_id`는 허용하지 않습니다. 병원 범위는
인증된 직원 컨텍스트에서만 가져오며 타 병원 리소스는 존재 여부를 숨기기 위해
`404`로 응답합니다. 테스트 데이터는 `SYN-` 식별자의 합성값만 사용합니다.

### 현재 통합 경계

현재 `User` 모델에는 확정된 `staff.hospital_id`와 `roles`가 아직 병합되지 않았습니다.
따라서 API 의존성은 해당 속성이 없는 로그인 주체를 허용하지 않고 `403`으로
차단합니다. KEY-73의 Staff·Hospital 관계가 병합되면 같은 의존성이 인증 컨텍스트의
값을 사용하며, 클라이언트가 병원 값을 지정하는 우회 경로는 생기지 않습니다.

KEY-73의 Staff 기준 테이블이 병합되어 `doctor_id`는 같은 병원의 재직 중인 `doctor`
역할 직원인지 검증한 뒤 저장합니다. 진료과 기준 테이블과 직원-진료과 관계는 아직
없으므로 non-null `department_id`는 `INVALID_DEPARTMENT`로 안전하게 실패합니다.
직원-진료과 관계가 연결되기 전에는 `DOCTOR_DEPARTMENT_MISMATCH`를 반환하지 않습니다.

환자번호 제한 정정은 `admin`과 임상 역할을 함께 가진 사용자, 진료가 없는 환자,
필수 정정 사유 조건까지 검사합니다. 감사 이벤트 테이블이 병합되기 전에는 실제 운영
활성화 대상에서 제외하며, 이벤트 기록 연결은 감사로그 담당 일감의 선행 조건입니다.

## 7. 아직 연결 중인 영역

아래 영역은 관련 Jira 인수조건과 병합된 구현을 기준으로 엔드포인트와 DTO가 확정될 때 이 문서에 추가한다.

- 의료문서 업로드·임시 저장
- 환자 링크 발급 관리
- D+7 응답 병원 조회
- 관리자·감사로그

확정되지 않은 경로와 필드를 문서에서 먼저 만들어 구현 범위를 넓히지 않는다.
