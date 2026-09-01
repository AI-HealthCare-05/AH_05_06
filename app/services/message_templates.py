"""문자 문구 — 와이어프레임 D2-5.

원문 부제: 「문자 본문 템플릿 — 안내문(링크 콘텐츠)과 층이 다르다」.

**기본 문구는 코드가 갖는다.** 표에는 고친 것만 들어간다 — 줄이 없으면 여기
적힌 글이 나간다. 그래서 「원본으로 되돌리기」가 줄을 지우는 일이 되고,
나중에 기본 문구를 고치면 안 고친 의원 전부가 함께 따라온다.

**지울 수 없는 변수가 있다.** 원문: 「{링크} · {번호}처럼 기능에 필요한
변수는 지울 수 없게 막는다」. 링크가 빠진 확인 문자는 환자가 열 곳이 없고,
그때는 문자가 나가도 안 나간 것과 같다.
"""

import re

from app.core.api_errors import ApiError
from app.dependencies.patient_access import ClinicalActor
from app.models.catalog import MessageTemplate, MessageTemplateKind
from app.services.patient_visit_scope import hospital_id_of

#: 90바이트를 넘으면 장문(LMS)이 되어 문자 단가가 달라진다(어드민 A1-5).
#: 그래서 화면이 문구마다 바이트 수를 보인다.
SMS_LIMIT = 90

#: 회차마다의 기본 문구 — 원문 D2-5 에 적힌 그대로다.
DEFAULT_BODY: dict[MessageTemplateKind, str] = {
    MessageTemplateKind.GUIDE: "[{의원명}] {환자명}님, 오늘 진료 안내입니다. {만료일}까지 보실 수 있어요: {링크}",
    MessageTemplateKind.CHECK_D7: "{환자명}님, 복약 {일차}일째 확인입니다. 잘 드시고 계신가요? {링크}",
    MessageTemplateKind.CHECK_D15: "{환자명}님, 복약 {일차}일째 확인입니다. 불편한 점은 없으세요? {링크}",
    MessageTemplateKind.CHECK_D30: "{환자명}님, 복약 한 달째 확인입니다. 계속 드시고 계신가요? {링크}",
    MessageTemplateKind.RUN_OUT: "[{의원명}] 처방약이 {D}일 뒤 소진됩니다. 재진 예약을 잡아주세요: {예약링크}",
    MessageTemplateKind.REVISIT: (
        "[{의원명}] {환자명}님, 처방받으신 약({일수}일분)이 소진되었습니다. 재진 예약을 잡아주세요 · 예약: {예약링크}"
    ),
}

#: 없으면 문자가 제 일을 못 하는 변수. 원문의 「{링크}는 지울 수 없다」.
REQUIRED_VARIABLES: dict[MessageTemplateKind, tuple[str, ...]] = {
    MessageTemplateKind.GUIDE: ("링크",),
    MessageTemplateKind.CHECK_D7: ("링크",),
    MessageTemplateKind.CHECK_D15: ("링크",),
    MessageTemplateKind.CHECK_D30: ("링크",),
    MessageTemplateKind.RUN_OUT: ("예약링크",),
    MessageTemplateKind.REVISIT: ("예약링크",),
}

#: **고칠 수 없는 문자.** 원문 「인증번호 / 수정 불가 · 시스템」. 표에 넣지
#: 않고 화면에만 보인다 — 무엇이 나가는지는 알아야 하고, 손댈 수는 없다.
SYSTEM_BODY = "[{의원명}] 인증번호 {번호} — 3분 안에 입력해 주세요"

#: 문구에 넣을 수 있는 변수 전부. 아는 것만 허용한다 — `{휴대폰}` 처럼
#: 채울 데가 없는 이름을 적어 두면, 그 글자가 그대로 환자에게 간다.
KNOWN_VARIABLES = frozenset({"의원명", "환자명", "만료일", "링크", "일차", "D", "일수", "예약링크", "번호"})

_VARIABLE = re.compile(r"\{([^{}]*)\}")


def variables_in(body: str | None) -> list[str]:
    return _VARIABLE.findall(body or "")


def sms_bytes(body: str) -> int:
    """**EUC-KR 기준이다** — 문자 단가를 정하는 것이 그 셈이다.

    한글 한 자가 2바이트, 영숫자가 1바이트다. UTF-8 로 세면 한글이 3바이트라
    90바이트 제한이 실제보다 훨씬 빨리 걸려, 보낼 수 있는 문구를 못 보낸다고
    말하게 된다.
    """
    total = 0
    for letter in body or "":
        try:
            total += len(letter.encode("euc-kr"))
        except UnicodeEncodeError:
            # EUC-KR 에 없는 글자(이모지 등)는 어차피 못 보낸다. 길이만
            # 보수적으로 잡아 두고, 실제 막는 것은 발송기 몫이다.
            total += 2
    return total


class MessageTemplateService:
    async def list(self, actor: ClinicalActor) -> dict[MessageTemplateKind, str]:
        """고친 것만 돌려준다. 없는 회차는 기본 문구다."""
        hospital_id = hospital_id_of(actor)
        rows = await MessageTemplate.filter(hospital_id=hospital_id)
        return {row.kind: row.body for row in rows}

    async def save(self, actor: ClinicalActor, kind: MessageTemplateKind, body: str) -> str:
        self._require_doctor(actor)
        body = (body or "").strip()
        self._check(kind, body)

        hospital_id = hospital_id_of(actor)
        await MessageTemplate.update_or_create(
            hospital_id=hospital_id,
            kind=kind,
            defaults={"body": body, "updated_by": actor.staff_id},
        )
        return body

    async def reset(self, actor: ClinicalActor, kind: MessageTemplateKind) -> str:
        """**줄을 지운다.** 기본 문구를 다시 베껴 넣지 않는 이유는, 그러면
        나중에 기본 문구를 고쳐도 되돌린 의원만 옛 글을 계속 쓰기 때문이다."""
        self._require_doctor(actor)
        await MessageTemplate.filter(hospital_id=hospital_id_of(actor), kind=kind).delete()
        return DEFAULT_BODY[kind]

    @staticmethod
    def _require_doctor(actor: ClinicalActor) -> None:
        """원문: 「수정은 의사 계정만 — **문자도 환자에게 가는 안내다** ·
        스탭은 열람」. 화면에서도 잠그지만 실제 차단은 여기서 한다."""
        if "doctor" not in actor.roles:
            raise ApiError(403, "DOCTOR_ONLY", "문자 문구는 의사 계정만 수정할 수 있습니다.")

    @staticmethod
    def _check(kind: MessageTemplateKind, body: str) -> None:
        if not body:
            raise ApiError(400, "EMPTY_BODY", "문구를 비워 둘 수 없습니다.")

        found = set(variables_in(body))

        missing = [name for name in REQUIRED_VARIABLES[kind] if name not in found]
        if missing:
            raise ApiError(
                422,
                "REQUIRED_VARIABLE_MISSING",
                "{" + missing[0] + "} 는 지울 수 없습니다 — 환자가 안내를 열 곳이 없어집니다.",
            )

        unknown = sorted(found - KNOWN_VARIABLES)
        if unknown:
            # 채울 데가 없는 이름은 그 글자가 그대로 환자에게 간다.
            raise ApiError(
                422,
                "UNKNOWN_VARIABLE",
                "{" + unknown[0] + "} 는 발송 시 채울 수 없는 변수입니다.",
            )
