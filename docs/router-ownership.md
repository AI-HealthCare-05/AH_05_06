# 라우터 소유권 — 어느 파일이 어느 경로를 갖는가

> KEY-164 · 작성 2026-08-24
> 근거: `app/tests/routing/test_route_ownership.py` — **이 문서가 아니라 그 검사가 강제한다.**

`#95`(KEY-133) 리뷰에서 「`/visits/{id}/ocr-job` 의 공개 경로는 visit 인데 구현은
`app/ocr/api.py` 에 있다」가 지적됐다. 조사해 보니 **오류가 아니라 이미 있던
규칙**이었다. 다만 아무 데도 안 적혀 있어서 다음 사람이 또 묻게 된다.

## 규칙 — 하위 자원이 자기 라우트를 갖는다

**URL 앞부분이 아니라 「무엇에 대한 것인가」가 소유를 정한다.** 파일은 그 자원의
서비스가 사는 곳에 둔다.

```
/visits/{id}                        진료 그 자체   apis/v1/visit_routers.py
/visits/{id}/guide/**               안내문         apis/v1/guide_routers.py
/visits/{id}/guide/link             환자 링크      apis/v1/patient_link_routers.py
/visits/{id}/checkin                환자 응답      apis/v1/patient_link_routers.py
/visits/{id}/ocr-job(s)             판독           ocr/api.py
/front-desk/visits/{id}/documents   문서           documents/api.py
```

`/visits/**` 가 여섯 모듈에 흩어져 보이지만 흩어진 것이 아니라 **자원별로 갈린
것**이다. 판독 라우트를 `visit_routers.py` 로 옮기면 `OcrService` · `OcrActor` ·
판독 오류 계약이 함께 따라오거나, 아니면 그것들을 두 곳에서 import 하게 된다.

### 왜 URL 기준이 아닌가

URL 기준으로 모으면 `visit_routers.py` 가 안내문·판독·문서·링크의 서비스를 전부
알아야 한다. 그러면 「진료를 고치는 코드」와 「판독 결과를 읽는 코드」가 한 파일에
살고, 한쪽을 고칠 때 다른 쪽을 깨뜨린다.

### 예외를 두는 자리

**하위 자원이 자기 서비스를 갖지 않으면** 부모 라우터에 둔다. 예를 들어
`GET /patients/{id}/visits` 는 목록일 뿐이라 `visit_routers.py` 에 있다.

## 오류 봉투는 라우터마다 opt-in 이다 — 짝을 맞춰야 한다

`route_class=ContractRoute` 를 단 라우터만 `ApiError` 를 공통 봉투로 바꾼다.
안 단 라우터에서 `ApiError` 가 나면 **아무도 안 받아 raw 500 으로 샌다.**

```
봉투 있음   front-desk · patients · visits · documents
봉투 없음   auth · health · guides · patient-links · patient-guides · patient-checkins · ocr
```

봉투 없는 쪽은 `AuthError` 만 던진다 — 그것은 `app/main.py` 의 전역 처리기가 받는다.

**새 라우터를 만들 때 둘 중 하나를 고른다.**

- 서비스가 `app.core.api_errors.ApiError` 를 던진다 → `route_class=ContractRoute` 를 단다
- 서비스가 `app.core.auth_errors.AuthError` 를 던진다 → 안 달아도 된다

`app/dependencies/patient_access.py` 의 `require_patient_*` 는 `ApiError` 를 던진다.
**그 의존성을 쓰는 라우터는 반드시 봉투를 입어야 한다.**

## ⚠ 알려진 함정 — `ApiError` 라는 이름이 두 뜻이다

```python
app.core.api_errors.ApiError(status_code, code, message)
app.core.auth_errors.AuthError(code, status_code, message)   # 순서가 반대다
```

그런데 `guides.py` · `patient_links.py` · `checkins.py` 는 이렇게 쓴다.

```python
from app.core.auth_errors import AuthError as ApiError
```

**같은 저장소에서 `ApiError(...)` 가 두 뜻을 갖는다.** 서비스 사이로 코드를
옮기면 상태 코드와 오류 코드가 조용히 뒤바뀐다.

고치려면 공통 오류 계약을 건드려야 해서 이 일감 범위 밖이다. 지금은
`test_the_two_error_types_still_disagree_on_argument_order` 가 **사실을 못 박아**
둔다 — 둘이 같아지는 날 그 검사가 죽고, 그때 별칭을 걷으면 된다.

## KEY-159 와의 관계

이 문서는 `app/ocr/api.py` 의 **배치를 바꾸지 않는다.** 위 규칙에 이미 맞기
때문이다. 그래서 「KEY-159 병합 뒤 재배치」라는 선행 조건이 이 결론에서는
성립하지 않는다 — 옮길 것이 없다.

**검사가 그것까지 알려 주지는 않는다.** 위 소유 표는 경로에 `/visits` 가
들어간 것만 세므로(`test_a_sub_resource_owns_its_own_routes`), KEY-159 가
`POST /documents/{id}/ocr` 를 지워도 표도 검사도 움직이지 않는다.

실제로 그랬다 — `#112` 가 그 라우트를 지웠고, 소유 표와 검사는 그대로다.
