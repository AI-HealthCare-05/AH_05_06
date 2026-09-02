from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.visits import GuideSectionKey


class ChatbotResponseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    link_token: str = Field(min_length=1, max_length=200)
    question: str = Field(min_length=1, max_length=500)

    @field_validator("link_token", "question")
    @classmethod
    def non_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("공백만 입력할 수 없습니다.")
        return stripped


class ChatbotResponse(BaseModel):
    answer: str
    evidence: str
    source: str
    limitation: str
    urgent: bool = False
    fallback: bool = False
    grounded_section: GuideSectionKey | None = None
    response_ref: str | None = None
