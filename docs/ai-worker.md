# AI 워커 연동 설계 — Redis Stream으로 무엇을 주고받나

> 대상 저장소 — `AI-HealthCare-05/AH_05_06` · `ai_worker/tasks/`를 채우기 전에 정할 것.
> 짝 문서 — [`spec-medical.md`](spec-medical.md) 「안내문 조립」·「`generate_failed`는 막다른 길이 아니다」 · [`spec-models-layout.md`](spec-models-layout.md)
> **아키텍처 그림이 정본이다** — Nginx → FastAPI → Redis Stream → Consumer Group(AI-Worker ×N) → SSE.

---

# 1. 우리 AI 작업은 둘뿐이다 — 학습은 없다

그림에는 「모델 학습 작업 처리」가 있지만 **우리에겐 학습이 없다.** 추론 둘이 전부다.

| 작업 | 넣는 것 | 내는 것 | 성격 |
|---|---|---|---|
| **`ocr.read`** 판독 | `record_image` 여러 장 | `extracted` 행들 | 이미지 → 값 · **못 읽는 일이 흔하다** |
| **`guide.compose`** 조립 | `extracted` + 승인된 `component` | `guide.sections` | 값 → 문장 · **거의 안 실패한다** |

둘은 **순서대로** 돈다 — 판독이 끝나야 조립할 값이 생긴다. 다만 **한 작업으로 묶지 않는다.** 스탭이 `S1-6`에서 값을 고친 뒤 조립하는 흐름(`[ 맞아요 · 안내문 만들기 ]`)이 있기 때문이다.

```
S1-5 업로드 → ocr.read → S1-6 판독 확인 (스탭이 값 확인 · 수정)
                              ↓ [ 맞아요 · 안내문 만들기 ]
                         guide.compose → S1-11 스탭 확인
```

---

# 2. 스트림과 그룹

| | 이름 | |
|---|---|---|
| 스트림 | `ai:tasks` | 작업 하나에 한 항목 |
| 소비자 그룹 | `ai:workers` | 워커 여럿이 **나눠 갖는다** — 중복 처리 없음 |
| 소비자 이름 | 컨테이너 호스트명 | `XCLAIM`이 죽은 소비자를 식별하는 근거 |
| 결과 채널 | `ai:result:{visit_id}` | pub/sub · **진료 건마다 따로** |

**결과 채널을 진료 건마다 나누는 이유** — FastAPI가 SSE 연결 하나에 그 환자 것만 흘려보내야 한다. 한 채널에 다 보내면 모든 연결이 남의 결과를 받아 걸러야 한다.

---

# 3. 작업 페이로드 — `XADD`로 넣는 것

## 3-1. `ocr.read`

```javascript
{
  "task":       "ocr.read",
  "task_id":    "<uuid>",              // 멱등 키 · 재시도해도 같은 값
  "visit_id":   "<uuid>",
  "images": [
    { "image_id": "<uuid>", "storage_key": "tmp/2026-08-18/ab12…" }
  ],
  "baseline_terms": [                   // 「기록에서 찾을 말」 — 판독의 사전
    { "code": "HB", "terms": ["혈색소", "Hb", "Hemoglobin"] }
  ],
  "enqueued_at": "2026-08-18T10:41:00+09:00"
}
```

**`baseline_terms`를 함께 넣는다.** `baseline` 표의 「기록에서 찾을 말」이 판독 사전이므로(`DHEA-S` / `DHEAS` / `황체호르몬`), 워커가 DB를 다시 읽지 않게 요청에 실어 보낸다.

## 3-2. `guide.compose`

```javascript
{
  "task":       "guide.compose",
  "task_id":    "<uuid>",
  "visit_id":   "<uuid>",
  "mode":       "full",                 // "full" | "fallback"
  "diagnosis":  "EMS",
  "drugs":      [{ "code": "DNG", "name": "비잔정 2mg", "days": 84 }],
  "extracted":  [ { "field": "HB", "value": "10.4", "unit": "g/dL", "state": "read" } ],
  "previous":   { "HB": "10.2", "visit_date": "2026-05-20" },
  "components": [ { "id": "CAU-DNG-01", "kind": "CAU", "body": "…", "locked": false } ],
  "challenges": [ … ],
  "enqueued_at": "…"
}
```

| | |
|---|---|
| **`mode: "fallback"`** | `S1-10`의 `[ 기본 안내문으로 만들기 ]` — **수치 없이** 처방 세트의 승인 문구만으로 조립한다 |
| `components` | **승인된 문구만** 실어 보낸다. 워커가 문구 저장소를 직접 뒤지지 않는다 |
| `previous` | 지난 방문 값 — 「8점이던 생리통이 오늘 4점까지」 같은 비교 문장의 재료 |

---

# 4. 결과 — `Publish`로 나오는 것

```javascript
{ "task_id": "…", "visit_id": "…", "status": "done",   "result": { … } }
{ "task_id": "…", "visit_id": "…", "status": "failed", "reason": "no_drug" }
```

## 4-1. `ocr.read` 결과

```javascript
{
  "extracted": [
    { "field": "diagnosis", "value": "자궁내막증", "source_image_id": "…", "state": "read" },
    { "field": "CA125",     "value": null, "source_image_id": "…", "state": "unreadable" },
    { "field": "HB", "value": "10.4", "unit": "g/dL", "test_date": "2026-05-20",
      "source_image_id": "…", "state": "read" }
  ],
  "image_kinds": [ { "image_id": "…", "kind": "emr" } ]
}
```

<!-- 판독은 값을 못 읽어도 성공이다. 이 구분이 흐려지면 S1-7이 성립하지 않는다. -->

**못 읽은 것은 실패가 아니다.** `state='unreadable'`로 **성공 결과에 담아** 보낸다 — 그것이 `S1-7`(못 읽은 항목)의 근거다. **추측해서 채우지 않는다.**

| 판독 상황 | `status` | 화면 |
|---|---|---|
| 다 읽힘 | `done` | `S1-6` |
| 일부 못 읽음 | **`done`** | `S1-7` — 그 줄만 점선 `?` |
| 같은 항목이 두 곳에 | **`done`** — 행을 둘 다 넣는다 | `S1-8` — 「다른 값 보기 ▾」 |
| 이번에 검사 안 함 | **`done`** — 검사 행이 없다 | `S1-9` — **가장 흔하다** |
| 워커가 터짐 | `failed` | 재시도(6장) |

**`kind`도 AI가 판별한다** — `emr` / `rx` / `lab` / `unknown`. **판독하는 것은 `emr`과 `rx`뿐이고 `lab`은 사람이 보고 입력한다.**

## 4-2. `guide.compose` 결과

```javascript
{
  "sections": { "purpose": "…", "how": "…", "caution": "…",
                "red": "…", "life": "…", "plan": "…" },
  "ai_flags": [ { "section": "caution", "reason": "지난번과 달라진 곳" } ]
}
```

| | |
|---|---|
| `red` | **AI가 손대지 않는다.** `component.locked=true`인 문구를 **그대로** 넣는다 — 약별로 정해져 있고 아무도 못 뺀다 |
| `ai_flags` | `⚠ 확인 부탁`의 근거 — **자신 없는 곳 · 지난번과 달라진 곳 · 값이 빠진 곳**에만 |
| 문구 없는 약 | 그 항목만 `약사 복약지도를 참고하세요`로 대체하고 `ai_flags`에 남긴다. **생성을 중단하지 않는다** |

**AI는 승인된 문구를 다듬을 뿐 새 의학 정보를 만들지 않는다.** `정상입니다` `호전 중` 같은 판정도 하지 않는다.

---

# 5. 상태와의 대응

| 작업 | 시작 시 상태 | 성공 | 실패 |
|---|---|---|---|
| `ocr.read` | `진료기록 없음` → **`판독 결과 확인`** | `S1-6`~`S1-9` | 6장 |
| `guide.compose` | **`생성 중`** | **`스탭 확인 중`** | **`생성 실패`** (`S1-10`) |

`guide.compose`가 `failed`를 내는 조건은 **하나뿐이다.**

> **약 이름과 일수를 못 찾음** — `extracted`에 `field='drug'` 행이 없거나 `state='unreadable'`

<!-- 실패 사유를 visit에 따로 저장하지 않는다. extracted가 곧 사유다 — 같은 것을 두 곳에 적으면 어긋난다. -->

**실패 사유를 따로 저장하지 않는다.** `S1-10`이 화면에 쓰는 「약 이름과 일수를 찾지 못했습니다」는 `extracted`에서 그대로 나온다.

---

# 6. 실패와 재시도 — 두 가지를 섞지 않는다

| | 무엇 | 누가 되살리나 |
|---|---|---|
| **워커가 터짐** | 컨테이너 재시작 · OOM · 네트워크 | **`XCLAIM`으로 자동 회수** — 다른 워커가 이어받는다 |
| **판독/조립이 안 됨** | 사진이 흐림 · 약을 못 찾음 | **자동 재시도하지 않는다** — 사람이 `S1-10`에서 고른다 |

**자동 재시도는 앞엣것에만 건다.** 뒤엣것은 몇 번을 돌려도 결과가 같다 — `S1-10`도 화면에 그렇게 적어 둔다(「대개 결과가 같습니다」).

```
XCLAIM 기준   min-idle-time 120초 · 최대 2회 회수
2회를 넘으면  status='failed' · reason='worker_lost' → S1-10
```

## 멱등성 — `[ 다시 만들기 ]`가 행을 더 만들지 않는다

`guide.visit_id`가 **unique**다. 조립 작업은 **반드시 upsert**여야 하며, 같은 `task_id`가 두 번 처리돼도 `guide` 행이 하나여야 한다. `extracted`도 재판독 시 **그 `visit_id`의 기존 행을 지우고 다시 넣는다**(같은 항목이 두 곳에 있는 경우가 정상이라 `(visit_id, field)`로는 못 잡는다).

---

# 7. SSE — 어디에 붙나

```
FastAPI  GET /api/v1/visits/{visit_id}/events   (SSE)
   ↓ subscribe  ai:result:{visit_id}
   ↓ 결과 도착
   → event: ocr.done      data: {...}
   → event: guide.done    data: {...}
   → event: failed        data: {reason}
```

| 화면 | 기다리는 구간 |
|---|---|
| `S1-5` → `S1-6` | 판독 |
| `S1-6` `[ 맞아요 · 안내문 만들기 ]` → `S1-11` | **조립 10초** |

**명세의 「조립 10초」가 이 구간이다.** 지금은 그 10초 동안 무엇을 보여줄지가 안 정해져 있다 — 세부 상태 `생성 중`이 `안내문 (⏳)` 탭을 여는 것까지만 정해져 있다.

**연결이 끊기면** — SSE는 브라우저가 자동 재연결한다. 재연결 시 **현재 상태를 먼저 한 번 내려준다**(작업이 이미 끝났을 수 있다). 상태는 이벤트에서 파생되므로 다시 계산하면 된다.

---

# 8. 원본 파일 — S3

| | |
|---|---|
| 어디 | **DB 밖 임시 저장소** · `record_image.storage_key` |
| 얼마나 | **TTL 72시간** — 상한이지 목표가 아니다 |
| 본칙 | **`D1` 승인과 같은 트랜잭션에서 삭제** · `deleted_at` 기록 |
| 워커는 | **읽기만** 한다. 지우는 것은 승인 처리의 일이다 |

> **이 사진은 실제 환자의 EMR 캡처다.** 제3자 실명과 담당의 성함이 섞일 수 있다.
>
> 버킷은 **비공개 · 서버 사이드 암호화 · 프리사인드 URL** 전제다. 아키텍처 그림에는 그 부분이 안 그려져 있다.
>
> 그리고 **OCR 원문 텍스트를 DB에 남기지 않는다** — `Cytology · HPV DNA · SCC Ag`처럼 **우리가 안 쓰는 검사결과**가 통째로 들어 있어, 남기면 「서비스 목적 외 검사결과」가 된다.

---

# 9. 워커가 하지 않는 것

| | 왜 |
|---|---|
| DB 쓰기 | **결과를 Publish만 한다.** 저장은 FastAPI가 한다 — 트랜잭션 경계가 한 곳이어야 한다 |
| 상태 바꾸기 | 상태는 **이벤트에서 파생**된다. 워커가 `visit.status`를 쓰지 않는다(그런 칸이 없다) |
| 문자 보내기 | 발송은 승인 뒤 예약된 일이다 |
| 🚨 문구 만들기 | `component.locked=true`를 **그대로** 쓴다 |
| 판정 문장 | `정상입니다` `호전 중` — 프로그램이 하지 않는다 |
| 원본 삭제 | 승인 트랜잭션의 일 |

---

# 10. 정할 것

| # | 무엇 | 왜 지금 |
|---|---|---|
| 1 | **판독 엔진** — 외부 API(Vision/Upstage 등)냐 로컬 모델이냐 | `ai` 그룹에 `torch`·`sentence-transformers`가 있지만 **OCR 라이브러리는 없다** |
| 2 | **조립을 LLM으로 할지** | 명세는 「승인된 문구를 고르고 순서를 잡는다」 — **규칙 기반으로도 된다.** LLM이면 🚨를 못 건드리게 막는 장치가 따로 필요하다 |
| 3 | **워커 수** | 지금 compose에 `ai-worker` 하나 · `replicas` 없음. 그림은 셋 |
| 4 | **S3 붙이기** | `boto3`·`aioboto3` 둘 다 의존성에 없다 |
| 5 | **재시도 한도** | 위 6장의 `120초 · 2회`는 제안값이다 |

**1번이 나머지를 정한다.** 외부 API면 워커가 가벼워 `replicas`를 늘리기 쉽고, 로컬 모델이면 EC2 사양과 S3 모델 파일 로딩이 따라온다.
