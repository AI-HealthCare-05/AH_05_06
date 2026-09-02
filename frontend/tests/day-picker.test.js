/* **날짜 줄** — 가운데 정렬 · 화살표 버튼 · 눌러서 달력.
 *
 * 와이어프레임 S1-1 좌측: `padding:9px 12px · gap:6px`, 화살표 `24×24 ·
 * border 1px · radius 5`, 날짜는 `flex:1 · 가운데 · 13px/700` 이고 「오늘」만
 * 약하게.
 *
 * 달력은 직접 그리지 않고 `<input type="date">` 를 겹쳐 둔다 — 브라우저·
 * 운영체제가 주는 달력이라 키보드로도 되고 언어·주 시작 요일도 그 기기 설정을
 * 따른다. 우리가 그리면 그 셋을 다시 만들어야 한다.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const { load } = require("./browser-shim.js");

const ROOT = path.join(__dirname, "..");
const PAGES = ["patients.html", "doctor.html", "ocr-review.html"];

function read(rel) {
  return fs.readFileSync(path.join(ROOT, rel), "utf8");
}

function rule(css, selector) {
  const at = css.indexOf("\n" + selector + " {");
  assert.notEqual(at, -1, `${selector} 규칙이 없다 — 검사가 헛돈다`);
  const open = css.indexOf("{", at);
  return css.slice(open, css.indexOf("}", open));
}

/* ── 달력이 준 날짜를 어떻게 읽는가 ───────────────────────────────────── */

test("**`2026-08-31` 을 그 날 00:00 으로 읽는다** — UTC 로 읽으면 하루가 밀린다", () => {
  const { dayFromInput } = load("api", "session", "patients-api", "shell");

  const day = dayFromInput("2026-08-31");
  assert.strictEqual(day.getFullYear(), 2026);
  assert.strictEqual(day.getMonth(), 7, "8월이 아니다");
  assert.strictEqual(day.getDate(), 31, "고른 날이 아니다 — new Date(문자열)은 UTC 자정이다");

  /* `new Date("2026-08-31")` 은 UTC 자정이라 KST 에서는 8월 30일 09:00 이다.
     그대로 쓰면 고른 날의 **하루 전** 목록이 열린다. */
  assert.notStrictEqual(
    day.getTime(),
    new Date("2026-08-31").getTime(),
    "문자열을 그대로 Date 에 넣고 있다 — 시간대만큼 밀린다",
  );
});

test("이상한 값에는 아무 날도 주지 않는다 — 목록이 엉뚱한 날로 가면 안 된다", () => {
  const { dayFromInput } = load("api", "session", "patients-api", "shell");

  for (const bad of ["", null, undefined, "2026-8-3", "오늘", "2026-08-31T00:00"]) {
    assert.strictEqual(dayFromInput(bad), null, `이상한 값을 받아들인다: ${bad}`);
  }
});

/* ── 무엇이라고 쓰는가 ────────────────────────────────────────────────── */

test("오늘이면 「오늘」을 붙이고, 그것만 약하게 둔다", () => {
  const { dayHeading } = load("api", "session", "patients-api", "shell");

  const day = new Date(2026, 7, 31);
  const same = dayHeading(day, new Date(2026, 7, 31, 16, 0));
  assert.match(same, /8월 31일 \(월\)/, "날짜 표기가 다르다");
  assert.match(same, /class="day__today">오늘</, "「오늘」이 없거나 약하게 안 뒀다");

  const other = dayHeading(day, new Date(2026, 8, 1));
  assert.match(other, /8월 31일 \(월\)/);
  assert.ok(!other.includes("오늘"), "지난 날짜인데 「오늘」이 붙는다");
});

/* ── 생김새 ──────────────────────────────────────────────────────────── */

test("**날짜가 가운데, 화살표가 양끝**", () => {
  const css = read("css/shell.css");

  const row = rule(css, ".list__day");
  assert.match(row, /gap:\s*6px/, "와이어프레임 간격과 다르다");
  assert.match(row, /padding:\s*9px 12px/, "와이어프레임 여백과 다르다");

  const pick = rule(css, ".day__pick");
  assert.match(pick, /flex:\s*1/, "날짜가 안 늘어나 가운데로 안 간다");
  assert.match(pick, /text-align:\s*center/, "날짜가 가운데가 아니다");

  const step = rule(css, ".day__step");
  assert.match(step, /width:\s*24px/, "화살표가 와이어프레임 크기와 다르다");
  assert.match(step, /border:\s*1px/, "화살표에 테두리가 없다 — 누를 수 있는지 안 보인다");
});

test("세 화면이 같은 날짜 줄을 쓴다 — 공통 골격이다", () => {
  for (const page of PAGES) {
    const html = read(page);
    assert.ok(html.includes('id="day-prev"'), `${page} 에 이전 날짜 단추가 없다`);
    assert.ok(html.includes('id="day-next"'), `${page} 에 다음 날짜 단추가 없다`);
    assert.ok(html.includes('id="day-input"'), `${page} 에서 날짜를 눌러도 달력이 안 열린다`);
    assert.ok(html.includes('type="date"'), `${page} 가 브라우저 달력을 안 쓴다`);
  }
});

/* ── 키보드 ──────────────────────────────────────────────────────────── */

test("**투명하게 겹쳐 두되 숨기지 않는다** — 숨긴 입력은 초점을 못 받는다", () => {
  const input = rule(read("css/shell.css"), ".day__input");

  assert.match(input, /opacity:\s*0/, "입력이 날짜 글자를 가린다");
  assert.ok(!/display:\s*none/.test(input), "숨긴 입력은 키보드로 못 연다 (WCAG 2.1.1)");
  assert.ok(!/visibility:\s*hidden/.test(input), "같은 이유로 visibility 도 안 된다");
});

test("연·월·일을 하나씩 칠 때마다 목록을 다시 부르지 않는다", () => {
  /* `input` 으로 들으면 아직 다 안 친 날짜로 세 번 부른다. `change` 여야 한다. */
  const source = read("js/shell.js");

  /* **리스너를 정확히 집는다.** `getElementById("day-input")` 로 찾으면
     `renderDay()` 안의 것(값을 채우는 자리)을 먼저 물어 엉뚱한 데를 잰다. */
  const at = source.indexOf("dayInput.addEventListener(");
  assert.notEqual(at, -1, "달력 입력을 안 듣는다 — 검사가 헛돈다");

  const listened = /dayInput\.addEventListener\("([a-z]+)"/.exec(source.slice(at));
  assert.ok(listened, "무엇으로 듣는지 못 읽었다");
  assert.strictEqual(
    listened[1],
    "change",
    "input 으로 들으면 연·월·일을 하나씩 칠 때마다 다 안 친 날짜로 목록을 부른다",
  );
});
