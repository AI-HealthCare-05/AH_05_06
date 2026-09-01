"""발송 이력 CSV — KEY-234, 와이어프레임 S2-4 하단 「CSV 내려받기」.

**표는 「일부 행만 표시」한다고 원문이 적어 두었고, 이 받기가 그 나머지를
가져가는 자리다** — 여기서도 자르면 둘 다 일부인 셈이 된다.

두 가지를 특히 잰다.

  · **셈식 주입.** 이름이 `=cmd|...` 로 시작하면 엑셀이 그것을 실행하려 든다.
    우리가 만든 파일이 남의 컴퓨터에서 도는 셈이라, 나가기 전에 막아야 한다.
  · **낱말이 두 곳에 산다.** 화면은 `frontend/js/message-words.js` 로 옮기고
    파일은 서버가 옮긴다. 한쪽만 고치면 같은 문자가 화면과 파일에서 다른
    이름으로 뜬다 — 여기서 둘이 같은지 잰다.
"""

import csv
import io
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from httpx import ASGITransport, AsyncClient
from tortoise.contrib.test import TestCase

from app.core.redis_client import get_redis
from app.core.time import DISPLAY_TIMEZONE, clinic_today
from app.core.utils.security import hash_password
from app.dtos.messages import SentMessageItem
from app.main import app
from app.models.patients import Patient, PatientGender
from app.models.staffs import Hospital, Staff
from app.models.visits import (
    GuideDocument,
    GuideMessage,
    GuideMessageFailure,
    GuideMessageKind,
    GuideMessageStatus,
    Visit,
)
from app.services.message_export import (
    FAILURE_SAYING,
    KIND_SAYING,
    csv_filename,
    csv_rows,
    defuse,
)
from app.services.staff_auth import StaffSessionService
from app.tests.fakes import FakeRedis

TODAY = clinic_today()
WORDS = Path(__file__).resolve().parents[3] / "frontend" / "js" / "message-words.js"


def an_item(**over: Any) -> SentMessageItem:
    values: dict[str, Any] = {
        "guide_message_id": 1,
        "visit_id": 11,
        "patient_id": 21,
        "happened_at": datetime(2026, 8, 11, 18, 0, tzinfo=DISPLAY_TIMEZONE),
        "kind": GuideMessageKind.GUIDE,
        "status": GuideMessageStatus.SENT,
        "failure_code": None,
        "name": "강예린",
        "hospital_patient_no": "11902",
        "gender": PatientGender.FEMALE,
        "birth_date": date(1997, 4, 22),
        "age": 29,
        "prescription_set": "자궁내막증 · 비잔",
        "viewed": True,
        "viewed_at": datetime(2026, 8, 11, 19, 30, tzinfo=DISPLAY_TIMEZONE),
    }
    values.update(over)
    return SentMessageItem(**values)


class CsvShapeTestCase(TestCase):
    def test_a_row_reads_the_way_the_screen_does(self) -> None:
        rows = csv_rows([an_item()])

        assert rows[0][0] == "발송일시"
        assert rows[1] == [
            "2026-08-11 18:00",
            "강예린",
            "11902",
            "여 · 29세 · 1997-04-22",
            "자궁내막증 · 비잔",
            "진료 안내문",
            "발송 완료",
            "",
            "열람",
            "2026-08-11 19:30",
        ]

    def test_a_failed_row_is_not_asked_about_viewing(self) -> None:
        row = csv_rows(
            [
                an_item(
                    status=GuideMessageStatus.FAILED,
                    failure_code=GuideMessageFailure.INVALID_PHONE,
                    viewed=False,
                    viewed_at=None,
                )
            ]
        )[1]

        assert row[6] == "발송 실패"
        assert row[7] == "잘못된 번호"
        assert row[8] == "—", "못 나간 문자에 열람을 묻는 것은 뜻이 없다"

    def test_unviewed_is_said_not_left_blank(self) -> None:
        row = csv_rows([an_item(viewed=False, viewed_at=None)])[1]

        assert row[8] == "미열람", "빈칸은 「모른다」로 읽힌다"
        assert row[9] == ""

    def test_every_row_has_the_same_number_of_cells(self) -> None:
        rows = csv_rows([an_item(), an_item(status=GuideMessageStatus.FAILED, failure_code=None)])

        assert {len(row) for row in rows} == {len(rows[0])}

    # ── 셈식 주입 ────────────────────────────────────────

    def test_a_name_that_looks_like_a_formula_is_defused(self) -> None:
        for lead in ("=", "+", "-", "@", "\t", "\r"):
            name = lead + "cmd|' /c calc'!A1"
            assert defuse(name).startswith("'" + lead), f"{lead!r} 로 시작하는 값이 그대로 나간다"

    def test_defusing_keeps_the_value(self) -> None:
        """지우거나 바꾸지 않는다 — 이름이 `-` 로 시작할 수도 있다."""
        assert defuse("-김") == "'-김"
        assert defuse("김서연") == "김서연", "멀쩡한 이름에 따옴표를 붙이면 안 된다"
        assert defuse("") == ""
        assert defuse(None) == ""

    def test_the_dangerous_columns_go_through_defuse(self) -> None:
        row = csv_rows([an_item(name="=1+1", hospital_patient_no="+1", prescription_set="-set")])[1]

        assert row[1] == "'=1+1"
        assert row[2] == "'+1"
        assert row[4] == "'-set"

    # ── 파일 이름 ────────────────────────────────────────

    def test_the_filename_says_which_period(self) -> None:
        name = csv_filename(date(2026, 8, 5), date(2026, 8, 11))

        assert name == "send-history-2026-08-05-to-2026-08-11.csv"
        assert name.isascii(), "한글 파일 이름은 브라우저마다 다르게 깨진다"

    # ── 낱말이 두 곳에서 같은가 ──────────────────────────

    def test_the_server_and_the_screen_say_the_same_words(self) -> None:
        if not WORDS.exists():
            # `fastapi` 컨테이너에는 `frontend/` 가 안 붙어 있다. 호스트에서
            # 도는 판이 정본이고(`DB_HOST=localhost uv run pytest app`), 거기서
            # 이 검사가 실제로 두 곳을 견준다.
            self.skipTest(f"{WORDS} 가 없다 — 화면 파일이 안 붙은 곳에서 돌고 있다")
        text = WORDS.read_text(encoding="utf-8")

        def said(block: str) -> dict[str, str]:
            body = re.search(r"var " + block + r" = \{(.*?)\n\};", text, re.S)
            assert body, f"{block} 를 못 찾았다 — 검사가 헛돈다"
            return dict(re.findall(r"(\w+):\s*\"([^\"]+)\"", body.group(1)))

        screen_kinds = said("MESSAGE_SAYING")
        for kind, word in KIND_SAYING.items():
            assert screen_kinds.get(str(kind)) == word, (
                f"{kind} 를 화면은 「{screen_kinds.get(str(kind))}」, 파일은 「{word}」로 부른다"
            )

        screen_failures = said("FAILURE_SAYING")
        for code, word in FAILURE_SAYING.items():
            assert screen_failures.get(str(code)) == word, f"{code} 의 이름이 두 곳에서 다르다"

        assert len(screen_kinds) == len(KIND_SAYING), "한쪽에만 회차가 늘었다"
        assert len(screen_failures) == len(FAILURE_SAYING), "한쪽에만 실패 사유가 늘었다"


class CsvDownloadTestCase(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.redis = FakeRedis()
        app.dependency_overrides[get_redis] = lambda: self.redis

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        super().tearDown()

    async def a_sent(self, hospital: Hospital, name: str, hour: int) -> None:
        when = datetime.combine(TODAY, datetime.min.time(), tzinfo=DISPLAY_TIMEZONE).replace(hour=hour)
        patient = await Patient.create(
            hospital_id=hospital.hospital_id,
            hospital_patient_no=f"{abs(hash(name)) % 90000 + 10000}",
            name=name,
            birth_date=date(1997, 4, 22),
            gender=PatientGender.FEMALE,
            phone="01044524085",
        )
        visit = await Visit.create(
            hospital_id=hospital.hospital_id, patient=patient, visited_at=when - timedelta(days=1)
        )
        document = await GuideDocument.create(hospital_id=hospital.hospital_id, visit=visit)
        await GuideMessage.create(
            guide_document=document,
            kind=GuideMessageKind.GUIDE,
            status=GuideMessageStatus.SENT,
            scheduled_at=when,
            sent_at=when,
        )

    async def test_the_download_is_not_truncated(self) -> None:
        """표는 자르지만 받기는 자르지 않는다 — 그러라고 있는 자리다."""
        hospital = await Hospital.create(name="도로시여성의원")
        staff = await Staff.create(
            hospital=hospital,
            login_id="csv",
            password_hash=hash_password("pw"),
            name="서지현",
            roles=["staff"],
            must_change_password=False,
        )
        for hour in range(9, 15):
            await self.a_sent(hospital, f"환자{hour}", hour)

        access, _ = await StaffSessionService(self.redis).start(staff)  # type: ignore[arg-type]
        params = {"from": TODAY.isoformat(), "to": TODAY.isoformat()}
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            listed = await client.get(
                "/api/v1/messages/history",
                headers={"Authorization": f"Bearer {access}"},
                params={**params, "limit": 2},
            )
            downloaded = await client.get(
                "/api/v1/messages/history.csv",
                headers={"Authorization": f"Bearer {access}"},
                params=params,
            )

        assert listed.status_code == 200
        assert len(listed.json()["items"]) == 2 and listed.json()["truncated"] is True

        assert downloaded.status_code == 200
        assert downloaded.headers["content-type"].startswith("text/csv")
        assert "send-history-" in downloaded.headers["content-disposition"]

        body = downloaded.text
        assert body.startswith("﻿"), "BOM 이 없으면 엑셀에서 한글이 깨진다"
        rows = list(csv.reader(io.StringIO(body.lstrip("﻿"))))
        assert len(rows) == 7, "머리줄 하나 + 여섯 줄이 다 나와야 한다"

    async def test_signed_out_cannot_download(self) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/v1/messages/history.csv",
                params={"from": TODAY.isoformat(), "to": TODAY.isoformat()},
            )
        assert response.status_code == 401
