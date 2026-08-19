# AI 작업 시작 가이드

Jira가 작업 범위의 기준이며 GitHub Issue는 명시적으로 요청받은 경우에만 사용한다.

## 기본 입력

Codex 또는 Claude Code에서 저장소 루트를 연 뒤 새 대화마다 아래 한 줄만 입력한다.

```text
KEY-50 작업 시작해줘
```

- Codex는 루트의 `AGENTS.md`, Claude Code는 루트의 `CLAUDE.md`를 프로젝트 지침으로 사용한다.
- AI가 Jira에 접근할 수 없다고 알리면 해당 일감의 링크나 설명을 붙여준다.
- AI는 구현 전에 범위, 수정 예상 파일, 테스트 계획을 먼저 요약한다.
- 커밋·PR 생성은 담당자가 요청한 경우에만 수행한다.

## GitHub 규칙

- 작업 기준은 Jira이며 하나의 브랜치·PR은 원칙적으로 하나의 Jira 하위 작업에 대응한다.
- 브랜치 예시: `feat/KEY-50-patient-history`, `fix/KEY-61-ocr-permission`
- 커밋 이모지·타입·본문 형식은 한금준이 작성한 `.github/commit_template.txt`를 기준으로 한다.
- Jira 연결이 필요한 작업은 커밋 요약에도 `[KEY-번호]`를 포함한다. 예: `✨ feat: [KEY-50] 환자 상세 조회 구현`
- PR 대상은 `develop`이고 `.github/PULL_REQUEST_TEMPLATE.md`의 항목을 채운다.
- GitHub Issue 생성 요청을 받은 경우에만 `.github/ISSUE_TEMPLATE`의 해당 템플릿을 사용한다.
- PR 병합 후 `qa-required` 라벨이 있으면 Jira `QA`, 없으면 `완료`로 전환된다.

## 완료 전 최소 확인

변경 범위에 맞는 항목만 실행하고 결과를 PR에 기록한다.

```bash
uv run ruff check .
uv run ruff format . --check
uv run coverage run -m pytest app
uv run coverage report -m
```

- 테스트 실행에 MySQL이나 환경변수가 필요해 실행하지 못했다면 실패를 숨기지 말고 이유를 기록한다.
- 인증·권한·OTP, 개인정보·원본 삭제·감사로그, OCR·LLM 의료 안전, 영역 간 통합, 회귀 위험이 큰 버그는 `qa-required`를 우선 검토한다.
- 그 외 작업은 리뷰어의 코드리뷰·기능 시연·인수조건 확인 후 완료한다.
