# 종단간 최소 동작본 계약 — 8/27 시연 (`KEY-148`)

> 상위: [`KEY-141`](https://leehee.atlassian.net/browse/KEY-141) · 기준 커밋 `develop`
> 이 문서가 정하는 것은 **네 사람이 같은 환자·같은 진료를 본다**는 것 하나다.

8/27 목표는 기능을 다 만드는 것이 아니라 **합성 환자 한 명이 처음부터 끝까지 한 번 완주**하는 것이다. 그러려면 `KEY-149`·`KEY-150`(한금준) · `KEY-151`·`KEY-90`(김고은) · `KEY-99`·`KEY-152`(유가은)가 **같은 식별자**를 물고 이어져야 한다. 각자 다른 환자를 고르면 화면은 다 되는데 여정이 안 이어진다.

---

## 1. 고른 시나리오 — `SYN-EMS-01`

| | 값 | 비고 |
|---|---|---|
| 병원 | **H1 · 기준의원** | `_HOSPITAL_NAMES["H1"]` |
| 스탭 | `staff01` **한소영** | `SYN-STAFF-01` · 기준 스탭 |
| 의사 | `doctor01` **박연** | `SYN-STAFF-02` · 승인은 이 계정으로 |
| 환자 | 차트 **12401** · **윤지아** · 1989-03-12 | `SYN-EMS-01` |
| 휴대폰 | `010-2431-7788` → 저장은 `01024317788` | 정규화는 `KEY-47`(#72) |
| 진료 | **2026-07-29** · 담당의 박연 | 진료일 하나뿐 |
| 처방 | 자궁내막증 · 비잔 (계속) · 비잔정 2mg · 1일 1회 · **84일** | |
| 검사 | 6개 — 혈색소 · 자궁내막종 · 내막두께 · AST/ALT · AMH · 기타검사 | |

### 왜 이 환자인가

CSV 의 `케이스의도` 가 **「정상 진행 · 기준 케이스」** 다. 골격에는 예외가 없어야 한다.

후보였던 `SYN-DUP-03`(김서연 · 12345)을 **쓰지 않는다.** 「표준 데모 환자 — 환자 화면 디자인 목업이 쓰는 그 사람」이라 끌렸지만 둘이 걸린다.

* **특이사항 `우울증 병력`** → 안전 차단(🚨 DEPRESSION) 분기를 강제한다. 골격이 확인할 것은 「흐름이 이어지는가」이지 「차단이 도는가」가 아니다
* **동명이인 무리 ①** — 김서연이 셋이다. 환자 선택이 곧 식별 시험이 된다

둘 다 **다음 주에 볼 것**이지 이번 주에 볼 것이 아니다.

### 이름으로 사람을 찾지 마라

**`박연` 은 H1 과 H2 에 각각 있다**(`SYN-STAFF-02` · `SYN-STAFF-16`). CSV 의 `케이스의도` 가 「★ 이름으로만 풀면 H1 박연과 섞인다」로 못박아 두었다.

식별자는 **`staff_id` · `patient_id` · `visit_id`** 다. 이름·차트번호는 화면에 보여 주는 값이지 코드가 무는 값이 아니다.

---

## 2. 한 명령으로 준비하기

```bash
docker compose up -d
SEED_STAFF_PASSWORD='<개발용 비밀번호>' \
  DB_HOST=127.0.0.1 REDIS_HOST=127.0.0.1 \
  uv run python scripts/seed.py --mode full
```

`--mode full` 이 병원 2 · 직원 17 · 환자 100 · 진료 99 를 넣는다. 100명을 다 넣는 이유는 **목록 화면이 한 명만 있으면 목록이 아니기 때문**이다. 여정은 그중 12401 한 명만 탄다.

호스트에서 돌릴 때 `DB_HOST`·`REDIS_HOST` 를 덮어써야 한다 — `.env` 의 값은 컨테이너 이름이라 호스트에서 해석되지 않는다(`KEY-101`).

### 식별자를 꺼내는 법

이름이나 차트번호를 코드에 박지 말고 여기서 꺼낸다.

```python
from app.models.patients import Patient
from app.models.staffs import Hospital, Staff
from app.models.visits import Visit

hospital = await Hospital.get(name="기준의원")
doctor   = await Staff.get(hospital_id=hospital.hospital_id, login_id="doctor01")
staff    = await Staff.get(hospital_id=hospital.hospital_id, login_id="staff01")
patient  = await Patient.get(hospital_id=hospital.hospital_id, hospital_patient_no="12401")
visit    = await Visit.filter(patient_id=patient.patient_id).order_by("-visited_at").first()
```

`hospital_id` 를 늘 함께 건다. 그것이 이 제품의 울타리다.

---

## 3. 진짜와 fallback 경계 — 여정 9단계

기준은 `develop`(2026-08-21 아침). **「없음」은 코드가 아직 없다는 뜻이고, 「막힘」은 코드는 있는데 지금 상태로는 안 돈다는 뜻이다.**

| # | 단계 | 화면 | API | 지금 | 이번 주 |
|---|---|---|---|---|---|
| 1 | 병원 로그인 | `login.html` | `POST /auth/login` | **진짜** | 그대로 |
| 2 | 환자·진료 선택 | `patients.html` | `GET /patients` · `/visits` | **진짜** | 그대로 |
| 3 | 문서 업로드 | `patients.html`(upload) | **없음** | ❌ | **fixture** |
| 4 | OCR 수정·확정 | `ocr-review.html` | `/ocr/jobs/*` · `/ocr/fields/*` | ⚠️ **막힘** | **fixture** — 아래 §4 |
| 5 | 안내 생성 | — | 없음 | ❌ | **fixture** (고정 템플릿) |
| 6 | 의사 승인 | `doctor.html` | `/visits/{id}/guide/approve` | 🟡 **`#50` 미병합** | 진짜 — 병합되면 |
| 7 | 환자 링크 조회 | `guide.html` | `/guides/{token}` 없음 | ❌ | 개발용 링크 (`KEY-90`) |
| 8 | D+7 응답 | `checkin.html` | `/checkins/{token}` 없음 | ❌ | **fixture 또는 진짜** (`KEY-151`) |
| 9 | 병원 확인 | — | 없음 | ❌ | (`KEY-99`) |

**진짜인 구간은 1·2 둘뿐이다.** 6은 병합만 하면 진짜가 된다.

### 화면은 이미 다 있다

`login` · `patients` · `ocr-review` · `doctor` · `guide` · `checkin` 여섯 화면이 이미 있고, 각자 `?mock=1` 로 서버 없이 도는 길을 갖고 있다(`api.js` · `patients-api.js` · `ocr-api.js` · `doctor-api.js` · `guide-api.js` · `checkin-api.js`).

**시연에서 `?mock=1` 을 쓰지 않는다.** 그건 화면 혼자 도는 길이라 데이터가 이어지지 않는다. 서버 fixture 로 채우고 진짜 경로로 부른다.

---

## 4. ⚠️ 지금 막혀 있는 것 — 3·4단계

**`POST /api/v1/documents/{document_id}/ocr` 는 지금 무엇을 보내도 `404` 를 준다.**

```python
# app/ocr/api.py:16
service = OcrService(TortoiseOcrRepository())        # 기본 검증기를 그대로 쓴다

# app/ocr/service.py
class TortoiseOcrRepository:
    def __init__(self, document_ownership=None):
        self.document_ownership = document_ownership or FailClosedDocumentOwnershipVerifier()

class FailClosedDocumentOwnershipVerifier:
    """Block OCR creation until the authoritative upload model is connected."""
    async def assert_owned(self, ...):
        raise _not_found()                            # 항상 404
```

문서를 만드는 표도 경로도 없어서 **의도적으로 닫아 둔 것**이다. 안전 쪽으로 닫은 판단 자체는 맞다 — 소유를 확인할 수 없는 문서로 OCR 을 돌리면 남의 진료에 붙을 수 있다.

**검사는 통과한다.** `app/tests/ocr/test_ocr_repository.py` 가 `SyntheticDocumentOwnershipVerifier` 를 주입하기 때문이다. 초록불이지만 실제 앱에서는 이 경로가 한 번도 성공한 적이 없다.

### 그래서 이번 주에는

**API 로 OCR 작업을 만들지 않는다.** fixture 가 `OcrJob` · `OcrResult` · `OcrField` 행을 **직접 넣는다.** 4단계의 수정·확정(`PATCH /ocr/fields/{id}` · `POST /ocr/jobs/{id}`)은 그 행 위에서 **진짜로** 돈다.

업로드 모델을 이번 주에 만들지 않는다 — 8/26까지 코드 완료라는 일정에 표가 하나 더 들어가면 여정이 안 끝난다.

> 담당(`KEY-149` 한금준)이 다르게 보시면 알려 주세요. 업로드 표를 만드는 쪽이 낫다고 판단되면 이 문단만 바꾸면 됩니다.

---

## 5. fixture 입출력 자리

| 무엇 | 어디 | 형식 |
|---|---|---|
| 환자·진료·처방 | `docs/data/synthetic-patients.csv` | 정본. **이미 있다** |
| 직원 | `docs/data/synthetic-staff.csv` | 정본. **이미 있다** |
| 적재 | `scripts/seed.py --mode full` | **이미 있다** |
| OCR 판독 결과 | `app/tests/fixtures/ocr/SYN-EMS-01.json` | **새로 만든다** (`KEY-149`) |
| 안내 본문 템플릿 | `app/tests/fixtures/guide/SYN-EMS-01.json` | **새로 만든다** (`KEY-150`) |
| SMS | 보내지 않는다. 콘솔 출력으로 대체 | `docs/synthetic-data-spec.md` §1 |

새 fixture 는 `app/tests/fixtures/` 아래에 둔다. 시드가 이미 그 폴더를 가져다 쓰고 있어(`fixtures/staff.py` · `fixtures/prescriptions.py`) 자리가 하나로 모인다.

**파일 이름에 시나리오 ID 를 쓴다.** 다음 주에 두 번째 환자를 얹을 때 무엇이 무엇인지 알 수 있어야 한다.

---

## 6. fallback 을 숨기지 않는다

회의 결정이다 — 「실제 구현과 fixture 구간을 숨기지 않습니다」.

화면에 fixture 로 채운 구간이 있으면 **그 자리에 표시**한다. 시연에서 무엇이 진짜인지 보는 사람이 알아야 한다.

```
[demo] 이 판독 결과는 고정 데이터입니다 — 실제 OCR 은 다음 주에 붙습니다
```

표시 문구·자리는 화면 담당이 정한다. 이 문서는 **표시한다는 것**만 정한다.

---

## 7. 지키는 것

* 실제 환자정보를 쓰지 않는다. 위 값은 전부 지어낸 것이다
* 운영 토큰·API 키를 쓰지 않고 로그에 남기지 않는다
* `SEED_STAFF_PASSWORD` 는 각자 로컬 환경변수다. 저장소에 넣지 않는다
* 이름이 아니라 `staff_id`·`patient_id`·`visit_id` 로 잇는다
* 막히면 우회하지 말고 공유한다 — 이 문서의 §4 가 그 예다

---

## 8. 아직 안 정한 것

| 무엇 | 왜 여기서 안 정하나 | 누가 |
|---|---|---|
| 환자 링크 토큰 모양 | 링크·OTP 계약이 `KEY-78` 범위 | 김고은 (`KEY-90`) |
| D+7 응답 저장 시점 | `KEY-138` 이 「선택 즉시 vs 저장 시」를 정하는 중 | 권일준 |
| 안내 본문 문구 | 식약처 근거 문장이라 임의로 못 쓴다 | `KEY-150` |
| 업로드 표 스키마 | 이번 주 범위 밖 (§4) | — |
