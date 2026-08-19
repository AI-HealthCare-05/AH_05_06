# AI 작업 시작 가이드

팀원이 AI와 구현을 시작할 때 아래 프롬프트를 복사하고 빈칸을 채운다. Jira가 작업 범위의 기준이며 GitHub Issue는 명시적으로 요청받은 경우에만 사용한다.

## 초기 프롬프트

```text
이 저장소의 다음 Jira 일감을 구현해 주세요.

- Jira: KEY-___
- 목표:
- 관련 화면 ID:
- 관련 API:
- 인수조건:
- 변경 금지 범위:

작업 전에 반드시 다음을 수행하세요.

1. AGENTS.md와 docs/project_workflow.md를 끝까지 읽으세요.
2. Jira 설명·인수조건과 관련 API 명세·와이어프레임을 확인하세요.
3. git status와 현재 브랜치를 확인하고 기존 사용자 변경을 보존하세요.
4. origin/develop 최신 상태를 기준으로 Jira 키가 포함된 작업 브랜치를 사용하세요.
5. 구현 범위, 수정 예상 파일, 테스트 계획을 짧게 제시한 뒤 작업하세요.

작업 중 다음 원칙을 지키세요.

- Jira에 없는 기능을 추가하거나 공통 모듈을 복제하지 마세요.
- 요구사항이나 문서가 충돌하면 추측하지 말고 확인 필요 항목으로 보고하세요.
- 실제 환자정보와 비밀번호·API 키·JWT·OTP·환자 링크 토큰을 사용하거나 노출하지 마세요.
- 역할·소유권 검증은 프론트엔드가 아니라 서버에서 최종 수행하세요.
- 확정된 OCR·처방·승인 지식 밖의 의료정보를 생성하지 마세요.
- 처방되지 않은 약, 진단 추정, 약물 변경·중단·용량 조절 권고를 추가하지 마세요.
- 관련 없는 리팩터링이나 파일 정리는 하지 마세요.

완료 시 변경 파일, 테스트 결과, 남은 제한사항, qa-required 필요 여부를 보고하세요.
커밋·PR 생성은 담당자가 요청한 경우에만 수행하세요.
```

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
