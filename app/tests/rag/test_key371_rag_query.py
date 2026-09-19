"""KEY-371: PCOS 생활관리 RAG 질의 구성 — 약 이름 제외·영어 문장형 검증."""

from app.models.catalog import SetDisease
from app.models.visits import GuideSectionKey
from app.services.guides import _PCOS_LIFE_QUERY, _rag_query


class TestRagQuery:
    def test_pcos_life_returns_fixed_english_query(self) -> None:
        query = _rag_query(SetDisease.PCOS, GuideSectionKey.LIFE, "PCOS", ("메트포르민", "레트로졸"))
        assert query == _PCOS_LIFE_QUERY

    def test_pcos_life_query_contains_no_korean_drug_names(self) -> None:
        query = _rag_query(SetDisease.PCOS, GuideSectionKey.LIFE, "PCOS", ("메트포르민", "레트로졸", "클로미펜"))
        assert "메트포르민" not in query
        assert "레트로졸" not in query
        assert "클로미펜" not in query

    def test_pcos_life_query_contains_lifestyle_vocabulary(self) -> None:
        query = _rag_query(SetDisease.PCOS, GuideSectionKey.LIFE, "PCOS", ("메트포르민",))
        assert "lifestyle" in query
        assert "PCOS" in query
        assert "weight management" in query
        assert "physical activity" in query

    def test_pcos_non_life_section_uses_legacy_query(self) -> None:
        query = _rag_query(SetDisease.PCOS, GuideSectionKey.MEDICATION, "PCOS", ("메트포르민",))
        assert query == "PCOS 메트포르민 medication"

    def test_endometriosis_life_uses_legacy_query(self) -> None:
        # 자궁내막증 생활관리는 fixed_template=True로 이 쿼리를 쓰지 않지만
        # 함수 자체는 기존 방식을 반환해야 한다 — 의도치 않은 분기 방지.
        query = _rag_query(SetDisease.ENDOMETRIOSIS, GuideSectionKey.LIFE, "ENDOMETRIOSIS", ("비잔",))
        assert query == "ENDOMETRIOSIS 비잔 life"

    def test_none_disease_uses_legacy_query(self) -> None:
        query = _rag_query(None, GuideSectionKey.LIFE, "", ("메트포르민",))
        assert query == " 메트포르민 life"

    def test_pcos_caution_section_includes_drug_names(self) -> None:
        query = _rag_query(SetDisease.PCOS, GuideSectionKey.CAUTION, "PCOS", ("메트포르민",))
        assert "메트포르민" in query
        assert "caution" in query
