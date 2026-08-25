# 환자용 API

> 인증 주체: 환자 링크로 진입해 OTP 인증을 마친 환자 세션

## 1. 기능 범위

```text
환자 링크 진입
→ OTP 인증
→ 승인 안내 조회
→ 복약·생활관리·챗봇 이용
→ D+7 복약·통증 응답 제출
```

환자 API는 직원용 JWT를 사용하지 않으며, 해당 환자와 진료에 연결된 승인 완료 데이터만 제공한다. 공통 보안 규칙은 [API 공통 규칙](common.md)을 따른다.

## 2. 계약 상태

| 영역 | 현재 최소 계약 | 관련 Jira |
|---|---|---|
| 환자 링크 | 개발용 링크 한 건으로 승인 안내 조회. 실제 SMS·예약 발송은 후속 범위 | [KEY-90](https://leehee.atlassian.net/browse/KEY-90) |
| OTP | 6자리·3분 유효, 5회 실패 시 10분 잠금 | [KEY-91](https://leehee.atlassian.net/browse/KEY-91) |
| 환자 세션 | OTP 성공 뒤 HttpOnly 쿠키로 30분 유지, 로그아웃·재인증 시 폐기·회전 | [KEY-92](https://leehee.atlassian.net/browse/KEY-92) |
| 승인 안내 조회 | 승인 완료 안내만 제공하고 원본·미승인 안내는 차단 | [KEY-151](https://leehee.atlassian.net/browse/KEY-151) |
| 챗봇 | 승인된 구조화 데이터와 지식만 컨텍스트로 사용 | [KEY-77](https://leehee.atlassian.net/browse/KEY-77) |
| D+7 응답 | 복약·통증 응답 한 건을 `visit_id`에 연결 | [KEY-151](https://leehee.atlassian.net/browse/KEY-151) |
| D+7 복약 신호 | **확정** — 아래 3절 | [KEY-138](https://leehee.atlassian.net/browse/KEY-138) |

### 2.1 개발용 환자 링크 — KEY-90 최소 계약

> 2026-08-24 · 8/27 Walking Skeleton 한정. 응답의 `demo_only: true`는
> 합성데이터 시연용이며 운영 발송 계약이 아님을 뜻한다.

```text
POST /api/v1/visits/{visit_id}/guide/link   직원 인증 필요
201 { "path": "/api/v1/guides/{token}",
      "expires_at": "…", "demo_only": true }

GET  /api/v1/guides/{token}                 환자 링크 자체가 접근 증명
200 { "version": 1, "approved_at": "…", "expires_at": "…",
      "sections": [{ "key": "medication", "body": "…" }],
      "demo_only": true }
```

- 링크는 승인 완료 상태(`SCHEDULED_TO_SEND`)인 안내에만 발급하며 72시간 유효하다.
- 발급은 같은 병원의 `staff` 또는 `doctor`만 가능하고, 타 병원 안내는 404로 감춘다.
- 원문 토큰은 발급 응답에서 한 번만 제공하고 DB에는 SHA-256 digest만 저장한다.
- 한 안내에 개발용 링크 하나만 허용한다. 반복 발급은 `409 LINK_ALREADY_ISSUED`다.
- 조회 응답에는 승인된 섹션의 최종 문구만 포함한다. 환자정보, OCR·의료문서 원문,
  생성 원문, 내부 경고와 승인자 식별자는 포함하지 않는다.
- 없는 토큰은 `404 LINK_NOT_FOUND`, 만료 토큰은 `410 LINK_EXPIRED`다.
- 실제 SMS·예약 발송·폐기·재발급 전체 흐름은 이번 계약 범위 밖이다. OTP는
  아래 KEY-91 계약을 사용하며, 환자 세션이 연결되기 전까지 개발 링크 조회
  자체를 OTP로 차단하지 않는다.

### 2.2 환자 OTP — KEY-91

```text
POST /api/v1/patient-auth/otp/issue
     { "link_token": "…" }
200  { "expires_at": "…", "retry_after_seconds": 60 }

POST /api/v1/patient-auth/otp/verify
     { "link_token": "…", "code": "123456" }
200  { "verified": true }
```

- OTP는 숫자 6자리이며 발급 시점부터 3분간 유효하다.
- 같은 링크의 재발급은 마지막 발급부터 60초 뒤 허용한다. 그 전에는
  `429 OTP_RESEND_TOO_SOON`과 동일한 초 단위 `Retry-After`·`retry_after_seconds`를
  반환하며 OTP를 교체하거나 전송하지 않는다.
- 연속 5회 실패하면 링크 단위로 10분간 잠근다. 재발급해도 실패 횟수와
  잠금은 초기화되지 않으며, 잠금 중 발급·검증은 모두 `429 OTP_LOCKED`다.
- 재발급하면 이전 OTP는 즉시 무효화한다. 성공한 OTP는 다시 사용할 수 없다.
- OTP 원문은 저장하지 않는다. 서버 비밀키·무작위 salt를 사용한 HMAC digest만
  저장하며 API 응답과 로그에도 원문을 포함하지 않는다.
- 실제 SMS 공급자는 이번 일감에 포함하지 않는다. 공급자가 연결되지 않은
  환경은 성공을 가장하지 않고 `503 OTP_DELIVERY_UNAVAILABLE`을 반환한다.
- `patient.sms_consent=false`인 수신 거부 환자는 OTP 상태를 만들거나 전송하지
  않고 `409 SMS_OPT_OUT`으로 차단한다.
- OTP 상태는 행 잠금 트랜잭션에서 먼저 반영한 뒤 잠금을 해제하고 외부
  전송을 호출한다. 전송 실패 시 동일한 최신 digest가 아직 소비되지 않은
  경우에만 신규 발급을 삭제하거나 이전 OTP 상태를 복원하여 동시 변경을
  덮어쓰지 않는다.
- 검증 성공 시 아래 KEY-92 환자 세션을 발급한다. 응답 본문에는 세션 원문을
  넣지 않고 브라우저의 HttpOnly 쿠키로만 전달한다.
- 주요 오류는 `404 LINK_NOT_FOUND`, `410 LINK_EXPIRED`, `409 OTP_NOT_ISSUED`,
  `401 OTP_INVALID`, `410 OTP_EXPIRED`, `409 OTP_ALREADY_USED`,
  `409 SMS_OPT_OUT`, `429 OTP_RESEND_TOO_SOON`, `429 OTP_LOCKED`다.

### 2.3 환자 인증 세션 — KEY-92

```text
POST /api/v1/patient-auth/otp/verify
     { "link_token": "…", "code": "123456" }
200  { "verified": true, "session_expires_in_seconds": 1800 }
Set-Cookie: patient_session=…; HttpOnly; SameSite=Lax; Max-Age=1800; Path=/api/v1

DELETE /api/v1/patient-auth/otp/session
204  Set-Cookie: patient_session=; Max-Age=0; Path=/api/v1
```

- 환자 세션은 직원 JWT·Refresh Token과 분리된 임의의 원문 토큰이다.
- 원문은 브라우저의 `patient_session` HttpOnly 쿠키에만 전달한다. Redis에는
  SHA-256 digest와 링크 digest만 30분 TTL로 저장한다.
- 쿠키가 없는 새 브라우저·시크릿 창·다른 기기는 OTP를 다시 확인해야 한다.
- 세션은 발급 후 30분이 지나면 만료된다. 환자 안내 조회와 D+7 조회·저장은
  모두 유효한 세션이 필요하며, 없거나 만료·폐기된 세션은
  `401 PATIENT_SESSION_EXPIRED`다.
- 세션은 인증한 링크 하나에만 묶인다. 같은 쿠키로 다른 환자 링크를 열 수 없다.
- 로그아웃은 서버 세션을 폐기하고 쿠키를 삭제한다.
- 같은 링크에서 OTP를 다시 확인하면 새 세션으로 회전하며 이전 브라우저의
  세션은 즉시 폐기한다.
- 세션이 남아 있어도 연결된 환자 링크가 만료되거나 안내 승인이 취소되면 기존
  링크 오류 계약에 따라 접근을 차단한다.

### 2.4 D+7 복약·통증 응답 — KEY-151 최소 계약

> 2026-08-24 · 8/27 Walking Skeleton 한정. KEY-90 개발용 링크의 같은 원문
> 토큰을 사용하며 실제 SMS·운영 OTP·실시간 신호 API는 이번 구현 범위 밖이다.

```text
GET  /api/v1/checkins/{token}
200  { "round_label": "복약 7일째 · 첫 확인",
       "answers": { "taking": null, "missing": { "lead": "…" } },
       "pain_types": [{ "key": "menstrual", "label": "월경통" }],
       "answered": false, "demo_only": true }

POST /api/v1/checkins/{token}
     { "medication": "taking",
       "pain": { "had": true, "score": 4, "types": ["menstrual"] } }
201  { "check_in_id": 1, "saved": true, "medication": "taking",
       "pain": { "had": true, "score": 4, "types": ["menstrual"] },
       "demo_only": true }

GET  /api/v1/visits/{visit_id}/checkin       직원 인증 필요
200  { "check_in_id": 1, "visit_id": 10, "medication": "taking",
       "pain": { "had": true, "score": 4, "types": ["menstrual"] },
       "submitted_at": "…", "demo_only": true }
```

- 환자 조회·저장은 KEY-90과 같은 링크 만료 및 승인 완료 검증을 거친다.
- 선택지별 안내 문구는 승인된 `medication` 섹션과, 있으면 `caution` 섹션의
  최종 문구만 재사용한다. 생성 원문·OCR·의료문서 원문·환자정보는 응답하지 않는다.
- `check_in.guide_document_id`를 통해 `GuideDocument.visit_id`에 연결하며
  `visit_id`를 응답 테이블에 중복 저장하지 않는다.
- 한 안내에는 D+7 응답 한 건만 저장한다. 반복 제출은
  `409 CHECKIN_ALREADY_ANSWERED`다.
- 병원 조회는 같은 병원의 `staff` 또는 `doctor`만 가능하다. 없는 응답과 타
  병원 응답은 모두 `404 CHECKIN_NOT_FOUND`로 감춘다.

### 2.3 환자 이용 이벤트 — KEY-170 기록 계약

> 2026-08-25 · **API가 아니라 기록 인터페이스다.** 이 절은 새 엔드포인트를
> 정의하지 않는다. 환자가 안내를 열거나 챗봇을 쓴 **결과의 모양**만 남기는
> 내부 계약이며, KEY-95·KEY-96이 같은 인터페이스를 부른다.

```python
from app.services.patient_usage import PatientUsageService

await PatientUsageService().record_guide_view(guide_document_id)

await PatientUsageService().record_chatbot_answer(
    guide_document_id,
    question_kind=PatientQuestionKind.MEDICATION,   # 갈래만
    outcome=PatientAnswerOutcome.BLOCKED,           # 답함·막음·못함
    grounded_section=GuideSectionKey.CAUTION,       # 어느 승인 섹션을 근거로 삼았나
)
```

- 남기는 것은 **여섯 가지뿐**이다. 안내문 식별자, 이벤트 유형, 질문 갈래,
  응답 결과, 근거 섹션, 발생 시각.
- **질문·답변·프롬프트 원문과 링크 토큰 원문은 남기지 않는다.** 값을 비우는
  것이 아니라 `patient_usage_event` 표에 **담을 칸을 두지 않는다.**
  칸이 생기면 `app/tests/patient_usage/` 의 칸 목록 검사가 죽는다.
- `visit_id`를 사본으로 두지 않고 `guide_document_id`를 통해 도달한다.
  두 값이 어긋날 자리를 만들지 않기 위해서다.
- 승인 완료(`SCHEDULED_TO_SEND`) 안내에만 남는다. 미승인 안내와 없는 안내는
  **똑같이** `404 GUIDE_NOT_FOUND`다. 답이 다르면 그 차이만으로 진료의 존재를
  알 수 있다.
- 병원이 붙는 자리는 **환자 링크 토큰이 정한다.** 기록 인터페이스는 병원
  번호를 받지 않으므로 타 병원 안내에 이벤트가 붙을 경로가 없다.
- **이 이벤트를 돌려주는 조회 API는 만들지 않는다.** 병원 사용자가 환자 챗봇
  원문을 열람할 창구를 두지 않기 위해서다(`docs/api/hospital.md` §9와 같은 결).

#### 아직 연결되지 않은 호출 지점

| 부르는 쪽 | 부를 것 | 상태 |
|---|---|---|
| `GET /api/v1/guides/{token}` | `record_guide_view()` | **연결 완료** — KEY-170 |
| 챗봇 스트리밍 UI (KEY-95) | `record_chatbot_answer()` | 미연결 — 챗봇 화면 자체가 미구현 |
| LLM·RAG 응답 경로 (KEY-96) | `record_chatbot_answer()` | 미연결 — 질문 갈래 분류와 차단 판정이 KEY-96 범위 |

## 3. D+7 복약 신호 — `POST /checkins/{token}/signals`

> 결정 2026-08-21 · 담당 권일준 · 리뷰어 유가은
> 근거: `#55`(KEY-98) 리뷰 · 와이어프레임 `P7-2`~`P7-5`

`#55`는 `notify`를 **저장할 때** 보낸다. 와이어프레임은 **고르는 즉시** 알리라고 한다. 저장 전에 화면을 닫으면 그 사이가 통째로 사라진다. **끊은 환자가 곧 폼을 끝까지 채울 가능성이 가장 낮은 환자다.**

```text
POST /checkins/{token}/signals
     { "answer_key": "stopped_side_effect",
       "client_id": "…",             기기 하나 — 순번이 통하는 범위
       "client_session_id": "…",     탭 하나 — 되짚기용, 판정에는 안 씀
       "client_sequence": 7 }        그 기기 안에서 단조증가하는 번호
201  { "signal_id": 8801, "answer_key": "stopped_side_effect", "notify": true,
       "current": true,              이 신호가 「지금 답」이 됐는가
       "current_answer_key": "stopped_side_effect" }
```

### 3.1 신호는 기록이 아니다

이 구분이 이 계약의 전부다. 와이어프레임이 이미 갈라 두었다 — `P7-3`의 「이 답은 **기록으로만** 남습니다 — 따로 연락드리지 않아요」.

| | 신호(signal) | 기록(record) |
|---|---|---|
| 뜻 | 「이 환자를 봐 주세요」 | 환자가 제출한 답 |
| 언제 | 고르는 즉시 | \[저장\]을 누를 때 |
| 의무기록인가 | **아니다** | **그렇다** |
| 바뀌는가 | 지우지 않는다 (append-only) | 마지막 저장이 정본 |
| 무엇이 지금 답인가 | **마지막 신호** | 마지막 저장 |

「14:23에 환자가 중단을 눌렀다」는 **나중에 답을 바꿔도 참이다.** 그래서 앞 신호를 지우지 않는다. 대신 **뒤에 온 신호가 앞을 덮는다** — 의료진 화면은 마지막 신호를 지금 환자의 답으로 읽는다.

> 「저장된 답을 옆에 함께 보인다」로는 못 막는다 — 저장 전에 닫은 환자에게는 **옆에 놓일 답이 없다.** 저장하지 않는 환자가 바로 이 계약이 존재하는 이유다.

### 3.2 무엇이 「지금 답」인가

**받은 차례만으로 정하면 안 된다.** 첫 요청이 느리면(첫 연결·재시도·혼잡) 나중에 고른 답이 먼저 닿는다. 그러면 환자는 「잘 먹고 있어요」로 바꿨는데 서버의 지금 답은 「중단」이 되고, 의원은 없는 문제를 쫓는다. **이 계약이 막으려던 상황이 그대로 되살아난다.**

**같은 기기면 `client_sequence` 가 큰 쪽, 다른 기기면 닿은 차례.**

| 식별값 | 무엇을 가리키나 | 어디에 남나 |
|---|---|---|
| `client_id` | **기기 하나** — 순번이 통하는 범위 | `localStorage` |
| `client_sequence` | 그 기기 안에서 단조증가하는 번호 | `localStorage` |
| `client_session_id` | **탭 하나** — 되짚기용, 판정에는 안 씀 | `sessionStorage` |

**순번은 기기 안에서만 뜻이 있다.** 다른 기기는 1 부터 시작하므로 큰 번호가 나중이라는 보장이 없다. 순번만 비교하면 **나중에 켠 기기의 답이 앞 기기의 큰 번호에 막힌다.**

```
기기 A   taking/1 → stopped_side_effect/2
기기 B   taking/1          ← 나중에 골랐는데 순번이 작다
```

기기가 다르면 사람이 옮겨 앉은 것이라 사이가 벌어져 있어 **도착 순서가 맞다.**

반대로 같은 기기 안에서는 새로고침·새 탭을 넘어 순번이 이어지므로, **새로고침 직전에 떠난 지연 요청도 순번으로 제대로 밀린다.**

```
화면 A   위험 답변 출발 → 망에서 지연
새로고침
화면 B   정상 답변 도착 → 지금 답 taking
화면 A   지연된 위험 답변 도착   ← 같은 기기 · 순번이 작아 못 덮는다
```

> 두 경우 다 유가은 님이 `#79` 재검토에서 재현해 주신 것이다. 「도착 순서만」도 「순번만」도 각각 한쪽을 놓친다.

> **늦게 닿은 옛 신호도 버리지 않는다.** 「14:23 에 중단을 눌렀다」는 그것대로 참이라 이력에 남는다. 「지금 답」 판정에서 밀릴 뿐이다.

**이 비교는 같은 기기 안에서만 유효하다.** 기기를 넘나드는 순서 보장은 이 계약 범위 밖이며, [KEY-151](https://leehee.atlassian.net/browse/KEY-151)에서 서버 쪽 authoritative 시각으로 별도 처리한다. 지금 규칙은 「기기가 다르면 사람이 옮겨 앉은 것이라 사이가 벌어져 있다」는 가정 위에 서 있고, 그 가정이 깨지는 경우(같은 사람이 두 기기를 번갈아 빠르게 누르는 것)는 도착 차례가 틀릴 수 있다.

### 3.3 저장이 마지막으로 바로잡는다

신호가 하나도 못 갔거나 마지막 것만 실패하면 서버에는 **옛 답이 「지금 답」으로 남는다.** 저장은 환자가 확정한 답이라, 서버가 그것으로 신호 상태를 맞춘다.

```text
POST /checkins/{token}
201  { …, "signal_answer_key": "taking" }   ← 정정한 결과를 돌려준다
```

정정 결과를 응답에 실는 이유는 **밖에서 확인할 방법을 남기기 위해서**다. 확인하려고 신호를 하나 더 보내면 그것이 지금 답이 돼 정작 재려던 것을 가린다.

여기서도 앞 신호를 **지우지 않는다** — 눌렀던 사실은 그대로 두고 판정만 옮긴다.

**저장도 신호와 같은 규칙으로 판정한다.** 저장은 **저장 시점에 새 `client_sequence` 를 발급받아** 신호와 같은 세 칸(`client_id` · `client_session_id` · `client_sequence`)을 함께 싣는다. 「늘 가장 나중」을 뜻하는 고정 sentinel 값을 쓰지 않는다.

```text
POST /checkins/{token}
{ …, "client_id": "…", "client_session_id": "…", "client_sequence": 7 }
```

고정값을 쓰면 **저장을 두 번 했을 때 두 값이 같아져 뒤엣것이 앞엣것을 못 덮는다.** 순번을 새로 뗀 저장은 같은 기기에서 늘 마지막에 뗀 번호라 자연히 가장 나중이고, 다른 기기면 신호와 똑같이 도착 차례로 견준다 — 특례가 필요 없다.

> 이 결정 전에는 비교가 「저장이면 도착 차례」로 갈라져 있어 **그 고정값을 아무도 읽지 않았다.** 죽은 값이 옳은 것처럼 보이던 자리다.

### 3.4 규칙

1. **화면은 고른 것을 그대로 보낸다. 알릴지는 서버가 정한다.** 응답의 `notify`가 그 판단이고, 무엇이 알릴 일인지는 승인된 주의사항이 정하지 화면이 정하지 않는다. `missing`(가끔 놓쳐요)은 `notify: false`다 — `P7-3`이 「🔔 알림을 만들지 않는다」로 못박았다. **기록은 남고 연락만 안 간다.**
2. **연달아 같은 답을 다시 눌러도 보내지 않는다.** `P7-2`~`P7-5`는 펼침 화면이라 환자가 설명을 **읽어 보려고** 눌렀다 되돌릴 수 있다. 다만 다른 답을 거쳐 돌아온 것은 새 신호다 — 그러지 않으면 마지막 신호가 실제로 고른 답과 어긋난다.
3. **답을 바꾸면 새 신호다.** 앞 신호는 지우지 않고, 뒤엣것이 앞을 덮는다.
4. **실패해도 화면을 막지 않는다.** 환자는 자기가 알림을 보내는 줄 모른다. 여기서 오류를 띄우면 무엇을 잘못했는지 알 수 없는 사람에게 사과를 시키는 꼴이 된다.
5. **저장 때 보내는 기존 `notify`가 안전망이다.** 신호가 실패했거나 아예 못 갔어도 저장이 그 사실을 다시 알린다. 서버는 이미 신호가 있으면 두 번 알리지 않는다.

`#55`의 저장 시점 `notify`는 **그대로 둔다.** 두 길이 겹치는 것이 아니라, 즉시 경로가 앞서고 저장 경로가 받쳐 준다.

### 3.5 안 2(선택하면 저장 API 자동 호출)를 고르지 않은 이유

**`P7-2`~`P7-5`는 펼침 화면이다.** 답을 누르면 그 답에 맞는 설명이 열린다. 환자가 「불편해서 중단했어요」를 **읽어 보려고** 눌렀다가 「잘 먹고 있어요」로 바꿀 수 있다. 안 2는 그 첫 손짓을 **기록**으로 남긴다 — 중단하지 않은 환자가 중단으로 남고, 의무기록이라 나중에 되짚을 근거가 없다.

그리고 세 가지가 더 어긋난다.

- **\[저장\]이 장식이 된다.** `P7-6`이 「✓ 기록이 저장됐어요」로 끝을 말하는데, 이미 저장돼 있으면 그 화면이 거짓이 된다.
- **통증·부위·메모가 빈 채로 저장된다.** 환자는 아직 적는 중이다.
- 환자가 **제출한 적 없다고 믿는 상태**에서 기록이 남는다.

### 3.6 아직 안 정한 것

- 의료진 화면이 신호를 어떻게 보여 줄지 — [KEY-99](https://leehee.atlassian.net/browse/KEY-99). **마지막 신호를 지금 답으로 읽어야** 철회가 성립한다.
- 신호 보관 기간과 해소 표시
- D+7 복약·통증 응답 표와 `GET/POST /checkins/{token}`은 KEY-151 최소 범위로
  구현됐다. 실시간 신호 저장 표와 `POST /checkins/{token}/signals` 서버 구현은
  이번 범위에 포함하지 않는다.
- **기기를 넘나드는 순서 보장.** 3.2 의 순번 비교는 같은 기기 안에서만 유효하다. 서버 쪽 authoritative 시각으로 정하는 것은 [KEY-151](https://leehee.atlassian.net/browse/KEY-151)에서 별도로 처리한다.
- **신호·저장이 둘 다 실패하면 이 계약만으로는 놓칠 수 있다.** 재전송 강화가 아니라, [KEY-99](https://leehee.atlassian.net/browse/KEY-99) 이후 의료진 화면에서 「이 환자가 D+7 응답을 아예 안 남겼다」를 감지하는 기능으로 닫는다. **신호 전달 자체를 보강하는 방향이 아님을 분명히 한다** — 다음에 이 항목을 다시 열 때 혼동하지 않도록.

## 4. 그 밖의 확정 전 작성 금지 항목

환자용 엔드포인트 경로, 요청·응답 DTO와 오류 코드는 관련 Jira의 인수조건과 구현 리뷰에서 확정한다. 확정 전 임의 경로를 추가하지 않는다.

확정 시 각 API에 다음 내용을 기록한다.

- Method와 Path
- 인증 전·후 접근 범위
- 요청·응답 필드와 `visit_id` 연결 방식
- 링크 만료·폐기, OTP 실패·잠금, 세션 만료 오류
- 승인 전 데이터·타 환자 데이터 차단
- 민감정보·토큰·access log 비노출 테스트

## 5. 병원 영역과의 연결

- 병원에서 승인 완료된 안내만 환자 조회 대상으로 전환한다.
- 환자 D+7 응답은 같은 `visit_id`의 병원 조회 흐름으로 환류한다.
- 병원과 환자 문서에 DTO를 중복 정의하지 않고 [공통 식별자와 영역 간 계약](common.md#4-공통-식별자와-영역-간-계약)을 참조한다.
