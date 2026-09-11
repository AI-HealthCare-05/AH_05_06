"""의원 정보를 보고 고친다 — A1-4 (KEY-331).

이 화면이 없는 동안 **그 빈자리가 환자에게 나갔다.** 소진·재진 문자의
`{예약링크}` 를 채울 데가 없어서 발송 코드가 `{링크}`(그 환자의 안내문 링크)를
그대로 넣었고, 「재진 예약을 잡아주세요: …」를 누른 환자는 예약 화면이 아니라
제 안내문을 다시 열었다. 문자가 나가는 쪽은 `messages/test_key331_booking_link.py`
가 잰다 — 여기서는 **그 값을 넣는 길**을 잰다.

    울타리      남의 의원 정보를 못 보고 못 고친다. 병원은 토큰에서만 온다
    검사        예약 링크는 `http(s)` 만. `javascript:` 를 환자에게 배달하지 않는다
    지움        `null` 은 지운 것, 안 보낸 칸은 그대로
    이름        의원 이름도 여기서 바꾼다. 비울 수 없고, 겹치면 409 다
    기록        바뀐 칸은 `hospital_update_event` 에 덧붙는다 (인수조건 5)
"""

from typing import Any

from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.staffs import Hospital, HospitalUpdateEvent, HospitalUpdateEventType
from app.tests.auth_base import AuthTestCase, login_headers, make_staff_account

HOSPITAL_URL = "/api/v1/admin/hospital"


def _body(**over: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "phone": "02-123-4567",
        "address": "서울시 강남구 어딘가 1층",
        "booking_url": "https://booking.example.com/dorothy",
    }
    payload.update(over)
    return payload


class HospitalInfoTestCase(AuthTestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.hospital = await Hospital.create(name="도로시여성의원")
        self.other = await Hospital.create(name="옆집여성의원")
        self.admin = await make_staff_account(self.hospital, "admin01", ["admin"], name="관리자")
        self.doctor = await make_staff_account(self.hospital, "doctor01", ["doctor"], name="박연")
        self.other_admin = await make_staff_account(self.other, "admin21", ["admin"], name="옆집관리자")

    def client(self) -> AsyncClient:
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


class TestOnlyAdminsGetThroughTheDoor(HospitalInfoTestCase):
    async def test_an_admin_reads_and_writes(self) -> None:
        async with self.client() as client:
            headers = await login_headers(client, "admin01")
            read = await client.get(HOSPITAL_URL, headers=headers)
            wrote = await client.patch(HOSPITAL_URL, json=_body(), headers=headers)

        assert read.status_code == 200, read.text
        assert wrote.status_code == 200, wrote.text

    async def test_a_doctor_is_refused(self) -> None:
        """**의사는 진료를 하지 의원 정보를 고치지 않는다.**

        403 이지 404 가 아니다 — 없는 척하면 관리자가 「내 권한이 없구나」
        대신 「기능이 없구나」로 읽는다.
        """
        async with self.client() as client:
            headers = await login_headers(client, "doctor01")
            read = await client.get(HOSPITAL_URL, headers=headers)
            wrote = await client.patch(HOSPITAL_URL, json=_body(), headers=headers)

        assert read.status_code == 403, read.text
        assert wrote.status_code == 403, wrote.text
        await self.hospital.refresh_from_db()
        assert self.hospital.booking_url is None, "막혔는데 값이 들어갔다"

    async def test_nobody_gets_in_without_a_token(self) -> None:
        async with self.client() as client:
            read = await client.get(HOSPITAL_URL)
            wrote = await client.patch(HOSPITAL_URL, json=_body())

        assert read.status_code == 401, read.text
        assert wrote.status_code == 401, wrote.text


class TestTheFenceHolds(HospitalInfoTestCase):
    async def test_each_admin_sees_their_own_clinic(self) -> None:
        """**병원은 토큰에서만 온다.** 옆집 관리자가 우리 줄을 보면 안 된다."""
        async with self.client() as client:
            mine = await client.get(HOSPITAL_URL, headers=await login_headers(client, "admin01"))
            theirs = await client.get(HOSPITAL_URL, headers=await login_headers(client, "admin21"))

        assert mine.json()["name"] == "도로시여성의원"
        assert theirs.json()["hospital_id"] == self.other.hospital_id
        assert theirs.json()["name"] == "옆집여성의원"

    async def test_editing_does_not_reach_the_other_clinic(self) -> None:
        async with self.client() as client:
            await client.patch(
                HOSPITAL_URL,
                json=_body(booking_url="https://booking.example.com/neighbour"),
                headers=await login_headers(client, "admin21"),
            )

        await self.hospital.refresh_from_db()
        await self.other.refresh_from_db()
        assert self.hospital.booking_url is None, "옆집이 우리 예약 주소를 고쳤다"
        assert self.other.booking_url == "https://booking.example.com/neighbour"

    async def test_the_request_cannot_name_a_clinic(self) -> None:
        """요청 본문으로 병원을 고를 수 없다 — `extra="forbid"` 가 막는다."""
        async with self.client() as client:
            answer = await client.patch(
                HOSPITAL_URL,
                json=_body(hospital_id=self.other.hospital_id),
                headers=await login_headers(client, "admin01"),
            )

        assert answer.status_code == 400, answer.text
        assert answer.json()["code"] == "INVALID_REQUEST"


class TestWhatGoesInComesBack(HospitalInfoTestCase):
    async def test_saved_values_are_readable_again(self) -> None:
        async with self.client() as client:
            headers = await login_headers(client, "admin01")
            await client.patch(HOSPITAL_URL, json=_body(), headers=headers)
            read = await client.get(HOSPITAL_URL, headers=headers)

        assert read.json()["phone"] == "02-123-4567"
        assert read.json()["booking_url"] == "https://booking.example.com/dorothy"
        assert read.json()["address"] == "서울시 강남구 어딘가 1층"

    async def test_a_fresh_clinic_reads_as_empty_not_as_an_error(self) -> None:
        """아직 아무도 안 적은 의원은 **세 칸이 `null`** 이다.

        여기서 500 이나 404 를 내면 관리자는 화면을 열지도 못하고, 열지 못하면
        적을 수도 없다 — 첫 관리자가 제일 먼저 만나는 자리다.
        """
        async with self.client() as client:
            read = await client.get(HOSPITAL_URL, headers=await login_headers(client, "admin01"))

        assert read.status_code == 200, read.text
        assert read.json()["phone"] is None
        assert read.json()["address"] is None
        assert read.json()["booking_url"] is None
        assert read.json()["name"] == "도로시여성의원"

    async def test_null_clears_a_value(self) -> None:
        """`null` 은 「지웠다」다 — 빈 문자열로 남기지 않는다."""
        async with self.client() as client:
            headers = await login_headers(client, "admin01")
            await client.patch(HOSPITAL_URL, json=_body(), headers=headers)
            await client.patch(HOSPITAL_URL, json={"booking_url": None}, headers=headers)

        await self.hospital.refresh_from_db()
        assert self.hospital.booking_url is None, "지웠는데 값이 남았다"

    async def test_blank_is_folded_to_null(self) -> None:
        """**없음은 하나여야 한다.** 공백만 적은 것은 안 적은 것이다.

        `""` 로 저장하면 표에 「없음」이 두 모양이 되고, 발송 게이트의
        `bool(booking_url)` 같은 판정이 둘 중 하나만 본다.
        """
        async with self.client() as client:
            headers = await login_headers(client, "admin01")
            await client.patch(HOSPITAL_URL, json=_body(), headers=headers)
            await client.patch(HOSPITAL_URL, json={"address": "   "}, headers=headers)

        await self.hospital.refresh_from_db()
        assert self.hospital.address is None

    async def test_a_field_left_out_is_left_alone(self) -> None:
        """**화면은 셋을 함께 보내지만 서버는 그것을 믿지 않는다.**

        칸 하나만 보낸 요청이 나머지 둘을 조용히 지우면, 화면 말고 다른
        손님(검사·스크립트·다음 화면)이 그 대가를 치른다.
        """
        async with self.client() as client:
            headers = await login_headers(client, "admin01")
            await client.patch(HOSPITAL_URL, json=_body(), headers=headers)
            await client.patch(HOSPITAL_URL, json={"phone": "02-999-8888"}, headers=headers)

        await self.hospital.refresh_from_db()
        assert self.hospital.phone == "02-999-8888"
        assert self.hospital.booking_url == "https://booking.example.com/dorothy", "안 보낸 칸이 지워졌다"
        assert self.hospital.address == "서울시 강남구 어딘가 1층", "안 보낸 칸이 지워졌다"

    async def test_an_empty_body_is_refused(self) -> None:
        """빈 몸은 「셋 다 지워라」로도 「아무것도 안 바꾼다」로도 읽힌다."""
        async with self.client() as client:
            headers = await login_headers(client, "admin01")
            await client.patch(HOSPITAL_URL, json=_body(), headers=headers)
            answer = await client.patch(HOSPITAL_URL, json={}, headers=headers)

        assert answer.status_code == 400, answer.text
        await self.hospital.refresh_from_db()
        assert self.hospital.booking_url == "https://booking.example.com/dorothy", "빈 요청이 값을 지웠다"

    async def test_the_clinic_name_can_be_changed_here(self) -> None:
        """**의원 이름도 이 화면에서 고친다** (KEY-319 인수조건).

        처음에는 「배포 한 판의 정체」라 막아 두었는데, 이미 나간 문자는
        `sent_body` 에 보낸 그대로 남으므로 앞뒤가 갈리지 않는다. 바꾼 사실은
        감사 기록이 든다 (이희진 님 #295 리뷰).
        """
        async with self.client() as client:
            answer = await client.patch(
                HOSPITAL_URL,
                json={"name": "도로시여성의원 강남점"},
                headers=await login_headers(client, "admin01"),
            )

        assert answer.status_code == 200, answer.text
        assert answer.json()["name"] == "도로시여성의원 강남점"
        await self.hospital.refresh_from_db()
        assert self.hospital.name == "도로시여성의원 강남점"

    async def test_an_empty_name_is_refused(self) -> None:
        """**이름은 비울 수 없다** — 다른 셋과 다른 자리다.

        빈 글자를 「없음」으로 접으면 `{의원명}` 자리가 빈 채로 문자에 나간다.
        `NOT NULL` 이기도 하다.
        """
        async with self.client() as client:
            headers = await login_headers(client, "admin01")
            blank = await client.patch(HOSPITAL_URL, json={"name": "   "}, headers=headers)
            nulled = await client.patch(HOSPITAL_URL, json={"name": None}, headers=headers)

        assert blank.status_code == 400, blank.text
        assert nulled.status_code == 400, nulled.text
        await self.hospital.refresh_from_db()
        assert self.hospital.name == "도로시여성의원"

    async def test_a_name_another_clinic_already_uses_is_refused_with_409(self) -> None:
        """**`Hospital.name` 은 unique 다.** 그대로 두면 DB 가 500 을 낸다 —
        관리자는 무엇이 문제인지 모르고 고칠 수도 없다.
        """
        async with self.client() as client:
            answer = await client.patch(
                HOSPITAL_URL,
                json={"name": "옆집여성의원"},
                headers=await login_headers(client, "admin01"),
            )

        assert answer.status_code == 409, answer.text
        assert answer.json()["code"] == "HOSPITAL_NAME_TAKEN"
        assert {item["field"] for item in answer.json()["field_errors"]} == {"name"}
        await self.hospital.refresh_from_db()
        assert self.hospital.name == "도로시여성의원"


class TestWhatChangedIsWrittenDown(HospitalInfoTestCase):
    """**인수조건 5 — 덧붙이기만 하는 기록.**

    `updated_by` 한 칸은 「마지막에 누가 만졌나」뿐이다. 이 화면이 적는 예약
    링크는 그대로 문자에 실려 환자에게 나가므로, **언제 어떤 주소가 나갔는지**를
    되짚으려면 바뀐 값 자체가 남아야 한다.
    """

    async def test_the_changed_fields_are_kept_with_before_and_after(self) -> None:
        async with self.client() as client:
            await client.patch(
                HOSPITAL_URL,
                json={"booking_url": "https://booking.example.com/dorothy"},
                headers=await login_headers(client, "admin01"),
            )

        event = await HospitalUpdateEvent.get(hospital_id=self.hospital.hospital_id)
        assert event.event_type is HospitalUpdateEventType.HOSPITAL_UPDATED
        assert event.actor_staff_id == self.admin.staff_id
        assert event.changes == [
            {"field": "booking_url", "before": None, "after": "https://booking.example.com/dorothy"}
        ]

    async def test_saving_the_same_value_again_writes_no_line(self) -> None:
        """**안 바뀐 저장은 줄을 안 만든다.** 같은 값을 다시 보낸 것까지 남기면
        「무엇이 바뀌었나」를 보는 표가 안 바뀐 줄로 덮인다.
        """
        async with self.client() as client:
            headers = await login_headers(client, "admin01")
            await client.patch(HOSPITAL_URL, json=_body(), headers=headers)
            await client.patch(HOSPITAL_URL, json=_body(), headers=headers)

        assert await HospitalUpdateEvent.filter(hospital_id=self.hospital.hospital_id).count() == 1

    async def test_a_refused_save_leaves_no_line(self) -> None:
        """**저장과 기록이 한 트랜잭션이다.** 이름이 겹쳐 409 로 막힌 요청이
        기록만 남기면, 그 표는 일어나지 않은 일을 적은 것이 된다.
        """
        async with self.client() as client:
            answer = await client.patch(
                HOSPITAL_URL,
                json={"name": "옆집여성의원"},
                headers=await login_headers(client, "admin01"),
            )

        assert answer.status_code == 409, answer.text
        assert await HospitalUpdateEvent.filter(hospital_id=self.hospital.hospital_id).count() == 0

    async def test_who_edited_is_recorded(self) -> None:
        """누가 고쳤나 — `MessageTemplate.updated_by` 와 같은 자리다.

        이 값이 바뀌면 환자에게 나가는 문자 내용이 바뀐다. 그 일을 한 사람이
        아무 데도 안 남으면 나중에 되짚을 수 없다.
        """
        async with self.client() as client:
            await client.patch(HOSPITAL_URL, json=_body(), headers=await login_headers(client, "admin01"))

        await self.hospital.refresh_from_db()
        assert self.hospital.updated_by == self.admin.staff_id


class TestWhatWeRefuseToSendToPatients(HospitalInfoTestCase):
    """**이 값은 그대로 문자에 실려 환자 휴대폰에서 열린다.**

    관리자가 실수로 붙여넣은 것을 우리가 환자에게 배달하는 꼴이 되면 안 된다.
    """

    async def _patch(self, body: dict[str, Any]) -> Any:
        async with self.client() as client:
            return await client.patch(HOSPITAL_URL, json=body, headers=await login_headers(client, "admin01"))

    async def test_a_javascript_url_is_refused(self) -> None:
        answer = await self._patch({"booking_url": "javascript:alert(1)"})

        assert answer.status_code == 400, answer.text
        await self.hospital.refresh_from_db()
        assert self.hospital.booking_url is None

    async def test_a_data_url_is_refused(self) -> None:
        answer = await self._patch({"booking_url": "data:text/html,<script>alert(1)</script>"})

        assert answer.status_code == 400, answer.text

    async def test_a_bare_domain_is_refused(self) -> None:
        """`booking.example.com` 은 문자에서 안 열릴 수 있다 — 규칙을 말해 준다."""
        answer = await self._patch({"booking_url": "booking.example.com"})

        assert answer.status_code == 400, answer.text

    async def test_http_is_allowed(self) -> None:
        """**`https` 만 받지는 않는다.** 의원이 쓰는 예약 페이지가 `http` 인
        경우가 실제로 있고, 그것을 막으면 관리자는 링크를 아예 못 넣는다 —
        그 결과는 소진 문자가 전부 보류되는 것이다."""
        answer = await self._patch({"booking_url": "http://booking.example.com/dorothy"})

        assert answer.status_code == 200, answer.text

    async def test_a_too_long_link_is_refused(self) -> None:
        answer = await self._patch({"booking_url": "https://booking.example.com/" + "a" * 500})

        assert answer.status_code == 400, answer.text


class TestThePhoneIsAClinicPhone(HospitalInfoTestCase):
    async def _patch(self, phone: str) -> Any:
        async with self.client() as client:
            return await client.patch(
                HOSPITAL_URL, json={"phone": phone}, headers=await login_headers(client, "admin01")
            )

    async def test_a_landline_is_allowed(self) -> None:
        """**환자 번호 검사(`validate_phone_number`)를 재사용하지 않는다.**

        그것은 `010` 으로 시작하는 휴대폰만 통과시키는데, 의원 대표번호는 대개
        유선이다. 재사용했으면 관리자가 제 의원 번호를 못 넣었다.
        """
        assert (await self._patch("02-123-4567")).status_code == 200

    async def test_a_mobile_is_allowed_too(self) -> None:
        assert (await self._patch("010-1234-5678")).status_code == 200

    async def test_digits_without_hyphens_are_allowed(self) -> None:
        assert (await self._patch("0212345678")).status_code == 200

    async def test_letters_are_refused(self) -> None:
        assert (await self._patch("02-가나다-4567")).status_code == 400

    async def test_a_too_short_number_is_refused(self) -> None:
        assert (await self._patch("123")).status_code == 400
