"""환자 링크 OTP·인증·세션·재발급 API 계약 — KEY-91, KEY-219."""

import datetime as _dt
from typing import Literal

from app.dtos.base import StrictModel


class PatientAuthContextRequest(StrictModel):
    link_token: str


class PatientAuthContextResponse(StrictModel):
    hospital_name: str
    masked_phone: str
    visited_at: _dt.date
    expires_at: _dt.datetime


class PatientSessionCheckRequest(StrictModel):
    """세션 확인도 **본문으로 받는다** — KEY-292.

    여태 `GET /patient-auth/session?link_token=<원문>` 이었다. 그러면 링크
    토큰이 **주소에 실려** nginx access log 에 원문 그대로 남는다 — 실제로
    확인했다.

        "GET /api/v1/patient-auth/session?link_token=<원문> HTTP/1.1" 401

    `app/core/masking.py` 가 `token` 을 가려야 할 값으로 두고 uvicorn 로그를
    막아 두었지만, **그것으로 nginx 로그는 못 막는다.** AGENTS.md 「환자 링크
    토큰을 코드·화면·로그·커밋에 남기지 않는다」에 정면으로 걸린다.

    읽기인데 `POST` 인 것이 어색해 보일 수 있다. 그런데 이 저장소의 다른
    링크 종점(`/context`·`/otp/issue`·`/otp/verify`)이 모두 같은 까닭으로
    본문을 쓴다 — 토큰을 주소에 안 싣는 것이 이 화면의 계약이다.
    """

    link_token: str


class PatientSessionResponse(StrictModel):
    active: Literal[True] = True
    expires_in_seconds: int


class PatientLinkReIssueRequest(StrictModel):
    link_token: str


class PatientLinkReIssueResponse(StrictModel):
    requested: Literal[True] = True


class PatientOtpIssueRequest(StrictModel):
    link_token: str


class PatientOtpIssueResponse(StrictModel):
    expires_at: _dt.datetime
    retry_after_seconds: int


class PatientOtpVerifyRequest(StrictModel):
    link_token: str
    # 정규식 검증 오류는 입력 원문을 422 응답에 되비출 수 있다. 형식 검증과
    # 실패 횟수 반영은 서비스에서 수행해 OTP가 화면 응답에 포함되지 않게 한다.
    code: str


class PatientOtpVerifyResponse(StrictModel):
    verified: Literal[True] = True
    session_expires_in_seconds: int
