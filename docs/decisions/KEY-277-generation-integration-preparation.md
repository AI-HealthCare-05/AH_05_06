# KEY-277 연결 준비 상태

Jira: https://leehee.atlassian.net/browse/KEY-277

## 이번 준비 범위

- KEY-276 검색 결과를 현재 DB와 다시 대조하는 `revalidate_guide_sources`.
- 승인·활성 버전·기관·URL·확인일·만료·병원·섹션·최소 점수·본문 해시 검증.
- 하나라도 불일치하면 전체 근거를 반환하지 않는다. 예외를 임의 본문으로 대체하지 않는다.
- 검증된 본문·문서/청크 ID·버전·기관·URL·확인일·점수·본문 해시를 frozen DTO로 복사한다.
- DTO의 본문은 repr에서 제외한다. 원문을 로그로 출력하지 않는다.

## 아직 연결하지 않은 범위

이 모듈은 생성 허가 또는 전체 안전 게이트가 아니다. 검색 결과를 재검증하는
준비 모듈이며 운영 호출부는 없다. 현재 GuideService.generate()와 환자·챗봇
동작은 변경하지 않는다. LLM 호출, 새 외부 데이터 전송은 하지 않는다.

2026-09-10 [리뷰 결정](https://github.com/AI-HealthCare-05/AH_05_06/pull/286#issuecomment-5613664688)에서
KEY-82 평가 통과, KEY-276·KEY-83 병합 및 KEY-75 재사용을 확인했다.
외부 선행 블로커는 없으며, 아래 생성 연결은 KEY-277의 남은 구현 범위다.
기존 GuideService 상태기계를 확장하고 실제 연결 시 승인된 PocEvaluationApproval을 적용한다.

1. 확정 OCR·처방에서 식별정보 없는 검색 질의를 구성한다.
2. KEY-276 provider 결과를 프롬프트 직전에 재검증한다.
3. 안전 훅을 재사용하고, 근거가 없으면 승인·버전 고정 템플릿만 사용한다.
4. GuideSectionSourceSnapshot 1:N 모델·migration과 실제 영속 저장을 구현한다.
5. 섹션 재생성 시 이전 버전 근거 보존과 병원용 조회/표시를 연결한다.
6. 실패·반려·재생성·승인 E2E 및 이미지 빌드·Pilot 검증을 수행한다.

최초 준비 커밋의 frozen DTO는 메모리 복사다. 아래 후속 저장 기능을 생성 호출부에 연결해야 한다.
KEY-277 전체 인수조건 완료 또는 배포 준비로 표시하지 않는다.

## 후속 구현 진행 (2026-09-10)

- GuideSectionSourceSnapshot 및 migration 52: 안내 버전·섹션별 1:N 근거 메타데이터 저장. develop의 51번과 중복되어 최신 모델 기준으로 Aerich 재생성했다.
- 원본 지식과 FK를 맺지 않으며, 섹션 재생성 시 SET NULL로 이전 버전 근거를 보존한다.
- 검증 근거와 승인 gate 결과 기반 템플릿 저장 함수를 추가했다. 충돌·인덱스 오류는 템플릿 사유로 허용하지 않는다.
- 병원 응답의 sections[].sources 및 의료진 원문 패널에 출처/템플릿 정보 표시를 추가했다.
- 아직 GuideService.generate 호출부는 연결 전이다. 운영 생성 완료로 간주하지 않는다.
- 2026-09-10 develop `b6bf470` 반영 후 migration 52를 Aerich로 재생성했다.
  `MODELS_STATE`에 `staff_account_event`, `guide_safety_check`,
  `drug_caution_content.physician_review` 및 새 근거 스냅샷 모델이 포함되는 회귀 검사를 추가했다.
- 기존 개발 DB와 분리한 MySQL 8.0에서 빈 DB 0→52, 기존 이력 0→51→52,
  각 DB의 upgrade 재실행(추가 적용 없음), 이후 `aerich migrate`의
  `No changes detected`를 확인했다. 기존 DB 시나리오는 합성 51번 스키마 기준이며
  운영 데이터 복제 검증은 아니다. downgrade 검증은 이번 실행에 포함하지 않았다.
- RAG 전체 테스트 110개 및 DB 연결 없는 마이그레이션 검사 64개 통과.
  전체 애플리케이션 CI 및 KEY-277 전체 기능 검증 완료를 뜻하지 않는다.

## 재검증 반환 계약

`GuideSourceValidation`은 검증된 `sources`와 `block_reason`을 반환한다.
성공 시 사유는 None이며, 실패 시 근거는 항상 빈 tuple이다.
검색의 no_verified_context, source_conflict, index_invalid는 그대로 구분한다.
충돌·인덱스 오류 및 필드 불일치는 근거 없음 fallback으로 변환하면 안 된다.
근거 없음도 이 모듈이 템플릿 사용을 승인하는 것은 아니며 기존 admission gate를 거친다.
필드별 실패 사유에는 본문이나 환자 정보가 포함되지 않는다.
호출자는 검색과 재검증에 같은 min_similarity를 전달한다(기본 0.72).
