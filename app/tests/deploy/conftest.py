"""배포 계약 검사들이 공유하는 읽기 도구 — KEY-191.

`test_pilot_deploy_contract.py` 와 `test_compose_contract.py` 가 같은 일을
따로 구현하고 있었다 (이희진 님 `#149` ⑤). 추출 규칙에 버그가 생기면 한쪽만
고치고 다른 쪽은 옛 버그를 그대로 갖는다.

값은 안 읽는다 — **이름과 구조만** 본다.
"""

import re
from pathlib import Path
from typing import Any

# `types-PyYAML` 은 안 넣는다 — 의존성을 하나 더 걸면 `uv.lock` 이 다시
# 풀리면서 torch 플랫폼 마커까지 함께 바뀐다. 검사 하나 때문에 남의 설치를
# 흔들 자리가 아니다. (`yaml` 자체는 `uvicorn` 이 app 그룹으로 끌어온다.)
import yaml  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[3]

#: `.env` 예시에서 **선언**으로 볼 줄. 주석 처리된 선언(`# NAME=`)도 센다 —
#: 값을 비워 두는 편이 맞는 설정이라도 이름은 보여야 한다.
#:
#: 산문은 걸리면 안 된다. 예전 판은 `"=" in line` 만 봐서
#: `# db (Docker 실행: DB_HOST=mysql / …)` 를 `db (Docker 실행: DB_HOST` 라는
#: **가짜 이름**으로 읽었다 (이희진 님 `#149` ②). 그 가짜가 목록에 있으면
#: 「예시에 이름이 없다」 검사가 조용히 통과한다.
DECLARATION = re.compile(r"^\s*#?\s*([A-Z][A-Z0-9_]*)\s*=")


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def declared_names(rel: str) -> set[str]:
    """예시 파일이 **이름을 보여 주는** 설정들."""
    return {m.group(1) for line in read(rel).splitlines() if (m := DECLARATION.match(line))}


def compose(rel: str) -> dict[str, Any]:
    """compose 파일을 **YAML 로 읽는다.**

    문자열로 자르면 주석 한 줄, 키 순서 하나에 엉뚱한 곳을 보게 된다 —
    그러면 검사가 「지키려던 것」이 아니라 다른 이유로 통과하거나 실패한다
    (이희진 님 `#149` ①⑥⑦).
    """
    loaded = yaml.safe_load(read(rel))
    assert isinstance(loaded, dict), f"{rel} 이 매핑이 아니다"
    return loaded


def service(rel: str, name: str) -> dict[str, Any]:
    svc = compose(rel).get("services", {}).get(name)
    assert isinstance(svc, dict), f"{rel} 에 {name} 서비스가 없다"
    return svc


def service_ports_of(svc: dict[str, Any]) -> list[str]:
    """서비스 정의 하나에서 **호스트로 여는** 포트 줄들.

    `or []` 인 것이 중요하다. `ports:` 키가 있는데 값이 비면 YAML 은 `None` 을
    주는데, `.get("ports", [])` 는 **키가 있으므로 기본값을 안 쓰고** `None` 을
    그대로 내준다. 그 자리에서 `TypeError` 가 난다.
    """
    return [str(port) for port in svc.get("ports") or []]


def service_ports(rel: str, name: str) -> list[str]:
    """한 서비스가 **호스트로 여는** 포트 줄들."""
    return service_ports_of(service(rel, name))


#: `${NAME}` · `${NAME:-기본값}` 둘 다.
COMPOSE_VAR = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)")


def compose_vars(text: str) -> set[str]:
    """`${NAME}` · `${NAME:-기본값}` 에서 이름만 뽑는다.

    손으로 `f"${{{name}}}" in text` 를 쓰지 않는다 — 문법이 바뀌면 여기만
    고치면 되게 한 자리로 모은다 (이희진 님 `#155` ④).
    """
    return set(COMPOSE_VAR.findall(text))


def host_side(spec: str) -> str:
    """`"127.0.0.1:${A:-1}:${B:-2}"` 에서 **컨테이너 쪽을 뺀 앞부분.**

    `rsplit(":", 1)` 로 자르면 `${B:-2}` 안의 콜론에 걸린다 — 지금은 안쪽에
    기본값이 없어 우연히 맞지만, 붙는 순간 조용히 엉뚱한 데서 잘린다
    (이희진 님 `#155` ⑦). 그래서 `${...}` 를 통째로 가린 뒤 자른다.
    """
    # `${…}` 를 한 글자로 덮어 **그 안의 콜론을 감춘다.** 한 번이면 된다 —
    # 예전에는 `COMPOSE_VAR.sub()` 를 한 번 더 씌웠는데, 이 `re.sub` 가
    # `${NAME}` 과 `${NAME:-기본값}` 을 이미 다 지우므로 **두 번째는 아무
    # 일도 안 했다** (한금준 님 `#155` ③).
    #
    # 갈리는 입력이 하나 있긴 하다 — 닫는 괄호가 없는 `${WEIRD`. 그건 compose 가
    # 먼저 거절하는 꼴이고, 그 경우 아래 `_unmask_index` 가 `}` 를 못 찾아
    # 어차피 터진다. 저장소의 포트 선언 13 개 전부에서 옛 판과 결과가 같은 것을
    # 대조해 확인했다. 하는 척하는 줄은 안 남긴다.
    masked = re.sub(r"\$\{[^}]*\}", "V", spec)
    if ":" not in masked:
        return ""
    cut = masked.rindex(":")
    return spec[: _unmask_index(spec, masked, cut)]


def _unmask_index(original: str, masked: str, index: int) -> int:
    """가린 문자열의 자리를 원본 자리로 되돌린다."""
    oi = mi = 0
    while mi < index and oi < len(original):
        if original[oi : oi + 2] == "${":
            oi = original.index("}", oi) + 1
        else:
            oi += 1
        mi += 1
    return oi
