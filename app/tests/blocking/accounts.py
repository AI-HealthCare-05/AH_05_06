"""차단 회귀 검사가 함께 쓰는 계정과 자료 — KEY-153.

이 파일의 규칙은 하나다. **토큰을 손으로 만들지 않는다.**

`KEY-116` 이 그 대가를 보여 줬다. OCR 검사가 `JwtService().issue_jwt_pair(user)`
로 토큰을 직접 만들어 써서, 라우트로는 아무도 얻을 수 없는 토큰 위에서 초록불이
켜졌다. 실제 앱에서는 다섯 엔드포인트가 전부 `401` 이었는데 아무도 몰랐다.

그래서 여기서는 `POST /api/v1/auth/login` 을 실제로 부른다. 로그인이 못 주는
토큰이면 검사도 못 쓴다 — 그게 맞다.

의원이 둘인 이유
--------------
「타 병원 자료가 안 보인다」를 재려면 **남의 의원 사람**이 있어야 한다.
`docs/api/hospital.md` 5절이 못박은 대로 타 병원 리소스는 `403` 이 아니라
`404` 다 — 존재 여부 자체를 감춘다.
"""

import itertools
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from httpx import ASGITransport, AsyncClient
from tortoise.timezone import now

from app.core.utils.security import hash_password
from app.main import app
from app.models.patients import Patient
from app.models.staffs import Hospital, Staff, StaffStatus
from app.models.visits import GuideDocument, GuideSection, GuideSectionKey, GuideStatus, Visit
from app.tests.ocr_fixture import complete_ocr

#: 합성 계정의 비밀번호. 운영 값과 겹치지 않게 한 곳에만 둔다.
PASSWORD = "Blocking-Test-1!"

LOGIN_URL = "/api/v1/auth/login"
BASE_URL = "http://test"


@dataclass(frozen=True)
class Actor:
    """로그인해서 토큰까지 받아 둔 사람."""

    login_id: str
    token: str
    hospital_id: int
    staff_id: int

    @property
    def auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}


@dataclass(frozen=True)
class Fence:
    """의원 하나와 그 안의 사람·자료."""

    hospital_id: int
    patient_id: int
    visit_id: int


async def _hospital(name: str) -> Hospital:
    hospital, _ = await Hospital.get_or_create(name=name)
    return hospital


async def make_staff(
    hospital: Hospital,
    login_id: str,
    roles: list[str],
    *,
    must_change_password: bool = False,
) -> Staff:
    """합성 직원 하나.

    `must_change_password` 를 **꺼서** 만든다. 모델 기본값은 참이고, 그 상태로는
    보호 API 가 전부 `403 password_change_required` 로 막힌다
    (`docs/api/hospital.md` — 「최초 로그인 사용자는 `L-3` 완료 전 다른 보호
    화면에 접근할 수 없음」). 그건 옳은 동작이라, 역할·병원 차단을 재려면
    먼저 이 문을 지난 사람이어야 한다.

    그 규칙 자체는 `must_change_password=True` 인 계정으로 따로 잰다.
    """
    return await Staff.create(
        hospital=hospital,
        login_id=login_id,
        password_hash=hash_password(PASSWORD),
        name=f"합성-{login_id}",
        roles=roles,
        status=StaffStatus.ACTIVE,
        must_change_password=must_change_password,
    )


async def make_staff_in(
    hospital_id: int,
    login_id: str,
    roles: list[str],
    *,
    must_change_password: bool = False,
) -> Actor:
    """이미 만들어 둔 의원에 사람을 하나 더 들인다.

    `build_two_hospitals()` 가 깐 다섯 말고 **한 명 더** 필요한 검사가 있다
    (남의 의원 의사 · 최초 로그인 상태의 의사). 세계를 통째로 다시 깔면
    검사가 무엇을 더했는지 읽기 어려워진다.
    """
    hospital = await Hospital.get(hospital_id=hospital_id)
    staff = await make_staff(hospital, login_id, roles, must_change_password=must_change_password)
    return await actor(login_id, hospital_id, staff.staff_id)


async def make_patient_and_visit(hospital_id: int, chart_no: str) -> tuple[int, int]:
    """그 의원 안의 환자 한 명과 진료 한 건. 격리 검사의 과녁이다."""
    patient = await Patient.create(
        hospital_id=hospital_id,
        hospital_patient_no=chart_no,
        name="합성환자",
        birth_date=date(1990, 1, 1),
        phone="01000000000",
    )
    visit = await Visit.create(
        hospital_id=hospital_id,
        patient_id=patient.patient_id,
        visited_at="2026-08-21T10:00:00+09:00",
    )
    return patient.patient_id, visit.visit_id


#: 생성 경로에 보낼 **요청 본문**. 위 `make_patient_and_visit` 이 ORM 으로 심는
#: 것과 짝이다 — 한쪽은 행을 만들고 한쪽은 API 에 보낸다. 다른 일이지만 **같은
#: 합성 환자·진료의 모양**이라 한 파일에 둔다. 필수 필드가 늘면 여기 둘을 함께
#: 본다 (이희진 님 `#122` 리뷰).
#:
#: 부를 때마다 새 값을 준다. 같은 몸을 두 번 보내면 차트번호 유니크 제약이나
#: 「한 환자에게 같은 날 진료 한 건」 제약에 걸려 `409` 가 난다 — 차단이 아니라
#: 중복이라 「정상 경로가 막혔다」로 잘못 읽힌다.
_serial = itertools.count(1)

#: 픽스처가 심는 진료가 `2026-08-21` 이라 그 뒤로 잡는다.
_VISIT_BASE = date(2026, 9, 1)


def new_patient_body() -> dict:
    return {
        "hospital_patient_no": f"SYN-BLOCK-{next(_serial)}",
        "name": "합성차단환자",
        "birth_date": "1990-01-01",
        "phone": "010-0000-1111",
        "sms_consent": False,
    }


def new_visit_body() -> dict:
    """진료일을 **한 방향으로만** 민다.

    예전에는 `% 28` 로 한 달 안에 감쌌다. 그런데 이 팩토리는 요청이 거부되는
    검사(401·403·404)에서도 불려서 번호를 소모한다. 라우트가 늘수록 여유가
    줄어 언젠가 같은 날이 두 번 나오고, 그때 `409` 로 **우연히** 실패한다.
    감싸지 않으면 그 자리가 없다 (이희진 님 `#122` 리뷰).
    """
    return {"visited_at": f"{_VISIT_BASE + timedelta(days=next(_serial))}T10:30:00+09:00"}


async def make_guide(hospital_id: int, visit_id: int, status: GuideStatus) -> int:
    """그 진료의 안내문 한 건.

    **생성 경로(`/guide/generate`)를 타지 않는다.** 그 경로는 확정 OCR 을
    요구해서 여기 필요한 것보다 훨씬 많은 것을 깔아야 한다. 이 파일이 재는
    것은 「누가 승인·조회할 수 있는가」이지 「어떻게 만들어지는가」가 아니다.

    다만 **토큰만은 여전히 라우트로 받는다** — 이 파일의 규칙은 그것이다.
    """
    guide = await GuideDocument.create(
        hospital_id=hospital_id,
        visit_id=visit_id,
        status=status,
        approved_at=now() if status is GuideStatus.SCHEDULED_TO_SEND else None,
        approved_by=1 if status is GuideStatus.SCHEDULED_TO_SEND else None,
    )
    await GuideSection.create(
        guide_document=guide,
        section_key=GuideSectionKey.MEDICATION,
        generated_body="합성 복약 안내",
    )
    return guide.guide_document_id


@dataclass(frozen=True)
class OcrFixture:
    """그 의원에 **실제로 있는** 판독 자료. 격리 검사의 과녁이다.

    타 병원 접근이 `404` 인 것만으로는 「격리됐다」를 못 보인다 — 그냥 그런
    리소스가 없어서 `404` 일 수도 있다. **같은 식별자로 주인은 열고 남은 못
    여는 것**을 보여야 격리다 (유가은 님 · 이희진 님 `#87` 리뷰).
    """

    job_id: str
    field_id: int
    #: **실제로 만든 문서다.** 한때 `0` 을 넣어 두고 아무 데서도 안 썼는데,
    #: docstring 은 「격리 검사의 과녁」이라 적혀 있어 말과 코드가 어긋났다
    #: (이희진 님 `#87` 리뷰).
    document_id: int


async def make_ocr(hospital_id: int, visit_id: int, job_id: str, requested_by: int) -> OcrFixture:
    """끝난 판독 한 건. 만드는 일은 `app/tests/ocr_fixture.py` 가 한다.

    예전에는 여기서 `OcrJob` · `OcrResult` · `OcrField` 를 손으로 만들었다.
    그래서 운영이 실제로 만드는 모양(`OcrDocumentText`, `completed_at` …)과
    조금씩 달랐다 (KEY-172).
    """
    done = await complete_ocr(
        hospital_id=hospital_id,
        visit_id=visit_id,
        job_id=job_id,
        requested_by=requested_by,
    )
    return OcrFixture(job_id=done.job_id, field_id=done.field_id, document_id=done.document_id)


def client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url=BASE_URL)


async def login(login_id: str) -> str:
    """**라우트를 통해** 액세스 토큰을 얻는다. 손으로 만들지 않는다."""
    async with client() as http:
        response = await http.post(LOGIN_URL, json={"login_id": login_id, "password": PASSWORD})
    assert response.status_code == 200, f"{login_id} 로그인이 {response.status_code} 다 — 이 검사가 서 있을 바닥이 없다"
    token: str = response.json()["access_token"]
    return token


async def actor(login_id: str, hospital_id: int, staff_id: int) -> Actor:
    return Actor(login_id=login_id, token=await login(login_id), hospital_id=hospital_id, staff_id=staff_id)


async def build_two_hospitals() -> dict[str, Any]:
    """의원 둘 · 역할 셋 · 각 의원의 환자·진료 하나씩.

    반환하는 것은 검사가 바로 쓸 수 있는 모양이다 — 누가 무엇에 손댈 수
    있어야 하고 없어야 하는지가 이 자료 하나로 갈린다.
    """
    h1 = await _hospital("합성 기준의원")
    h2 = await _hospital("합성 이웃의원")

    staff1 = await make_staff(h1, "blk_staff1", ["staff"])
    doctor1 = await make_staff(h1, "blk_doctor1", ["doctor"])
    admin1 = await make_staff(h1, "blk_admin1", ["admin"])
    staff2 = await make_staff(h2, "blk_staff2", ["staff"])
    newbie1 = await make_staff(h1, "blk_newbie1", ["staff"], must_change_password=True)

    p1, v1 = await make_patient_and_visit(h1.hospital_id, "BLK-H1-001")
    p2, v2 = await make_patient_and_visit(h2.hospital_id, "BLK-H2-001")

    return {
        "staff1": await actor("blk_staff1", h1.hospital_id, staff1.staff_id),
        "doctor1": await actor("blk_doctor1", h1.hospital_id, doctor1.staff_id),
        # 관리자만 가진 계정 — 의원 운영은 되지만 진료 자료는 못 본다(KEY-9).
        "admin1": await actor("blk_admin1", h1.hospital_id, admin1.staff_id),
        "staff2": await actor("blk_staff2", h2.hospital_id, staff2.staff_id),
        # 최초 로그인 상태 그대로인 사람 — 비밀번호를 바꾸기 전이다.
        "newbie1": await actor("blk_newbie1", h1.hospital_id, newbie1.staff_id),
        "h1": Fence(hospital_id=h1.hospital_id, patient_id=p1, visit_id=v1),
        "h2": Fence(hospital_id=h2.hospital_id, patient_id=p2, visit_id=v2),
    }
