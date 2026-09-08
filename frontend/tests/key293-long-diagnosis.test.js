/* 긴 진단명이 테두리 밖으로 나가지 않는다 — KEY-293.
 *
 * S1-6 맨 위 「진단」 칸은 206px 인데 값칸이 `height: 34px` 로 **못 박혀** 있었다.
 * 「다낭성난소증후군(PCOS)」이 들어오면 글자는 세 줄로 벌어지는데 상자는 34px 에
 * 묶여, 첫 줄과 마지막 줄이 테두리 **밖**에 서고 위아래 라벨과 겹쳤다.
 *
 * 그린 모양은 브라우저에서 본다(PR 에 측정값을 적었다). 여기서 재는 것은
 * **규칙끼리 앞뒤가 맞는가**다 — 이 자리는 숫자 몇 개가 서로 기대고 있어서,
 * 하나만 고치면 조용히 다시 깨진다.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const { read, codeOnly, rule } = require("./source.js");

/* 주석을 걷고 읽는다 — `rule()` 은 첫 `}` 에서 자르는데, 이 파일의 주석에는
   설명하려고 적어 둔 중괄호가 들어 있다. */
const CSS = () => codeOnly(read("css/ocr-review.css"));

/** 같은 이름의 규칙이 여러 벌일 때 **전부** 준다 — `rule()` 은 첫 벌만 준다. */
function allRules(css, selector) {
  const out = [];
  const lines = css.split("\n");
  for (let i = 0; i < lines.length; i++) {
    if (lines[i].trim() !== selector + " {") continue;
    const open = css.indexOf("{", css.split("\n").slice(0, i).join("\n").length);
    out.push(css.slice(open, css.indexOf("}", open)));
  }
  assert.ok(out.length, `${selector} 규칙이 없다 — 검사가 헛돈다`);
  return out;
}

const px = (body, prop) => {
  const found = new RegExp(`(?:^|[;{\\s])${prop}:\\s*(\\d+)px`, "m").exec(body);
  assert.ok(found, `${prop} 를 못 읽었다`);
  return Number(found[1]);
};

test("맨 위 값칸의 높이를 못 박지 않는다 — 긴 진단명이 테두리를 넘던 자리", () => {
  const top = rule(CSS(), ".top .field__value");

  /* `height: 34px` 이 바로 그 버그였다. 최소값으로 남기고 자라게 둔다. */
  assert.doesNotMatch(top, /(?:^|[;{\s])height:\s*\d+px/m, "높이를 다시 못 박았다 — 긴 값이 테두리를 넘는다");
  assert.match(top, /min-height:\s*34px/, "짧은 값의 34px 모양이 사라졌다");
  assert.match(top, /height:\s*auto/, "내용에 맞춰 자라지 않는다");
});

test("**두 줄에서 멈추고, 잘렸다는 것이 보인다** — 인수조건 2·3", () => {
  const top = rule(CSS(), ".top .field__value");

  assert.match(top, /-webkit-line-clamp:\s*2/, "두 줄 제한이 없다 — 긴 약품명이 맨 위 줄을 밀어낸다");
  assert.match(top, /-webkit-box-orient:\s*vertical/, "줄 수 제한이 서려면 세로 상자여야 한다");
  assert.match(top, /overflow:\s*hidden/, "넘친 줄이 그대로 보인다 — 말줄임이 안 선다");

  /* 괄호 붙은 긴 낱말이 칸을 가로로 뚫지 않아야 한다. */
  assert.match(top, /overflow-wrap:\s*anywhere/, "긴 낱말이 칸을 가로로 뚫는다");
});

test("한 줄일 때 높이가 정확히 34px 로 떨어진다 — 짧은 진단명 모양이 안 바뀐다", () => {
  const css = CSS();
  const top = rule(css, ".top .field__value");
  const base = rule(css, ".field__value");

  const padding = /padding:\s*(\d+)px\s+(\d+)px/.exec(top);
  assert.ok(padding, "padding 을 못 읽었다");
  const vertical = Number(padding[1]) * 2;
  const line = px(top, "line-height");
  assert.match(base, /border:\s*1px/, "테두리 두께가 1px 이 아니다 — 아래 셈이 어긋난다");

  /* 이 셋이 `min-height` 와 맞아야 짧은 값의 칸 크기가 그대로다.
     하나만 고치면 조용히 어긋나므로 여기서 묶어 둔다. */
  assert.strictEqual(
    vertical + line + 2,
    px(top, "min-height"),
    `padding(${vertical}) + line-height(${line}) + 테두리(2) 가 min-height 와 안 맞는다`,
  );
});

test("**아래쪽 `flex: 0 0 68px` 에 다시 묶이지 않는다** — 값칸이 68px 이던 진짜 까닭", () => {
  const css = CSS();

  /* 파일 뒤쪽에 값칸을 68px 로 고정하는 규칙이 따로 있다. flex 항목에서는
     basis 가 width 를 이기므로, `width: 100%` 만으로는 안 풀린다 — 진단 칸이
     206px 인데 값칸만 68px 이라 글자가 세 줄로 벌어졌다. */
  const pinned = allRules(css, ".field__value").filter((body) => /flex:\s*0\s+0\s+68px/.test(body));
  assert.ok(pinned.length, "68px 고정 규칙이 사라졌다 — 아래 단언의 전제가 무너진다");

  const top = rule(css, ".top .field__value");
  assert.match(top, /flex:\s*1\s+1\s+auto/, "맨 위 값칸이 68px 에 묶인 채다 — 긴 진단명이 세 줄로 벌어진다");
});
