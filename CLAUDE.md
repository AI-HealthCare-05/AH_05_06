# Claude Code 프로젝트 지침

@AGENTS.md
@docs/project_workflow.md
@docs/AI_WORK_START.md

사용자가 `KEY-번호 작업 시작해줘`라고 요청하면 다음 순서로 진행한다.

1. Jira에서 해당 일감의 설명, 인수조건, 관련 화면·API와 의존성을 확인한다.
2. Jira에 접근할 수 없으면 추측하거나 구현하지 말고 일감 링크나 설명을 요청한다.
3. 저장소 상태와 `develop` 기준을 확인한다.
4. 구현 범위, 수정 예상 파일, 테스트 계획을 먼저 짧게 제시한 뒤 작업한다.
