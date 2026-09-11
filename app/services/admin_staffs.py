"""직원 목록·추가 — A1-1 · A1-2 (KEY-321).

`Staff` 모델과 역할 조합(KEY-36 · KEY-269)은 이미 있었는데 **그것을 읽고 쓰는
길이 없었다.** `admin.html` 이 골격만인 것도 그래서다 (KEY-176).

여기서 지키는 것 셋.

  * 병원 울타리 — 목록도 생성도 `actor.hospital_id` 로만 정한다
  * 역할 조합 — `rbac.is_valid_role_combination` 한 곳에서 판정한다
  * 감사 기록 — 계정 생성과 기록을 **한 트랜잭션**으로 묶는다
"""

import logging

from tortoise.exceptions import IntegrityError
from tortoise.transactions import in_transaction

from app.core.api_errors import ApiError
from app.core.rbac import is_valid_role_combination
from app.core.utils.security import hash_password
from app.dependencies.admin_access import AdminActor
from app.dtos.admin_staffs import StaffCreatedResponse, StaffCreateRequest, StaffListResponse, StaffSummary
from app.models.staffs import Staff, StaffAccountEvent, StaffAccountEventType

LOGGER = logging.getLogger(__name__)


class AdminStaffService:
    @staticmethod
    async def list_staffs(actor: AdminActor) -> StaffListResponse:
        """**내 의원 직원만.** 퇴사자도 보인다 — 지난 기록이 그 이름을 가리킨다.

        `status` 를 함께 내려주므로 화면이 가려 그릴 수 있다. 서버가 지워 보내면
        「그만둔 사람이 만든 안내문」의 작성자가 화면에서 사라진다.

        정렬은 **만든 차례**다. 이름순으로 두면 새로 만든 계정이 목록 가운데
        끼어들어, 방금 만든 것이 만들어졌는지 눈으로 확인하기 어렵다.
        """
        rows = await Staff.filter(hospital_id=actor.hospital_id).order_by("staff_id")
        return StaffListResponse(
            staffs=[
                StaffSummary(
                    staff_id=row.staff_id,
                    login_id=row.login_id,
                    name=row.name,
                    #: **접지 않고 그대로 준다.** enum 으로 옮기면 아는 값 밖의
                    #: 것 하나에 목록 전체가 500 이 된다 — 계약 주석 참고
                    #: (한금준 님 `#285` 리뷰 ①).
                    roles=[str(role) for role in row.roles or []],
                    status=row.status,
                    must_change_password=row.must_change_password,
                    last_login_at=row.last_login_at,
                    created_at=row.created_at,
                )
                for row in rows
            ]
        )

    @staticmethod
    async def create_staff(actor: AdminActor, request: StaffCreateRequest) -> StaffCreatedResponse:
        """계정을 만들고 **같은 트랜잭션에서** 감사 기록을 남긴다.

        갈라 두면 계정은 생겼는데 기록이 없는 상태가 생긴다 — 권한을 준 일이
        아무 데도 안 남는 것이라, 그 계정이 무엇을 하든 되짚을 수 없다.

        **비밀번호는 해시만 저장한다.** 원문은 이 함수 밖으로 안 나가고,
        로그에도 감사 기록에도 응답에도 담기지 않는다.
        """
        roles = [str(role) for role in request.roles]
        if not is_valid_role_combination(roles):
            raise ApiError(
                400,
                "INVALID_ROLE_COMBINATION",
                "만들 수 없는 역할 조합입니다. 의사·스탭·어드민 하나이거나, 의사+어드민 · 스탭+어드민만 됩니다.",
                #: **봉투 모양을 맞춘다.** 저장소의 구조화된 `field_errors` 는
                #: `ContractRoute` 가 만드는 `list[{field, message}]` 뿐인데 여기만
                #: dict 였다 — 그것을 리스트로 순회하는 쪽이 이 400 에서 터진다
                #: (한금준 님 `#285` 리뷰 ②).
                field_errors=[{"field": "roles", "message": f"고를 수 없는 조합입니다: {sorted(roles)}"}],
            )

        try:
            async with in_transaction() as connection:
                staff = await Staff.create(
                    using_db=connection,
                    hospital_id=actor.hospital_id,
                    login_id=request.login_id,
                    password_hash=hash_password(request.password),
                    name=request.name,
                    roles=roles,
                    # 관리자가 정해 준 첫 비밀번호는 첫 로그인에서 반드시 바뀐다(L-3).
                    # 모델 기본값과 같은 값이지만 **여기서 뜻을 밝힌다** — 기본값이
                    # 바뀌어도 이 경로의 약속은 안 바뀐다.
                    must_change_password=True,
                )
                await StaffAccountEvent.create(
                    using_db=connection,
                    hospital_id=actor.hospital_id,
                    actor_staff_id=actor.staff_id,
                    subject_staff_id=staff.staff_id,
                    event_type=StaffAccountEventType.STAFF_CREATED,
                    roles=roles,
                )
        except IntegrityError as error:
            # **아이디 중복인지 되물어 확인한다.** 처음에는 `IntegrityError` 를
            # 전부 「아이디 중복」으로 옮겼는데, 그러다 감사 기록 쪽의 NOT NULL
            # 위반이 관리자 화면에 「이미 쓰고 있는 아이디입니다」로 떴다 —
            # 아이디를 바꿔 가며 몇 번을 눌러도 같은 말이 나온다. 잘못을 남의
            # 이름으로 부르면 고칠 수 없다.
            #
            # **제 의원 안에서만 본다** (KEY-324). 전에는 `login_id` 가 전체에서
            # 유일해서 다른 의원이 쓰는 아이디로도 409 가 났다 — 관리자가 아이디를
            # 하나씩 넣어 보며 남의 의원 계정 존재를 알아낼 수 있었다. 이제
            # 유일성이 의원 안이라 남의 의원은 여기에 안 걸린다.
            if await Staff.filter(hospital_id=actor.hospital_id, login_id=request.login_id).exists():
                LOGGER.info("직원 계정 생성 실패 — 아이디 중복 (의원 %s)", actor.hospital_id)
                raise ApiError(409, "LOGIN_ID_TAKEN", "이미 쓰고 있는 아이디입니다.") from error
            raise

        return StaffCreatedResponse(
            staff_id=staff.staff_id,
            login_id=staff.login_id,
            name=staff.name,
            #: 저장한 것과 같은 값이다. `roles` 는 저장하려고 문자열로 편 것이고
            #: 계약이 말하는 것은 `StaffRole` 이라, 받은 것을 그대로 돌려준다.
            roles=request.roles,
            status=staff.status,
            must_change_password=staff.must_change_password,
        )
