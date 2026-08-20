"""병원과 직원 — KEY-73 인증 백엔드의 바닥.

`docs/auth-contract.md`(KEY-8 v1)와 기획의 `staff` 표를 그대로 옮긴 것이다.
지금 `app/models/users.py`는 `email` 로그인 · `is_admin` bool 인 예시 골격이라
계약이 붙을 자리가 없다. 그 자리를 여기서 만든다.

`users.User`는 이 티켓에서 지우지 않는다 — 아직 `/users/me`가 쓰고 있고,
정리는 계정 관리(A1-2) 몫이다.
"""

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
    name = fields.CharField(max_length=100)

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
    #: Tortoise 가 만들어 주는 FK 컬럼. 선언해 두지 않으면 타입 검사가 못 본다.
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
    left_at = fields.DatetimeField(null=True)
    last_login_at = fields.DatetimeField(null=True)

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
