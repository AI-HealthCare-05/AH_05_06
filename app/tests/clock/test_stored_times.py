"""저장되는 시각이 의원 시간대와 맞는가 — KEY-234.

**아홉 시간 어긋나 있었다.** `use_tz: True` 에서 `tortoise.timezone.now()` 는
UTC 를 주는데, asyncmy 는 값을 넣을 때 tzinfo 를 버리고 벽시계만 적고
(KEY-181) 읽을 때는 설정의 `Asia/Seoul` 로 도장을 찍는다. 그래서 `auto_now_add`
로 적힌 값이 전부 아홉 시간 이르게 읽혔다 — 직접 KST 로 넣는 `visited_at` 만
멀쩡했다.

**눈에 보이는 것보다 나쁜 것은 시각 비교였다.** 링크 만료와 인증번호 잠금이
`expires_at <= now()` 로 재는데 왼쪽이 아홉 시간 이르니 **잠금이 즉시 풀렸다.**

화면 검사로는 안 잡힌다 — 화면은 서버가 준 글자를 그릴 뿐이다. 여기서 잰다.
"""

from datetime import datetime, timedelta

from tortoise.contrib.test import TestCase
from tortoise.timezone import now

from app.core.config import Config
from app.models.patients import Patient, PatientGender
from app.models.staffs import Hospital
from app.models.visits import Visit

KST = Config().TIMEZONE


class StoredTimeTestCase(TestCase):
    async def a_visit(self) -> Visit:
        clinic = await Hospital.create(name="시각 확인 의원")
        patient = await Patient.create(
            hospital_id=clinic.hospital_id,
            hospital_patient_no="TZ001",
            name="확인",
            birth_date="1990-01-01",
            gender=PatientGender.FEMALE,
            phone="01000000000",
        )
        return await Visit.create(hospital_id=clinic.hospital_id, patient=patient, visited_at=datetime.now(KST))

    def test_now_speaks_the_clinic_clock(self) -> None:
        """**여기가 뿌리다.** `now()` 가 UTC 를 주면 적히는 값이 전부 어긋난다."""
        stamped = now()

        assert stamped.tzinfo is not None, "시간대 없는 값은 어느 시계인지 알 수 없다"
        assert stamped.utcoffset() == timedelta(hours=9), (
            f"의원 시계가 아니다: {stamped.tzinfo} — `use_tz` 를 켜면 UTC 가 된다"
        )

    async def test_a_stamped_row_reads_back_as_now(self) -> None:
        """`auto_now_add` 로 적힌 값이 지금과 같아야 한다."""
        visit = await self.a_visit()

        drift = abs((visit.created_at - now()).total_seconds())

        assert drift < 60, f"방금 만든 줄의 시각이 {drift / 3600:.0f}시간 어긋난다"

    async def test_what_we_put_in_comes_back_out(self) -> None:
        when = datetime(2026, 9, 1, 18, 30, tzinfo=KST)
        clinic = await Hospital.create(name="왕복 확인 의원")
        patient = await Patient.create(
            hospital_id=clinic.hospital_id,
            hospital_patient_no="TZ002",
            name="왕복",
            birth_date="1990-01-01",
            gender=PatientGender.FEMALE,
            phone="01000000001",
        )
        made = await Visit.create(hospital_id=clinic.hospital_id, patient=patient, visited_at=when)

        again = await Visit.get(visit_id=made.visit_id)

        assert again.visited_at == when, f"{when} 을 넣었는데 {again.visited_at} 로 읽힌다"

    async def test_a_future_time_stays_in_the_future(self) -> None:
        """**만료와 잠금이 이 비교로 돈다.**

        링크 만료(`expires_at <= now()`)와 인증번호 잠금(`locked_until <=
        timestamp`)이 여기 걸린다. 적을 때와 읽을 때의 시계가 다르면 15분짜리
        잠금이 그 자리에서 풀린다 — 실제로 그랬다.
        """
        visit = await self.a_visit()
        later = now() + timedelta(minutes=15)
        await Visit.filter(visit_id=visit.visit_id).update(updated_at=later)

        again = await Visit.get(visit_id=visit.visit_id)

        assert again.updated_at > now(), "15분 뒤로 적었는데 이미 지난 것으로 읽힌다"


class ConfigAgreementTestCase(TestCase):
    """**검사 판과 앱이 같은 시계를 써야 한다.**

    `generate_config` 가 `use_tz` 를 기본값(False)으로 두는 바람에, 앱이
    `True` 인 동안 검사만 `False` 로 돌았다 — 위의 검사들이 다 통과하면서
    서버는 아홉 시간 어긋나 있었다. 설정이 갈리면 검사는 아무것도 못 본다.
    """

    def test_the_test_bench_uses_the_app_clock(self) -> None:
        from app.core.db.databases import TORTOISE_ORM
        from app.tests.conftest import get_test_db_config

        bench = get_test_db_config()

        assert bench["use_tz"] == TORTOISE_ORM["use_tz"], "검사와 서버가 다른 시계로 돈다"
        assert bench["timezone"] == TORTOISE_ORM["timezone"]
