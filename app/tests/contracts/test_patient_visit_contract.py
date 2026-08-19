from pathlib import Path

CONTRACT_PATH = Path(__file__).parents[3] / "docs" / "contracts" / "patient-visit-api-v1.md"


def test_front_desk_visit_contract_has_complete_read_model() -> None:
    contract = CONTRACT_PATH.read_text(encoding="utf-8")

    required_terms = {
        "GET /api/v1/front-desk/visits",
        "hospital_patient_no",
        "birth_date",
        "diagnosis_name",
        "work_category",
        "detail_status",
        "IN_PROGRESS",
        "NEEDS_ATTENTION",
        "APPROVAL_REQUESTED",
        "SEND_PENDING",
        "COMPLETED",
        "next_cursor",
        "Asia/Seoul",
    }

    assert all(term in contract for term in required_terms)


def test_review_decisions_are_explicit_in_contract() -> None:
    contract = CONTRACT_PATH.read_text(encoding="utf-8")

    assert "department_id" in contract
    assert "DOCTOR_DEPARTMENT_MISMATCH" in contract
    assert "PATIENT_NUMBER_LOCKED" in contract
    assert "UPPER_SNAKE_CASE" in contract
    assert "VISIT_ALREADY_REGISTERED" in contract
