# OpenAPI 기준선 기록

OpenAPI JSON은 사람이 직접 편집하는 명세가 아니라, 해당 시점 서버의 FastAPI
라우터와 Pydantic DTO에서 생성한 산출물이다. 따라서 **과거 기준선**과 **현재
최종 계약**을 같은 파일로 취급하지 않는다.

| 구분 | 파일 | 생성 기준 | 용도 |
|---|---|---|---|
| Sprint 4 초기 기준선 | [`openapi-2026-09-01.json`](openapi-2026-09-01.json) | 2026-09-01 23:33 KST, 커밋 `51cbfdbc3fdc0343ffed9c7520f597f718ea0db4` | 9/1 이후 계약 변경의 영향 비교 |
| 현재 최종 계약 | [`openapi.json`](openapi.json) | 현재 `develop`의 서버 DTO | 개발·PR·CI가 검증하는 계약 |

현재 계약은 아래 명령으로만 갱신한다. CI도 같은 명령의 `--check` 모드로,
코드는 바뀌었는데 산출물 커밋을 빼먹은 PR을 실패시킨다.

```bash
uv run --group app python scripts/generate_openapi.py
uv run --group app python scripts/generate_openapi.py --check
```

기준선 파일 자체는 과거 시점의 기록이므로 CI가 현재 DTO와 같아야 한다고
검사하지 않는다. API의 의도·호환성 판단은 `common.md`·`hospital.md`·`patient.md`,
그리고 해당 Jira·PR에서 함께 검토한다.
