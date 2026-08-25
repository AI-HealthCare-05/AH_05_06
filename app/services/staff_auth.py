"""직원 로그인 — KEY-73 (`docs/api/hospital.md` 4·5절).

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

from app.core.auth_errors import (
    ACCOUNT_LOCKED,
    INVALID_CREDENTIALS,
    INVALID_REQUEST,
    TOKEN_EXPIRED,
    AuthError,
)
from app.core.jwt.exceptions import TokenError
from app.core.jwt.tokens import AccessToken, RefreshToken
from app.core.utils.security import hash_password, verify_password
from app.models.staffs import Staff, StaffStatus
from app.services.login_attempts import MAX_FAILURES, LoginAttempts
from app.services.session_store import SessionStore


class StaffAuthService:
    def __init__(self, redis: Redis) -> None:
        self.attempts = LoginAttempts(redis)

    async def login(self, login_id: str, password: str) -> Staff:
        """누구인지만 가려낸다. 토큰 발급과 세션 등록은 StaffSessionService 가 한다 —
        로그인과 refresh 가 같은 자리에서 세션을 열어야 규칙이 갈라지지 않는다."""
        # 잠긴 아이디는 비밀번호를 맞춰도 들어오지 못한다. 맞았을 때만 통과시키면
        # 잠금이 「비밀번호 맞추기 게임」의 속도만 늦추는 장치가 된다.
        #
        # 세는 것을 **비밀번호를 보기 전에** 한다. 보고 나서 세면 동시에 들어온
        # 요청들이 전부 같은 숫자를 보고 통과해 5회를 넘긴다(`begin()` 참고).
        attempt = await self.attempts.begin(login_id)
        if attempt > MAX_FAILURES:
            raise await self._locked(login_id)

        staff = await Staff.get_or_none(login_id=login_id)

        # 없는 계정에서도 비밀번호를 검증한 것과 비슷한 시간을 쓴다.
        # 바로 돌려보내면 응답 시간만으로 계정 존재 여부가 드러난다.
        stored = staff.password_hash if staff else _DUMMY_HASH
        ok = verify_password(password, stored)

        if staff is None or not ok or staff.status is not StaffStatus.ACTIVE:
            raise await self._failed(login_id, attempt)

        await self.attempts.clear(login_id)
        staff.last_login_at = now()
        await staff.save(update_fields=["last_login_at", "updated_at"])
        return staff

    async def _failed(self, login_id: str, count: int) -> AuthError:
        # 세는 것은 `begin()` 이 이미 했다. 여기서 또 세면 한 번 틀릴 때마다
        # 둘씩 올라간다.
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


class StaffSessionService:
    """refresh · logout — KEY-73 (계약 4·5절)."""

    def __init__(self, redis: Redis) -> None:
        self.sessions = SessionStore(redis)

    async def start(self, staff: Staff) -> tuple[AccessToken, RefreshToken]:
        refresh = RefreshToken()
        refresh["staff_id"] = staff.staff_id
        # **쿠키 수명을 토큰이 들고 다니지 않는다** (KEY-179).
        # 예전에는 `remember` 를 claim 에 실어 rotation 때 이어받았다. 접수 PC 는
        # 공용이라 그 선택지 자체를 없앴고, 이제 쿠키는 언제나 세션 쿠키다 —
        # 브라우저를 닫으면 사라진다. 이어받을 것이 없으니 claim 도 없앤다.
        await self.sessions.open(refresh["jti"], staff.staff_id)
        access = refresh.access_token
        # 발급한 액세스도 기억해 둔다 — 나중에 세션을 전부 끊을 때
        # 리프레시만 죽이면 이 토큰이 남은 수명만큼 계속 살아 있다.
        await self.sessions.track_access(access["jti"], staff.staff_id)
        return access, refresh

    async def rotate(self, raw_token: str) -> tuple[Staff, AccessToken, RefreshToken]:
        """쓴 토큰을 폐기하고 새것을 준다.

        확인 순서가 곧 답이 갈리는 순서다.
          ① 서명·만료      → 아니면 401
          ② 이 토큰을 차지한다 → 못 차지했으면 이미 쓰였거나 유휴로 끊긴 것
          ③ 이미 쓰인 것   → **도난**이므로 그 계정의 세션을 전부 끊는다

        ②가 원자적이어야 한다. 「보고 나서 없애면」 같은 토큰으로 거의 동시에
        온 두 요청이 **둘 다 통과해** 각각 새 세션을 받는다 — 훔친 토큰과
        정상 클라이언트가 겹치는 순간이 정확히 그 경우다(`SessionStore.claim`).
        """
        try:
            token = RefreshToken(token=raw_token)
        except TokenError as err:
            raise _expired() from err

        staff_id = token.payload.get("staff_id")
        jti = token.payload.get("jti")
        if not staff_id or not jti:
            # 옛 계약(user_id)으로 만든 토큰이 오면 여기 걸린다.
            raise _expired()

        if not await self.sessions.claim(jti, int(staff_id)):
            if await self.sessions.was_used(jti):
                # 폐기된 토큰이 다시 왔다 — 훔친 것이 쓰였다는 뜻이다.
                killed = await self.sessions.revoke_all(int(staff_id))
                raise AuthError(
                    TOKEN_EXPIRED,
                    401,
                    "다시 로그인해 주세요.",
                    extra={"revoked_sessions": killed},
                )
            # 유휴 30분이 지난 것. 다른 세션은 건드리지 않는다.
            raise _expired()

        staff = await Staff.get_or_none(staff_id=int(staff_id))
        if staff is None or staff.status is not StaffStatus.ACTIVE:
            # 로그인한 뒤에 그만둔 사람. 세션이 살아 있어도 더는 못 들어온다.
            await self.sessions.revoke_all(int(staff_id))
            raise _expired()

        # 폐기는 claim() 이 이미 했다.
        access, refresh = await self.start(staff)
        return staff, access, refresh

    async def logout(self, raw_refresh: str | None, access_jti: str | None, staff_id: int | None) -> None:
        """액세스와 리프레시를 함께 무효로 만든다.

        쿠키가 없어도(이미 지워졌어도) 조용히 끝낸다 — 로그아웃이 실패해서
        로그인 상태로 남는 것이 제일 나쁘다.
        """
        if access_jti:
            await self.sessions.revoke_access(access_jti)
        if not raw_refresh:
            return
        try:
            token = RefreshToken(token=raw_refresh)
        except TokenError:
            return
        jti = token.payload.get("jti")
        owner = token.payload.get("staff_id") or staff_id
        if jti and owner:
            await self.sessions.retire(jti, int(owner))


def _expired() -> AuthError:
    """만료·폐기된 토큰. 「인증정보가 틀렸다」와 다른 코드여야 한다 —
    사용자가 해야 할 일이 다르다(다시 입력 vs 다시 로그인)."""
    return AuthError(TOKEN_EXPIRED, 401, "세션이 만료되었습니다. 다시 로그인해 주세요.")


class PasswordService:
    """비밀번호 변경 — KEY-73 (계약 4절)."""

    def __init__(self, redis: Redis) -> None:
        self.sessions = SessionStore(redis)

    async def change(self, staff: Staff, new_password: str, current_password: str | None) -> None:
        """어느 갈래인지는 **서버가** `must_change_password` 로 정한다.

        요청이 정하게 두면, 최초 로그인이 아닌 사람도 `current_password` 를
        빼고 보내면 확인 없이 바꿀 수 있다.
        """
        if not staff.must_change_password:
            if current_password is None:
                raise AuthError(
                    INVALID_REQUEST,
                    422,
                    "지금 쓰시는 비밀번호를 함께 입력해 주세요.",
                )
            if not verify_password(current_password, staff.password_hash):
                raise AuthError(INVALID_REQUEST, 422, "지금 쓰시는 비밀번호가 맞지 않습니다.")
        # 최초 로그인이면 current_password 가 와도 무시한다 — 방금 그 비밀번호로
        # 로그인했으므로 한 번 더 받을 이유가 없다.

        if verify_password(new_password, staff.password_hash):
            # 최초 로그인의 이유가 「정해준 사람이 계속 알고 있다」라, 같은 값으로
            # 바꾸면 아무것도 달라지지 않는다.
            raise AuthError(INVALID_REQUEST, 422, "지금 쓰시는 것과 다른 비밀번호로 만들어 주세요.")

        staff.password_hash = hash_password(new_password)
        staff.must_change_password = False
        staff.password_changed_at = now()
        await staff.save(update_fields=["password_hash", "must_change_password", "password_changed_at", "updated_at"])

        # 바꾸는 이유가 「남이 알고 있다」이므로 그 남의 세션도 같이 끊는다.
        # 자기 세션도 함께 끊긴다 — 화면은 로그인으로 돌아가 새 비밀번호로 들어온다.
        await self.sessions.revoke_all(staff.staff_id)
