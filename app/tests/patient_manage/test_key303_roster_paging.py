"""환자 관리 표를 쪽으로 넘기고, 검색창으로 마지막 진료일을 찾는다 — KEY-303.

**전에는 조용히 잘렸다.** 화면이 `limit=50` 을 한 번 부르고 `next_cursor` 를
아무도 안 봤다. 전체가 101명이어도 50명에서 끝났는데, 배지는 서버가 세어 준
101 을 그대로 보여 줘서 잘린 줄도 몰랐다.

커서가 아니라 자리(offset)로 센다 — 커서는 앞으로만 가서 「이전」이 안 된다.
"""

from datetime import date

import pytest

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
