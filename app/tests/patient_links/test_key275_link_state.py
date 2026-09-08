"""링크 상태를 읽는 길 — KEY-275.

문자 설정(S1-14)과 현황(D1-6) 두 화면이 같은 「환자 링크」 블록을 그리는데,
**링크가 살아 있는지 볼 길이 없었다.** `GuideResponse` 에도 없고 조회 API 도
없었다. 현황 화면은 안내문 API 를 아예 안 부르므로 그 응답에 얹지 않고 이 길을
따로 냈다.

여기서 지키는 것은 셋이다.

    주소가 안 나간다        서버는 원문을 안 갖고, 나가면 DB 유출이 곧 링크 유출이다
    없는 것은 오류가 아니다  승인 전 진료마다 화면이 오류를 받으면 안 된다
    남의 의원이 안 보인다    「없는 진료」와 「남의 진료」가 같은 답이다
"""

from datetime import timedelta

from tortoise.timezone import now

from app.models.visits import GuideStatus, PatientGuideLink
from app.tests.patient_links.test_patient_links import (
    TOKEN,
    PatientLinkTestCase,
    make_guide,
    make_hospital,
    make_staff,
)

PATH = "/api/v1/visits/{visit_id}/guide/link"


class ReadLinkStateTestCase(PatientLinkTestCase):
    async def read(self, visit_id: int, staff):
        async with self.client() as client:
            return await client.get(PATH.format(visit_id=visit_id), headers=await self.headers(staff))

    async def test_a_visit_without_a_link_answers_not_an_error(self) -> None:
        """**없다는 것이 답이지 실패가 아니다.**

        404 로 만들면 승인 전 진료마다 화면이 오류를 받는다. 그러면 화면은
        오류를 정상으로 삼키는 갈래를 갖게 되고, **그 갈래가 진짜 오류(권한·타
        의원)까지 함께 삼킨다.**
        """
        hospital = await make_hospital("KEY-275 합성의원")
        guide = await make_guide(hospital, GuideStatus.STAFF_REVIEW)
        staff = await make_staff(hospital, "key275-none", ["staff"])

        answer = await self.read(guide.visit_id, staff)

        assert answer.status_code == 200, answer.text
        assert answer.json() == {"issued": False, "expires_at": None}

    async def test_an_issued_link_reports_when_it_closes(self) -> None:
        hospital = await make_hospital("KEY-275 합성의원")
        guide = await make_guide(hospital, GuideStatus.SCHEDULED_TO_SEND)
        staff = await make_staff(hospital, "key275-live", ["staff"])
        issued = await self.issue(guide, staff)
        assert issued.status_code == 201

        answer = await self.read(guide.visit_id, staff)

        assert answer.status_code == 200, answer.text
        body = answer.json()
        assert body["issued"] is True
        assert body["expires_at"] == issued.json()["expires_at"]

    async def test_the_raw_token_never_comes_back(self) -> None:
        """**주소는 이 길로 안 나간다.**

        서버가 원문을 안 갖는 것이 이 설계의 요점이다(`token_digest` 뿐).
        상태 조회가 주소를 실어 주려면 원문을 저장해야 하고, 그러면 DB 가 새는
        순간 **살아 있는 환자 링크가 통째로** 넘어간다. AGENTS.md 「환자 링크
        토큰을 코드·화면·로그·커밋에 남기지 않는다」와 같은 자리다.
        """
        hospital = await make_hospital("KEY-275 합성의원")
        guide = await make_guide(hospital, GuideStatus.SCHEDULED_TO_SEND)
        staff = await make_staff(hospital, "key275-secret", ["staff"])
        await self.issue(guide, staff)

        answer = await self.read(guide.visit_id, staff)

        assert TOKEN not in answer.text
        assert "path" not in answer.json()
        saved = await PatientGuideLink.get(guide_document_id=guide.guide_document_id)
        assert saved.token_digest not in answer.text, "해시조차 내보내지 않는다"

    async def test_a_revoked_link_still_counts_as_issued(self) -> None:
        """**폐기한 링크는 「기한 지남」이지 「아직 없음」이 아니다.**

        `revoke` 는 행을 지우지 않고 `expires_at` 을 지금으로 당긴다. 이것을
        「아직 발급되지 않았습니다」로 보이면 스탭이 **방금 자기가 폐기한 것을
        못 만든 것으로** 읽고, 화면은 [새 링크] 단추를 안 내민다 — 되돌릴 길이
        화면에서 사라진다.
        """
        hospital = await make_hospital("KEY-275 합성의원")
        guide = await make_guide(hospital, GuideStatus.SCHEDULED_TO_SEND)
        staff = await make_staff(hospital, "key275-revoked", ["staff"])
        await self.issue(guide, staff)
        async with self.client() as client:
            revoked = await client.delete(
                PATH.format(visit_id=guide.visit_id),
                headers=await self.headers(staff),
            )
        assert revoked.status_code == 204

        answer = await self.read(guide.visit_id, staff)

        body = answer.json()
        assert body["issued"] is True, "폐기를 「없음」으로 보이면 새로 만들 단추가 사라진다"
        assert body["expires_at"] is not None
        # 화면은 이 값 하나로 「기한 지남」을 판정한다.
        assert body["expires_at"] <= now().isoformat()

    async def test_another_clinics_live_link_is_invisible(self) -> None:
        """**남의 의원 링크가 실제로 살아 있을 때** 안 보이는가.

        울타리는 링크 조회와 안내문 조회 **두 곳**에 있다. 링크가 없는 진료로만
        재면 첫 조회가 `None` 을 돌려주고 두 번째 울타리가 대신 막아서, **링크
        쪽 울타리를 빼도 검사가 초록이다.** 그래서 남의 의원에 살아 있는 링크를
        세워 두고 잰다.

        새면 나가는 것은 만료 시각과 「이 진료에 링크가 있다」는 사실이다 —
        남의 의원 환자가 지금 안내문을 받고 있다는 뜻이라 그 자체가 진료 정보다.
        """
        mine = await make_hospital("KEY-275 우리의원")
        theirs = await make_hospital("KEY-275 남의의원")
        guide = await make_guide(theirs, GuideStatus.SCHEDULED_TO_SEND)
        insider = await make_staff(theirs, "key275-insider", ["staff"])
        issued = await self.issue(guide, insider)
        assert issued.status_code == 201, issued.text

        outsider = await make_staff(mine, "key275-outsider", ["staff"])
        theirs_answer = await self.read(guide.visit_id, outsider)
        nowhere_answer = await self.read(guide.visit_id + 100_000, outsider)

        assert theirs_answer.status_code == 404, theirs_answer.text
        assert theirs_answer.json()["code"] == "GUIDE_NOT_FOUND"
        assert issued.json()["expires_at"] not in theirs_answer.text
        assert nowhere_answer.json() == theirs_answer.json(), "두 답이 다르면 남의 진료의 존재가 새어 나간다"

    async def test_reissuing_moves_the_closing_time_both_screens_read(self) -> None:
        """**두 화면이 저절로 맞는 까닭.**

        화면은 상태를 저장하지 않고 이 길로 다시 묻는다. 한쪽에서 새로 만들면
        다른 쪽도 새 만료일을 읽는다 — 티켓의 인수조건 ① 이 서버에서 성립하는
        자리다.
        """
        hospital = await make_hospital("KEY-275 합성의원")
        guide = await make_guide(hospital, GuideStatus.SCHEDULED_TO_SEND)
        staff = await make_staff(hospital, "key275-reissue", ["staff"])
        await self.issue(guide, staff)
        before = (await self.read(guide.visit_id, staff)).json()["expires_at"]

        async with self.client() as client:
            again = await client.post(
                PATH.format(visit_id=guide.visit_id) + "/re-issue",
                headers=await self.headers(staff),
            )
        assert again.status_code == 200, again.text

        after = (await self.read(guide.visit_id, staff)).json()["expires_at"]
        assert after != before, "재발급했는데 다른 화면은 옛 만료일을 읽는다"
        assert after == again.json()["expires_at"]

    async def test_a_reader_without_an_issuer_role_is_refused(self) -> None:
        """읽기도 발급자 권한을 요구한다 — 만료일은 그 진료가 있다는 사실을 말한다.

        `admin` 은 의원 계정 관리용이라 `ISSUER_ROLES` 밖이다.
        """
        hospital = await make_hospital("KEY-275 합성의원")
        guide = await make_guide(hospital, GuideStatus.SCHEDULED_TO_SEND)
        stranger = await make_staff(hospital, "key275-admin", ["admin"])

        answer = await self.read(guide.visit_id, stranger)

        assert answer.status_code == 403
        assert answer.json()["code"] == "FORBIDDEN"

    async def test_an_expired_link_is_reported_as_it_is(self) -> None:
        """만료를 서버가 숨기지 않는다 — 화면이 「기한 지남」을 그릴 근거다."""
        hospital = await make_hospital("KEY-275 합성의원")
        guide = await make_guide(hospital, GuideStatus.SCHEDULED_TO_SEND)
        staff = await make_staff(hospital, "key275-expired", ["staff"])
        await self.issue(guide, staff)
        gone = now() - timedelta(hours=1)
        await PatientGuideLink.filter(guide_document_id=guide.guide_document_id).update(expires_at=gone)

        body = (await self.read(guide.visit_id, staff)).json()

        assert body["issued"] is True
        assert body["expires_at"] < now().isoformat()
