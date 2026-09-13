"""직원 목록·추가 — A1-1 · A1-2 (KEY-321).

`Staff` 모델과 역할 조합(KEY-36 · KEY-269)은 이미 있었는데 **그것을 읽고 쓰는
길이 없었다.** `admin.html` 이 골격만인 것도 그래서다 (KEY-176).

여기서 지키는 것 셋.

  * 병원 울타리 — 목록도 생성도 `actor.hospital_id` 로만 정한다
  * 역할 조합 — `rbac.is_valid_role_combination` 한 곳에서 판정한다
  * 감사 기록 — 계정 생성과 기록을 **한 트랜잭션**으로 묶는다
"""

import logging
from datetime import UTC, datetime
from typing import Any

from tortoise.exceptions import IntegrityError
from tortoise.transactions import in_transaction

from app.core.api_errors import ApiError
from app.core.rbac import is_valid_role_combination
from app.core.utils.security import hash_password
from app.dependencies.admin_access import AdminActor
from app.dtos.admin_staffs import (
    StaffCreatedResponse,
    StaffCreateRequest,
    StaffListResponse,
    StaffSummary,
    StaffUpdatedResponse,
    StaffUpdateRequest,
)
from app.models.staffs import Staff, StaffAccountEvent, StaffAccountEventType, StaffRole, StaffStatus
from app.services.session_store import SessionStore

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
    async def update_staff(
        actor: AdminActor,
        staff_id: int,
        request: StaffUpdateRequest,
        sessions: SessionStore,
    ) -> StaffUpdatedResponse:
        """역할·재직 상태를 바꾸고 비밀번호를 재설정한다 — A1-3 (KEY-330).

        **준 것만 바꾼다.** 셋 다 선택이고, 한 번에 여러 개를 줄 수도 있다.

        상태를 **잠근 채로** 본다. 두 관리자가 동시에 「마지막 관리자」의 admin 을
        빼면, 둘 다 「나 말고도 관리자가 있다」를 읽고 통과해 **관리자 없는 의원**이
        된다 — 그 자리는 화면으로 되돌릴 길이 없다.
        """
        async with in_transaction() as connection:
            staff = (
                await Staff.filter(staff_id=staff_id, hospital_id=actor.hospital_id)
                .using_db(connection)
                .select_for_update()
                .first()
            )
            #: 다른 의원 직원은 **없는 것처럼** 답한다 — 있다는 사실도 알리지 않는다.
            if staff is None:
                raise ApiError(404, "STAFF_NOT_FOUND", "직원을 찾을 수 없습니다.")

            roles = _roles_to_save(request, staff)
            status = request.status or StaffStatus(staff.status)
            await _guard_last_admin(actor, staff, roles=roles, status=status, connection=connection)

            changed: list[StaffAccountEventType] = []
            if request.roles is not None and roles != list(staff.roles):
                staff.roles = roles
                changed.append(StaffAccountEventType.STAFF_ROLES_CHANGED)
            if request.status is not None and status is not StaffStatus(staff.status):
                staff.status = status
                staff.left_at = datetime.now(UTC) if status is StaffStatus.LEFT else None
                changed.append(
                    StaffAccountEventType.STAFF_LEFT
                    if status is StaffStatus.LEFT
                    else StaffAccountEventType.STAFF_REINSTATED
                )
            if request.password is not None:
                staff.password_hash = hash_password(request.password)
                #: 관리자가 준 임시 비밀번호다 — 받은 사람이 첫 로그인에서 바꾼다(L-3).
                staff.must_change_password = True
                changed.append(StaffAccountEventType.STAFF_PASSWORD_RESET)

            await staff.save(using_db=connection)
            for event_type in changed:
                #: **바뀐 뒤의 역할**을 남긴다. 무엇이 됐는지가 되짚을 때 필요한 값이다.
                #: 비밀번호는 원문도 해시도 안 담는다 — 담을 칸 자체가 없다.
                await StaffAccountEvent.create(
                    using_db=connection,
                    hospital_id=actor.hospital_id,
                    actor_staff_id=actor.staff_id,
                    subject_staff_id=staff.staff_id,
                    event_type=event_type,
                    roles=list(staff.roles),
                )

        #: **끊는 것은 트랜잭션 밖이다.** 세션은 Redis 에 있어 롤백을 못 따라온다 —
        #: 저장이 되돌려졌는데 로그아웃만 남으면 멀쩡한 사람이 튕긴다.
        revoked = 0
        if _should_log_out(request, changed):
            revoked = await sessions.revoke_all(staff.staff_id)
            LOGGER.info("직원 계정 변경으로 세션을 끊었다 — 직원 %s · %s 개", staff.staff_id, revoked)

        return StaffUpdatedResponse(
            staff_id=staff.staff_id,
            login_id=staff.login_id,
            name=staff.name,
            roles=list(staff.roles),
            status=StaffStatus(staff.status),
            must_change_password=staff.must_change_password,
            revoked_sessions=revoked,
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
            # `login_id` 는 **전체에서** 유일하다 — 로그인이 병원을 알기 전에
            # 일어나기 때문이다(`Staff` 모델). 그래서 다른 의원이 쓰고 있어도
            # 여기서 걸린다. 어느 의원이 쓰는지는 **말하지 않는다.**
            if await Staff.filter(login_id=request.login_id).exists():
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


def _roles_to_save(request: StaffUpdateRequest, staff: Staff) -> list[str]:
    """바꿀 역할. 안 주면 지금 것 그대로.

    조합 규칙은 **만들 때와 같은 것**을 탄다 — 만들 수 없는 조합이 수정으로는
    들어갈 수 있으면 규칙이 아니다.
    """
    if request.roles is None:
        return list(staff.roles)
    roles = [str(role) for role in request.roles]
    if not is_valid_role_combination(roles):
        raise ApiError(
            400,
            "INVALID_ROLE_COMBINATION",
            "만들 수 없는 역할 조합입니다. 의사·스탭·어드민 하나이거나, 의사+어드민 · 스탭+어드민만 됩니다.",
            field_errors=[{"field": "roles", "message": f"고를 수 없는 조합입니다: {sorted(roles)}"}],
        )
    return roles


async def _guard_last_admin(
    actor: AdminActor,
    staff: Staff,
    *,
    roles: list[str],
    status: StaffStatus,
    connection: Any,
) -> None:
    """🚩 **관리자 없는 의원을 만들지 않는다.**

    그 의원에 재직 중인 `admin` 이 이 사람뿐인데 `admin` 을 빼거나 퇴사시키면,
    아무도 직원을 관리할 수 없게 된다 — **화면에는 되돌릴 길이 없다.** 서버에
    직접 넣거나 시드를 다시 돌려야 한다.

    **의원 단위 규칙이다.** 옆 의원에 관리자가 있다고 이 의원이 관리자 없이
    남아도 되는 것이 아니다.

    자기 자신도 같은 문이다 — 오히려 여기가 더 흔하다. 관리자가 제 역할을
    실수로 빼면 그 자리에서 화면이 닫힌다.
    """
    keeps_admin = StaffRole.ADMIN.value in roles and status is StaffStatus.ACTIVE
    if keeps_admin:
        return
    was_admin = StaffRole.ADMIN.value in list(staff.roles) and StaffStatus(staff.status) is StaffStatus.ACTIVE
    if not was_admin:
        return

    #: 🚩 **세는 줄도 함께 잠근다** (KEY-330, 이희진 님 #294 리뷰).
    #:
    #: 위에서 잠근 것은 「지금 고치는 그 사람」 한 줄뿐이다. 그것만으로는 문이
    #: 열린다 — 관리자가 A·B 둘뿐인 의원에서 두 사람이 거의 동시에 A 와 B 를
    #: 각각 내리면, 한쪽은 A 를 잠그고 「B 가 있다」를 보고 다른 쪽은 B 를 잠그고
    #: 「A 가 있다」를 본다. 서로 아직 커밋 전이라 **둘 다 통과하고, 둘 다
    #: 커밋되면 관리자 0명인 의원**이 된다. 이 함수가 막겠다고 적어 둔 바로 그
    #: 자리다.
    #:
    #: MySQL 은 `FOR UPDATE` 와 집계를 같이 못 쓴다. 그래서 세지 않고 **줄을
    #: 가져오면서** 잠근다. 겹치면 뒤엣것이 기다리고, 서로 엇갈려 맞물리면
    #: 교착으로 한쪽이 되돌아간다 — **둘 다 성공하는 것보다 그편이 낫다.**
    others = (
        await Staff.filter(
            hospital_id=actor.hospital_id,
            status=StaffStatus.ACTIVE,
            roles__contains=[StaffRole.ADMIN.value],
        )
        .exclude(staff_id=staff.staff_id)
        .order_by("staff_id")
        .select_for_update()
        .using_db(connection)
    )
    if others:
        return
    raise ApiError(
        409,
        "LAST_ADMIN",
        "이 의원의 마지막 관리자입니다. 다른 관리자를 먼저 세워 주세요.",
        field_errors=[{"field": "roles", "message": "관리자가 없는 의원이 됩니다"}],
    )


def _should_log_out(request: StaffUpdateRequest, changed: list[StaffAccountEventType]) -> bool:
    """이 저장이 그 사람을 **로그아웃시켜야 하는가.**

    퇴사와 비밀번호 재설정 둘 다 그렇다. `has_role` 이 상태를 보므로 퇴사자의
    새 요청은 막히지만, **이미 발급된 액세스 토큰은 만료까지 살아 있다** —
    그만둔 사람이 그동안 계속 쓴다. 비밀번호 재설정은 본인이 바꿀 때와 같은
    규칙이다(`staff_auth.py`).

    역할만 바꾼 것은 안 끊는다. 다음 요청부터 새 역할로 판정되고, 굳이 끊으면
    일하던 사람이 까닭 없이 튕긴다.
    """
    if request.password is not None:
        return True
    return StaffAccountEventType.STAFF_LEFT in changed
