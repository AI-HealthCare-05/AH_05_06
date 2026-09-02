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
