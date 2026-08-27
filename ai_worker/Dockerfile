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

# 3. **워커가 실제로 쓰는 것만 깐다** (KEY-198).
#
#    처음에는 주석이 「app 그룹만」인데 명령은 `--group ai` 였다 — 어긋난 채로
#    병합돼서 `tortoise` 가 안 깔렸고 **컨테이너가 임포트에서 죽었다**(KEY-197).
#    KEY-56(`9d26e45`)이 `main.py` 에 그 임포트를 넣으면서 여기를 안 늘렸고,
#    CI 가 이 이미지를 굽지 않아 병합 뒤에도 안 드러났다.
#
#    고칠 때 `--group app` 을 통째로 붙였는데, 그러면 워커가 안 쓰는 것까지
#    들어온다. `ai_worker.main` 임포트 그래프를 실제로 재서 `worker` 그룹을
#    따로 만들었다 (`pyproject.toml` 의 그 그룹 주석에 뺀 이유가 적혀 있다).
#
#    `aerich` 가 빠지는 것이 특히 중요하다 — 워커는 이미 DB 크리덴셜을 쥐고
#    있어서, 스키마를 갈아엎는 `aerich upgrade`·`downgrade` 까지 같은 이미지에
#    두면 한 번 뚫렸을 때 번지는 범위가 커진다.
RUN uv sync --group worker --group ai --no-dev --frozen

# 4. 로컬 소스 코드를 컨테이너 내부로 복사합니다.
# ai_worker는 app.* 를 직접 임포트하므로 두 패키지를 모두 복사한다.
COPY ./app ./app
COPY ./ai_worker ./ai_worker

# 5. Worker 진입점을 실행합니다 (KEY-56).
CMD ["uv", "run", "--no-sync", "python", "-m", "ai_worker.main"]
