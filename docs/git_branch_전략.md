# Git Flow 브랜치 전략

> 이 프로젝트는 Git Flow 브랜치 전략을 따릅니다.
> main과 develop 두 개의 상시 브랜치를 축으로 두고,  
> 목적에 따라 일시적인 브랜치(작업 / 릴리스 / 핫픽스)를 분기했다가 병합 후 삭제하는 구조입니다.

---

## 1. 배경

프로젝트 현황 결과:

- 원격에 이미 `develop` 브랜치가 존재함
- `docs/1일차_team_rules.md`에 커밋 / PR / 코드리뷰 규칙은 잘 잡혀 있음
- 다만 **브랜치 전략** 자체는 `main` 기준의 단순한 형태(GitHub Flow에 가까움)로만 정의되어 있음

---

## 2. 브랜치 5종

| 브랜치 | 역할 | 분기 위치 | merge 대상 |
|---|---|---|---|
| `main` | 배포 가능한 안정 버전만 유지 | – | – |
| `develop` | 다음 릴리스 통합 브랜치 | `main` | – |
| `feat/*`, `fix/*`, `docs/*` 등 | 실제 작업 단위 (기존 네이밍 유지) | `develop` | `develop` |
| `release/vX.Y.Z` | 배포 준비 (QA, 버전 정리) | `develop` | `main` + `develop` |
| `hotfix/*` | 운영 중 긴급 버그 수정 | `main` | `main` + `develop` |

---

## 3. 핵심 변경점

평소 작업 브랜치의 **분기 · PR 기준을 `main` → `develop`으로 변경**하고,
릴리스 시점에만 `release/*`를 통해 `main`으로 승격시키는 구조입니다.

기존 규칙은 그대로 유지됩니다:

- 커밋 메시지 규칙: `[#이슈번호] 타입: 내용`
- PR 리뷰 규칙: 최소 1인 승인

---

## 4. 브랜치 다이어그램

![Git Flow 브랜치 전략](assets/git_flow_strategy.png)

---

## 5. 워크플로우

### 5.1 일반 기능 개발

```bash
git checkout develop
git pull origin develop
git checkout -b feat/기능명

# 작업 후
git commit -m "feat: [KEY-12] 기능 설명"
git push origin feat/기능명
# → develop 대상으로 PR 생성 → 리뷰 1인 승인 → merge
```

### 5.2 릴리스

```bash
git checkout -b release/v1.0.0 develop
# QA, 버그 픽스, 버전 표기 정리

# 완료 후
#  1) release/v1.0.0 → main PR (merge 후 태그 v1.0.0)
#  2) release/v1.0.0 → develop PR (릴리스 중 수정사항 역병합)
```

### 5.3 핫픽스

```bash
git checkout -b hotfix/버그명 main
# 긴급 수정

#  1) hotfix/* → main PR (merge 후 패치 태그)
#  2) hotfix/* → develop PR (동일 수정 반영)
```

---

## 6. GitHub 저장소 보호 규칙 권장사항

- `main` 브랜치 보호: 직접 push 금지, PR 필수, 승인 1인 이상
- `develop` 브랜치 보호: 직접 push 금지, PR 필수
- **default branch를 `develop`으로 변경** (PR 기본 타깃이 develop이 되도록)

---

## 7. GitHub Flow와 비교한 채택 이유

| 항목 | GitHub Flow | Git Flow (채택) |
|---|---|---|
| 브랜치 수 | main + 작업 브랜치 | main / develop / feat / release / hotfix |
| 릴리스 관리 | main merge = 즉시 배포 | release 브랜치에서 QA 후 승격 |
| 긴급 대응 | 별도 개념 없음 | hotfix 브랜치로 운영 이슈 분리 대응 |
| 적합한 상황 | CD 파이프라인이 갖춰진 소규모/상시 배포 | 릴리스 단위가 명확하고 QA 단계가 있는 팀 |

`main`을 항상 배포 가능한 상태로 유지하면서
통합 작업은 `develop`에서 진행하는 Git Flow가 더 적합하다고 판단했습니다.
