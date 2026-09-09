"""환자 관리 표를 쪽으로 넘기고, 검색창으로 마지막 진료일을 찾는다 — KEY-303.

**전에는 조용히 잘렸다.** 화면이 `limit=50` 을 한 번 부르고 `next_cursor` 를
아무도 안 봤다. 전체가 101명이어도 50명에서 끝났는데, 배지는 서버가 세어 준
101 을 그대로 보여 줘서 잘린 줄도 몰랐다.

커서가 아니라 자리(offset)로 센다 — 커서는 앞으로만 가서 「이전」이 안 된다.
"""

from datetime import date

import pytest
from tortoise.contrib.test import TestCase

from app.models.patients import Patient, PatientGender
from app.models.staffs import Hospital
from app.repositories.patient_repository import PatientRepository
from app.services.patients import parse_last_visit_query


class TestTheSearchBoxReadsDates:
    """검색창 하나를 이름·차트번호·휴대폰과 나눠 쓴다. 날짜 칸을 따로 두지 않기로 했다."""

    @pytest.mark.parametrize(
        ("typed", "expected"),
        [
            ("2026-08-15", (date(2026, 8, 15), date(2026, 8, 15))),
            ("2026-8-5", (date(2026, 8, 5), date(2026, 8, 5))),
            ("2026-08", (date(2026, 8, 1), date(2026, 8, 31))),
            ("2026-02", (date(2026, 2, 1), date(2026, 2, 28))),
            ("2024-02", (date(2024, 2, 1), date(2024, 2, 29))),  # 윤년
            ("  2026-08-15  ", (date(2026, 8, 15), date(2026, 8, 15))),
        ],
    )
    def test_a_date_shaped_word_means_the_last_visit(self, typed: str, expected: tuple[date, date]) -> None:
        assert parse_last_visit_query(typed) == expected

    @pytest.mark.parametrize(
        "typed",
        [
            None,
            "",
            "   ",
            "윤지아",
            "12401",  # 차트번호 — 숫자만이라 하이픈 꼴과 겹칠 수 없다
            "010-2431-7788",  # 휴대폰 — 넉 자리 해가 안 된다
            "2026",  # 해만으로는 안 찾는다
            "2026-13",  # 없는 달을 조용히 12월로 고치지 않는다
            "202608",  # 하이픈이 없으면 날짜가 아니다 — 여섯 자리 차트번호일 수 있다
            "20260815",
            "2026-02-30",  # 없는 날도 마찬가지
            "26-08",
        ],
    )
    def test_everything_else_stays_a_name_search(self, typed: str | None) -> None:
        """날짜가 아니면 그대로 이름·차트·휴대폰 검색으로 넘긴다.

        **조용히 고치지 않는다.** `2026-13` 을 12월로 읽으면 사람은 13월을 쳤다는
        것을 모른 채 엉뚱한 답을 믿는다.
        """
        assert parse_last_visit_query(typed) is None

    def test_a_chart_number_never_becomes_a_date(self) -> None:
        """차트번호가 날짜로 새면 이름으로 찾던 사람이 빈 표를 본다."""
        for chart_no in ("12401", "09948", "1", "00000", "202608", "20260815"):
            assert parse_last_visit_query(chart_no) is None


class TestTheCountsFollowTheSearch(TestCase):
    """검색어를 넣은 채 조각을 고르면 **배지도 같이 좁아진다** — 이희진 님 #270 리뷰 ②.

    진료에서 나오는 조각(진행 중 · 챙겨주세요)의 셈은 의원의 최근 진료를 훑어
    낸다. 그 셈이 검색어를 모르면 표는 걸러졌는데 배지는 안 걸러져 **배지가 표보다
    커진다.** 그 값이 쪽 나눔의 총수라, 「다음」을 눌렀을 때 빈 표가 뜬다.

    저장소의 `ids_scoped` 가 검색어에 걸리는 번호를 다 주고, 서비스가 그것으로
    조각의 셈을 좁힌다.
    """

    async def test_the_repository_hands_back_every_matching_id(self) -> None:
        """쪽 크기와 무관하게 **다** 준다 — 한 쪽만 주면 셈이 다시 어긋난다."""
        hospital = await Hospital.create(name="도로시여성의원")
        for i in range(7):
            await Patient.create(
                hospital_id=hospital.hospital_id,
                name=f"윤지아{i}",
                hospital_patient_no=f"9000{i}",
                birth_date=date(1990, 1, 1),
                gender=PatientGender.FEMALE,
                phone=f"0102222{i:04d}",
            )
        await Patient.create(
            hospital_id=hospital.hospital_id,
            name="다른사람",
            hospital_patient_no="88888",
            birth_date=date(1990, 1, 1),
            gender=PatientGender.FEMALE,
            phone="01033330000",
        )

        repo = PatientRepository()
        hit = await repo.ids_scoped(hospital.hospital_id, keyword="윤지아")
        assert len(hit) == 7, "쪽 크기에 잘리면 셈이 표보다 작아진다"

        everyone = await repo.ids_scoped(hospital.hospital_id, keyword=None)
        assert everyone == [], "검색어가 없으면 좁힐 것도 없다 — 의원 전체를 다 읽지 않는다"

    async def test_a_word_that_matches_nobody_narrows_to_nothing(self) -> None:
        hospital = await Hospital.create(name="도로시여성의원")
        await Patient.create(
            hospital_id=hospital.hospital_id,
            name="윤지아",
            hospital_patient_no="12401",
            birth_date=date(1990, 1, 1),
            gender=PatientGender.FEMALE,
            phone="01024317788",
        )

        assert await PatientRepository().ids_scoped(hospital.hospital_id, keyword="없는이름") == []
