/* **공통 골격** — 상단바 가운데 탭과 좌측 목록 접기.
 *
 * 와이어프레임의 의료진·어드민 프레임이 픽셀까지 같은 골격을 쓴다
 * (어드민 묶음 주석: 「7프레임 전부 픽셀까지 동일」).
 *
 *     상단바 56px   로고 + 브랜드 / **가운데 탭** / 오른쪽 계정 · 🔔 · ⏻
 *     좌 320px      제목줄 + `◀` 접기 단추(28px) → 목록 → 하단 안내
 *     접힌 상태     48px 레일 (`S1-7` 「좌측 48px 접힌 레일」)
 *
 * 접힘은 **직접 접은 것만 기억한다.** 판독 화면(`S1-6`)에 들어가면 원문을 넓게
 * 보려고 저절로 접히는데, 그것까지 기억하면 다음에 환자 목록을 열었을 때 까닭
 * 없이 접혀 있다 — 사람은 자기가 접은 기억이 없으니 고장으로 읽는다.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const { load } = require("./browser-shim.js");
const { markupOnly, codeOnly } = require("./source.js");

const ROOT = path.join(__dirname, "..");
const SHELL_PAGES = ["patients.html", "ocr-review.html", "doctor.html", "admin.html"];

/* CSS 규칙 하나를 정확히 집는다.
 *
 *   · `.list__head {` 로 찾으면 `.list--folded .list__head {` 를 먼저 물어
 *     엉뚱한 블록을 잰다 — 그래서 **줄 처음**에 오는 것만 본다.
 *   · 묶음 선택자(`A,\nB {`)도 찾는다. `.button-primary--sm` 뒤에 ` {` 가
 *     아니라 `,` 가 와서 「규칙이 없다」로 떨어진 적이 있다. */
function rule(css, selector) {
  const lines = css.split("\n");
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    if (line !== selector + " {" && line !== selector + ",") continue;

    /* 묶음이면 `{` 가 나오는 줄까지 내려간다 */
    let j = i;
    while (j < lines.length && !lines[j].includes("{")) j += 1;

    const open = css.indexOf("{", css.split("\n").slice(0, j).join("\n").length);
    return css.slice(open, css.indexOf("}", open));
  }
  assert.fail(`${selector} 규칙이 없다 — 검사가 헛돈다`);
}

function read(rel) {
  return fs.readFileSync(path.join(ROOT, rel), "utf8");
}

/* ── 접히는 규칙 ──────────────────────────────────────────────────────── */

test("**직접 접은 것과 화면이 접은 것을 가른다**", () => {
  const { listShouldFold } = load("list-fold");

  assert.strictEqual(listShouldFold(true, false), true, "사람이 접었으면 접힌다");
  assert.strictEqual(listShouldFold(false, true), true, "판독 화면은 저절로 접힌다");
  assert.strictEqual(listShouldFold(true, true), true);
  assert.strictEqual(listShouldFold(false, false), false, "아무도 안 접었는데 접혀 있다");
});

test("기억이 없거나 이상해도 펴진 채로 시작한다", () => {
  const { listShouldFold } = load("list-fold");
  /* 저장소가 막힌 창에서는 기억을 못 읽는다. 그때 접힌 채로 시작하면
     사람은 목록이 사라진 화면을 만난다. */
  assert.strictEqual(listShouldFold(undefined, undefined), false);
  assert.strictEqual(listShouldFold(null, false), false);
  assert.strictEqual(listShouldFold("1", false), false, "문자열 참에 속지 않는다");
});

/* ── 네 화면이 같은 골격을 쓰는가 ─────────────────────────────────────── */

test("**의료진·어드민 화면 넷에 접기 단추가 다 있다** — 공통 골격이다", () => {
  for (const page of SHELL_PAGES) {
    const html = read(page);
    assert.ok(html.includes('class="list__fold"'), `${page} 에 접기 단추가 없다`);
    assert.ok(html.includes('class="list__label"'), `${page} 에 목록 제목이 없다`);
    assert.ok(html.includes("/js/list-fold.js"), `${page} 가 접기 규칙을 안 싣는다`);
  }
});

test("**어느 화면도 저절로 접지 않는다** — 목록이 사라지면 다음 환자로 가는 길을 잃는다", () => {
  /* 와이어프레임 S1-7 은 판독 화면을 「좌측 48px 접힌 레일」로 그렸다. 그대로
     넣어 봤더니 화면을 옮길 때마다 목록이 사라져, 다음 환자를 고르려면 매번
     다시 펴야 했다. 접고 싶으면 `◀` 로 접는다 — 그 선택은 기억된다. */
  for (const page of SHELL_PAGES) {
    assert.ok(
      !read(page).includes("shell--fold-list"),
      `${page} 가 까닭 없이 접힌 채로 열린다`,
    );
  }
});

/* ── 상단바 ───────────────────────────────────────────────────────────── */

test("**상단바 탭이 가운데다** — 양옆이 같은 폭을 가져야 가운데가 가운데다", () => {
  const css = read("css/shell.css");

  /* 브랜드와 오른쪽 칸이 같은 `flex` 를 가져야 한다. 한쪽만 늘어나면
     탭이 한쪽으로 밀린다 — 와이어프레임은 가운데로 그렸다. */
  const brand = rule(css, ".topbar__brand");
  const right = rule(css, ".topbar__right");

  assert.match(brand, /flex:\s*1 1 0/, "브랜드 칸이 안 늘어난다 — 탭이 왼쪽에 붙는다");
  assert.match(right, /flex:\s*1 1 0/, "오른쪽 칸이 안 늘어난다 — 탭이 오른쪽으로 밀린다");
});

test("접힌 레일이 48px 다 — 와이어프레임 S1-7 이 그린 폭", () => {
  const css = read("css/shell.css");
  const folded = rule(css, ".list--folded");
  assert.match(folded, /flex-basis:\s*48px/, "접힌 폭이 48px 가 아니다");
});

test("접히면 목록·검색·안내가 숨는다 — 폭이 없으면 글자가 깨진다", () => {
  const css = read("css/shell.css");
  const hide = css.slice(css.indexOf(".list--folded .list__search"));
  for (const cls of ["list__search", "list__rows", "list__note", "list__label"]) {
    assert.ok(hide.slice(0, 400).includes(cls), `접혔을 때 ${cls} 를 안 숨긴다`);
  }
});

/* ── 접기 단추가 무슨 말을 하는가 ─────────────────────────────────────── */

/* 아래 둘은 `applyFold` 를 **직접 부른다.** 원문에서 `byHand` 라는 글자를 찾는
   식으로 재면, 인자 이름이 남아 있는 한 무엇을 지워도 통과한다(돌연변이로
   확인했다). 화면 요소와 저장소를 흉내 내면 동작 자체를 잴 수 있다. */
function foldBox(options) {
  const list = {
    classes: new Set(),
    classList: {
      toggle(name, on) {
        if (on) list.classes.add(name);
        else list.classes.delete(name);
      },
      contains: (name) => list.classes.has(name),
    },
  };
  const button = { attrs: {}, textContent: "", setAttribute(k, v) { button.attrs[k] = v; } };
  const store = { value: null, throws: (options || {}).throws === true };

  const context = {
    console,
    document: {
      querySelector: (sel) => (sel === ".list" ? list : sel === ".list__fold" ? button : null),
    },
    sessionStorage: {
      getItem() {
        if (store.throws) throw new Error("사생활 보호 창");
        return store.value;
      },
      setItem(k, v) {
        if (store.throws) throw new Error("사생활 보호 창");
        store.value = v;
      },
      removeItem() {
        if (store.throws) throw new Error("사생활 보호 창");
        store.value = null;
      },
    },
  };
  require("node:vm").createContext(context);
  require("node:vm").runInContext(read("js/list-fold.js"), context);
  return { context, list, button, store };
}

test("단추가 지금 상태를 말한다 — 화면낭독기가 읽을 수 있어야 한다", () => {
  const { context, button } = foldBox();

  context.applyFold(true, false);
  assert.strictEqual(button.attrs["aria-expanded"], "false", "접혔는데 펴졌다고 알린다");
  assert.strictEqual(button.textContent, "▶", "접혔는데 화살표가 그대로다");

  context.applyFold(false, false);
  assert.strictEqual(button.attrs["aria-expanded"], "true");
  assert.strictEqual(button.textContent, "◀");
});

test("**저절로 접힌 것은 기억하지 않는다** — 다음에 열었을 때 까닭 없이 접혀 있다", () => {
  const byScreen = foldBox();
  byScreen.context.applyFold(true, false); // 판독 화면이 접었다
  assert.strictEqual(byScreen.store.value, null, "화면이 접은 것을 기억했다");

  const byHand = foldBox();
  byHand.context.applyFold(true, true); // 사람이 접었다
  assert.strictEqual(byHand.store.value, "1", "사람이 접은 것을 안 기억한다");

  byHand.context.applyFold(false, true); // 사람이 폈다
  assert.strictEqual(byHand.store.value, null, "편 것을 안 지운다");
});

test("저장소가 막혀도 죽지 않는다 — 사생활 보호 창에서 던진다", () => {
  const { context, list } = foldBox({ throws: true });

  assert.doesNotThrow(() => context.foldMemory(), "기억을 읽다 죽는다");
  assert.strictEqual(context.foldMemory(), false, "못 읽었으면 펴진 것으로 본다");
  assert.doesNotThrow(() => context.applyFold(true, true), "기억을 적다 죽는다");
  assert.ok(list.classes.has("list--folded"), "기억은 못 해도 화면은 접혀야 한다");
});

/* ── 와이어프레임 치수 ─────────────────────────────────────────────────── */

test("**좌측 머리가 세로로 쌓인다** — 가로로 두면 줄바꿈이 나서 흩어진다", () => {
  const css = read("css/shell.css");
  const head = rule(css, ".list__head");

  assert.match(head, /flex-direction:\s*column/, "머리가 가로다 — 검색·등록이 제목줄 옆으로 밀린다");
  assert.match(head, /padding:\s*14px 14px 12px/, "와이어프레임 여백과 다르다");
});

test("제목줄에서 라벨이 늘어나고 단추가 오른쪽 끝에 선다", () => {
  const css = read("css/shell.css");
  const title = rule(css, ".list__title");
  const label = rule(css, ".list__label");

  assert.match(title, /display:\s*flex/, "제목줄이 가로가 아니다");
  assert.match(label, /flex:\s*1/, "라벨이 안 늘어난다 — 단추가 라벨에 붙는다");
  assert.match(label, /font-size:\s*16px/, "와이어프레임 원문은 16px 다");
});

test("접기 단추가 28×28 이다 — 와이어프레임 원문", () => {
  const css = read("css/shell.css");
  const fold = rule(css, ".list__fold");
  assert.match(fold, /width:\s*28px/);
  assert.match(fold, /height:\s*28px/);
});

test("**[+ 환자 등록]이 전체 폭이고 테두리가 2px 다** — 좌측 칸의 유일한 주 진입", () => {
  /* 어휘는 `shell.css` 에 있다 — 목록 레일은 화면마다 같아야 하는데, 판독
     화면은 `patients.css` 를 싣지 않아 거기 두면 모양 없이 떴다. */
  const add = rule(read("css/shell.css"), ".list__add");

  assert.match(add, /width:\s*100%/, "폭이 없으면 글자만큼 줄어 잘린 것처럼 보인다");
  assert.match(add, /border:\s*2px/, "주 진입인데 테두리가 얇다 — 어드민 [+ 직원 추가]도 2px 다");

  /* 판독 화면에서는 `<a>` 라 글자가 왼쪽으로 붙고 밑줄이 그어진다 */
  assert.match(add, /text-align:\s*center/, "링크로 그리면 글자가 왼쪽에 붙는다");
  assert.match(add, /text-decoration:\s*none/, "링크에 밑줄이 그어진다");
});

test("**목록 레일이 화면마다 같다** — 등록 버튼이 사라지면 「없어졌다」로 읽힌다", () => {
  /* 「진료기록」 칸이 판독 화면이 된 뒤로, 그 화면에 오면 등록 버튼이 없었다.
     등록 폼은 환자 화면에만 두고(두 벌이면 갈린다) 버튼은 그리로 보낸다. */
  for (const page of ["patients.html", "ocr-review.html"]) {
    const html = markupOnly(read(page));
    assert.match(html, /class="list__add"/, `${page} 목록에 등록 버튼이 없다`);
  }

  const review = markupOnly(read("ocr-review.html"));
  assert.match(review, /href="\/patients\.html\?add=1"/, "판독 화면 버튼이 갈 곳이 없다");

  /* 받는 쪽이 그 주소를 알아야 한다 */
  const code = codeOnly(read("js/patients.js"));
  assert.match(code, /add=1/, "환자 화면이 그 주소를 모른다 — 눌러도 등록 화면이 안 열린다");
  const at = code.indexOf("add=1");
  const around = code.slice(at, at + 300);
  assert.match(around, /open\(/, "등록 화면을 안 연다");
  assert.match(around, /replaceState/, "주소가 남는다 — 새로고침할 때마다 등록 화면이 뜬다");
});

test("**높이는 토큰을 따른다** — 와이어프레임 34px 보다 접근성이 우선이다", () => {
  /* 와이어프레임 원문은 34px 인데 tokens.css 가 44px 로 두었다 —
     「손가락과 초점이 닿는 최소 크기」. WCAG 2.5.5 최소 터치 영역이라
     와이어프레임 치수로 되돌리면 퇴보다. 이 선택을 검사로 남긴다. */
  const tokens = read("css/tokens.css");
  assert.match(tokens, /--field-h:\s*44px/, "터치 영역이 44px 아래로 내려갔다");

  const add = rule(read("css/shell.css"), ".list__add");
  assert.match(add, /height:\s*var\(--field-h\)/, "높이를 토큰이 아니라 숫자로 박았다");
});

/* ── 환자 등록 (S1-2) ─────────────────────────────────────────────────── */

test("**왼쪽에 쓰는 것, 오른쪽에 확인하는 것** — 다 채운 뒤 스크롤해 내려가지 않는다", () => {
  const html = markupOnly(read("patients.html"));
  const css = read("css/patients.css");

  /* ①로 찾고 ②를 채우는 것은 한 줄기 일이라 위아래로 잇고, 「등록 전 확인」은
     그 결과를 훑는 자리라 옆에 세운다 — 채우면서 오른쪽이 같이 차는 것이 보인다. */
  assert.ok(html.includes('class="reg__cols"'), "두 칸을 감싸는 자리가 없다");

  const cols = rule(css, ".reg__cols");
  assert.match(cols, /display:\s*flex/, "2단이 아니다");
  assert.match(cols, /gap:\s*26px/, "와이어프레임 간격과 다르다");

  const col = rule(css, ".reg__col");
  assert.match(col, /flex:\s*3/, "왼쪽이 안 늘어난다");
  assert.match(col, /min-width:\s*0/, "긴 내용이 칸을 밀어낸다");
  assert.match(col, /flex-direction:\s*column/, "①② 가 위아래로 안 선다");

  /* ①②는 왼쪽 칸 **안**에, 확인은 오른쪽 칸 안에 */
  const left = element(html, '<div class="reg__col">');
  assert.ok(left.includes("① 환자 찾기"), "① 이 왼쪽에 없다");
  assert.ok(left.includes("② 환자 정보"), "② 가 왼쪽에 없다");
  assert.ok(!left.includes("등록 전 확인"), "확인이 왼쪽에 딸려 들어갔다");

  const side = element(html, '<div class="reg__col reg__col--side">');
  assert.ok(side.includes("등록 전 확인"), "확인이 오른쪽에 없다");
  assert.ok(side.includes('id="recap"'), "확인 내용이 오른쪽에 없다");
});

/* 여는 태그부터 **짝이 맞는 닫는 태그**까지를 돌려준다.
   `indexOf` 로 구간을 자르면 닫는 태그가 어디 있든 같은 문자열이 나와,
   칸을 일찍 닫거나 다른 칸으로 옮겨도 검사가 통과한다(돌연변이로 확인했다). */
function element(html, opener) {
  const tag = /^<([a-z]+)/.exec(opener);
  assert.ok(tag, `여는 태그를 못 읽었다: ${opener}`);
  const open = `<${tag[1]}`;
  const close = `</${tag[1]}>`;

  const start = html.indexOf(opener);
  assert.notEqual(start, -1, `${opener} 가 없다 — 검사가 헛돈다`);

  let depth = 0;
  let at = start;
  while (at < html.length) {
    if (html.startsWith(open, at)) depth++;
    else if (html.startsWith(close, at)) {
      depth--;
      if (depth === 0) return html.slice(start, at + close.length);
    }
    at++;
  }
  assert.fail(`${opener} 가 안 닫힌다`);
}

test("①과 ②가 그 안에 다 들어 있다 — 하나만 감싸면 2단이 안 된다", () => {
  const inside = element(read("patients.html"), '<div class="reg__cols">');

  assert.ok(inside.includes("① 환자 찾기"), "①이 2단 밖에 있다");
  assert.ok(inside.includes("② 환자 정보"), "②가 2단 밖에 있다 — 칸을 일찍 닫았다");
});

test("**자리가 없으면 알아서 세로로 돌아간다** — 창 폭으로 자르지 않는다", () => {
  /* 화면 크기로 자르면 숫자를 하나 정해야 하는데, 좌측 목록이 접히거나 펴지면
     본문 폭이 달라져 같은 창에서도 답이 바뀐다. `flex-wrap` + `flex-basis` 면
     자리가 없을 때만 접힌다. */
  for (const [file, sel] of [["css/patients.css", ".reg__cols"], ["css/blocks.css", ".cols2"]]) {
    const box = rule(read(file), sel);
    assert.match(box, /flex-wrap:\s*wrap/, `${sel} 이 접히지 못한다 — 칸이 찌그러진다`);
  }
  for (const [file, sel, basis] of [
    ["css/patients.css", ".reg__col", "420px"],
    ["css/patients.css", ".reg__col--side", "300px"],
    ["css/blocks.css", ".cols2__side", "340px"],
  ]) {
    const side = rule(read(file), sel);
    assert.match(side, new RegExp(`flex:\\s*\\d+ 1 ${basis}`), `${sel} 에 최소 폭이 없다 — 접힐 때를 모른다`);
  }
});

test("**상태 칩이 한 줄에 들어갈 크기다** — 두 줄이면 목록이 그만큼 짧아진다", () => {
  /* 다섯이 320px 안에 서야 한다. WCAG 2.2 의 최소 목표 크기(2.5.8)는 24px 이라
     26px 은 그 위다. 44px(2.5.5 AAA)은 이 폭에서 못 쓴다 — 셋 다 만족하는 값이
     없어서, 「닿을 수 있는 최소」와 「한 줄」 둘을 고른 것이다. */
  const chip = rule(read("css/shell.css"), ".chip");

  const height = /height:\s*(\d+)px/.exec(chip);
  assert.ok(height, "칩 높이가 없다 — 검사가 헛돈다");
  assert.ok(Number(height[1]) >= 24, `목표 크기가 24px 아래다: ${height[1]}px (WCAG 2.5.8)`);
  assert.ok(Number(height[1]) <= 28, `칩이 커서 다섯이 한 줄에 안 선다: ${height[1]}px`);

  assert.match(chip, /white-space:\s*nowrap/, "칩 안에서 글자가 접히면 높이가 들쭉날쭉해진다");
});

test("**등록 폼의 라벨이 입력 왼쪽에 붙는다** — 위에 두면 여덟 칸이 한 화면에 안 들어온다", () => {
  const html = read("patients.html");
  const css = read("css/patients.css");

  /* 와이어프레임 S1-2·S1-3 의 ② 칸: 행은 `flex · gap:14px`,
     라벨은 `width:78px · flex:none`, 입력은 `flex:1 · min-width:0`. */
  assert.ok(html.includes('class="fields"'), "폼 행을 묶는 자리가 없다");

  const rows = rule(css, ".fields");
  assert.match(rows, /flex-direction:\s*column/, "행이 세로로 안 쌓인다");

  const row = rule(css, ".fields .field");
  assert.match(row, /display:\s*flex/, "라벨이 입력 위에 있다");
  assert.match(row, /gap:\s*14px/, "와이어프레임 간격과 다르다");

  const label = rule(css, ".fields .field__label");
  assert.match(label, /width:\s*78px/, "라벨 폭이 와이어프레임과 다르다");
  assert.match(label, /flex:\s*none/, "라벨이 늘어나 입력을 밀어낸다");
});

test("도움말은 입력 옆이 아니라 아래에 온다 — 옆에 두면 입력이 절반으로 줄어든다", () => {
  const css = read("css/patients.css");

  const row = rule(css, ".fields .field");
  assert.match(row, /flex-wrap:\s*wrap/, "도움말이 줄바꿈을 못 해 입력 옆에 붙는다");

  const hint = rule(css, ".fields .field__hint");
  assert.match(hint, /width:\s*100%/, "도움말이 자기 줄을 안 갖는다");
  assert.match(hint, /margin:[^;]*92px/, "도움말이 입력과 세로선이 안 맞는다 (78 + 14)");
});

test("죽은 규칙을 남기지 않았다 — grid2 는 아무도 안 쓴다", () => {
  /* `grid2` 를 `fields` 로 바꾸면서 화면에서 사라졌다. CSS 에만 남으면
     다음 사람이 「이건 뭘 위한 규칙이지」를 확인하느라 시간을 쓴다. */
  const used = read("patients.html").includes("grid2");
  const defined = read("css/patients.css").includes("grid2");
  assert.strictEqual(used, false, "화면이 아직 grid2 를 쓴다");
  assert.strictEqual(defined, false, "쓰지 않는 grid2 규칙이 CSS 에 남아 있다");
});

/* ── 환자 카드 (S1-4) ─────────────────────────────────────────────────── */

test("**머리말과 탭이 한 줄이다** — 탭을 아래로 내리면 지난 방문이 잘린다", () => {
  const html = read("patients.html");

  /* 와이어프레임 S1-4: `padding:11px 26px · flex · align-items:center · gap:18px`.
     왼쪽에 누구인지, 오른쪽에 어디를 보는지. */
  const head = element(html, '<div class="patient-head">');
  assert.ok(head.includes('id="p-name"'), "머리말에 이름이 없다");
  assert.ok(head.includes('id="tabs"'), "탭이 머리말 밖에 있다 — 아래 줄을 차지한다");

  /* 머리말은  로 올렸다 — 전에는 `.patient-head` 가
     shell.css 에, `.patient-head__top` 이 detail.css 에 갈려 있어서
     판독 확인 화면에서 이름·차트·상태가 세 줄로 흩어졌다. */
  const css = rule(read("css/blocks.css"), ".patient-head");
  assert.match(css, /display:\s*flex/, "머리말이 가로가 아니다");
  assert.match(css, /gap:\s*18px/, "와이어프레임 간격과 다르다");

  /* **본문과 갈린다** — 흰 바탕에 아래 선 하나. 누구의 기록인지가 본문에
     묻히면 다른 환자에게 잘못 넣는다. */
  assert.match(css, /border-bottom:\s*1px/, "본문과 나누는 선이 없다");
  assert.match(css, /background:/, "머리말 바탕이 본문과 같다");

  /* 판 가장자리까지 펴야 한다 — 안 그러면 가운데만 뜬 띠가 된다.
     `.pane` 이 18px 24px 을 물고 있으므로 그만큼 되민다. */
  const pane = rule(read("css/shell.css"), ".pane");
  const pad = /padding:\s*(\d+)px\s+(\d+)px/.exec(pane);
  assert.ok(pad, ".pane 여백을 못 읽었다 — 검사가 헛돈다");
  assert.ok(
    css.includes("-" + pad[1] + "px -" + pad[2] + "px"),
    `머리말이 판 가장자리까지 안 펴진다 — .pane 이 ${pad[1]}px ${pad[2]}px 을 물고 있다`,
  );
});

test("**탭이 버튼 형식이다** — 고른 것만 채워진다", () => {
  /* 단계 줄은 `css/blocks.css` 로 올렸다 — 판독 확인 화면이 `detail.css` 를
     안 싣는 탓에 같은 단계 줄이 아무 모양 없이 떴다. */
  const css = read("css/blocks.css");

  const tab = rule(css, ".tab");
  assert.match(tab, /height:\s*30px/, "와이어프레임은 30px 다");
  assert.match(tab, /border-radius/, "테두리가 없으면 버튼으로 안 보인다");
  assert.match(tab, /border:\s*1px/, "테두리가 없다");

  const on = rule(css, '.tab[aria-selected="true"]');
  assert.match(on, /background:\s*var\(--accent\)/, "고른 탭이 안 채워진다");
  assert.match(on, /font-weight:\s*700/, "고른 탭이 안 굵어진다");
});

test("안 고른 탭 색은 와이어프레임을 안 따른다 — 대비가 1.6 이라 안 읽힌다", () => {
  /* 원문은 `#D1D5DB` 인데 흰 배경에서 대비가 1.6 이다. 토큰의 --ink-2(6.35)를
     쓰고, 「지금 여기가 아니다」는 채움과 굵기로 말한다 (KEY-106 과 같은 판단). */
  const tab = rule(read("css/blocks.css"), ".tab");
  assert.match(tab, /color:\s*var\(--ink-2\)/, "안 고른 탭이 읽히지 않는 색이다");
  assert.ok(!/#D1D5DB/i.test(tab), "와이어프레임 색을 그대로 옮겼다");
});

test("**본문이 좌우 2단이다** — 왼쪽은 오늘 손볼 것, 오른쪽은 참고할 것", () => {
  const html = read("patients.html");
  const basic = element(html, '<div class="cols2">');

  const left = basic.slice(0, basic.indexOf('cols2__side', basic.indexOf("cols2__side") + 1));
  const right = basic.slice(basic.indexOf('cols2__side', basic.indexOf("cols2__side") + 1));

  assert.ok(left.includes("환자 정보") && left.includes("오늘 진료"), "왼쪽 칸이 비었다");
  assert.ok(right.includes("지난 방문"), "지난 방문이 오른쪽에 없다");
  assert.ok(right.includes("발송 이력"), "발송 이력이 오른쪽에 없다");

  /* 블록 어휘는 `css/blocks.css` 로 올렸다 — 판독 확인 화면도 같은 상자를
     쓰는데 그 화면은 `detail.css` 를 안 싣기 때문이다 (WP-S③ 공용 모듈). */
  const css = rule(read("css/blocks.css"), ".cols2");
  assert.match(css, /display:\s*flex/, "2단이 아니다");
  assert.match(css, /gap:\s*26px/, "와이어프레임 간격과 다르다");
});

test("`tab--later` 가 상단바와 같은 파일에 있다 — 어드민은 detail.css 를 안 싣는다", () => {
  /* 옮기기 전에는 detail.css 에 있었고, 어드민 상단바의 「관리·설정」이
     스타일 없이 떴다. 상단바는 shell.css 것이다. */
  assert.ok(read("css/shell.css").includes(".tab--later"), "상단바 파일에 규칙이 없다");
  assert.ok(!read("css/detail.css").includes(".tab--later"), "규칙이 두 곳에 있다");
  assert.ok(read("admin.html").includes("shell.css"), "어드민이 상단바 파일을 안 싣는다");
});

test("**목록 줄의 상태가 이름과 같은 줄에 있다** — 셋째 줄로 내리면 하루치가 안 들어온다", () => {
  const { rowHtml } = load("api", "session", "patients-api", "shell");

  const html = rowHtml(
    {
      visit_id: 1,
      patient_id: 2,
      name: "서연수",
      hospital_patient_no: "123478",
      age: 43,
      diagnosis_name: "자궁내막증",
      doctor: { name: "박연 원장" },
      work_category: "IN_PROGRESS",
      detail_status: "NO_RECORD",
    },
    "false",
  );

  /* 와이어프레임 S1-4 의 줄은 두 줄이다 — 첫 줄 왼쪽에 이름·진단, 오른쪽 끝에
     상태. 스탭이 훑는 것은 이름과 상태 둘뿐이라 눈이 한 번만 움직여야 한다. */
  const top = element(html, '<span class="row__top">');
  assert.ok(top.includes("서연수"), "이름이 첫 줄에 없다");
  assert.ok(
    /row__state|state--/.test(top),
    "상태가 이름 줄 밖에 있다 — 아래로 내려갔거나 다른 칸에 들어갔다",
  );
  /* 첫 줄에 차트·나이·담당의까지 들어오면 줄이 넘쳐 이름이 밀린다.
     첫 줄은 이름 · 진단 · 상태 셋뿐이다. */
  assert.ok(!top.includes("row__meta"), "차트·나이까지 이름 줄로 올라왔다");

  assert.ok(!html.includes("<br>"), "줄바꿈으로 상태를 내린다 — 줄이 세 줄이 된다");
});

test("진단이 길면 진단이 줄고 상태는 안 밀린다", () => {
  const css = read("css/shell.css");

  const dx = rule(css, ".row__dx");
  assert.match(dx, /flex:\s*1/, "진단이 안 늘어나 상태가 가운데에 붙는다");
  assert.match(dx, /text-overflow:\s*ellipsis/, "긴 진단이 줄을 밀어낸다");

  const state = rule(css, ".row__state");
  assert.match(state, /flex:\s*none/, "상태가 찌그러진다 — 훑을 때 못 읽는다");
});

/* ── 상태 칩의 숫자 배지 ─────────────────────────────────────────────── */

test("**숫자가 칩 폭을 차지하지 않는다** — 라벨에 섞으면 숫자마다 줄바꿈이 오간다", () => {
  const css = read("css/shell.css");
  const badge = rule(css, ".chip__count");

  /* iOS 앱 아이콘의 알림 수처럼 오른쪽 위에 띄운다. 절대 위치라 칩이 넓어지지
     않는다 — 「작성 중 2」처럼 한 문자열로 두면 숫자가 바뀔 때마다 폭이 흔들려
     다섯째 칩이 다음 줄로 내려갔다 올라온다. */
  assert.match(badge, /position:\s*absolute/, "배지가 칩 폭을 넓힌다");
  assert.match(badge, /top:\s*-?\d/, "배지가 위로 안 올라간다");
  assert.match(badge, /right:\s*-?\d/, "배지가 오른쪽 끝에 안 붙는다");

  const chip = rule(css, ".chip");
  assert.match(chip, /position:\s*relative/, "배지가 칩이 아니라 화면 기준으로 뜬다");
});

test("배지가 잘리지 않게 위쪽에 자리가 있다", () => {
  const chips = rule(read("css/shell.css"), ".chips");
  const pad = /padding:\s*(\d+)px/.exec(chips);
  assert.ok(pad, "칩 줄 여백이 없다 — 검사가 헛돈다");
  assert.ok(Number(pad[1]) >= 10, `위 여백이 좁아 배지가 잘린다: ${pad[1]}px`);
});

test("**라벨에 숫자를 다시 섞지 않는다**", () => {
  const source = read("js/shell.js");
  const at = source.indexOf("function renderChipCounts");
  assert.notEqual(at, -1, "칩 숫자를 그리는 자리가 없다 — 검사가 헛돈다");

  const body = source.slice(at, source.indexOf("\nfunction ", at + 10));
  const labelLine = body.split("\n").find((l) => l.includes('querySelector("[data-label]")'));
  assert.ok(labelLine, "라벨을 쓰는 자리가 없다");
  assert.ok(
    !/\+\s*count|count\s*\+/.test(labelLine),
    `라벨에 숫자를 붙인다 — 칩 폭이 흔들린다: 「${labelLine.trim()}」`,
  );
});

test("소리로 듣는 사람에게는 숫자를 붙여 읽어 준다", () => {
  const { chipCountLabel } = load("api", "session", "patients-api", "shell");

  /* 배지는 눈으로만 읽힌다. 화면낭독기가 「작성 중」만 읽으면 2건이 있다는 것을
     알 수 없다 — 배지의 뜻이 소리로 전해지지 않는다. */
  assert.strictEqual(chipCountLabel("작성 중", 2), "작성 중, 2건");
  assert.strictEqual(chipCountLabel("완료", 0), "완료", "0건에 숫자를 붙이면 시끄럽다");
});

/* ── 상단바 아이콘 단추 ──────────────────────────────────────────────── */

const MEDIC_PAGES = ["patients.html", "doctor.html", "ocr-review.html", "admin.html"];

test("**아이콘이 이모지가 아니라 SVG 다** — 이모지는 기기마다 다르게 그려진다", () => {
  /* tokens.css 가 「장식용 이모지」를 안 쓰기로 정해 뒀다. 이모지는 기기마다
     모양이 달라 같은 화면이 사람마다 달라 보이고, 색도 못 맞춘다. */
  for (const page of MEDIC_PAGES) {
    const html = read(page);
    assert.ok(!html.includes("🔔"), `${page} 에 종 이모지가 남아 있다`);
    assert.ok(!html.includes("⏻"), `${page} 에 전원 이모지가 남아 있다`);
    assert.ok(html.includes('<svg class="icon"'), `${page} 에 그림글자가 없다`);
  }
});

test("그림은 화면낭독기가 읽지 않고, 단추가 대신 말한다", () => {
  for (const page of MEDIC_PAGES) {
    const html = read(page);
    /* SVG 를 읽으면 「path path」가 들린다. 뜻은 단추의 aria-label 이 갖는다. */
    for (const svg of html.match(/<svg class="icon"[^>]*>/g) || []) {
      assert.ok(svg.includes('aria-hidden="true"'), `${page} 의 그림을 낭독기가 읽는다`);
    }
    assert.ok(html.includes('aria-label="로그아웃"'), `${page} 의 로그아웃 단추가 말이 없다`);
  }
});

test("**누를 수 있는 것으로 보인다** — 테두리가 없으면 글자로 읽힌다", () => {
  const btn = rule(read("css/shell.css"), ".icon-button");
  assert.match(btn, /border:\s*1px/, "테두리가 없다 — 상단바에 놓인 글자로 읽힌다");
  assert.match(btn, /background:\s*var\(--card\)/, "배경이 없어 단추 면이 안 보인다");
});

test("알림 배지가 칩 배지와 같은 모양이다 — 한 뜻이 두 모양이면 다시 배운다", () => {
  const css = read("css/shell.css");
  const alert = rule(css, ".icon-button__count");
  const chip = rule(css, ".chip__count");

  for (const prop of ["position", "min-width", "height", "font-size", "border-radius"]) {
    const a = new RegExp(prop + ":\\s*([^;]+)").exec(alert);
    const c = new RegExp(prop + ":\\s*([^;]+)").exec(chip);
    assert.ok(a && c, `${prop} 를 한쪽이 안 갖는다`);
    assert.strictEqual(a[1].trim(), c[1].trim(), `${prop} 가 서로 다르다`);
  }
});

test("좌측 목록 제목이 「환자 리스트」다", () => {
  for (const page of ["patients.html", "doctor.html", "ocr-review.html"]) {
    assert.ok(
      read(page).includes('<span class="list__label">환자 리스트</span>'),
      `${page} 의 목록 제목이 다르다`,
    );
  }
  assert.ok(read("admin.html").includes('<span class="list__label">어드민</span>'));
});

/* ── 진료기록 올리기 (S1-6·S1-7 판독 화면 안) ─────────────────────────
 *
 * 올리는 자리가 **판독 화면 하나**로 모였다. 전에는 진료기록 탭에도 업로드
 * 화면이 따로 있어서 같은 칸에 두 화면이었고, 판독이 끝난 환자를 눌러도 빈
 * 업로드 판이 떴다.
 */

test("**올리는 자리가 판독 블록 안에 있다** — 다른 화면으로 보내지 않는다", () => {
  const html = read("ocr-review.html");
  const box = element(html, '<section class="box box--raw">');

  /* 판독을 보다가 「사진이 흐려서 못 읽었구나」를 알게 되는 자리다.
     그때 다른 화면으로 갔다 오면 보던 값을 잃는다. */
  for (const part of ['id="add-doc"', 'id="add-panel"', 'id="drop2"', 'id="pick2"', 'class="kinds"']) {
    assert.ok(box.includes(part), `판독 블록 밖에 있다: ${part}`);
  }
});

test("올리는 판은 접힌 채로 시작한다 — 판독을 보러 온 자리다", () => {
  const html = read("ocr-review.html");
  const panel = /<div class="add-panel" id="add-panel"([^>]*)>/.exec(html);
  assert.ok(panel, "올리는 판이 없다 — 검사가 헛돈다");
  assert.match(panel[1], /\bhidden\b/, "펼친 채로 시작한다 — 판독 값이 아래로 밀린다");

  const button = /<button[\s\S]*?id="add-doc"[\s\S]*?>/.exec(html);
  assert.ok(button, "여는 단추가 없다");
  assert.match(button[0], /aria-expanded="false"/, "낭독기에 접힘이 안 간다");
});

test("환자 화면에는 업로드 판이 없다 — 같은 칸에 두 화면이 되지 않는다", () => {
  const html = read("patients.html");
  for (const gone of ['id="panel-record"', 'id="drop"', 'id="later"', 'id="reading-go"']) {
    assert.ok(!html.includes(gone), `업로드 화면이 남아 있다: ${gone}`);
  }
});

test("드롭존 그림도 이모지가 아니다", () => {
  const html = read("ocr-review.html");
  assert.ok(!html.includes("🖼"), "드롭존에 이모지가 남아 있다");
  assert.ok(!html.includes("📄"), "PDF 이모지가 남아 있다");
});

test("**상단바가 아주 얕게 떠 있다** — 진하면 그림자가 먼저 눈에 걸린다", () => {
  const bar = rule(read("css/shell.css"), ".topbar");

  assert.match(bar, /box-shadow:/, "상단바에 그림자가 없다");
  assert.match(bar, /z-index:/, "아래 흰 칸에 그림자가 묻힌다");

  /* 얕아야 한다. 진하면 읽어야 할 것(환자 이름 · 탭)에서 눈을 뺏는다.
     흐림 반경과 짙기 둘 다 본다 — 한쪽만 재면 다른 쪽으로 진해질 수 있다. */
  const blur = /box-shadow:\s*[\d.]+\w*\s+[\d.]+\w*\s+([\d.]+)px/.exec(bar);
  assert.ok(blur, "그림자 흐림 반경을 못 읽었다 — 검사가 헛돈다");
  assert.ok(Number(blur[1]) <= 6, `그림자가 너무 퍼졌다: ${blur[1]}px`);

  const alpha = /\/\s*([\d.]+)%\s*\)/.exec(bar);
  assert.ok(alpha, "그림자 짙기를 못 읽었다 — 검사가 헛돈다");
  assert.ok(Number(alpha[1]) <= 12, `그림자가 너무 진하다: ${alpha[1]}%`);

  /* 줄이 경계를 긋고 그림자는 깊이만 준다 — 줄을 빼면 경계가 흐려진다 */
  assert.match(bar, /border-bottom:\s*1px solid var\(--line\)/, "경계 줄이 사라졌다");
});

test("**모든 화면이 같은 이름을 쓴다** — 화면마다 다르면 다른 프로그램으로 읽힌다", () => {
  const pages = ["patients.html", "doctor.html", "admin.html", "ocr-review.html"];
  for (const page of pages) {
    const html = markupOnly(read(page));
    const at = html.indexOf('class="topbar__brand"');
    assert.notEqual(at, -1, `${page} 에 상단바 이름이 없다`);

    /* 안에 span 이 하나 더 있어 짝을 세기 어렵다 — 다음 요소가 시작하기
       전까지를 이름으로 본다. */
    const stop = html.indexOf("<nav", at);
    const text = html
      .slice(at, stop === -1 ? at + 300 : stop)
      .replace(/<[^>]+>/g, " ")
      .replace(/\s+/g, " ")
      .trim();
    assert.match(text, /케어온/, `${page} 이름이 다르다: 「${text}」`);
    assert.match(text, /도로시여성의원/, `${page} 에 의원 이름이 없다: 「${text}」`);
  }

  /* 창 제목도 같이 바뀌어야 한다 — 탭 목록에서 옛 이름이 남는다 */
  for (const page of pages) {
    const title = /<title>([^<]*)<\/title>/.exec(read(page));
    assert.ok(title, `${page} 에 창 제목이 없다`);
    assert.ok(!title[1].includes("복약 안내 도우미"), `${page} 창 제목에 옛 이름이 남았다: ${title[1]}`);
  }
});

test("의원 이름은 한 겹 옅다 — 둘 다 굵으면 무엇이 프로그램 이름인지 흐려진다", () => {
  const clinic = rule(read("css/shell.css"), ".topbar__clinic");
  assert.match(clinic, /color:\s*var\(--ink-2\)/, "서비스 이름과 같은 진하기다");

  /* 가르는 줄은 글자가 아니라 테두리다 — 「|」를 글자로 적으면 글꼴에 따라
     높이와 굵기가 제각각이고 화면낭독기가 「막대」로 읽는다. */
  assert.match(clinic, /border-left:\s*1px solid/, "가르는 줄이 없다");
  assert.ok(!markupOnly(read("patients.html")).includes("topbar__brand\">케어온 |"), "가름줄을 글자로 적었다");
});

test("**환자 목록도 아주 얕게 떠 있다** — 상단바와 같은 규칙", () => {
  const list = rule(read("css/shell.css"), ".list");

  assert.match(list, /box-shadow:/, "목록에 그림자가 없다");
  assert.match(list, /z-index:/, "본문 흰 바탕 아래로 묻힌다");

  /* 오른쪽으로만 드리운다 — 목록은 왼쪽 끝에 붙어 있다 */
  const shadow = /box-shadow:\s*([\d.]+)\w*\s+([\d.]+)\w*\s+([\d.]+)\w*/.exec(list);
  assert.ok(shadow, "그림자 값을 못 읽었다 — 검사가 헛돈다");
  assert.ok(Number(shadow[1]) > 0, "오른쪽으로 안 드리운다");
  assert.equal(Number(shadow[2]), 0, "위아래로도 드리운다 — 상단바 그림자와 겹친다");
  assert.ok(Number(shadow[3]) <= 6, `그림자가 너무 퍼졌다: ${shadow[3]}px`);

  const alpha = /\/\s*([\d.]+)%\s*\)/.exec(list);
  assert.ok(alpha && Number(alpha[1]) <= 12, "그림자가 너무 진하다");
});

test("**띄운 셋이 같은 값이다** — 다르면 「띄운 것」이 여러 가지로 읽힌다", () => {
  /* 상단바 · 환자 목록 · 환자 카드 머리. 셋 다 「아래 내용 위에 있다」는 한
     가지를 말한다 — 값이 갈리면 하나는 더 떠 보이고 하나는 붙어 보인다. */
  const shell = read("css/shell.css");
  const blocks = read("css/blocks.css");

  const alphaOf = (body) => {
    const m = /box-shadow:[^;]*\/\s*([\d.]+)%\s*\)/.exec(body);
    assert.ok(m, "그림자 짙기를 못 읽었다 — 검사가 헛돈다");
    return m[1];
  };
  const blurOf = (body) => {
    const m = /box-shadow:\s*[\d.]+\w*\s+[\d.]+\w*\s+([\d.]+)\w*/.exec(body);
    assert.ok(m, "그림자 흐림을 못 읽었다 — 검사가 헛돈다");
    return m[1];
  };

  const bar = rule(shell, ".topbar");
  const list = rule(shell, ".list");
  const head = rule(blocks, ".patient-head");

  assert.equal(alphaOf(list), alphaOf(bar), "환자 목록 그림자가 상단바와 다르다");
  assert.equal(alphaOf(head), alphaOf(bar), "환자 카드 머리 그림자가 상단바와 다르다");
  assert.equal(blurOf(list), blurOf(bar), "환자 목록 그림자 흐림이 상단바와 다르다");
  assert.equal(blurOf(head), blurOf(bar), "환자 카드 머리 그림자 흐림이 상단바와 다르다");

  /* 환자 카드 머리는 **아래로만** 드리운다 */
  const dir = /box-shadow:\s*([\d.]+)\w*\s+([\d.]+)\w*/.exec(head);
  assert.equal(Number(dir[1]), 0, "환자 카드 머리가 옆으로도 드리운다");
  assert.ok(Number(dir[2]) > 0, "환자 카드 머리가 아래로 안 드리운다");
  assert.match(head, /z-index:/, "본문 흰 바탕 아래로 묻힌다");
});

test("**등록 전 확인 칸도 바탕이 있다** — 바닥 색이면 잠긴다", () => {
  /* `--bg` 는 화면 **바닥** 색이다. 그 값을 칸 바탕에 주면 바닥 위에 얹힌
     칸은 테두리만 남고 배경이 없어 보인다 — 실제로 그렇게 보였다. */
  const tokens = read("css/tokens.css");
  const ground = /--bg:\s*([^;]+);/.exec(tokens);
  const card = /--card:\s*([^;]+);/.exec(tokens);
  assert.ok(ground && card, "바닥 · 카드 색을 못 읽었다 — 검사가 헛돈다");
  assert.notEqual(ground[1].trim(), card[1].trim(), "바닥과 카드가 같은 색이다");

  const confirm = rule(read("css/patients.css"), ".box--confirm");
  assert.match(confirm, /background:\s*var\(--card\)/, "확인 칸이 바닥 색이다 — 잠겨 보인다");
});

test("환자 등록 제목 아래에 줄을 긋지 않는다 — 상자 테두리가 이미 경계다", () => {
  const head = rule(read("css/patients.css"), ".reg__head");
  assert.ok(!/border-bottom:/.test(head), "제목 밑줄이 남아 있다 — 선이 두 겹으로 보인다");
});

test("**취소는 한 곳이다** — 같은 일을 하는 단추가 둘이면 하나만 고쳐진다", () => {
  const html = markupOnly(read("patients.html"));
  const cancels = (html.match(/id="reg-cancel[^"]*"/g) || []);
  assert.deepEqual(cancels, ['id="reg-cancel"'], `등록 화면에 취소가 ${cancels.length}개다`);

  /* 그 하나는 아래 단추줄에 있다 — 위 제목줄이 아니다 */
  const head = element(html, '<div class="reg__head">');
  assert.ok(!head.includes("취소"), "제목줄에 취소가 남아 있다");

  /* 손잡이도 사라진 것을 잡으면 안 된다 — 없는 요소에 붙이면 그 자리에서 죽는다 */
  const code = codeOnly(read("js/patients.js"));
  assert.ok(!code.includes("reg-cancel-top"), "없는 단추를 잡는다 — 화면이 그 줄에서 죽는다");
  assert.match(code, /getElementById\("reg-cancel"\)/, "남은 취소가 안 눌린다");
});

test("**접으면 머리 단추 하나만 남는다** — 빠뜨린 것은 48px 레일에서 쪼개진다", () => {
  const css = read("css/shell.css");

  /* 레일 폭을 먼저 확인한다 — 넓으면 이 검사가 헛돈다 */
  assert.match(rule(css, ".list--folded"), /flex-basis:\s*48px/, "접힌 폭이 48px 이 아니다");

  /* 접었을 때 감추는 목록에 **목록 머리의 모든 칸**이 들어야 한다.
     하나라도 빠지면 그것만 남아 세로로 쪼개진다 — 「+ 환자 등록」이 그랬다. */
  const folded = css.slice(css.indexOf(".list--folded .list__search"));
  const block = folded.slice(0, folded.indexOf("}"));

  for (const part of ["list__search", "list__add", "list__rows", "list__note", "list__day", "chips"]) {
    assert.ok(block.includes(part), `접었을 때 .${part} 가 안 감춰진다 — 레일에 끼어 깨진다`);
  }

  /* 감추는 규칙이 실제로 감추는가 */
  assert.match(folded.slice(0, folded.indexOf("}") + 40), /display:\s*none/, "감추는 규칙이 없다");
});

test("**환자 머리는 스크롤해도 붙어 있는다** — 누구인지를 잃으면 잘못 넣는다", () => {
  const head = rule(read("css/blocks.css"), ".patient-head");

  assert.match(head, /position:\s*sticky/, "스크롤하면 머리가 화면 밖으로 나간다");
  assert.match(head, /top:/, "붙을 자리를 안 정했다 — sticky 만으로는 안 붙는다");
  assert.match(head, /z-index:/, "아래 내용이 머리 위로 지나간다");

  /* 붙는 자리는 판의 위 여백만큼 되민 값이라야 한다 — 0 이면 그만큼 늦게 붙어
     머리 위로 내용이 한 줄 지나간다. */
  const pane = rule(read("css/shell.css"), ".pane");
  const padding = /padding:\s*(\d+)px/.exec(pane);
  assert.ok(padding, "판의 여백을 못 읽었다 — 검사가 헛돈다");
  assert.match(
    head,
    new RegExp(`top:\\s*-${padding[1]}px`),
    `붙는 자리가 판 여백(${padding[1]}px)과 안 맞는다`,
  );

  /* 스크롤하는 것이 판이어야 sticky 가 산다 */
  assert.match(pane, /overflow-y:\s*auto/, "판이 스크롤하지 않는다 — 붙을 곳이 없다");
});
