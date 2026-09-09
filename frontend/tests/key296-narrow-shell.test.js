/* 좁은 창에서 두 칸을 위아래로 쌓는다 — KEY-296.
 *
 * `.list` 가 `flex: 0 0 320px` 로 안 줄어드니, 창이 320px 이면 목록이 창을
 * 통째로 먹고 작업판은 48px 만 남아 창 **밖으로** 밀려 났다. 그 안의 탭 줄은
 * 405px 로 서서 751px 까지 뻗었다.
 *
 * shim 은 그리지 않는다 — 폭·줄바꿈은 원문으로 잴 수 없다. 그래서 여기서는
 * **규칙이 제자리에 있는지**만 지킨다. 실제 치수는 브라우저로 쟀고 결과는
 * 커밋 메시지와 PR 에 적었다:
 *
 *   320 · 375 · 768 · 900 → 세로로 쌓임, `scrollWidth = 창폭`, 넘치는 것 없음
 *   901 · 1024 · 1280     → 두 칸 그대로(목록 320px), 넘치는 것 없음
 */
const { test } = require("node:test");
const assert = require("node:assert");
const { read, codeOnly } = require("./source.js");

/** `@media (...)` 한 덩이의 속. 중괄호를 세어 짝을 찾는다 — 안에 규칙이 여럿
    있어 `indexOf("}")` 로는 첫 규칙에서 잘린다. */
function mediaBlock(css, condition) {
  const at = css.indexOf("@media " + condition);
  assert.notStrictEqual(at, -1, `@media ${condition} 가 없다 — 검사가 헛돈다`);
  const open = css.indexOf("{", at);
  let depth = 0;
  for (let i = open; i < css.length; i++) {
    if (css[i] === "{") depth += 1;
    else if (css[i] === "}") {
      depth -= 1;
      if (depth === 0) return css.slice(open + 1, i);
    }
  }
  throw new Error(`@media ${condition} 가 안 닫혔다`);
}

/** 그 덩이 안의 선택자 하나. */
function ruleIn(block, selector) {
  const lines = block.split("\n");
  for (let i = 0; i < lines.length; i++) {
    if (lines[i].trim() !== selector + " {" && lines[i].trim() !== selector + ",") continue;
    let j = i;
    while (j < lines.length && !lines[j].includes("{")) j += 1;
    const open = block.indexOf("{", lines.slice(0, j).join("\n").length);
    return block.slice(open + 1, block.indexOf("}", open));
  }
  throw new Error(`${selector} 가 그 @media 안에 없다`);
}

const shell = () => codeOnly(read("css/shell.css"));
const blocks = () => codeOnly(read("css/blocks.css"));

test("좁은 창에서는 목록과 작업판이 위아래로 쌓인다", () => {
  const narrow = mediaBlock(shell(), "(max-width: 900px)");

  assert.match(ruleIn(narrow, ".main"), /flex-direction:\s*column/, "옆으로 세우면 320px 에 두 칸이 못 든다");

  const list = ruleIn(narrow, ".list");
  assert.match(list, /width:\s*100%/, "눕고 나면 폭은 창이 정한다");
  assert.match(list, /flex:\s*0 0 auto/, "`0 0 320px` 가 남으면 세로로 쌓여도 320px 로 버틴다");
  assert.match(list, /min-width:\s*0/, "flex 항목의 `min-width: auto` 가 안에 든 것만큼 버틴다");
  assert.match(list, /max-height:/, "높이를 안 막으면 작업판이 첫 화면에서 사라진다");
  assert.match(list, /min-height:\s*0/, "`min-height: auto` 가 `max-height` 를 밀어낸다");
  assert.match(list, /border-bottom:/, "경계도 아래로 돈다 — 오른쪽 줄은 옆에 설 때의 것이다");
});

test("접기는 넓은 창에만 있다 — 눕힌 목록을 비우지 않는다", () => {
  const css = shell();
  const wide = mediaBlock(css, "(min-width: 901px)");

  /* 접힘은 `sessionStorage` 에 남는다(`js/list-fold.js`). 폭으로 안 가르면
     넓은 창에서 접어 둔 채 좁히기만 해도 목록 자리에 빈 띠가 남는다. */
  assert.match(wide, /\.list--folded/, "접힘 규칙이 넓은 창 덩이 밖에 있다");

  const outside = css.split("@media")[0];
  assert.doesNotMatch(outside, /\.list--folded/, "접힘 규칙이 폭과 무관하게 걸려 있다");

  /* 감춘 것을 되돌리는 길이 없다는 것이 이 구조의 까닭이다 */
  const narrow = mediaBlock(css, "(max-width: 900px)");
  assert.doesNotMatch(narrow, /display:\s*revert/, "`revert` 는 브라우저 기본값으로 돌아가 「+ 환자 등록」이 깨진다");
});

test("두 폭이 맞물린다 — 어느 폭에서도 규칙이 비지 않는다", () => {
  const css = shell();
  const max = /@media \(max-width: (\d+)px\)/.exec(css);
  const min = /@media \(min-width: (\d+)px\)/.exec(css);

  assert.ok(max && min, "두 덩이가 다 있어야 한다");
  assert.strictEqual(
    Number(min[1]) - Number(max[1]),
    1,
    `${max[1]} 과 ${min[1]} 사이가 벌어졌다 — 그 폭에서 접기도 눕기도 안 걸린다`,
  );
});

test("판의 좌우 여백은 한 곳에서만 정한다", () => {
  const css = shell();
  const pane = /\.pane \{([\s\S]*?)\}/.exec(css)[1];

  assert.match(pane, /--pane-pad-x:\s*24px/, "판이 여백을 내놓지 않으면 걸치는 것이 숫자를 베낀다");
  assert.match(pane, /--pane-pad-y:\s*18px/);
  assert.match(pane, /padding:\s*var\(--pane-pad-y\) var\(--pane-pad-x\)/);

  /* 좁은 창에서는 값만 바꾼다 — `padding` 을 새로 적으면 되미는 쪽이 안 따라온다 */
  const narrow = mediaBlock(css, "(max-width: 900px)");
  const narrowPane = ruleIn(narrow, ".pane");
  assert.match(narrowPane, /--pane-pad-x:\s*12px/);
  assert.doesNotMatch(narrowPane, /^\s*padding:/m, "여백을 다시 적으면 걸치는 것이 12px 씩 삐져나간다");

  /* 걸치는 머리말이 그 값을 쓴다 */
  const head = /\.patient-head \{([\s\S]*?)\n\}/.exec(blocks())[1];
  assert.match(head, /margin:\s*calc\(-1 \* var\(--pane-pad-y, 18px\)\) calc\(-1 \* var\(--pane-pad-x, 24px\)\)/);
  assert.match(head, /top:\s*calc\(-1 \* var\(--pane-pad-y, 18px\)\)/);
  assert.doesNotMatch(head, /margin:\s*-18px -24px/, "숫자를 베끼면 좁은 창에서 다시 어긋난다");
});

test("좁은 창에서는 탭 줄이 줄어들어 접힌다", () => {
  const narrow = mediaBlock(blocks(), "(max-width: 900px)");
  const tabs = ruleIn(narrow, ".tabs");

  /* `flex: none` 이면 접을 폭을 안 받아 `flex-wrap` 이 있어도 안 접힌다 */
  assert.match(tabs, /flex:\s*1 1 auto/, "줄어들 수 없으면 405px 로 서서 판을 넘는다");
  assert.match(tabs, /min-width:\s*0/);

  const wide = /\.tabs \{([\s\S]*?)\}/.exec(blocks())[1];
  assert.match(wide, /flex:\s*none/, "넓은 창에서 줄어들게 두면 머리말이 길 때 탭이 먼저 눌린다");
  assert.match(wide, /flex-wrap:\s*wrap/);
});

test("좁은 창의 상단바는 길을 남기고 이름표를 접는다", () => {
  const narrow = mediaBlock(shell(), "(max-width: 900px)");

  /* 320px 에 브랜드·의원 이름·탭 셋·이름·역할·아이콘 둘은 함께 못 선다(실측 456px) */
  assert.match(narrow, /\.topbar__clinic,\s*\n\s*\.who \{\s*\n\s*display: none;/, "의원 이름과 이름표를 접지 않으면 상단바가 창을 넘는다");
  assert.doesNotMatch(narrow, /\.topbar__nav[\s\S]{0,80}display:\s*none/, "탭 셋은 남긴다 — 눌러야 갈 수 있다");
  assert.doesNotMatch(narrow, /\.icon-button[\s\S]{0,80}display:\s*none/, "알림·로그아웃은 남긴다");

  const brand = ruleIn(narrow, ".topbar__brand");
  assert.match(brand, /flex:\s*0 1 auto/, "`1 1 0` 이라도 `nowrap` 이라 최소 폭만큼 버틴다");
  assert.match(brand, /text-overflow:\s*ellipsis/);
});
