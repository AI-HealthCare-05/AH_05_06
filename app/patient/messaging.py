from dataclasses import dataclass
from enum import StrEnum


class MessageKind(StrEnum):
    ACCESS_LINK = "access_link"
    OTP = "otp"


@dataclass(frozen=True)
class SentMessage:
    kind: MessageKind
    recipient: str
    content: str


class PatientMessageGateway:
    async def send(self, message: SentMessage) -> None:
        raise NotImplementedError


class InMemoryPatientMessageGateway(PatientMessageGateway):
    """Local/test adapter. No API exposes these message bodies."""

    def __init__(self) -> None:
        self.messages: list[SentMessage] = []

    async def send(self, message: SentMessage) -> None:
        self.messages.append(message)
