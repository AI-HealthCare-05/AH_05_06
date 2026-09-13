"""어드민 — 직원 목록·추가 (A1-1 · A1-2) 계약. KEY-321.

`docs/api/hospital.md` 2절이 「아이디 규칙 `^[a-z0-9]{4,}$` · 생성 후 변경
불가」를 정해 두었고, 로그인 DTO 는 **일부러 그 검사를 안 한다** — 형식으로
422 를 주면 규칙에 안 맞는 문자열이 「없는 아이디」와 다른 답을 받아 계정
존재 여부를 흘리기 때문이다. 그래서 형식은 **여기서** 본다.
"""

from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, Field, model_validator

from app.core.validators import validate_staff_password
from app.dtos.base import StrictModel
from app.models.staffs import StaffRole, StaffStatus

#: 계약 2절의 아이디 규칙. 소문자와 숫자만, 넉 자 이상.
#: 대문자를 받아 소문자로 접지 않는다 — `Admin01` 을 넣은 사람은 그것으로
#: 로그인하려 하는데 저장된 것은 `admin01` 이라, 만든 직후부터 어긋난다.
LOGIN_ID_PATTERN = r"^[a-z0-9]{4,}$"


class StaffSummary(StrictModel):
    """목록 한 줄 — A1-1 이 그리는 것.

    **비밀번호와 관련된 어떤 값도 없다.** 해시도 내보내지 않는다. 화면이
    쓰지 않는 값을 계약에 담으면 그 값이 로그·캐시·브라우저 기록으로 퍼진다.
    """

    staff_id: int
    login_id: str
    name: str
    #: **읽을 때는 저장된 것을 그대로 준다** — `list[StaffRole]` 이 아니다.
    #:
    #: enum 으로 두면 `roles` JSON 에 아는 값 밖의 것이 한 줄이라도 있을 때
    #: `ValueError` 로 **목록 전체가 500** 이 된다 — 관리자가 그 의원의 아무
    #: 직원도 못 본다. 레거시 데이터 · 백필 · raw insert · `bulk_create` 처럼
    #: `Staff.save()` 검증을 지나지 않는 길이 있다 (한금준 님 `#285` 리뷰 ①).
    #:
    #: 건너뛰지 않고 **보인다.** 이상한 값을 감추면 그것을 고칠 사람이 그 사실을
    #: 모른다 — 화면은 모르는 값을 그대로 적는다(`staffRolesLabel`).
    #:
    #: **만드는 쪽은 그대로 엄하다** — `StaffCreateRequest.roles` 는 `StaffRole`
    #: 이고 조합 규칙까지 본다. 들어오는 문은 좁게, 나가는 창은 정직하게.
    roles: list[str]
    status: StaffStatus
    #: 첫 로그인 전인지 화면이 알아야 한다 — A1-1 의 「초기 비밀번호 상태」.
    must_change_password: bool
    last_login_at: datetime | None
    created_at: datetime


class StaffListResponse(StrictModel):
    """**쪽 나눔을 두지 않는다.** 한 의원의 직원은 수십 명 규모다 —
    커서를 두면 화면이 「더 보기」를 그려야 하는데 그 자리가 A1-1 에 없다.
    수백을 넘기기 시작하면 그때 계약을 바꾼다.
    """

    staffs: list[StaffSummary]


class StaffCreateRequest(StrictModel):
    """A1-2 가 보내는 것 넷.

    **병원은 안 받는다.** 로그인한 관리자의 병원으로 정한다 — 요청이 정하게
    하면 다른 의원에 계정을 만들 수 있다.

    **`status` 도 안 받는다.** 만들어지는 계정은 언제나 `active` 다. 퇴사
    처리는 A1-3 몫이고, 만들면서 퇴사시키는 일은 없다.
    """

    login_id: Annotated[str, Field(pattern=LOGIN_ID_PATTERN, max_length=50)]
    name: Annotated[str, Field(min_length=1, max_length=50)]
    #: 관리자가 정해 주는 첫 비밀번호. 받은 계정은 첫 로그인에서 반드시 바꾼다(L-3).
    password: Annotated[str, Field(max_length=128), AfterValidator(validate_staff_password)]
    #: 조합 규칙은 `app/core/rbac.py` 의 `VALID_ROLE_COMBINATIONS` 가 본다 —
    #: 여기서는 「하나 이상 · 아는 값」까지만 본다. 조합이 왜 다섯인지는 값이
    #: 아니라 규칙이라 서비스에서 한 번에 판정한다.
    roles: Annotated[list[StaffRole], Field(min_length=1, max_length=3)]


class StaffCreatedResponse(StrictModel):
    """만든 결과.

    **비밀번호를 되돌려주지 않는다.** 관리자가 방금 적어 넣은 값이라 화면이
    이미 알고 있고, 응답에 실으면 그 값이 접속 기록·프록시 로그·브라우저
    개발자 도구에 한 겹 더 남는다.
    """

    staff_id: int
    login_id: str
    name: str
    #: 방금 만든 계정이라 **값이 확실하다** — 조합 규칙을 지난 것만 여기 온다.
    #: 목록(`StaffSummary`)이 `list[str]` 인 것과 다른 까닭이 이것이다.
    roles: list[StaffRole]
    status: StaffStatus
    must_change_password: bool


class StaffUpdateRequest(StrictModel):
    """A1-3 이 보내는 것 — **준 것만 바꾼다** (KEY-330).

    셋 다 선택이다. 역할만 바꾸거나, 퇴사만 시키거나, 비밀번호만 새로 줄 수
    있다. 아무것도 안 주면 `422` 다 — 「바꿀 것이 없는 저장」은 화면이 뭔가를
    빠뜨렸다는 뜻이지, 조용히 성공으로 답할 일이 아니다.

    **`login_id` 와 `name` 은 안 받는다.** 아이디는 만든 뒤에 못 바꾸고(계약
    §8.3), 이름은 A1-3 원문의 편집 대상이 아니다 — 필요해지면 그때 계약을 연다.
    """

    #: 바꿀 역할. 조합 규칙은 만들 때와 **같은 것**(`is_valid_role_combination`)을 탄다.
    roles: list[StaffRole] | None = None
    #: 재직 상태. `left` 면 그 사람은 더 이상 못 들어온다.
    status: StaffStatus | None = None
    #: 새 임시 비밀번호. 주면 받은 사람이 **첫 로그인에서 바꾼다**(L-3).
    #: 원문은 이 요청 밖으로 안 나간다 — 응답에도 감사 기록에도 안 담는다.
    password: Annotated[str, Field(max_length=128), AfterValidator(validate_staff_password)] | None = None

    @model_validator(mode="after")
    def something_to_change(self) -> "StaffUpdateRequest":
        if self.roles is None and self.status is None and self.password is None:
            raise ValueError("바꿀 것을 하나는 주세요 — roles · status · password 중에서.")
        return self


class StaffUpdatedResponse(StrictModel):
    """바꾼 뒤의 그 줄. 화면이 목록을 다시 안 불러도 되게 **저장된 값 그대로** 준다.

    **비밀번호는 담지 않는다.** 관리자가 방금 정해 준 값이라 화면이 이미 알고
    있고, 응답에 실으면 그 값이 로그·캐시·브라우저 기록으로 퍼진다.
    """

    staff_id: int
    login_id: str
    name: str
    roles: list[str]
    status: StaffStatus
    must_change_password: bool
    #: 이 저장으로 끊긴 세션 수. 퇴사·비밀번호 재설정은 **그 사람을 로그아웃시킨다** —
    #: 몇이 끊겼는지 보여야 관리자가 「지금 쓰고 있었구나」를 안다.
    revoked_sessions: int
