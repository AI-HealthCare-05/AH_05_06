"""의원 정보 — A1-4 (KEY-331).

`Hospital` 표는 처음부터 있었는데 **이름 한 칸뿐이었고, 그 표를 읽고 쓰는
길이 없었다.** 그 빈자리가 조용한 것이 아니었다 — 소진·재진 문자의
`{예약링크}` 를 채울 데가 없어서 발송 코드가 안내문 링크를 대신 넣었다.

여기서 지키는 것 둘.

  * 병원 울타리 — `actor.hospital_id` 말고 다른 데서 병원을 받지 않는다
  * 없음은 하나 — 빈 문자열을 `None` 으로 접어 저장한다(`_clean`). 「예약
    링크가 없다」가 표에서 두 모양이면 발송 게이트가 한쪽만 본다
"""

from app.core.api_errors import ApiError
from app.dependencies.admin_access import AdminActor
from app.dtos.admin_hospital import HospitalResponse, HospitalUpdateRequest
from app.models.staffs import Hospital

#: 이 화면이 고칠 수 있는 칸. **이름은 없다** — 의원 이름은 배포 한 판의
#: 정체라 시드가 정한다. 바꾸면 이미 나간 문자의 `{의원명}` 과 앞으로 나갈
#: 것이 갈린다.
EDITABLE = ("phone", "address", "booking_url")


class AdminHospitalService:
    @staticmethod
    async def get_hospital(actor: AdminActor) -> HospitalResponse:
        return _response(await _mine(actor))

    @staticmethod
    async def update_hospital(actor: AdminActor, request: HospitalUpdateRequest) -> HospitalResponse:
        """보낸 칸만 고친다 — 계약이 「셋을 함께 보낸다」이지만 **서버는 그것을
        믿지 않는다.**

        화면이 셋을 함께 보내기로 한 것은 화면의 규율이고, 서버가 안 보낸 칸을
        멋대로 지우면 다른 손님(검사·스크립트·다음 화면)이 칸 하나만 보내는
        순간 나머지 둘이 조용히 사라진다. 지우는 것은 **`null` 을 보낸 것**만이다.
        """
        hospital = await _mine(actor)

        #: **보낸 칸만 옮긴다.** 안 보낸 칸은 DB 에서 읽어 온 값 그대로 남아
        #: 같은 값이 다시 저장된다 — 「지웠다」는 `null` 을 보낸 것뿐이다.
        #:
        #: `update_fields` 로 거르지 않고 여기서 거른다. 두 곳이 같은 일을
        #: 하면 한쪽을 망가뜨려도 다른 쪽이 가려 주어, 검사가 그 망가짐을
        #: 못 본다(실측: 둘 다 두었더니 어느 쪽을 뒤집어도 초록불이었다).
        for name in request.model_fields_set:
            setattr(hospital, name, getattr(request, name))
        hospital.updated_by = actor.staff_id
        await hospital.save(update_fields=[*EDITABLE, "updated_by", "updated_at"])
        return _response(hospital)


async def _mine(actor: AdminActor) -> Hospital:
    """**토큰이 가리키는 의원만.** 요청에서 병원을 받지 않는다.

    404 를 내는 자리는 정상적으로는 안 온다 — 로그인한 계정이 있다는 것은 그
    의원 줄이 있다는 뜻이다. 그래도 `get()` 의 예외를 500 으로 흘리지 않는다:
    관리자에게 「서버가 고장났다」와 「의원 줄이 없다」는 다른 말이고, 뒤쪽은
    시드가 덜 돈 배포에서 실제로 볼 수 있는 모양이다.
    """
    hospital = await Hospital.filter(hospital_id=actor.hospital_id).first()
    if hospital is None:
        raise ApiError(404, "HOSPITAL_NOT_FOUND", "의원 정보를 찾을 수 없습니다.")
    return hospital


def _response(hospital: Hospital) -> HospitalResponse:
    return HospitalResponse(
        hospital_id=hospital.hospital_id,
        name=hospital.name,
        phone=hospital.phone,
        address=hospital.address,
        booking_url=hospital.booking_url,
    )
