"""CLOVA 키가 **밖으로 나가는 모든 길**에서 가려지는가 — KEY-190 · 이희진 님 `#137` ③.

실제 판독을 한 번 돌려 보라는 요청에는 조건이 붙어 있었다.

> 응답·로그에 키 값 자체가 안 찍히는지만 커밋 전에 한 번 확인해주시고요.

**한 번 보는 것으로는 다음 사람을 못 지킨다.** 그래서 여기서 잰다.

재기 전에 실제로 새고 있었다. 같은 파일 세 줄 차이로 갈렸다.

    CLOVA_OCR_SECRET_KEY='...'            ← 평문 (맨 `str` 이었다)
    OPENAI_API_KEY=SecretStr('**********')

이 저장소는 **공개**다. 스크립트 출력을 PR 에 붙이는 흐름이 KEY-190 인수조건
(「저장소·PR·로그에 운영 자격증명이나 토큰이 남지 않음」)에 걸려 있어, 새는
자리를 타입으로 막고 그것이 유지되는지 여기서 지킨다.

여기 쓰는 값은 **합성이다** — 실제 키를 쓰지 않는다.
"""

import json
import logging
import traceback
from pathlib import Path

import httpx
import pytest
from pydantic.types import SecretStr

from ai_worker.adapters.clova import ClovaOcrError, call_clova_ocr
from app.core.config import Config

#: 실제 키가 아니다. 훑기가 닿았는지 보려고 심는 표식이다.
MARKER = "SYNTHETIC-CLOVA-KEY-NOT-A-REAL-SECRET-0001"

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 16


def _config() -> Config:
    return Config(
        CLOVA_OCR_INVOKE_URL="https://ocr.synthetic.invalid/general",
        CLOVA_OCR_SECRET_KEY=SecretStr(MARKER),
        CLOVA_OCR_TIMEOUT_SECONDS=10.0,
    )


#: **패치하기 전의 진짜 클래스.** `ai_worker.adapters.clova.httpx` 는 전역
#: `httpx` 와 같은 모듈 객체라, 팩토리 안에서 `httpx.AsyncClient` 를 다시
#: 부르면 방금 끼워 넣은 팩토리 자신이 불린다(무한 재귀).
_REAL_ASYNC_CLIENT = httpx.AsyncClient


def _client_factory(handler):
    """**진짜 `httpx` 요청을 만들게 한다.**

    `AsyncClient` 를 통째로 목으로 바꾸면 헤더가 실제로 조립되지 않아서,
    「오류 메시지에 키가 없다」가 **키가 애초에 거기 없어서** 참이 된다.
    `MockTransport` 는 전송만 가로채므로 요청 객체는 실물이다.
    """

    def factory(**kwargs):
        kwargs.pop("transport", None)
        return _REAL_ASYNC_CLIENT(transport=httpx.MockTransport(handler), **kwargs)

    return factory


class TestTheKeyIsMaskedInTheConfigObject:
    """설정 객체는 디버깅할 때 **통째로 찍기 쉬운 물건**이다."""

    @pytest.mark.parametrize(
        "how",
        [
            pytest.param(repr, id="repr"),
            pytest.param(str, id="str"),
            pytest.param(lambda c: c.model_dump(), id="model_dump"),
            pytest.param(lambda c: c.model_dump_json(), id="model_dump_json"),
            pytest.param(lambda c: json.dumps(c.model_dump(), default=str), id="json.dumps"),
        ],
    )
    def test_it_does_not_come_out(self, how) -> None:
        assert MARKER not in str(how(_config()))

    def test_the_value_is_still_reachable_on_purpose(self) -> None:
        """**위 검사가 「값이 아예 없어서」 통과하면 안 된다.**

        어댑터는 이 값을 실제로 헤더에 실어야 한다.
        """
        assert _config().CLOVA_OCR_SECRET_KEY.get_secret_value() == MARKER

    def test_the_neighbour_stays_masked_too(self) -> None:
        """`OPENAI_API_KEY` 가 맨 `str` 로 되돌아가면 같은 구멍이 다시 난다."""
        other = "SYNTHETIC-OPENAI-KEY-0002"

        assert other not in repr(Config(OPENAI_API_KEY=SecretStr(other)))

    def test_an_empty_key_means_disabled(self) -> None:
        """`SecretStr("")` 이 참으로 새면 Worker 가 키 없이 CLOVA 를 부른다."""
        assert (
            Config(CLOVA_OCR_INVOKE_URL="https://x.invalid", CLOVA_OCR_SECRET_KEY=SecretStr("")).clova_enabled is False
        )
        assert _config().clova_enabled is True


class TestTheKeyReachesTheHeaderAndNowhereElse:
    """양성 대조 — **키가 실제로 요청에 실린다.** 아래 검사들의 전제다."""

    async def test_the_header_actually_carries_it(self, monkeypatch: pytest.MonkeyPatch) -> None:
        seen: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen.update(request.headers)
            return httpx.Response(200, json={"images": [{"inferResult": "SUCCESS", "fields": []}]})

        monkeypatch.setattr("ai_worker.adapters.clova.config", _config())
        monkeypatch.setattr("ai_worker.adapters.clova.httpx.AsyncClient", _client_factory(handler))

        await call_clova_ocr(JPEG, "image/jpeg")

        assert seen.get("x-ocr-secret") == MARKER, "키가 헤더에 안 실린다 — 아래 검사가 헛돈다"

    async def test_the_url_is_not_where_it_goes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """쿼리스트링에 실리면 프록시·접근로그에 그대로 남는다."""
        seen: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(str(request.url))
            return httpx.Response(200, json={"images": [{"inferResult": "SUCCESS", "fields": []}]})

        monkeypatch.setattr("ai_worker.adapters.clova.config", _config())
        monkeypatch.setattr("ai_worker.adapters.clova.httpx.AsyncClient", _client_factory(handler))

        await call_clova_ocr(JPEG, "image/jpeg")

        assert seen and MARKER not in seen[0]


class TestNoFailurePathPrintsIt:
    """**실패할 때가 위험하다** — 그때만 사람이 메시지를 복사해서 붙인다."""

    @staticmethod
    def _fail(kind: str):
        def handler(request: httpx.Request) -> httpx.Response:
            if kind == "timeout":
                raise httpx.TimeoutException("timed out", request=request)
            if kind == "network":
                raise httpx.ConnectError("connection refused", request=request)
            if kind == "http_500":
                return httpx.Response(500, text="upstream is unhappy")
            if kind == "bad_json":
                return httpx.Response(200, text="<html>not json</html>")
            if kind == "no_images":
                return httpx.Response(200, json={})
            return httpx.Response(200, json={"images": [{"inferResult": "FAILURE", "message": "bad image"}]})

        return handler

    @pytest.mark.parametrize("kind", ["timeout", "network", "http_500", "bad_json", "no_images", "infer_failed"])
    async def test_the_error_text_is_clean(self, kind: str, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("ai_worker.adapters.clova.config", _config())
        monkeypatch.setattr("ai_worker.adapters.clova.httpx.AsyncClient", _client_factory(self._fail(kind)))

        with pytest.raises(ClovaOcrError) as caught:
            await call_clova_ocr(JPEG, "image/jpeg")

        # 사람이 실제로 보는 세 가지: 메시지 · repr · 역추적.
        assert MARKER not in str(caught.value), f"{kind}: 오류 메시지에 키가 있다"
        assert MARKER not in repr(caught.value), f"{kind}: repr 에 키가 있다"
        assert MARKER not in "".join(traceback.format_exception(caught.value)), f"{kind}: 역추적에 키가 있다"

    @pytest.mark.parametrize("kind", ["network", "http_500", "infer_failed"])
    async def test_the_log_line_is_clean(self, kind: str, monkeypatch: pytest.MonkeyPatch, caplog) -> None:
        """Worker 는 이 오류를 그대로 로그에 적는다 (`ocr_task.py` fallback 경로)."""
        monkeypatch.setattr("ai_worker.adapters.clova.config", _config())
        monkeypatch.setattr("ai_worker.adapters.clova.httpx.AsyncClient", _client_factory(self._fail(kind)))

        with caplog.at_level(logging.DEBUG):
            with pytest.raises(ClovaOcrError) as caught:
                await call_clova_ocr(JPEG, "image/jpeg")
            logging.getLogger("ocr").warning(
                "CLOVA 오류 → fixture fallback — ocr_job_id=%s, code=%s: %s", 1, caught.value.code, caught.value
            )

        assert MARKER not in caplog.text, f"{kind}: 로그에 키가 남는다"


class TestTheDevRunnerIsSafeToPasteIntoAPublicPr:
    """`scripts/test_clova_ocr.py` 출력은 **PR 에 붙는다** — 저장소가 공개다."""

    @staticmethod
    def _runner():
        import importlib.util

        path = Path(__file__).resolve().parents[3] / "scripts" / "test_clova_ocr.py"
        spec = importlib.util.spec_from_file_location("_clova_runner", path)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_it_does_not_print_the_invoke_path(self) -> None:
        """경로 뒷부분이 앱마다 다른 식별자다 — 호스트까지만 남긴다."""
        url = "https://abc123def.apigw.ntruss.com/custom/v1/40201/9f8e7d6c5b4a/general"

        shown = self._runner()._redact_url(url)

        assert "9f8e7d6c5b4a" not in shown, "invoke 경로가 그대로 찍힌다"
        assert "custom/v1" not in shown
        assert "abc123def.apigw.ntruss.com" in shown, "어디로 갔는지도 안 보이면 쓸모가 없다"

    def test_it_never_prints_the_secret_itself(self) -> None:
        """러너 어디에도 키를 찍는 줄이 없어야 한다."""
        import ast

        path = Path(__file__).resolve().parents[3] / "scripts" / "test_clova_ocr.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        prints = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print"
        ]

        assert prints, "print 를 하나도 못 찾았다 — 검사가 헛돈다"

        # **값을 읽는 자리만 본다.** 낱말로 훑으면 「`.env` 에
        # `CLOVA_OCR_SECRET_KEY` 를 채워 주세요」 같은 **안내 문구**가 걸린다.
        # 그건 이름이지 값이 아니다 — 이 저장소에서 세 번째 밟는 함정이라
        # `ast.Attribute` 로 좁힌다.
        offenders = [
            ast.unparse(node)
            for node in prints
            for sub in ast.walk(node)
            if isinstance(sub, ast.Attribute) and sub.attr == "CLOVA_OCR_SECRET_KEY"
        ]
        assert not offenders, f"러너가 키 값을 찍는다: {offenders}"
