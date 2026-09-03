from app.core.db.databases import TORTOISE_APP_MODELS
from app.models.feedback import (
    PatientFeedback,
    PatientFeedbackCategory,
    PatientFeedbackSourceScreen,
    PatientFeedbackTarget,
)


def test_feedback_model_keeps_only_scoped_references_and_feedback_content() -> None:
    fields = set(PatientFeedback._meta.fields_map)

    assert {
        "hospital_id",
        "guide_document",
        "usage_event",
        "target",
        "source_screen",
        "section_key",
        "content_key",
        "detected_tab",
        "category",
        "details",
        "idempotency_digest",
    } <= fields
    assert not {"link_token", "otp", "patient_session", "patient_id", "question", "answer"} & fields


def test_feedback_contract_enums_match_the_patient_ui_contract() -> None:
    assert {item.value for item in PatientFeedbackTarget} == {"CHATBOT_RESPONSE", "GUIDE_SECTION"}
    assert {item.value for item in PatientFeedbackSourceScreen} == {"P6", "P9"}
    assert {item.value for item in PatientFeedbackCategory} == {
        "HELPFUL",
        "UNHELPFUL",
        "WRONG",
        "HARD_TO_UNDERSTAND",
        "UNSAFE",
        "OTHER",
    }


def test_feedback_model_is_registered_for_runtime_and_migrations() -> None:
    assert "app.models.feedback" in TORTOISE_APP_MODELS
