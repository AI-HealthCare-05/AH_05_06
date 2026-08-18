# `app/models/` 배치 초안 — 22표를 일곱 파일로

> 대상 저장소 — `AI-HealthCare-05/AH_05_06` · 템플릿 계층(`models → repositories → services → dtos → apis`)을 그대로 따른다.
> 짝 문서 — [`spec-medical.md`](spec-medical.md) · [`spec-patient.md`](spec-patient.md) · [`spec-admin.md`](spec-admin.md)
> **이 문서는 초안이다.** 3장의 「먼저 정할 것 셋」이 닫히기 전에는 코드를 시작하지 않는다.

---

# 0. 나눠지는 축이 둘이다

구조화가 「기능과 역할을 잘 나누기 위함」이라고 할 때, 사실 **서로 다른 두 장대**를 한 말로 부르고 있다.

| 축 | 나누는 것 | 누가 정했나 |
|---|---|---|
| **가로 — 계층** | **책임** — 각 층이 무엇까지 알아도 되는가 | 템플릿이 이미 정해 놓았다 |
| **세로 — 도메인** | **무엇을 다루는가** — 진료인가 발송인가 기록인가 | **이 문서가 정한다** — 지금 `users` 하나뿐이라 비어 있다 |

둘은 **서로 수직**이다. 계층을 잘 나눠도 도메인을 못 나누면 `models/models.py` 한 파일에 22표가 쌓이고, 도메인을 잘 나눠도 계층을 무시하면 라우터가 SQL을 직접 쓴다.

> **계층은 「무엇을 못 하게 할지」, 도메인은 「누가 어디를 맡을지」 정한다.**
> 앞에건 버그를 막고, 뒤에건 사람끼리 부딪히는 것을 막는다. 6인이 동시에 작업할 때 실제로 아픈 것은 **뒤쪽**이다.

## 가로 — 템플릿이 강제하는 다섯 층

| 층 | 하는 일 | 하면 안 되는 일 |
|---|---|---|
| `models/` | 표 정의 | 업무 규칙을 넣지 않는다 |
| `repositories/` | 쿼리만 | **판단하지 않는다** — 「승인할 수 있나」는 여기 일이 아니다 |
| **`services/`** | **규칙 · 조합** | HTTP를 모른다 — `Request`나 `Response`를 다루지 않는다 |
| `dtos/` | 요청/응답 모양 · 검증 | DB를 모른다 |
| `apis/` | 엔드포인트 · 주입 | **로직을 넣지 않는다** — 서비스를 부를 뿐 |

그래서 `user_routers.py`가 다섯 줄이다 — 받아서 서비스에 넘기고 응답을 싸는 것까지가 끝이다.

**우리 명세에 대면 이렇게 앉는다.**

| 우리 규칙 | 어느 층 |
|---|---|
| 「`[승인]`은 의사 계정만」 | `services/` — 권한 판단은 규칙이다 |
| 「상태는 저장하지 않고 이벤트에서 파생」 | `services/` — `toGroup(세부 상태)`는 순수 함수 |
| 「🚨는 아무도 못 뺀다」 | `services/` + `dtos/` — 화면에서도 API에서도 막는다 |
| 「`일주일 뒤`는 끌 수 없다」 | `dtos/` 검증 — 요청 자체를 거른다 |
| 「승인과 동시에 원본 삭제」 | `services/` — 한 트랜잭션 |

---

# 1. 결론 — 일곱 파일

템플릿은 **도메인당 한 파일**이다(`app/models/users.py`). 같은 결로 22표를 일곱으로 나눈다.

| 파일 | 표 | 수 | 무엇을 담나 |
|---|---|---|---|
| `users.py` | `staff` | 1 | **직원** — 로그인하는 사람 (기존 파일 · 3장 ① 참조) |
| `patients.py` | `patient` `patient_session` `auth_attempt` | 3 | **환자와 그 접속** — 환자는 로그인하지 않는다 |
| `visits.py` | `visit` `record_image` `extracted` `guide` `visit_flag` | 5 | **진료 한 건이 만들어 내는 것 전부** |
| `messages.py` | `message` `checkin_response` `notification` | 3 | **나가는 것과 돌아오는 것** |
| `catalog.py` | `prescription_set` `component` `baseline` `challenge` | 4 | **사전 등록** — 원장님이 도입 첫날 정하는 것 |
| `clinic.py` | `clinic` `sms_balance` `sms_usage` | 3 | **의원 운영** |
| `logs.py` | `event_log` `chat_log` `feedback` | 3 | **기록** — 고치지도 지우지도 않는다 |
| | | **22** | |

## 왜 이렇게 나누나

| | |
|---|---|
| **한 진료가 만드는 것은 한 파일에** | `visit` → `record_image` → `extracted` → `guide` → `visit_flag`는 **생명주기가 하나**다. 승인 한 번에 다섯이 함께 움직인다 |
| **환자 신원과 접속을 붙인다** | `patient_session`·`auth_attempt`는 `patient` 없이는 뜻이 없다. OTP 정책이 바뀌면 세 표가 함께 바뀐다 |
| **사전 등록을 따로 뺀다** | `catalog.py`의 넷은 **진료와 무관하게** 도입 첫날 채우고, 이후 거의 안 바뀐다. 진료 갈래와 수명이 다르다 |
| **기록은 끝에 모은다** | `logs.py`의 셋은 **아무도 고치지 않는다.** 다른 표를 참조만 하고 참조당하지 않아, 마지막에 두면 import가 한 방향으로 흐른다 |

## import 방향 — 순환이 없다

```
users.py · patients.py · catalog.py · clinic.py     ← 아무것도 참조하지 않는다
        ↓
visits.py        (patient · staff · prescription_set 참조)
        ↓
messages.py      (visit · patient 참조)
        ↓
logs.py          (staff · patient · visit 참조)
```

**위에서 아래로만 참조한다.** 이 순서를 지키면 Tortoise의 문자열 참조(`"models.Visit"`)를 쓰지 않아도 되고, 순환 import가 원천적으로 안 생긴다.

---

# 2. 등록할 두 자리

새 모델 파일을 만들면 **반드시 두 곳에 등록한다.** 빠뜨리면 조용히 안 잡힌다.

## 2-1. `app/core/db/databases.py`

```python
TORTOISE_APP_MODELS = [
    "aerich.models",
    "app.models.users",
    "app.models.patients",     # 추가
    "app.models.visits",       # 추가
    "app.models.messages",     # 추가
    "app.models.catalog",      # 추가
    "app.models.clinic",       # 추가
    "app.models.logs",         # 추가
]
```

**여기 빠지면 `aerich migrate`가 그 표를 못 본다.** 마이그레이션이 조용히 비어서 나온다.

## 2-2. 마이그레이션은 손으로 쓰지 않는다

```bash
uv run aerich migrate --name add_visits    # 모델 → 마이그레이션 파일 생성
uv run aerich upgrade                       # 실제 반영
```

`app/core/db/migrations/`는 aerich가 만드는 자리다. **손으로 SQL을 쓰지 않는다** — 로즈앤 때와 다른 점이다.

---

# 3. 먼저 정할 것 셋 ★

**이 셋이 닫히기 전에는 모델을 쓰지 않는다.** 나중에 바꾸면 전부 다시 짜야 한다.

## ① `staff`와 템플릿 `User`는 다른 물건이다

| | 템플릿 `User` | 우리 `staff` |
|---|---|---|
| 로그인 | `email` | **`login_id`** — 영문 소문자+숫자 4자 이상 · 생성 후 변경 불가 |
| 비밀번호 | `hashed_password` | `password_hash` |
| 역할 | `is_admin` (bool 하나) | **`roles` jsonb** — 관리자 · 의사 · 스탭 **중복 선택** + `is_owner` |
| 개인정보 | `gender` `birthday` `phone_number` | **없다** — 직원 개인정보를 들지 않는다 |
| 퇴사 | `is_active` | `status` enum + `left_at` — **삭제하지 않는다** |
| 첫 로그인 | 없음 | **`must_change_password`** — `L-3` 화면의 근거 |
| 기본키 | `BigIntField` | **`uuid`** |

**역할 모델이 근본적으로 다르다.** 우리는 「관리자 + 스탭」처럼 **겹치는 역할**이 정상이고(`A1-2` 화면이 체크박스 셋), 템플릿은 `is_admin` 하나다.

| 고를 수 있는 길 | |
|---|---|
| **`User`를 `staff`로 대체** | 명세대로 간다. 대신 `app/services/auth.py`·`app/dtos/auth.py`·테스트 9개를 함께 고쳐야 한다 |
| `User`를 확장 | `email`을 안 쓰고 `login_id`를 더하는 꼴이라, 결국 대체와 같은 일을 하면서 안 쓰는 칸이 남는다 |
| 둘 다 둔다 | **권하지 않는다** — 로그인하는 사람이 두 표에 생긴다 |

## ② 기본키를 `uuid`로 갈지

명세 22표가 **전부 `uuid`** 전제다. 템플릿 `User`는 `BigIntField`.

| | |
|---|---|
| `uuid`로 통일 | 명세를 그대로 옮긴다 · 표 사이 참조가 명확 · **템플릿 `User`를 고쳐야 함** |
| `BigInt`로 통일 | 템플릿을 안 건드림 · **명세 22표의 `id` 정의를 전부 바꿔야 함** · 환자 링크 토큰에 순번이 드러나는 것은 별개 문제(토큰은 `message.token`이라 무관) |

**섞으면 안 된다.** `visit.patient_id`가 uuid인데 `patient.id`가 int면 그 자리에서 막힌다.

## ③ 갈래별 작업 분담

일곱 파일이 **그대로 분담 단위**가 될 수 있다. 다만 두 곳에서 충돌이 잦다.

| 충돌 지점 | 완화 |
|---|---|
| `app/apis/v1/__init__.py` | 라우터 등록 한 줄씩 — **같은 자리를 여섯이 고친다.** 한 사람이 모아서 넣거나, PR 순서를 정한다 |
| `app/core/db/databases.py` | `TORTOISE_APP_MODELS` — **일곱 줄을 먼저 한 번에 넣어 두면** 이후 충돌이 없다 |

---

# 4. 만드는 순서

의존 방향을 따라간다. **앞을 건너뛰면 뒤가 안 된다.**

| # | 무엇 | 왜 이때 |
|---|---|---|
| 1 | **3장 ①②를 닫는다** | 기본키와 직원 모델이 정해져야 나머지가 다 따라온다 |
| 2 | `users.py`(staff) · `clinic.py` | 로그인과 의원 설정이 없으면 아무도 못 들어온다 |
| 3 | `catalog.py` | `visit`이 `prescription_set_id`를 참조한다 |
| 4 | `patients.py` | `visit`이 `patient_id`를 참조한다 |
| 5 | `visits.py` | 여기부터 화면이 붙는다 (`S1-5`~`S1-13`) |
| 6 | `messages.py` | 승인 뒤 발송 — **이 프로그램의 본체** |
| 7 | `logs.py` | 다른 표가 다 있어야 참조가 성립한다 |

`ai_worker/tasks/`(판독 · 조립)는 **5번 이후**에 붙는다 — `extracted`가 있어야 넣을 곳이 생긴다.

---

# 5. 손대지 않는 곳

| | |
|---|---|
| `app/core/jwt/` · `app/dependencies/security.py` | 인증이 완성돼 있다. `Depends(get_request_user)`로 갖다 쓴다 |
| `app/core/db/migrations/` | aerich가 만드는 자리 |
| `infra/` | nginx · 배포용 compose — 배포 담당 영역 |

**환자 인증은 여기에 없다.** 직원용 JWT와 환자용 OTP(`P1-1`~`P1-5`)는 **다른 체계**다 — 환자는 `patient_session`과 `message.token`으로 들어오고 30분 세션을 받는다. `app/core/jwt/`를 환자에 끌어다 쓰지 않는다.
