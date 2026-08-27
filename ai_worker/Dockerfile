FROM python:3.13-slim

WORKDIR /app

# **빌드 도구를 먼저 깐다** — `app/Dockerfile` 과 같다.
# `app` 그룹의 `asyncmy` 는 arm64 에 미리 만든 휠이 없어 소스에서 빌드된다.
# 이것이 없으면 `uv sync` 가 거기서 죽는다 (KEY-197).
RUN apt-get update && apt-get install -y \
    build-essential \
    python3-dev \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# 1. uv 설치 (공식 이미지에서 복사해오는 가장 깔끔한 방법)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# 2. 의존성 패키지 관리 파일을 컨테이너 내부에 복사합니다.
COPY pyproject.toml uv.lock ./

# 3. **두 그룹을 다 깐다.** 주석은 처음부터 「app 그룹만」이라고 적혀 있었는데
#    명령은 `--group ai` 였다 — 주석과 명령이 어긋난 채로 병합됐다 (KEY-197).
#
#    `ai_worker/main.py` 는 `tortoise` 와 `app.core.*` 를 임포트한다.
#    `tortoise-orm` 은 `app` 그룹(`pyproject.toml`)이라 `ai` 만 깔면
#    **컨테이너가 임포트에서 죽는다** — CLOVA 키가 있어도 판독이 못 돈다.
#
#    KEY-56(`9d26e45`)이 `main.py` 에 그 임포트를 넣으면서 여기를 안 늘렸고,
#    CI 가 이 이미지를 굽지 않아 병합 뒤에도 안 드러났다. 배포하려고 처음
#    구우면서 나왔다.
RUN uv sync --group app --group ai --no-dev --frozen

# 4. 로컬 소스 코드를 컨테이너 내부로 복사합니다.
# ai_worker는 app.* 를 직접 임포트하므로 두 패키지를 모두 복사한다.
COPY ./app ./app
COPY ./ai_worker ./ai_worker

# 5. Worker 진입점을 실행합니다 (KEY-56).
CMD ["uv", "run", "--no-sync", "python", "-m", "ai_worker.main"]
