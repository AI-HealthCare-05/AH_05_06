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
  const brand = css.slice(css.indexOf(".topbar__brand {"), css.indexOf(".topbar__nav {"));
  const right = css.slice(css.indexOf(".topbar__right {"), css.indexOf(".topbar__right {") + 200);

  assert.match(brand, /flex:\s*1 1 0/, "브랜드 칸이 안 늘어난다 — 탭이 왼쪽에 붙는다");
  assert.match(right, /flex:\s*1 1 0/, "오른쪽 칸이 안 늘어난다 — 탭이 오른쪽으로 밀린다");
});

test("접힌 레일이 48px 다 — 와이어프레임 S1-7 이 그린 폭", () => {
  const css = read("css/shell.css");
  const folded = css.slice(css.indexOf(".list--folded {"), css.indexOf(".list--folded {") + 120);
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
