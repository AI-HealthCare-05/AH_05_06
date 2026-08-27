#!/bin/bash
set -eo pipefail

# 합성 EMR 을 **누가 돌려도 같은 바이트로** 그린다 — KEY-190.
#
# `make_ocr_fixture.py` 가 내는 SVG 는 결정적이지만, 그것을 그림으로 바꾸는
# 순간 기계마다 달라진다. 글꼴 스택이
#
#     AppleSDGothicNeo, AppleGothic, NanumGothic, sans-serif
#
# 라서 맥에서는 애플 글꼴로, 리눅스에서는 다른 것으로 떨어진다. 픽셀이 달라지면
# **판독 결과도 달라져서** 「같은 입력으로 재현」이 성립하지 않는다.
#
# 그래서 그리는 환경을 컨테이너에 가둔다. 아래 세 줄이 고정하는 것이 전부다.
#
#     알파인 3.20 · rsvg-convert 2.58.5-r0 · font-noto-cjk 0_git20220127-r1
#
# 산출물은 **커밋하지 않는다.** 보관 위치가 아직 안 정해졌다
# (`docs/ocr-fixtures.md` 5절 · `KEY-163` §8).

BASE_IMAGE="alpine:3.20"
RSVG_VERSION="2.58.5-r0"
FONT_VERSION="0_git20220127-r1"
RENDER_TAG="ah-ocr-render:key190"
DPI=150

out_dir="${1:-build/ocr-fixtures}"
mkdir -p "$out_dir"

echo "① 합성 EMR 을 만든다 (SVG · 기대값)"
uv run python scripts/make_ocr_fixture.py --out "$out_dir" >/dev/null

echo "② 그리는 환경을 세운다"
docker build -q -t "$RENDER_TAG" - <<DOCKER >/dev/null
FROM ${BASE_IMAGE}
RUN apk add --no-cache rsvg-convert=${RSVG_VERSION} font-noto-cjk=${FONT_VERSION}
DOCKER

echo "③ 그린다"
for fmt in png pdf; do
  args=""
  [[ "$fmt" == "png" ]] && args="--dpi-x=${DPI} --dpi-y=${DPI}"
  docker run --rm -v "$(cd "$out_dir" && pwd)":/w "$RENDER_TAG" \
    rsvg-convert $args -f "$fmt" -o "/w/SYN-EMS-01.emr.v1.${fmt}" /w/SYN-EMS-01.emr.v1.svg
done

echo ""
echo "④ sha256 — 문서의 값과 같아야 한다"
for f in "$out_dir"/SYN-EMS-01.emr.v1.{png,pdf}; do
  printf '  %-28s %s\n' "$(basename "$f")" "$(shasum -a 256 "$f" | cut -d' ' -f1)"
done
echo ""
echo "값이 다르면 정본 CSV 가 바뀐 것이다 — docs/ocr-fixtures.md 를 함께 고친다."
