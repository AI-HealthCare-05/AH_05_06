"""8/27 종단간 최소 동작본이 무는 데이터가 실제로 있는가 — KEY-148.

`docs/contracts/walking-skeleton-v1.md` 가 네 사람에게 「이 환자·이 진료를 쓰라」고
말한다. 그 문서가 가리키는 값이 CSV 에서 사라지거나 바뀌면 **다음 주 월요일에
네 사람이 각자 다른 곳에서 막힌다.** 그때 원인을 찾는 것보다 지금 죽는 편이 낫다.

여기서 재는 것은 넷이다.

    ① 고른 시나리오가 CSV 에 있고 문서가 적은 값과 같다
    ② 골격에 예외가 없다 — 특이사항 없음 · 동명이인 아님
    ③ 승인할 의사와 로그인할 스탭이 같은 병원에 있다
    ④ 이름으로 풀면 안 되는 이유가 실재한다 (박연 동명이인)
"""

import csv
from pathlib import Path

DOCS = Path(__file__).resolve().parents[3] / "docs"
PATIENTS_CSV = DOCS / "data" / "synthetic-patients.csv"
STAFF_CSV = DOCS / "data" / "synthetic-staff.csv"
CONTRACT = DOCS / "contracts" / "walking-skeleton-v1.md"

with PATIENTS_CSV.open(encoding="utf-8-sig") as _f:
    PATIENTS: list[dict[str, str]] = list(csv.DictReader(_f))
with STAFF_CSV.open(encoding="utf-8-sig") as _f:
    STAFF: list[dict[str, str]] = list(csv.DictReader(_f))

#: 계약이 고른 것. 이 값을 바꾸려면 문서도 함께 바꿔야 한다.
SCENARIO = "SYN-EMS-01"
CHART_NO = "12401"
HOSPITAL = "H1"
DOCTOR_LOGIN = "doctor01"
STAFF_LOGIN = "staff01"


def _patient() -> dict[str, str]:
    row = next((r for r in PATIENTS if r["시나리오ID"] == SCENARIO), None)
    assert row is not None, f"{SCENARIO} 이 환자 CSV 에서 사라졌다"
    return row


def _staff(login_id: str) -> dict[str, str]:
    row = next((r for r in STAFF if r["login_id"] == login_id), None)
    assert row is not None, f"{login_id} 이 직원 CSV 에서 사라졌다"
    return row


class TestTheChosenScenarioIsStillThere:
    def test_the_patient_row_exists_with_the_chart_number_we_documented(self) -> None:
        assert _patient()["차트번호"].strip() == CHART_NO

    def test_the_visit_has_a_date(self) -> None:
        """진료가 없으면 업로드도 판독도 붙을 자리가 없다."""
        assert _patient()["진료일"].strip(), f"{SCENARIO} 에 진료일이 없다"

    def test_the_visit_has_a_prescription(self) -> None:
        """복약안내를 만들려면 약이 있어야 한다."""
        row = _patient()
        for column in ("처방세트", "약", "용법", "처방일수"):
            assert row[column].strip(), f"{SCENARIO} 의 {column} 이 비었다"

    def test_the_visit_has_lab_values_to_read(self) -> None:
        """OCR 이 읽을 것이 없으면 4단계가 빈다."""
        labs = [
            "혈색소",
            "자궁내막종",
            "내막두께",
            "ASTALT",
            "월경주기",
            "총테스토스테론",
            "DHEAS",
            "LH_FSH",
            "AMH",
            "기타검사",
        ]
        filled = [c for c in labs if _patient()[c].strip()]
        assert len(filled) >= 3, f"{SCENARIO} 의 검사값이 {len(filled)}개뿐이다"

    def test_the_patient_agreed_to_sms(self) -> None:
        """수신 거부면 7·8단계(링크 발송·D+7)가 계약상 막힌다."""
        assert _patient()["문자수신동의"].strip() == "Y"


class TestTheSkeletonHasNoExceptions:
    """골격이 확인할 것은 「흐름이 이어지는가」다. 분기가 붙으면 그것부터 만들게 된다."""

    def test_no_safety_flag_on_this_patient(self) -> None:
        """특이사항이 있으면 🚨 안전 차단 분기를 먼저 만들어야 한다.

        `SYN-DUP-03`(우울증 병력)을 안 고른 이유가 이것이다.
        """
        assert not _patient()["특이사항"].strip(), f"{SCENARIO} 에 특이사항이 생겼다 — 골격에 안전 차단 분기가 끼어든다"

    def test_this_patient_name_is_not_shared_with_anyone(self) -> None:
        """동명이인이면 환자 선택이 곧 식별 시험이 된다. 골격의 관심사가 아니다."""
        name = _patient()["이름"].strip()
        same = [r["시나리오ID"] for r in PATIENTS if r["이름"].strip() == name]
        assert same == [SCENARIO], f"{name} 이 여럿이다: {same}"


class TestTheAccountsWeSignInWith:
    def test_the_approving_doctor_is_active_and_in_the_same_hospital(self) -> None:
        doctor = _staff(DOCTOR_LOGIN)
        assert doctor["병원"] == HOSPITAL
        assert "doctor" in doctor["roles"], "승인은 의사 역할만 한다"
        assert doctor["status"] == "active"

    def test_the_desk_staff_can_sign_in_without_a_password_change(self) -> None:
        """`must_change_password` 가 Y 면 L-3 을 먼저 지나야 해서 시연이 끊긴다."""
        staff = _staff(STAFF_LOGIN)
        assert staff["병원"] == HOSPITAL
        assert staff["status"] == "active"
        assert staff["must_change_password"] == "N"

    def test_the_visit_doctor_matches_the_account_we_approve_with(self) -> None:
        """진료의 담당의와 승인 계정이 다르면 「자기 환자」 화면이 안 맞는다."""
        assert _patient()["담당의"].strip() == _staff(DOCTOR_LOGIN)["이름"].strip()


class TestWhyWeDoNotResolvePeopleByName:
    def test_the_doctor_name_really_is_ambiguous_across_hospitals(self) -> None:
        """계약이 「이름으로 찾지 마라」고 적은 근거가 실재하는가.

        근거가 사라지면 그 문장은 잔소리가 된다 — 그때는 문서에서 빼야 한다.
        """
        name = _staff(DOCTOR_LOGIN)["이름"].strip()
        hospitals = {r["병원"] for r in STAFF if r["이름"].strip() == name}
        assert len(hospitals) > 1, (
            f"{name} 이 이제 한 병원에만 있다 — 계약 §1 의 「이름으로 찾지 마라」 근거를 다시 써야 한다"
        )


class TestTheContractDocumentAgreesWithTheData:
    """문서가 적은 값과 CSV 가 갈리면 읽는 사람이 문서를 믿는다."""

    def test_the_document_exists(self) -> None:
        assert CONTRACT.exists(), f"{CONTRACT} 가 없다"

    def test_the_document_names_the_scenario_and_the_accounts(self) -> None:
        text = CONTRACT.read_text(encoding="utf-8")
        for token in (SCENARIO, CHART_NO, DOCTOR_LOGIN, STAFF_LOGIN):
            assert token in text, f"계약 문서가 {token} 을 말하지 않는다"

    def test_the_documented_patient_details_match_the_csv(self) -> None:
        text = CONTRACT.read_text(encoding="utf-8")
        row = _patient()
        for column in ("이름", "생년월일", "진료일"):
            value = row[column].strip()
            assert value in text, f"문서의 {column} 이 CSV({value})와 다르다"
