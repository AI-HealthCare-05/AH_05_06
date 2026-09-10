# KEY-277 Pilot 인수 확인

## 실행 구분

- 로컬 자동검사: 합성 MySQL·Redis, 합성 임베딩/모델 응답을 사용한다.
- 모델 프롬프트에는 합성 처방의 카탈로그 이름만 전달하는지 검사한다.
- 아래 Pilot 수동 실측은 아직 수행하지 않았다. 자동검사 통과를 수동 확인으로 대신 기록하지 않는다.
- 실제 환자 데이터·문자 발송·환자 링크 발급은 이 검증의 대상이 아니다.
- 검색 재시도 소진 시 고정 사유의 오류 로그를 발생시키지만, 운영 알림 수신 채널과의 연결·전달은 아직 검증하지 않았다. 오류 로그 발생을 알림 수신 완료로 계산하지 않는다.

## 로컬 검증 기록

- `pytest -n4 -q --tb=short app ai_worker`: **2581 passed, 1 xfailed, 9 warnings, 14 subtests passed**. 전용 합성 MySQL 8.0·Redis에서 실행했다. xfailed와 기존 HTTP 422 deprecation 경고는 성공 건수에 포함하지 않는다.
- 프런트 계약 검사: **1180 passed**. 화면을 그리지 않는 검사이므로 아래 수동 항목을 대체하지 않는다.
- Ruff check·format check, mypy 434개 파일, OpenAPI 산출물 대조, `git diff --check`: 통과.
- KEY-82 평가: 6개 사례 통과, checksum `0a6c9161d77a65dbf860c3d4d7eaf9c0efe5ee768bced68db514f5716da87bb5` 일치.
- migration 52: 전용 합성 빈 DB 0→52 및 기존 51 스키마→52, upgrade 재실행 추가 적용 없음, 이후 Aerich `No changes detected` 확인. 운영 데이터 복제 검증은 아니다.
- API·AI 워커·웹 로컬 이미지 빌드 통과. 운영/Pilot 컨테이너를 교체하거나 레지스트리에 배포하지 않았다.
- 전체 검사 중 추가한 downgrade 검사에서 공용 이벤트 루프를 해제하는 테스트 결함을 발견하여 수정했다. 수정 후 위 전체 회귀를 다시 실행했다.

## 배포 전 준비

1. 같은 PR 커밋으로 API·AI 워커·웹 이미지를 고정한다.
2. migration 52까지 적용한 후 `aerich migrate`가 추가 변경을 만들지 않는지 확인한다.
3. KEY-82 §6의 승인 checksum과 고정 모델 revision을 확인한다. 임계값은 0.72, top-k는 3이다.
4. 검증 병원의 합성 진료·확정 OCR·카탈로그 처방과 승인된 지식/템플릿을 준비한다.
5. API·워커 양쪽 `GUIDE_RAG_ENABLED=true`를 적용한다. 모델/키는 출력·기록하지 않는다.
6. 고정 revision 임베딩 모델을 워커에서 사용할 수 있는지, 오류 로그의 운영 알림 수신자를 확인한다.

## 시나리오

| 시나리오 | 기대 결과 | 로컬 자동검사 | Pilot 수동 |
| --- | --- | --- | --- |
| 정상 | 접수→저장, 섹션 출처·버전·확인일 표시, 승인 전 환자 접근 불가 | test_normal_generation_persists_sources_and_has_no_patient_identifiers / 기존 승인 게이트 회귀 | 미실행 |
| 근거 없음 | 검증된 승인 고정 템플릿·ID·버전 표시, LLM 미호출 | test_no_evidence_uses_only_approved_versioned_templates | 미실행 |
| 미승인 지식 | 미승인 본문을 모델에 전달하지 않음 | test_unapproved_sources_never_reach_model | 미실행 |
| 출처 충돌 | 차단, 템플릿으로 숨기지 않음 | test_source_conflict_blocks_without_fallback | 미실행 |
| 범위 위반 | 타 병원/다른 섹션 근거 차단, 타 병원 조회 404 | test_out_of_scope_cached_hit_cannot_reach_model / test_poll_is_hospital_scoped_and_returns_saved_sources | 미실행 |
| 검색 장애 | 3회 소진 후 승인 템플릿, 화면 사유 및 운영 알림 | test_search_outage_retries_then_records_template_reason | 미실행 |
| LLM 실패 | 3회 소진 후 실패, 부분 안내문·모델 원문 없음 | test_llm_failure_exhausts_then_fails_without_partial_guide | 미실행 |
| 안전 차단 | 생성문 미저장, GuideSafetyCheck BLOCK 감사 보존 | test_safety_block_cannot_save_model_text | 미실행 |

추가: 인덱스 오류는 재인덱싱 전 차단, 생성 중 처방/출처 변경은 저장 차단,
재생성 이후에도 이전 근거 스냅샷은 보존되어야 한다.

실측 기록에는 배포 커밋·이미지 식별자·실행 시각·합성 진료 식별자·관찰 결과만 남긴다.
인증키·환자 정보·전체 프롬프트·외부 오류 응답은 첨부하지 않는다.
오류 조건을 만들기 위해 운영 지식을 직접 철회하거나 운영 인덱스를 훼손하지 않는다.
격리된 합성 대상과 장애 주입 방법을 배포 담당자와 먼저 확정한다.

## 완료 게이트

Pilot 8종 실측 및 운영 알림 수신 확인 → 금준님 최종 리뷰 → Draft 해제/병합 판단.
의사 승인 없는 안내를 챗봇 근거로 사용하는 변경은 포함하지 않는다.
