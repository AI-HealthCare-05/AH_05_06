"""스탭 미리보기가 환자와 **같은 파생**을 받는가 — KEY-294 (KEY-286 후속).

KEY-286 은 미리보기를 환자 렌더러와 같은 스타일·같은 골격으로 바꿨다. 그런데
**나의 목표 · 처방받은 약 · 약별 복용 방법** 세 카드는 못 그렸다 — 스탭 종점이
그 값을 안 줬기 때문이다. 「환자가 받는 그대로」라고 적어 놓고 부분만 보이는
자리가 남아 있었다.

**여기서 재는 것은 두 종점이 같은 것을 주는가**다. 「같은 함수를 부르나」가
아니라, 같은 진료에 대해 **응답이 실제로 같은가**를 잰다 — 부르는 함수가 같아도
한쪽이 뒤에서 값을 더하거나 빼면 갈린다.
"""

from datetime import UTC, datetime, timedelta

from app.dependencies.patient_auth import require_patient_session
from app.main import app
from app.models.catalog import BaselineDirection, LabBaseline, SetDisease
from app.models.ocr import OcrField
from app.models.visits import GuideDocument, PatientGuideLink, Visit
from app.services.patient_links import digest_link_token
from app.tests.guide_apis.test_guide_generate import (
    BASE,
    GenerateGuideTestCase,
    attach_confirmed_ocr,
    attach_prescription,
    make_clinic,
    make_staff,
    make_visit,
)

#: 이 검사 안에서만 사는 값. 진짜 토큰은 화면·로그·커밋에 안 남긴다(`AGENTS.md`).
SYNTHETIC_TOKEN = "synthetic-key294-token"


def without_nones(value: object) -> object:
    """`null` 인 칸을 뺀다.

    환자 종점은 `response_model_exclude_none=True` 라 빈 칸을 아예 안 싣고,
    스탭 종점은 싣는다. **그 차이는 값의 차이가 아니다** — 화면에서도 「키가
    없다」와 「`null` 이다」가 똑같이 거짓이다. 여기서 재려는 것은 값이므로
    직렬화 취향은 걷어 내고 본다.
    """
    if isinstance(value, dict):
        return {key: without_nones(inner) for key, inner in value.items() if inner is not None}
    if isinstance(value, list):
        return [without_nones(item) for item in value]
    return value


class TestKey294PreviewPayload(GenerateGuideTestCase):
    async def make_world(self, chart: str, *, with_derivations: bool):
        clinic = await make_clinic()
        staff = await make_staff(clinic, f"{chart}staff", ["staff"])
        doctor = await make_staff(clinic, f"{chart}doctor", ["doctor"])
        visit = await make_visit(clinic, f"SYN-{chart.upper()}")
        visit.doctor_id = doctor.staff_id
        await visit.save(update_fields=["doctor_id"])
        field = await attach_confirmed_ocr(visit, staff.staff_id)

        if with_derivations:
            await attach_prescription(visit, [("비잔", "1일 1회", 28)])
            await field.fetch_related("ocr_result")
            result = field.ocr_result
            confirmed_at = datetime(2026, 8, 22, 9, tzinfo=UTC)
            #: 판독 픽스처가 이미 `DIAGNOSIS` 를 만든다 — 하나뿐이라(유니크) 값만 바꾼다.
            diagnosis = await OcrField.get(ocr_result=result, field_type="DIAGNOSIS")
            diagnosis.extracted_value = "자궁내막증"
            diagnosis.is_confirmed = True
            diagnosis.confirmed_by = staff.staff_id
            diagnosis.confirmed_at = confirmed_at
            await diagnosis.save()
            await OcrField.create(
                ocr_result=result,
                field_type="CA-125",
                extracted_value="42 U/L",
                is_confirmed=True,
                confirmed_by=staff.staff_id,
                confirmed_at=confirmed_at,
            )
            await LabBaseline.create(
                hospital_id=clinic.hospital_id,
                doctor_id=doctor.staff_id,
                disease=SetDisease.ENDOMETRIOSIS,
                name="CA-125",
                direction=BaselineDirection.LOWER,
                high="35",
                keywords="CA-125, CA125",
                unit="U/L",
                position=0,
            )
        return clinic, staff, doctor, visit

    async def read_guide(self, visit_id: int, staff) -> dict:
        async with self.client() as client:
            headers = await self.sign_in(staff)
            await client.post(f"{BASE}/{visit_id}/guide/generate", headers=headers)
            got = await client.get(f"{BASE}/{visit_id}/guide", headers=headers)
        assert got.status_code == 200, got.text
        return got.json()

    async def test_the_preview_carries_the_three_cards_the_screen_could_not_draw(self) -> None:
        _, staff, _, visit = await self.make_world("k294full", with_derivations=True)

        preview = (await self.read_guide(visit.visit_id, staff))["preview"]

        assert preview["visit"] == "2026.08.22", "「나의 목표」 머리의 진료일이 없다"
        detail = preview["guide"]
        assert detail["drug"]["n"] == "비잔", "처방받은 약 카드를 채울 값이 없다"
        assert [goal["n"] for goal in detail["goals"]] == ["CA-125"], "나의 목표 카드를 채울 값이 없다"
        assert detail["how"], "약별 복용 방법 카드를 채울 값이 없다"

    async def test_an_empty_visit_still_gets_an_envelope_with_the_date(self) -> None:
        """처방도 기준선도 없는 진료 — 카드는 못 채워도 **날짜는 있다.**

        환자 화면은 목표가 없어도 「나의 목표」 카드를 세우고 머리에 진료일을
        단다. 봉투째 비우면 미리보기만 그 날짜를 잃는다.
        """
        _, staff, _, visit = await self.make_world("k294bare", with_derivations=False)

        preview = (await self.read_guide(visit.visit_id, staff))["preview"]

        assert preview is not None, "채울 것이 없다고 봉투째 비우면 미리보기가 진료일을 잃는다"
        assert preview["visit"] == "2026.08.22"
        assert preview["guide"]["goals"] == [], "없는 목표를 지어냈다"
        assert preview["guide"]["drug"] is None, "없는 처방을 지어냈다"
        assert preview["guide"]["how"] is None, "없는 복용 방법을 지어냈다"

    async def test_the_staff_preview_and_the_patient_screen_get_the_same_derivation(self) -> None:
        """**두 종점의 응답이 같다.** 이것이 이 티켓의 인수조건 2다."""
        _, staff, doctor, visit = await self.make_world("k294same", with_derivations=True)

        async with self.client() as client:
            staff_headers = await self.sign_in(staff)
            doctor_headers = await self.sign_in(doctor)
            await client.post(f"{BASE}/{visit.visit_id}/guide/generate", headers=staff_headers)
            await client.post(f"{BASE}/{visit.visit_id}/guide/submit", headers=staff_headers)
            approved = await client.post(f"{BASE}/{visit.visit_id}/guide/approve", headers=doctor_headers)
            assert approved.status_code == 200, approved.text

            guide = await GuideDocument.get(visit_id=visit.visit_id)
            await PatientGuideLink.create(
                guide_document=guide,
                token_digest=digest_link_token(SYNTHETIC_TOKEN),
                issued_by=staff.staff_id,
                expires_at=datetime.now(UTC) + timedelta(hours=72),
            )

            staff_side = await client.get(f"{BASE}/{visit.visit_id}/guide", headers=staff_headers)
            #: 환자 OTP 세션은 이 검사의 관심이 아니다 — 재는 것은 **파생이 같은가**다.
            app.dependency_overrides[require_patient_session] = lambda: None
            try:
                patient_side = await client.get(f"/api/v1/guides/{SYNTHETIC_TOKEN}")
            finally:
                app.dependency_overrides.pop(require_patient_session, None)

        assert patient_side.status_code == 200, patient_side.text
        assert without_nones(staff_side.json()["preview"]["guide"]) == without_nones(patient_side.json()["guide"]), (
            "스탭 미리보기와 환자 화면이 다른 파생을 받는다 — 「환자가 받는 그대로」가 거짓이 된다"
        )
        assert staff_side.json()["preview"]["visit"] == patient_side.json()["visit"], "진료일이 갈렸다"

    async def test_the_preview_adds_no_new_personal_data(self) -> None:
        """새로 나가는 것은 처방·검사 파생과 진료일뿐이다 — 인수조건 4."""
        _, staff, _, visit = await self.make_world("k294safe", with_derivations=True)

        preview = (await self.read_guide(visit.visit_id, staff))["preview"]

        assert set(preview) == {"visit", "guide"}, f"봉투에 모르는 값이 늘었다 — {sorted(preview)}"
        assert set(preview["guide"]) <= {"summary", "goals", "goalSay", "drug", "why", "how", "next"}, (
            f"파생에 모르는 값이 늘었다 — {sorted(preview['guide'])}"
        )

        blob = str(preview)
        visit_row = await Visit.get(visit_id=visit.visit_id).prefetch_related("patient")
        assert visit_row.patient.phone not in blob, "연락처가 미리보기에 실렸다"
        assert SYNTHETIC_TOKEN not in blob and "token" not in blob, "링크 토큰 자리가 미리보기에 생겼다"
