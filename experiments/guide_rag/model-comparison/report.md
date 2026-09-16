# 안내문 RAG: 한국어 분석 · 재순위 모델 실측

합성 주제 문서 16개, 질의 20개(정답 있음 15개·없음 5개). 실제 의료 근거나 생성 안내문 품질 평가가 아닙니다.

Dense는 기존 고정 MiniLM, 한국어 분석은 Kiwi, 재순위 모델은 BAAI/bge-reranker-v2-m3입니다. 모델 버전과 파일 해시는 results.json에 기록했습니다.

모든 Hybrid는 Dense 후보 임계값 0, BM25 양수 점수, RRF 60, 후보 최대 10개, 최종 최대 3개로 통일했습니다. 임계값 0은 후보 회수 실험값이며 운영 적용 제안이 아닙니다.

## original

| 조합 | 정답 Top3 | 정답 1위 | MRR@3 | 근거 없는 질문에 후보 반환 |
|---|---:|---:|---:|---:|
| bm25_simple | 9/11 | 9/11 | 0.818 | 0/1 |
| hybrid_simple | 11/11 | 11/11 | 1.000 | 1/1 |
| bm25_kiwi | 11/11 | 11/11 | 1.000 | 0/1 |
| hybrid_kiwi | 11/11 | 11/11 | 1.000 | 1/1 |
| hybrid_simple_rerank | 11/11 | 11/11 | 1.000 | 1/1 |
| hybrid_kiwi_rerank | 11/11 | 11/11 | 1.000 | 1/1 |

## challenge

| 조합 | 정답 Top3 | 정답 1위 | MRR@3 | 근거 없는 질문에 후보 반환 |
|---|---:|---:|---:|---:|
| bm25_simple | 2/4 | 2/4 | 0.500 | 3/4 |
| hybrid_simple | 4/4 | 4/4 | 1.000 | 4/4 |
| bm25_kiwi | 4/4 | 3/4 | 0.875 | 3/4 |
| hybrid_kiwi | 4/4 | 4/4 | 1.000 | 4/4 |
| hybrid_simple_rerank | 4/4 | 4/4 | 1.000 | 4/4 |
| hybrid_kiwi_rerank | 4/4 | 4/4 | 1.000 | 4/4 |

## all

| 조합 | 정답 Top3 | 정답 1위 | MRR@3 | 근거 없는 질문에 후보 반환 |
|---|---:|---:|---:|---:|
| bm25_simple | 11/15 | 11/15 | 0.733 | 3/5 |
| hybrid_simple | 15/15 | 15/15 | 1.000 | 5/5 |
| bm25_kiwi | 15/15 | 14/15 | 0.967 | 3/5 |
| hybrid_kiwi | 15/15 | 15/15 | 1.000 | 5/5 |
| hybrid_simple_rerank | 15/15 | 15/15 | 1.000 | 5/5 |
| hybrid_kiwi_rerank | 15/15 | 15/15 | 1.000 | 5/5 |

## 해석 범위

- BM25 단독 행은 형태소 분석의 효과를 분리해서 보는 보조 비교입니다.
- 재순위 모델은 후보 순서만 변경합니다. 별도 거절 기준을 적용하지 않았으므로 근거 없는 질문에도 후보를 반환할 수 있습니다. 원시 점수는 확률이 아닙니다.
- 미승인·타 병원·과거 버전·라이선스 미확인 후보 반환은 모든 조합에서 0건입니다.
- 같은 작은 합성셋으로 반복 탐색했습니다. 독립 검증이나 임상 성능 증명이 아니며, 실제 승인 문서의 혼동 사례로 다시 평가해야 합니다.
- BGE-M3 Dense+Sparse 자체는 이번에 실행하지 않았습니다. 기존 Dense에 한국어 BM25와 reranker를 추가하는 조합을 비교했습니다.
- 운영 코드·DB·안내문 생성 경로·챗봇 설정은 변경하지 않았습니다.

## 질의별 순위

### Q01: PCOS 야즈정 medication

정답: pcos-med

- bm25_simple: pcos-med
- hybrid_simple: pcos-med, med-general, endo-med
- bm25_kiwi: pcos-med
- hybrid_kiwi: pcos-med, med-general, endo-med
- hybrid_simple_rerank: pcos-med, endo-med, med-general
- hybrid_kiwi_rerank: pcos-med, endo-med, med-general

### Q02: 자궁내막증 비잔정 medication

정답: endo-med

- bm25_simple: endo-med
- hybrid_simple: endo-med, pcos-med, med-general
- bm25_kiwi: endo-med
- hybrid_kiwi: endo-med, pcos-med, med-general
- hybrid_simple_rerank: endo-med, pcos-med, med-general
- hybrid_kiwi_rerank: endo-med, pcos-med, med-general

### Q03: PCOS 야즈정 caution

정답: pcos-care

- bm25_simple: pcos-care
- hybrid_simple: pcos-care, care-general, endo-care
- bm25_kiwi: pcos-care
- hybrid_kiwi: pcos-care, care-general, endo-care
- hybrid_simple_rerank: pcos-care, endo-care, care-general
- hybrid_kiwi_rerank: pcos-care, endo-care, care-general

### Q04: 자궁내막증 비잔정 caution

정답: endo-care

- bm25_simple: endo-care
- hybrid_simple: endo-care, care-general, pcos-care
- bm25_kiwi: endo-care
- hybrid_kiwi: endo-care, care-general, pcos-care
- hybrid_simple_rerank: endo-care, pcos-care, care-general
- hybrid_kiwi_rerank: endo-care, pcos-care, care-general

### Q05: PCOS life

정답: pcos-life

- bm25_simple: pcos-life
- hybrid_simple: pcos-life, food, sleep
- bm25_kiwi: pcos-life
- hybrid_kiwi: pcos-life, food, sleep
- hybrid_simple_rerank: pcos-life, endo-life, food
- hybrid_kiwi_rerank: pcos-life, endo-life, food

### Q06: 자궁내막증 life

정답: endo-life

- bm25_simple: endo-life
- hybrid_simple: endo-life, pcos-life, sleep
- bm25_kiwi: endo-life
- hybrid_kiwi: endo-life, pcos-life, sleep
- hybrid_simple_rerank: endo-life, pcos-life, food
- hybrid_kiwi_rerank: endo-life, pcos-life, food

### Q07: TESTX17 검사 목표

정답: lab

- bm25_simple: lab
- hybrid_simple: lab, endo-life, sleep
- bm25_kiwi: lab
- hybrid_kiwi: lab, endo-life, sleep
- hybrid_simple_rerank: lab, exercise, endo-life
- hybrid_kiwi_rerank: lab, exercise, endo-life

### Q08: 잠과 휴식에 관한 설명

정답: sleep

- bm25_simple: 없음
- hybrid_simple: sleep, pcos-life, endo-life
- bm25_kiwi: sleep
- hybrid_kiwi: sleep, pcos-life, endo-life
- hybrid_simple_rerank: sleep, food, endo-life
- hybrid_kiwi_rerank: sleep, food, endo-life

### Q09: 걷기 신체 활동

정답: exercise

- bm25_simple: exercise, endo-life
- hybrid_simple: exercise, endo-life, pcos-life
- bm25_kiwi: exercise, endo-life
- hybrid_kiwi: exercise, endo-life, pcos-life
- hybrid_simple_rerank: exercise, pcos-life, endo-life
- hybrid_kiwi_rerank: exercise, pcos-life, endo-life

### Q10: 식생활에 관한 안내

정답: food

- bm25_simple: 없음
- hybrid_simple: food, pcos-life, exercise
- bm25_kiwi: food
- hybrid_kiwi: food, pcos-life, exercise
- hybrid_simple_rerank: food, pcos-life, sleep
- hybrid_kiwi_rerank: food, pcos-life, sleep

### Q11: 우주선 궤도 추진체

정답: 없음

- bm25_simple: 없음
- hybrid_simple: exercise, endo-life, sleep
- bm25_kiwi: 없음
- hybrid_kiwi: exercise, endo-life, sleep
- hybrid_simple_rerank: sleep, exercise, endo-life
- hybrid_kiwi_rerank: sleep, exercise, endo-life

### Q12: PCOS 야즈정 생활관리

정답: pcos-life

- bm25_simple: pcos-life, food, sleep
- hybrid_simple: pcos-life, food, sleep
- bm25_kiwi: pcos-life, food, sleep
- hybrid_kiwi: pcos-life, food, sleep
- hybrid_simple_rerank: pcos-life, endo-life, sleep
- hybrid_kiwi_rerank: pcos-life, endo-life, sleep

### A01: 야즈정 PCOS 복약 안내

정답: pcos-med

- bm25_simple: pcos-med, endo-med, med-general
- hybrid_simple: pcos-med, endo-med, med-general
- bm25_kiwi: pcos-med, endo-med, med-general
- hybrid_kiwi: pcos-med, endo-med, med-general
- hybrid_simple_rerank: pcos-med, endo-med, med-general
- hybrid_kiwi_rerank: pcos-med, endo-med, med-general

### A02: 비잔정 자궁내막증 주의사항

정답: endo-care

- bm25_simple: endo-care, care-general, pcos-care
- hybrid_simple: endo-care, care-general, pcos-care
- bm25_kiwi: endo-care, care-general, pcos-care
- hybrid_kiwi: endo-care, care-general, pcos-care
- hybrid_simple_rerank: endo-care, pcos-care, care-general
- hybrid_kiwi_rerank: endo-care, pcos-care, care-general

### A03: 충분히 자고 쉬는 생활

정답: sleep

- bm25_simple: 없음
- hybrid_simple: sleep, pcos-life, exercise
- bm25_kiwi: food, sleep, exercise
- hybrid_kiwi: sleep, food, pcos-life
- hybrid_simple_rerank: sleep, food, pcos-life
- hybrid_kiwi_rerank: sleep, food, pcos-life

### A04: 식생활을 관리하는 내용

정답: food

- bm25_simple: 없음
- hybrid_simple: food, pcos-life, exercise
- bm25_kiwi: food, sleep, exercise
- hybrid_kiwi: food, pcos-life, exercise
- hybrid_simple_rerank: food, pcos-life, sleep
- hybrid_kiwi_rerank: food, pcos-life, sleep

### A05: PCOS 수술 비용 보험 청구

정답: 없음

- bm25_simple: pcos-life
- hybrid_simple: pcos-life, endo-life, lab
- bm25_kiwi: pcos-life
- hybrid_kiwi: pcos-life, endo-life, lab
- hybrid_simple_rerank: pcos-life, endo-life, lab
- hybrid_kiwi_rerank: pcos-life, endo-life, lab

### A06: 야즈정 가격 재고 구매처

정답: 없음

- bm25_simple: pcos-med
- hybrid_simple: pcos-med, med-general, endo-med
- bm25_kiwi: pcos-med
- hybrid_kiwi: pcos-med, med-general, endo-med
- hybrid_simple_rerank: pcos-med, endo-med, med-general
- hybrid_kiwi_rerank: pcos-med, endo-med, med-general

### A07: 자궁내막증 유전자 검사 결과 해석

정답: 없음

- bm25_simple: endo-care
- hybrid_simple: endo-care, pcos-care, care-general
- bm25_kiwi: endo-care
- hybrid_kiwi: endo-care, pcos-care, care-general
- hybrid_simple_rerank: endo-care, pcos-care, care-general
- hybrid_kiwi_rerank: endo-care, pcos-care, care-general

### A08: 날씨 기온 강수 확률

정답: 없음

- bm25_simple: 없음
- hybrid_simple: lab, sleep, food
- bm25_kiwi: 없음
- hybrid_kiwi: lab, sleep, food
- hybrid_simple_rerank: lab, sleep, food
- hybrid_kiwi_rerank: lab, sleep, food
