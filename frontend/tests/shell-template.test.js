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
  for (const [file, sel] of [["css/patients.css", ".reg__cols"], ["css/detail.css", ".cols2"]]) {
    const box = rule(read(file), sel);
    assert.match(box, /flex-wrap:\s*wrap/, `${sel} 이 접히지 못한다 — 칸이 찌그러진다`);
  }
  for (const [file, sel] of [["css/patients.css", ".reg__cols > .box"], ["css/detail.css", ".cols2__side"]]) {
    const side = rule(read(file), sel);
    assert.match(side, /flex:\s*1 1 340px/, `${sel} 에 최소 폭이 없다 — 접힐 때를 모른다`);
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

  const css = rule(read("css/shell.css"), ".patient-head");
  assert.match(css, /display:\s*flex/, "머리말이 가로가 아니다");
  assert.match(css, /gap:\s*18px/, "와이어프레임 간격과 다르다");
});

test("**탭이 버튼 형식이다** — 고른 것만 채워진다", () => {
  const css = read("css/detail.css");

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
  const tab = rule(read("css/detail.css"), ".tab");
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

  const css = rule(read("css/detail.css"), ".cols2");
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

/* ── 진료기록 업로드 (S1-5) ──────────────────────────────────────────── */

test("**업로드 화면이 상자 하나에 담긴다** — 기본정보의 「환자 정보」와 같은 모양", () => {
  const html = read("patients.html");
  const panel = element(html, '<div class="panel" id="panel-record" hidden>');

  /* 화면마다 담는 모양이 다르면 같은 자리인지가 안 보이고, 탭을 옮길 때마다
     눈이 새로 자리를 찾는다. */
  assert.ok(panel.includes('<section class="box">'), "업로드가 상자에 안 담겼다");

  const box = element(panel, '<section class="box">');
  for (const part of ["진료기록 업로드", 'id="drop"', 'class="kinds"', 'id="later"', 'id="next"']) {
    assert.ok(box.includes(part), `상자 밖에 남은 것이 있다: ${part}`);
  }
});

test("아래 단추가 작다 — 이 화면의 주인공은 드롭존이다", () => {
  const html = read("patients.html");
  const css = read("css/upload.css");

  assert.ok(html.includes("button-ghost--sm"), "「나중에 업로드」가 크다");
  assert.ok(html.includes("button-primary--sm"), "「업로드 후 안내문 생성」이 크다");

  const small = rule(css, ".button-primary--sm");
  const height = /height:\s*(\d+)px/.exec(small);
  assert.ok(height, "작은 단추 높이가 없다 — 검사가 헛돈다");
  assert.ok(Number(height[1]) < 44, `단추가 안 작아졌다: ${height[1]}px`);
  assert.ok(Number(height[1]) >= 24, `목표 크기가 24px 아래다: ${height[1]}px (WCAG 2.5.8)`);
});

test("드롭존 그림도 이모지가 아니다", () => {
  const html = read("patients.html");
  assert.ok(!html.includes("🖼"), "드롭존에 이모지가 남아 있다");
  assert.ok(html.includes('class="drop__pic"'), "드롭존에 그림글자가 없다");

  const pic = /<svg class="drop__pic"[^>]*>/.exec(html);
  assert.ok(pic, "그림글자를 못 찾았다");
  assert.ok(pic[0].includes('aria-hidden="true"'), "그림을 낭독기가 읽는다");
});
