"""직원 로그인 — KEY-73 (`docs/auth-contract.md` 4·5절).

무엇을 하느냐보다 **무엇을 알려주지 않느냐**가 이 파일의 요점이다.

    없는 아이디        → 401 invalid_credentials
    비밀번호 틀림      → 401 invalid_credentials   (같은 코드 · 같은 문구)
    퇴사자             → 401 invalid_credentials   (같은 코드 · 같은 문구)

셋을 갈라 답하면 누가 이 의원에 있는지, 누가 그만뒀는지가 새어 나간다.
실패 횟수도 셋 모두에서 똑같이 오른다 — 안 그러면 「횟수가 안 오른다」가
그 자체로 답이 된다(`login_attempts.py` 참고).
"""

from redis.asyncio import Redis
from tortoise.timezone import now

from app.core.auth_errors import ACCOUNT_LOCKED, INVALID_CREDENTIALS, AuthError
from app.core.jwt.tokens import AccessToken, RefreshToken
from app.core.utils.security import verify_password
from app.models.staffs import Staff, StaffStatus
from app.services.login_attempts import MAX_FAILURES, LoginAttempts


class StaffAuthService:
    def __init__(self, redis: Redis) -> None:
        self.attempts = LoginAttempts(redis)

    async def login(self, login_id: str, password: str) -> tuple[Staff, AccessToken, RefreshToken]:
        # 잠긴 아이디는 비밀번호를 맞춰도 들어오지 못한다. 맞았을 때만 통과시키면
        # 잠금이 「비밀번호 맞추기 게임」의 속도만 늦추는 장치가 된다.
        if await self.attempts.is_locked(login_id):
            raise await self._locked(login_id)

        staff = await Staff.get_or_none(login_id=login_id)

        # 없는 계정에서도 비밀번호를 검증한 것과 비슷한 시간을 쓴다.
        # 바로 돌려보내면 응답 시간만으로 계정 존재 여부가 드러난다.
        stored = staff.password_hash if staff else _DUMMY_HASH
        ok = verify_password(password, stored)

        if staff is None or not ok or staff.status is not StaffStatus.ACTIVE:
            raise await self._failed(login_id)

        await self.attempts.clear(login_id)
        staff.last_login_at = now()
        await staff.save(update_fields=["last_login_at", "updated_at"])

        refresh = RefreshToken()
        refresh["staff_id"] = staff.staff_id
        return staff, refresh.access_token, refresh

    async def _failed(self, login_id: str) -> AuthError:
        count = await self.attempts.record_failure(login_id)
        if count >= MAX_FAILURES:
            return await self._locked(login_id)
        return AuthError(
            INVALID_CREDENTIALS,
            401,
            "아이디 또는 비밀번호가 올바르지 않습니다.",
            # 어느 쪽이 틀렸는지는 말하지 않지만, 몇 번 틀렸는지는 알려 준다.
            # 입력된 문자열로 세기 때문에 이 숫자가 계정 존재를 흘리지 않는다.
            extra={"fail_count": count, "max_failures": MAX_FAILURES},
        )

    async def _locked(self, login_id: str) -> AuthError:
        seconds = await self.attempts.retry_after(login_id)
        return AuthError(
            ACCOUNT_LOCKED,
            429,
            "로그인 시도가 많아 잠시 잠겼습니다. 잠시 뒤 다시 시도해 주세요.",
            extra={"retry_after_seconds": seconds},
            # 표준 헤더라 프록시와 클라이언트가 그대로 이해한다.
            headers={"Retry-After": str(seconds)},
        )


# 계정이 없을 때도 해시 검증을 한 번 돌리기 위한 값이다.
# 어떤 비밀번호와도 맞지 않는다.
_DUMMY_HASH = "$2b$12$" + "." * 53
