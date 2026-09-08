# KEY-276 승인 의료지식 적재·검색 파이프라인

## 목적과 안전 경계

이 작업은 승인 의료지식을 private MinIO에 보관하고 MySQL 8에 버전·청크·임베딩을
저장한 뒤 Python cosine으로 검색하는 경계까지만 만든다. 안내문 생성, 챗봇,
환자 화면에는 연결하지 않는다. 생성 연결은 KEY-277의 별도 범위다.

선행 정본인 `KEY-82-rag-search-poc.md`는 Pilot에서 로컬 임베딩만 허용한다.
따라서 Jira 본문의 “OpenAI Embeddings” 표현보다 선행 안전 결정을 우선하여
`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`의 고정 revision과
384차원을 사용한다. 외부 임베딩 전송은 보안·의료 검토가 별도로 승인되기 전까지
구현하거나 활성화하지 않는다.

## 저장 구조

- `knowledge_document`: 제목, 기관, 원문 URL, 병원 범위, 입력 유형의 고정 식별자
- `knowledge_version`: 원문 hash, private object key, 라이선스, 검증일, 승인 상태
- `knowledge_chunk`: 800자 이하 정규화 텍스트, 위치·페이지·OCR 좌표, 로컬 임베딩
- `knowledge_ingestion_attempt`: 원문 없는 실행 상태, 안전한 오류 코드, 재시도 시각

문서 버전은 `DRAFT → APPROVED → DEPRECATED`로 이동한다. 현재 승인본에만
`current_approved_key=document_id`를 채우고 unique 제약을 걸어 문서당 현행 승인본이
두 개 생기지 않게 한다. 같은 문서·버전에 다른 바이트를 덮어쓰는 요청은
`VERSION_CONTENT_MISMATCH`로 막는다. 같은 바이트 재처리는 청크를 중복 생성하지 않는다.

## 입력 계약

세 입력은 `KnowledgeIngestionService.ingest()` 하나로 들어간다.

1. 텍스트 PDF: `pypdf`로 페이지별 텍스트와 페이지 번호를 보존한다.
2. 스캔/이미지: Worker의 CLOVA 어댑터가 텍스트, 좌표, 평균 신뢰도를 넘긴다.
3. 구조화 API: 원본 JSON snapshot을 MinIO에 보관하고 정렬된 `경로 = 값` 행으로 정규화한다.

원문/snapshot은 `approved-knowledge` 버킷의
`knowledge/{scope}/{source_key}/{version}/{sha256}.source`에 둔다. object key는 URL이
아니며 presigned/public URL을 반환하는 기능도 두지 않는다. `minio_init.sh`는 버킷을
만들 때마다 익명 정책을 `none`으로 재설정한다.

## 승인과 검색 규칙

승인은 다음을 모두 만족해야 한다.

- A등급 출처이며 기관과 원문 URL이 있다.
- 라이선스 확인이 끝났다.
- 적재 실행이 `READY`이고 청크가 있다.
- 검토 만료일을 이미 지난 자료가 아니다.

검색은 승인 상태, 현행 버전, A등급, 라이선스, 검증일, 병원 범위, section, 검토
유효기간, 고정 임베딩 모델·revision·차원을 모두 검사한다. 결과에는 문서/청크 ID,
기관, URL, 버전, 검증일, 병원 범위, score와 `approved_current` 검증 상태를 담는다.
한 건도 없으면 텍스트를 만들지 않고 `NO_VERIFIED_CONTEXT`만 반환한다.

## 실행과 검증

```bash
uv sync --group app --group dev
DB_HOST=127.0.0.1 uv run aerich upgrade
DB_HOST=127.0.0.1 uv run pytest -q \
  app/tests/rag/test_key82_knowledge_search.py \
  app/tests/rag/test_key276_approved_knowledge_pipeline.py
```

환경변수 `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`, `KNOWLEDGE_MINIO_ENDPOINT`,
`KNOWLEDGE_MINIO_BUCKET`은 `.env`/배포 secret에서만 주입한다. 로그·오류 코드·커밋에는
자격증명이나 원문을 남기지 않는다.
