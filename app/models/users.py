from enum import StrEnum

from tortoise import fields, models


class StaffRole(StrEnum):
    """직원 역할 — 중복 선택이 정상이다 (`A1-2` 체크박스 셋)."""

    STAFF = "staff"
    DOCTOR = "doctor"
    ADMIN = "admin"


class StaffStatus(StrEnum):
    """퇴사자는 지우지 않고 상태로 남긴다 — 지난 기록이 이름을 참조한다."""

    ACTIVE = "active"
    LEFT = "left"


class Staff(models.Model):
    """로그인하는 사람. 직원 개인정보(생년월일·연락처)는 들지 않는다."""

    staff_id = fields.BigIntField(primary_key=True)
    hospital_id = fields.BigIntField()
    login_id = fields.CharField(max_length=50, unique=True)
    password_hash = fields.CharField(max_length=128)
    name = fields.CharField(max_length=50)
    roles = fields.JSONField()
    is_owner = fields.BooleanField(default=False)
    status = fields.CharEnumField(enum_type=StaffStatus, default=StaffStatus.ACTIVE)
    must_change_password = fields.BooleanField(default=True)
    left_at = fields.DatetimeField(null=True)
    last_login_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "staff"
        indexes = (("hospital_id", "status"),)

    @property
    def is_active(self) -> bool:
        return self.status == StaffStatus.ACTIVE

    def has_role(self, role: StaffRole | str) -> bool:
        return str(role) in (self.roles or [])


class Gender(StrEnum):
    MALE = "MALE"
    FEMALE = "FEMALE"


class User(models.Model):
    id = fields.BigIntField(primary_key=True)
    email = fields.CharField(max_length=40)
    hashed_password = fields.CharField(max_length=128)
    name = fields.CharField(max_length=20)
    gender = fields.CharEnumField(enum_type=Gender)
    birthday = fields.DateField()
    phone_number = fields.CharField(max_length=11)
    is_active = fields.BooleanField(default=True)
    is_admin = fields.BooleanField(default=False)
    last_login = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        table = "users"
