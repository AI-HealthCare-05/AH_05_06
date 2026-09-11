"""병원과 직원 — KEY-73 인증 백엔드의 바닥.

`docs/api/hospital.md`(KEY-8 v1)와 기획의 `staff` 표를 그대로 옮긴 것이다.
지금 `app/models/users.py`는 `email` 로그인 · `is_admin` bool 인 예시 골격이라
계약이 붙을 자리가 없다. 그 자리를 여기서 만든다.

`users.User`는 여전히 지우지 않는다. `/users/me`는 KEY-167에서 지웠지만
(부를 수 없는 죽은 API였다), 모델과 JWT 경로 정리는 계정 관리(A1-2) 몫이다.
"""

from datetime import datetime
from enum import StrEnum

from tortoise import fields, models
from tortoise.exceptions import ValidationError
from tortoise.fields import OnDelete


class StaffStatus(StrEnum):
    ACTIVE = "active"
    LEFT = "left"


class StaffRole(StrEnum):
    ADMIN = "admin"
    DOCTOR = "doctor"
    STAFF = "staff"


class Hospital(models.Model):
    """병원 하나. 모든 진료 데이터가 이 울타리 안에 있다.

    환자·진료에도 hospital_id 가 있지만 가리킬 테이블이 없었다(PR #25 리뷰).
    로그인한 직원에게서 병원을 얻는 것이 계약(KEY-26 4절)이라, 직원 모델을
    만드는 이 티켓에서 울타리도 같이 세운다.
    """

    hospital_id = fields.BigIntField(primary_key=True)
    name = fields.CharField(max_length=100, unique=True)

    #: 의원 정보 — A1-4 (KEY-331). **쓸 데가 있는 것만 둔다.**
    #:
    #: 사업자번호·대표자 같은 값은 지금 아무도 안 기다린다. 담을 자리를
    #: 미리 만들면 「이 값은 어디서 쓰나」에 아무도 답하지 못한다.
    #:
    #: 셋 다 비어 있을 수 있다 — 의원을 만드는 자리(시드·검사 픽스처)가
    #: 이름만 주고, 관리자가 A1-4 에서 채운다.

    #: 환자 화면의 「문의하기」가 걸 번호 (P5-1 · P6-1).
    phone = fields.CharField(max_length=20, null=True)
    address = fields.CharField(max_length=200, null=True)
    #: `{예약링크}` 가 가리킬 곳. **안내문 링크가 아니다** — 재진 예약을 잡는
    #: 의원의 예약 페이지다(네이버 예약·카카오 등).
    booking_url = fields.CharField(max_length=500, null=True)
    #: 누가 마지막으로 고쳤나 — `MessageTemplate.updated_by` 와 같은 자리다.
    #: 이 값이 바뀌면 **환자에게 나가는 문자 내용이 바뀐다**(`{예약링크}`).
    updated_by = fields.BigIntField(null=True)

    staffs: fields.ReverseRelation["Staff"]
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "hospital"


class Staff(models.Model):
    """로그인하는 사람.

    삭제하지 않고 status 를 left 로만 바꾼다. 지난 기록이 이 이름을 가리키고 있다.
    """

    staff_id = fields.BigIntField(primary_key=True)
    hospital: fields.ForeignKeyRelation[Hospital] = fields.ForeignKeyField(
        "models.Hospital",
        related_name="staffs",
        on_delete=OnDelete.RESTRICT,
        source_field="hospital_id",
    )
    # Tortoise 가 `source_field` 로 만들어 주는 칸이라 런타임에는 있지만
    # 검사기 눈에는 안 보인다. 병원 울타리를 이 값으로 치므로 적어 둔다.
    hospital_id: int

    # 로그인은 병원을 알기 전에 일어난다. 그래서 아이디는 병원 안이 아니라
    # 전체에서 유일해야 한다 — 두 병원에 같은 `staff01`이 있으면 누구인지 모른다.
    login_id = fields.CharField(max_length=50, unique=True)
    password_hash = fields.CharField(max_length=128)
    name = fields.CharField(max_length=50)

    # 역할은 겹친다. 실장은 `["admin","staff"]`, 1인 의원 원장님은 `["admin","doctor"]`.
    # 권한 판정은 합집합이다 — 하나라도 가졌으면 할 수 있다.
    roles: fields.Field[list[str]] = fields.JSONField()

    # v1에서 쓰지 않는다. KEY-26 §9 「미사용 `is_owner` 유지」를 따른다.
    # 기획(`spec-medical.md`)은 「MVP에서 만들지 않는다」라 둘이 갈린다 — PR에 적어 둔다.
    is_owner = fields.BooleanField(default=False)

    # 관리자가 만든 계정은 첫 로그인에서 반드시 바꾼다(L-3).
    must_change_password = fields.BooleanField(default=True)
    password_changed_at = fields.DatetimeField(null=True)

    status = fields.CharEnumField(enum_type=StaffStatus, default=StaffStatus.ACTIVE)
    # `null=True` 인데 Tortoise 스텁은 `datetime` 으로 준다. 실제로 None 이 들어가는
    # 칸이니 여기에 적어 둔다 — 안 그러면 None 을 넣는 쪽마다 억제를 달게 된다
    # (`scripts/seed.py` 가 그랬다 · KEY-114).
    left_at: datetime | None = fields.DatetimeField(null=True)
    last_login_at: datetime | None = fields.DatetimeField(null=True)

    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "staff"
        indexes = (("hospital_id", "status"),)

    def has_role(self, role: StaffRole | str) -> bool:
        """퇴사자는 역할이 남아 있어도 아무것도 못 한다."""
        if self.status is not StaffStatus.ACTIVE:
            return False
        return str(role) in (self.roles or [])

    async def save(self, *args: object, **kwargs: object) -> None:
        # 빈 배열은 저장할 수 없다. 아무 역할도 없는 계정은 로그인해도 갈 곳이
        # 없는데, 그 사실이 로그인 뒤에야 드러난다.
        valid = {role.value for role in StaffRole}
        roles = self.roles or []
        if not roles:
            raise ValidationError("roles 는 최소 하나여야 합니다.")
        unknown = [r for r in roles if r not in valid]
        if unknown:
            raise ValidationError(f"모르는 역할입니다: {unknown}")
        await super().save(*args, **kwargs)  # type: ignore[arg-type]


class StaffAccountEventType(StrEnum):
    """계정에 무슨 일이 있었나.

    **쓰는 것만 적는다.** A1-2 가 하나로 시작했고, A1-3(수정 · 비밀번호
    재설정)이 들어오며 넷이 늘었다 — 쓰지도 않을 이름을 미리 적어 두면
    「이 값은 어디서 남나」에 아무도 답하지 못한다.
    """

    STAFF_CREATED = "STAFF_CREATED"
    #: 역할을 바꿨다 — KEY-330. 바뀐 **뒤의** 역할을 `roles` 에 남긴다.
    STAFF_ROLES_CHANGED = "STAFF_ROLES_CHANGED"
    #: 퇴사 처리했다. 계정을 지우지 않는다 — 지난 기록이 이 이름을 가리킨다.
    STAFF_LEFT = "STAFF_LEFT"
    #: 퇴사를 되돌려 다시 재직으로 뒀다.
    STAFF_REINSTATED = "STAFF_REINSTATED"
    #: 관리자가 임시 비밀번호를 새로 줬다. **비밀번호는 어느 칸에도 안 담는다** —
    #: 「누가 누구에게 언제」까지만 남는다.
    STAFF_PASSWORD_RESET = "STAFF_PASSWORD_RESET"


class StaffAccountEvent(models.Model):
    """직원 계정에 생긴 일 — **덧붙이기만 한다** (KEY-321, 와이어프레임 A1-6).

    「누가 언제 누구의 계정을 만들었나」가 남아야 나중에 되짚을 수 있다. 계정은
    권한을 주는 일이라, 진료 기록을 고치는 것과 같은 무게로 남긴다.

    **고치거나 지우지 않는다.** 이 모델을 쓰는 코드는 `create` 만 부른다. 감사
    기록을 나중에 손댈 수 있으면 그것은 감사 기록이 아니다.

    **비밀번호는 어느 칸에도 안 담는다.** 원문도 해시도 없다 — 담을 자리를
    만들지 않는 것이 담지 않겠다는 약속을 지키는 가장 확실한 방법이다
    (`PatientUsageEvent` 가 원문을 안 담는 것과 같은 규율).

    `actor` 는 그 일을 한 사람, `subject` 는 그 일을 당한 계정이다. 둘 다
    `RESTRICT` 다 — 계정을 지우는 경로가 지금 없고(`status` 를 `left` 로만
    바꾼다), 생겨도 감사 기록이 먼저 사라지면 안 된다.

    KEY-322 가 이벤트 넷을 한 목록으로 합칠 때 이 표가 다섯째가 된다. 그때 쓸
    공통 모양(시각 · 행위자 · 유형 · 대상)을 미리 갖춰 둔다.
    """

    staff_account_event_id = fields.BigIntField(primary_key=True)
    hospital: fields.ForeignKeyRelation[Hospital] = fields.ForeignKeyField(
        "models.Hospital",
        related_name="staff_account_events",
        on_delete=OnDelete.RESTRICT,
        source_field="hospital_id",
    )
    hospital_id: int
    #: 한 일을 한 사람. 관리자다.
    #:
    #: **이름이 `actor` 가 아니라 `actor_staff` 인 까닭.** Tortoise 가 만들어 주는
    #: `<필드이름>_id` 접근자는 `source_field` 가 아니라 **필드 이름**에서 나온다.
    #: `actor` 로 두면 접근자가 `actor_id` 인데 칸은 `actor_staff_id` 라, `create()`
    #: 에 `actor_staff_id=` 를 넘겨도 **조용히 무시되고 NULL 이 들어간다**
    #: (실측: `Column 'actor_staff_id' cannot be null`). 이름을 맞춰 둔다.
    actor_staff: fields.ForeignKeyRelation["Staff"] = fields.ForeignKeyField(
        "models.Staff",
        related_name="staff_account_events_made",
        on_delete=OnDelete.RESTRICT,
        source_field="actor_staff_id",
    )
    actor_staff_id: int
    #: 그 일이 일어난 계정.
    subject_staff: fields.ForeignKeyRelation["Staff"] = fields.ForeignKeyField(
        "models.Staff",
        related_name="staff_account_events_received",
        on_delete=OnDelete.RESTRICT,
        source_field="subject_staff_id",
    )
    subject_staff_id: int
    event_type = fields.CharEnumField(enum_type=StaffAccountEventType)
    #: 그때 준 역할. 나중에 A1-3 이 역할을 바꿔도 **준 시점의 값**이 남는다.
    roles: fields.Field[list[str]] = fields.JSONField()
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "staff_account_event"
        indexes = (("hospital_id", "created_at"),)
