# Sprint 3 검수 증적 — KEY-71

> 작성 2026-08-19 · **갱신 2026-08-20** · 담당 권일준 · 리뷰어 유가은
> 기준 커밋 `a6a9005` (`develop`)

이 문서는 **무엇이 통과했는가**보다 **무엇이 검사를 빠져나갔는가**를 남긴다.
통과한 숫자는 다음 스프린트에 쓸모가 없지만, 검사가 못 보는 자리는 그대로 남는다.

> **2026-08-20 갱신** — 3절에 적었던 CI 구멍 둘이 `KEY-102`(PR `#43`)로 막혔다.
> 「열린 구멍」으로 적어 둔 문서가 사실과 달라지면 그 자체가 문제라 바로 고친다.
> **막혔다는 주장도 실측으로 남긴다** — 3-1 · 3-2 를 보라.

---

## 1. 판정

**Sprint 3 완료로 보고할 수 없다.** 부모 일감 `KEY-44`(Sprint 3 OCR 핵심 흐름
E2E·회귀 QA)가 요구하는 **OCR 흐름이 아직 한 번도 끝까지 돌지 않았다.**

| 조각 | 상태 |
|---|---|
| OCR 모델 (`KEY-59`) | PR `#31` 승인 · **미병합** |
| OCR API (`KEY-60`) | PR `#32` **변경 요청** |
| 판독 확인 화면 (`KEY-62`) | PR `#40` 리뷰 대기 |
| 필드 수정 연동 (`KEY-63`) | **미착수** — 위 셋에 막힘 |

넷이 사슬이라 E2E 를 태울 구간이 없다. 아래는 **그 앞 단계까지의 검수 증적**이다.

---

## 2. 자동 검사 — 실측

`develop` `a6a9005` 에서 그대로 돌린 결과다. (2026-08-20)

```
$ DB_HOST=127.0.0.1 uv run pytest app -q
217 passed, 3 skipped in 2.29s

$ uv run ruff check .
All checks passed!

$ uv run ruff format . --check
73 files already formatted

$ uv run mypy app                       # ← 2026-08-20 부터 CI 에서도 돈다
Success: no issues found in 66 source files

$ uv run coverage run -m pytest app && uv run coverage report
TOTAL   1468   133   91%
```

### 건너뛴 3건 — 의도된 대기

```
test_rbac_guard.py:24        KEY-21 서버 가드 미구현 — app/core/rbac.py 가 들어오면 켜진다
test_field_mapping.py:181    patient API 가 아직 없다 — 생기면 켜진다 (KEY-12·KEY-16)
test_field_mapping.py:181    visit API 가 아직 없다
```

셋 다 `importorskip` 으로 **구현이 들어오면 저절로 켜지도록** 걸어 두었다.
뒤 둘은 `KEY-34`(PR `#39`)가 병합되는 순간 켜진다 — 그때 필드명이 어긋나 있으면
거기서 걸린다.

---

## 3. 검사가 못 보던 곳 — 세 군데 중 둘은 막혔다

숫자보다 이쪽이 중요하다. **초록불이 초록불을 뜻하지 않는 구간**이었다.

| | | |
|---|---|---|
| 3-1 | 스택형 PR 에 CI 가 안 돈다 | ✅ **막힘** — `KEY-102` (PR `#43`, 2026-08-19 병합) |
| 3-2 | mypy 가 CI 에 없다 | ✅ **막힘** — 같은 PR |
| 3-3 | 프런트에 자동 검사가 0 이다 | 🔴 **열려 있다** |

아래에 **무엇이 문제였고 무엇으로 막혔는지**를 함께 남긴다. 고친 뒤에 문제를
지워 버리면 다음에 같은 자리가 다시 열렸을 때 알아보지 못한다.

### 3-1. ✅ 스택형 PR 에 CI 가 안 돌던 것 — 막힘

**무엇이 문제였나.** `.github/workflows/checks.yml` 의 `pull_request` 트리거가
`main` · `develop` · `release/*` · `hotfix/*` 뿐이라, **feature 브랜치를 base 로 하는
PR 은 lint 도 test 도 돌지 않았다.** 그런데 `mergeStateStatus` 는 `CLEAN` 이라
화면에서는 초록불로 보였다 — **검사를 안 받은 것과 통과한 것이 같아 보였다.**

이 구멍으로 **실제 사고가 한 번 났다** — 4절의 `OCR-1` 을 보라. `#31` 이 그때
CI 를 받은 것은 워크플로가 고쳐져서가 아니라 **base 를 `develop` 으로 되돌려
피해 간 것**이었다.

**무엇으로 막았나.** `KEY-102`(PR `#43`, 2026-08-19 병합) — 브랜치 규칙의 네
접두어를 트리거에 넣었다.

```yaml
  pull_request:
    branches:
      - main
      - develop
      - 'release/*'
      - 'hotfix/*'
      - 'feat/**'
      - 'fix/**'
      - 'docs/**'
      - 'test/**'
```

**막혔다는 증거.** 어제 이 구멍에 있던 `#32` 가 오늘은 검사를 받는다.

```
2026-08-19  #32  base=feat/KEY-59-ocr-models  checks=[]                                 ← 검사 없음
2026-08-20  #32  base=feat/KEY-59-ocr-models  checks=[lint:SUCCESS, test:SUCCESS]       ← 돈다
```

같은 질의로 다시 확인할 수 있다.

```
$ gh pr list --state open --json number,statusCheckRollup \
    --jq '.[]|select([.statusCheckRollup[]?|select(.name=="test")]|length==0)|"#\(.number)"'
```

> **주의 — 이미 열려 있던 PR 은 새 푸시가 있어야 켜진다.** `pull_request` 는
> `opened` · `synchronize` 에 반응하므로, 워크플로가 바뀌어도 **가만히 있는 PR 은
> 그대로 검사 없이 남는다.** 위 질의에 오래된 PR 이 잡히면 고장이 아니라
> 「아직 밀지 않은 것」이다 — `develop` 을 한 번 당겨 올리면 돈다.

### 3-2. ✅ mypy 가 CI 에 없던 것 — 막힘

**무엇이 문제였나.** `develop` 에 5건이 있었고 아무도 못 봤다.
`health_routers.py:31` 은 `KEY-19`(PR `#17`) 병합분이라 **8월 19일부터 계속 있었다.**

```
app/models/visits.py:18                     Need type annotation for "patient"
app/apis/v1/health_routers.py:31            Incompatible types in "await"
app/tests/models/test_patient_visit_models.py:47,49,50   "Field[Any]" has no attribute ...
```

**무엇으로 막았나.** 같은 PR 에서 **5건을 먼저 고치고** `lint` 잡에 mypy 를 넣었다.
순서를 바꿨다면 켜는 순간 `develop` 이 빨간불이 된다.

**같이 걸린 것 하나.** `lint` 잡은 `uv sync --frozen` 만 했는데 `mypy` 는 `dev`
그룹이고 `tortoise` · `fastapi` 는 `app` 그룹이다. 워크트리로 CI 환경을 재현해
확인했다.

```
uv sync --frozen             → Found 58 errors in 26 files   ← 전부 import-not-found
uv sync --group app --frozen → Found 5 errors in 3 files     ← 진짜 오류만
```

**mypy 만 켜고 이 줄을 빠뜨렸으면 켠 그날 되돌렸을 것이다.** 도구를 켜는 일은
도구를 고르는 것 반, **그 도구가 볼 수 있게 환경을 맞추는 것 반**이다.

**막혔다는 증거.**

```
$ grep -c mypy .github/workflows/checks.yml
2
$ uv run mypy app
Success: no issues found in 66 source files
```

### 3-3. 🟠 프런트는 자동 검사가 0 이다

`frontend/` 는 순수 HTML/CSS/JS 라 `pytest` 도 `ruff` 도 보지 않는다.
이번 스프린트에 잡은 결함 **절반이 이 영역**이고, 전부 **사람이 눌러 보거나
리뷰로** 찾았다(4절). 자동화가 없다는 사실 자체를 위험으로 남긴다.

---

## 4. 이번 스프린트에 잡은 결함 — 무엇이 무엇을 잡았나

「어떻게 드러났나」를 함께 적는다. 다음 스프린트에 **어느 방법에 시간을 쓸지**의 근거다.

### 코드 리뷰가 잡은 것

| | 결함 | 그대로 나갔다면 |
|---|---|---|
| `OCR-1` | 모델 `Meta` 의 `unique_together`·`indexes` 가 **필드명**을 쓴다(`source_field` 와 어긋남) | `generate_schemas` 실패 → **OCR 과 무관한 테스트 160개가 통째로 죽는다.** 마이그레이션 SQL 은 멀쩡해서 운영 경로만 되고 테스트만 깨진다 |
| `FE-1` | 취소가 등록 화면을 벗어나지 못한다 | 취소를 눌러도 그 자리에 머문다 |
| `FE-2` | 「작성 중」 탭을 꺼 둔 채 등록하면 그 진료가 목록에서 걸러진다 | 엉뚱한 환자 화면이 열리거나 `null` 로 죽는다 |
| `FE-3` | 중복 확인 응답에 순서 보장이 없다 | **치지도 않은 번호를 근거로 등록을 막는다** (재현 확인) |
| `FE-4` | 검색어를 치는 것만으로 오른쪽 환자가 바뀐다 | 클릭 없이 다른 환자 화면이 열린다 — **남의 진료에 기록이 붙는 경로** |
| `FE-5` | 신규 등록 확인 화면이 방금 친 번호를 가린다 | 등록 직전 자릿수 오타를 잡을 마지막 자리가 없다 |
| `FIX-1` | `lastadmin01` 이 실제로는 마지막 관리자가 아니다 (admin 이 5명) | `KEY-24` 가 **다른 이유로** 통과·실패한다 |
| `API-1` | 전화번호 검색이 정규화되지 않는다 | 하이픈을 넣으면 0건 → 직원이 미등록으로 오인해 **중복 등록** (재현 확인) |
| `API-2` | 계약 §6 의 진료 생성 정본 예시가 그대로 `400` | 담당의 없이만 진료를 만들 수 있다 (재현 확인) |

### 실제로 돌려 보다 잡은 것

| | 결함 | 어떻게 드러났나 |
|---|---|---|
| `MIG-1` | 마이그레이션이 **적용 자체가 안 된다** | 독스트링의 따옴표가 테이블 주석 SQL 을 깨뜨림. `aerich upgrade` 에서 문법 오류 |
| `MIG-2` | 롤백이 부모를 먼저 지워 외래키에 걸린다 | `aerich downgrade` 실패. aerich 가 만든 순서가 틀렸다 |
| `AUTH-1` | 리프레시 쿠키가 **액세스 토큰 만료**로 사라진다 | 14일짜리가 60분에 죽는다 |
| `AUTH-2` | `COOKIE_DOMAIN=localhost` 가 `example.prod.env` 에도 있다 | 운영에서 **브라우저가 리프레시 쿠키를 전부 버린다** — 로그인은 되고 30분 뒤 끊긴다 |
| `AUTH-3` | 화면과 서버의 비밀번호 규칙이 다르다 | 화면은 「영문·숫자·기호」, 서버는 **대문자 필수** → `abcd1234!` 가 거부된다 |
| `AUTH-4` | `/users/me` 가 직원 토큰을 만나면 `500` | `payload["user_id"]` 를 바로 꺼내 `KeyError` |
| `FE-6` | 「업로드 후 안내문 생성」이 **404** | 없는 `/guide.html` 로 보낸다 |
| `FE-7` | 안내 문구가 다른 환자로 넘어가도 남는다 | 새 환자 이름 아래 붙어 **이 사람 것을 올렸다는 뜻**으로 읽힌다 |

### 돌연변이 검사가 잡은 것 — **검사 자체가 헛돌던 것 3건**

여기가 이번 스프린트에서 제일 값진 발견이다. **검사가 있는데 아무것도 안 보고 있었다.**

| | 헛돌던 검사 | 왜 못 봤나 |
|---|---|---|
| `TEST-1` | 「잠금 TTL 은 첫 실패에서만 건다」 | `FakeRedis` 가 TTL 을 늘 같은 값(600)으로 덮어써서 **값만 보면 차이가 없다.** 몇 번 걸었는지를 세도록 고침 |
| `TEST-2` | 「`with_roles()` 가 예약 계정을 안 준다」 | 정본 CSV 순서상 앞에 다른 계정이 있어 **가드가 없어도 통과**. 후보를 하나로 줄인 CSV 로 바꿔 확인하도록 고침 |
| `TEST-3` | 「신규 등록 확인 화면에 비밀번호가 없다」 | `must_change_password` 에 `password` 가 들어 있어 **문자열 검사가 늘 실패**. 해시 자체를 찾도록 고침 |

`TEST-2` 는 리뷰어가 코드에 대해 지적한 위험(「지금은 우연히 안전하다」)을
**검사가 그대로 물려받고 있던** 경우다. 사람이 지적한 것을 검사로 옮길 때
같은 우연에 기대지 않았는지 한 번 더 봐야 한다는 뜻이다.

---

## 5. 아직 안 고쳐진 것

| | 어디 | 무엇 |
|---|---|---|
| 🔴 | `#32` (KEY-60) | 변경 요청 상태 — OCR API |
| 🔴 | `#39` (KEY-34) | `API-1` 전화번호 검색 · `API-2` `doctor_id` |
| ~~🔴~~ | ~~워크플로~~ | ~~3-1 스택형 PR CI 구멍~~ → ✅ `KEY-102` (`#43`) |
| ~~🟠~~ | ~~`develop`~~ | ~~3-2 mypy 5건~~ → ✅ 같은 PR |
| 🟠 | 계약 | `GET /front-desk/visits?date=` 가 **계약에도 구현에도 없다** — `S1-1` 왼쪽 목록이 붙을 곳이 없다 |
| 🟠 | `#31` 리뷰 | 「못 읽은 항목도 행을 만드는가」·「저신뢰 임계값을 서버가 주는가」 미답 — `KEY-62`·`KEY-63` 이 이 답에 걸려 있다 |
| 🟡 | 문서 | `is_owner` 를 `spec-medical.md` 는 만들지 말라 하고 `KEY-26 §9` 는 유지하라 한다 |
| 🟡 | 문서 | 오류 코드 대소문자 — 인증 계약은 소문자, `KEY-26` 은 대문자 |
| 🟡 | 프로세스 | `project_workflow.md` 는 GitHub Issue 를 만들지 말라는데 실제로는 7개가 있다 |

---

## 6. 잔여 위험

**1. 병원 격리를 DB 가 안 지킨다.**
`patient.hospital_id` · `visit.hospital_id` 는 서비스 계층 검사에만 기대고 있다.
`KEY-73`(PR `#37`)이 `hospital` 테이블을 세우므로, 병합 뒤 외래키를 걸어야
「코드가 지키는 규칙」이 「DB 가 지키는 규칙」이 된다.

**2. 같은 날짜 중복 진료를 DB 가 안 막는다.**
계약이 서비스 계층에 맡겼는데, 읽고 나서 세는 방식이라 **동시에 두 요청이 오면
둘 다 통과한다.** 접수창구에서 스탭 둘이 같은 환자를 동시에 등록하는 일은 실제로 있다.

**3. 프런트에 자동 검사가 없다.**
4절의 결함 절반이 프런트인데 전부 사람이 찾았다. 사람이 안 볼 때 같은 것이 또 난다.

**4. 열린 PR 11개.**
오늘 하루에 열렸고 대부분 승인 대기다. `#27` → `#35`, `#31` → `#32` 처럼 사슬이라
앞이 막히면 뒤가 다 선다. 병합 순서를 정해 두지 않으면 마감 앞에서 몰린다.

---

## 7. 다음 스프린트에 넘기는 것

| 순서 | 무엇 | 왜 먼저인가 |
|---|---|---|
| ~~1~~ | ~~스택형 PR CI (3-1)~~ | ✅ `KEY-102` (`#43`) — 2026-08-19 병합 |
| ~~5~~ | ~~mypy 를 CI 에 (3-2)~~ | ✅ 같은 PR |
| **1** | `#39` 의 `API-1`·`API-2` | `API-1` 은 한 줄, `API-2` 는 결정만 필요 |
| **2** | `#31` 리뷰 질문 두 개에 답 | `KEY-62`·`KEY-63` 이 여기 걸려 있다 |
| **3** | `front-desk/visits` 계약 | `S1-1` 이 매일 처음 부르는 API |
| **4** | 병원 격리 외래키 | `#37` 병합 직후가 제일 싸다 |
| **5** | 프런트 자동 검사 (3-3) | 이번 결함 절반이 이 영역인데 전부 사람이 찾았다 |

---

## 부록 — 이 문서를 다시 만드는 법

```bash
git checkout develop && git pull
DB_HOST=127.0.0.1 uv run pytest app -q -rs          # 통과·건너뜀
uv run ruff check . && uv run ruff format . --check
uv run mypy app                                      # 2026-08-20 부터 CI 에서도 돈다
DB_HOST=127.0.0.1 uv run coverage run -m pytest app && uv run coverage report

gh pr list --state open  --json number,title,author,reviewDecision,statusCheckRollup
gh pr list --state merged --limit 30 --json number,title,mergedAt
```

`statusCheckRollup` 에 `test` 가 **없는** PR 은, 3-1 이 막힌 지금은 **워크플로가
바뀐 뒤로 아직 한 번도 밀지 않은 PR** 이다. `develop` 을 당겨 올리면 검사가 돈다.
