# API 명세서

이 디렉터리는 구현 중인 API 계약의 공통 진입점이다. API는 인증 주체와 사용 흐름이 다른 병원용과 환자용으로 나누고, 양쪽이 함께 지켜야 하는 규칙은 한 곳에서 관리한다.

## 문서 구조

```text
API 명세서
├─ common.md       공통 규칙
├─ hospital.md     병원용 API
└─ patient.md      환자용 API
```

| 문서 | 책임 범위 |
|---|---|
| [공통 규칙](common.md) | 버전, 인증 경계, 오류, 식별자, 민감정보, 영역 간 데이터 계약 |
| [병원용 API](hospital.md) | 직원 로그인, 환자·진료, 의료문서·OCR, 안내 생성·승인, 관리자 기능 |
| [환자용 API](patient.md) | 환자 링크, OTP·세션, 승인 안내 조회, 챗봇, D+7 응답 |

## 관리 원칙

- 엔드포인트와 요청·응답 계약은 인증 주체에 따라 병원용 또는 환자용 한 곳에만 작성한다.
- 병원과 환자가 함께 사용하는 승인 안내·D+7 환류 계약은 공통 규칙에 정의하고 양쪽 문서에서 링크한다.
- 같은 계약을 여러 파일에 복제하지 않는다.
- 엔드포인트·HTTP 메서드, 필수 필드, 인증·권한, 공통 오류, 영역 간 데이터 계약의 큰 변경은 구현 전에 팀에 공유한다.
- 결정된 변경의 영향 범위와 근거는 Jira와 PR에 기록한다.

## OpenAPI 산출물

[`openapi.json`](openapi.json)은 현재 FastAPI 라우터와 Pydantic DTO에서 자동 생성하는
기계 판독용 계약 산출물이다. 사람이 계약의 배경·결정을 적는 문서는 이 디렉터리의
Markdown 파일이고, `openapi.json`을 직접 편집하지 않는다.

```bash
# 서버 DTO를 기준으로 산출물을 갱신한다.
uv run --group app python scripts/generate_openapi.py

# 파일을 고치지 않고 현재 서버 DTO와 일치하는지만 확인한다.
uv run --group app python scripts/generate_openapi.py --check
```

- API DTO·라우터를 바꾸는 PR은 첫 명령으로 산출물을 재생성하고 함께 커밋한다.
- CI는 두 번째 명령을 실행한다. 산출물 갱신을 빼먹으면 CI가 실패한다.
- 이 파일은 **현재 최종 계약**이다. 2026-09-01 기준선은
  [`openapi-2026-09-01.json`](openapi-2026-09-01.json)으로 별도 보관하며, 현재
  서버와 비교하는 CI 대상이 아니다. 두 파일의 생성 시점·용도는
  [`openapi-baselines.md`](openapi-baselines.md)에 기록한다.

기존에 분산돼 있던 직원 인증, 환자·진료, OCR 상세 계약과 구현 기록은 병원용 API 문서로 통합했다. 이후 계약은 위 세 문서에서만 관리한다.
