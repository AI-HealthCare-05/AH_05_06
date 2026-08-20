"""로그인 실패 횟수와 잠금 — KEY-73.

계약(`docs/auth-contract.md` 3절)이 푼 문제가 여기 들어 있다.

`L-2`는 두 가지를 동시에 요구한다.
  ① 아이디가 있는지 없는지 감춘다
  ② 실패 횟수를 보여준다 — 「(2회)」

실패를 **계정** 기준으로 세면 ①이 깨진다. 없는 아이디로 다섯 번 두드렸을 때
횟수가 안 오르면, **횟수가 안 오른다는 사실 자체가 「그런 아이디는 없다」는
답이 된다.**

그래서 계정이 아니라 **입력된 문자열**을 키로 삼는다. 없는 아이디도 똑같이
오르고 똑같이 5회에서 잠긴다. 공격자가 얻는 정보가 없다.

TTL 을 그대로 잠금 시간으로 쓴다 — 풀어 주는 일을 따로 관리하지 않아도 된다.

IP 로 세지 않는 이유: 의원 하나가 공인 IP 를 공유하면 **한 사람의 오타로
의원 전체가 잠긴다.** 진료 중에 그런 일이 생기면 안 된다.
"""

from redis.asyncio import Redis

MAX_FAILURES = 5
LOCK_SECONDS = 600

_KEY = "login_fail:{login_id}"


class LoginAttempts:
    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    def _key(self, login_id: str) -> str:
        """대소문자를 접어서 센다.

        DB 는 `utf8mb4_unicode_ci` 라 `Staff01` 과 `staff01` 이 **같은 계정**을
        찾는데, 예전에는 이 키가 입력 문자열 그대로라 **다른 카운터**가 생겼다.
        대소문자를 바꿔 가며 두드리면 계정 하나에 사실상 무제한 시도가 생겨
        5회 잠금이 무력해진다.

        아이디 규칙(`^[a-z0-9]{4,}$` · `docs/auth-contract.md`)이 소문자뿐이라
        접어도 서로 다른 계정이 한 칸에 섞이지 않는다. 없는 아이디도 그대로
        자기 칸을 가지므로 「횟수가 안 오른다」로 존재가 새는 일도 없다.
        """
        return _KEY.format(login_id=login_id.strip().lower())

    async def failures(self, login_id: str) -> int:
        raw = await self.redis.get(self._key(login_id))
        return int(raw) if raw else 0

    async def is_locked(self, login_id: str) -> bool:
        return await self.failures(login_id) >= MAX_FAILURES

    async def retry_after(self, login_id: str) -> int:
        """남은 잠금 시간(초). 화면이 「10분 뒤에 다시」를 계산하는 근거다."""
        ttl = await self.redis.ttl(self._key(login_id))
        # -1 은 만료가 없는 키, -2 는 없는 키다. 둘 다 여기 오면 안 되지만
        # 왔을 때 0 을 주면 화면이 「지금 다시 해 보세요」라고 거짓말한다.
        return ttl if ttl > 0 else LOCK_SECONDS

    async def record_failure(self, login_id: str) -> int:
        """실패를 하나 세고 지금까지의 횟수를 준다.

        만료는 **첫 실패에서만** 건다. 실패할 때마다 다시 걸면 계속 두드리는
        동안 잠금이 영원히 안 풀린다.
        """
        key = self._key(login_id)
        count = await self.redis.incr(key)
        if count == 1:
            await self.redis.expire(key, LOCK_SECONDS)
        return int(count)

    async def clear(self, login_id: str) -> None:
        """들어왔으면 지운다. 어제 오타 두 번이 오늘까지 따라오지 않게."""
        await self.redis.delete(self._key(login_id))
