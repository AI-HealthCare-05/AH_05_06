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

const ROOT = path.join(__dirname, "..");
const SHELL_PAGES = ["patients.html", "ocr-review.html", "doctor.html", "admin.html"];

/* CSS 규칙 하나를 정확히 집는다. `.list__head {` 로 찾으면
   `.list--folded .list__head {` 를 먼저 물어 엉뚱한 블록을 잰다. */
function rule(css, selector) {
  const at = css.indexOf("\n" + selector + " {");
  assert.notEqual(at, -1, `${selector} 규칙이 없다 — 검사가 헛돈다`);
  const open = css.indexOf("{", at);
  const close = css.indexOf("}", open);
  return css.slice(open, close);
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

test("판독 화면만 저절로 접힌다 — 나머지는 펴진 채로 연다", () => {
  assert.ok(
    read("ocr-review.html").includes("shell--fold-list"),
    "판독 화면이 저절로 안 접힌다 — 원문 칸이 좁아진다 (S1-7)",
  );
  for (const page of ["patients.html", "doctor.html", "admin.html"]) {
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
  const css = read("css/patients.css");
  const add = rule(css, ".list__add");

  assert.match(add, /width:\s*100%/, "폭이 없으면 글자만큼 줄어 잘린 것처럼 보인다");
  assert.match(add, /border:\s*2px/, "주 진입인데 테두리가 얇다 — 어드민 [+ 직원 추가]도 2px 다");
});

test("**높이는 토큰을 따른다** — 와이어프레임 34px 보다 접근성이 우선이다", () => {
  /* 와이어프레임 원문은 34px 인데 tokens.css 가 44px 로 두었다 —
     「손가락과 초점이 닿는 최소 크기」. WCAG 2.5.5 최소 터치 영역이라
     와이어프레임 치수로 되돌리면 퇴보다. 이 선택을 검사로 남긴다. */
  const tokens = read("css/tokens.css");
  assert.match(tokens, /--field-h:\s*44px/, "터치 영역이 44px 아래로 내려갔다");

  const css = read("css/patients.css");
  const add = rule(css, ".list__add");
  assert.match(add, /height:\s*var\(--field-h\)/, "높이를 토큰이 아니라 숫자로 박았다");
});

/* ── 환자 등록 (S1-2) ─────────────────────────────────────────────────── */

test("**①환자 찾기와 ②환자 정보가 좌우 2단이다** — 세로로 쌓으면 한 화면에 안 들어온다", () => {
  const html = read("patients.html");
  const css = read("css/patients.css");

  /* 와이어프레임 S1-2 우측 본문: `display:flex · gap:26px`.
     스탭은 찾은 결과를 보면서 아래 칸을 채운다 — 스크롤로 갈리면 앞뒤를 오간다. */
  assert.ok(html.includes('class="reg__cols"'), "두 칸을 감싸는 자리가 없다");

  const cols = rule(css, ".reg__cols");
  assert.match(cols, /display:\s*flex/, "2단이 아니다");
  assert.match(cols, /gap:\s*26px/, "와이어프레임 간격과 다르다");

  const box = rule(css, ".reg__cols > .box");
  assert.match(box, /flex:\s*1/, "한 칸이 안 늘어난다");
  assert.match(box, /min-width:\s*0/, "긴 내용이 칸을 밀어낸다");
});

/* 여는 태그부터 **짝이 맞는 닫는 태그**까지를 돌려준다.
   `indexOf` 로 구간을 자르면 `</div>` 가 어디 있든 같은 문자열이 나와,
   칸을 일찍 닫아도 검사가 통과한다(돌연변이로 확인했다). */
function element(html, opener) {
  const start = html.indexOf(opener);
  assert.notEqual(start, -1, `${opener} 가 없다 — 검사가 헛돈다`);

  let depth = 0;
  let at = start;
  while (at < html.length) {
    if (html.startsWith("<div", at)) depth++;
    else if (html.startsWith("</div>", at)) {
      depth--;
      if (depth === 0) return html.slice(start, at + 6);
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

test("좁은 화면에서는 세로로 돌아간다 — 2단을 우겨넣으면 둘 다 못 읽는다", () => {
  const css = read("css/patients.css");
  const at = css.indexOf("@media (max-width: 1100px)");
  assert.notEqual(at, -1, "좁은 화면 규칙이 없다");
  assert.match(css.slice(at, at + 160), /display:\s*block/, "좁아도 2단을 고집한다");
});

test("**상태 칩 높이는 토큰 결정을 지킨다** — 와이어프레임 11px 보다 크다", () => {
  /* 와이어프레임은 `font-size:11px · padding:3px 10px`(약 21px)인데 구현은
     32px 다. 주석에 이유가 적혀 있다 — 「320px 폭에 다섯이 들어가야 해서
     44px 은 못 쓴다. 폭은 그대로 두고 높이만 올려 줄바꿈을 늘리지 않는다」.
     초점과 손가락이 닿아야 하는 자리라 와이어프레임 치수로 되돌리지 않는다. */
  const chip = rule(read("css/shell.css"), ".chip");
  assert.match(chip, /height:\s*32px/, "칩 높이가 바뀌었다 — 초점이 닿기 어려워진다");
  assert.match(chip, /padding:\s*0 10px/, "칩 폭이 바뀌면 320px 안에서 줄바꿈이 늘어난다");
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
