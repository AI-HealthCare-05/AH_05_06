/* **5단계 줄은 어느 화면에서든 같은 것이다** — 판독 화면에서 돌아갈 길이 없던 버그.
 *
 * 같은 다섯 단계가 두 화면에 다른 물건으로 있었다.
 *
 *     patients.html    <button class="tab" role="tab">   눌러서 옮겨 다닌다
 *     ocr-review.html  <li class="step">                 그림일 뿐, 안 눌린다
 *
 * 그래서 판독 화면에서 「기본정보」를 눌러도 아무 일이 없었고, 앞 화면으로
 * 돌아가려면 왼쪽 목록에서 그 환자를 다시 골라야 했다. 머리말 모양도 두 화면이
 * 달라서 옮길 때마다 다른 화면처럼 보였다.
 *
 * 구조 진단 §5.1 이 적어 둔 그 자리다 — 「같은 5단계를 한 화면은 `<li>`, 다른
 * 화면은 `<button role="tab">` 으로 만들었다」.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const { load } = require("./browser-shim.js");

const ROOT = path.join(__dirname, "..");

function read(rel) {
  return fs.readFileSync(path.join(ROOT, rel), "utf8");
}

const nav = () => load("api", "step-nav");

/* ── 어디까지 왔는지 ─────────────────────────────────────────────────── */

test("**지나온 칸은 ✓, 지금은 ●, 아직은 ○**", () => {
  const { stepMark } = nav();

  assert.strictEqual(stepMark("basic", "record"), "✓", "지나온 칸이 ✓ 가 아니다");
  assert.strictEqual(stepMark("record", "record"), "●", "지금 칸이 ● 가 아니다");
  assert.strictEqual(stepMark("guide", "record"), "○", "아직인 칸이 ○ 가 아니다");
  assert.strictEqual(stepMark("status", "record"), "○");
});

/* ── 어디로 가는가 ───────────────────────────────────────────────────── */

test("**판독 화면에서 다른 칸을 누르면 환자 카드로 돌아간다**", () => {
  const { stepHref } = nav();

  const back = stepHref("basic", "record", "/ocr-review.html", 12);
  assert.strictEqual(back, "/patients.html?visit=12&tab=basic", "돌아갈 주소가 틀렸다");
});

test("지금 서 있는 칸에는 주소를 주지 않는다 — 제자리로 오는 링크가 가장 나쁘다", () => {
  const { stepHref } = nav();
  assert.strictEqual(stepHref("record", "record", "/ocr-review.html", 12), null);
});

test("같은 화면 안의 칸에는 주소를 주지 않는다 — 새로 받으면 고르던 값이 사라진다", () => {
  const { stepHref } = nav();
  /* 환자 카드 안에서 탭을 옮기는 것은 화면을 다시 받는 일이 아니다. */
  assert.strictEqual(stepHref("guide", "basic", "/patients.html", 12), null);
});

test("모르는 칸에는 주소를 주지 않는다", () => {
  const { stepHref } = nav();
  assert.strictEqual(stepHref("없음", "record", "/ocr-review.html", 12), null);
});

/* ── 돌아왔을 때 ─────────────────────────────────────────────────────── */

test("**주소에서 어느 진료의 어느 칸인지 읽는다**", () => {
  const { stepFromSearch } = nav();

  assert.deepEqual(stepFromSearch("?visit=12&tab=basic"), { visitId: 12, tab: "basic" });
  assert.deepEqual(stepFromSearch("?tab=guide&visit=7"), { visitId: 7, tab: "guide" });
});

test("모르는 칸 이름은 안 받는다 — 없는 패널을 열면 빈 화면이 된다", () => {
  const { stepFromSearch } = nav();
  assert.strictEqual(stepFromSearch("?visit=1&tab=없음").tab, null);
  assert.strictEqual(stepFromSearch("?visit=1").tab, null);
  assert.strictEqual(stepFromSearch("").visitId, null);
});

/* ── 두 화면이 같은 것을 쓰는가 ──────────────────────────────────────── */

test("**판독 화면에 `<li class=\"step\">` 가 남아 있지 않다**", () => {
  const html = read("ocr-review.html");

  assert.ok(!html.includes('class="step'), "안 눌리는 단계 줄이 남아 있다");
  assert.ok(!html.includes("<ol class=\"steps\">"), "옛 단계 줄이 남아 있다");
  assert.ok(html.includes('class="tabs" id="tabs"'), "공용 단계 줄 자리가 없다");
});

test("두 화면이 같은 모듈을 싣는다", () => {
  for (const page of ["patients.html", "ocr-review.html"]) {
    assert.ok(read(page).includes("/js/step-nav.js"), `${page} 가 공용 모듈을 안 싣는다`);
  }
});

test("판독 화면의 머리말이 환자 카드와 같은 모양이다", () => {
  const html = read("ocr-review.html");
  for (const part of ["patient-head__who", 'id="p-name"', 'id="p-state"', 'id="p-visit"']) {
    assert.ok(html.includes(part), `머리말에 ${part} 가 없다 — 화면마다 다르게 보인다`);
  }
});

/* ── 진료일 표시 ─────────────────────────────────────────────────────── */

test("머리말의 진료일에 시각이 안 붙는다", () => {
  const source = read("js/ocr-review.js");
  const at = source.indexOf("function shortDate");
  assert.notEqual(at, -1, "shortDate 가 없다 — 검사가 헛돈다");

  const body = source.slice(at, source.indexOf("\n  }", at));
  assert.ok(
    !/iso\.slice\(5\)/.test(body),
    "앞 다섯 자만 떼어낸다 — 시각까지 남아 「08-31T17:04:42+09:00」로 뜬다",
  );
});

/* ── 의사 화면도 같은 단계 줄을 쓴다 ─────────────────────────────────── */

const { read: readSrc, codeOnly: stripSrc, markupOnly: stripTags } = require("./source.js");

test("**의사 화면의 단계 줄이 눌린다** — 정적 `<ol>` 이라 갈 길이 없었다", () => {
  const page = stripTags(readSrc("doctor.html"));

  /* 예전에는 `<li class="step">` 을 박아 뒀다 — `<li>` 는 안 눌린다 */
  assert.ok(!page.includes('<ol class="steps">'), "정적 단계 목록이 남아 있다");
  assert.ok(!page.includes('class="step step--'), "정적 단계 항목이 남아 있다");

  /* 스탭 화면과 같은 자리·같은 이름 */
  assert.ok(page.includes('<div class="tabs" id="tabs"'), "단계 줄을 담을 자리가 없다");
  assert.ok(page.includes('<script src="/js/step-nav.js"></script>'), "단계 줄을 그리는 파일을 안 싣는다");
});

test("**머리말 안에 선다** — 아래 줄을 차지하면 이름 밑으로 내려온다", () => {
  const page = stripTags(readSrc("doctor.html"));
  const head = page.slice(page.indexOf('<div class="patient-head">'));
  const upto = head.slice(0, head.indexOf('<h1'));

  assert.ok(upto.includes('id="tabs"'), "단계 줄이 머리말 밖에 있다");
  assert.ok(upto.includes('patient-head__who'), "스탭 화면과 머리말 구조가 다르다");
});

test("**누르면 그 단계로 간다** — 이 화면에는 그 탭들의 본문이 없다", () => {
  const code = stripSrc(readSrc("js/doctor.js"));

  assert.ok(code.includes("stepsHtml("), "단계 줄을 안 그린다");
  assert.ok(code.includes('closest(".tab[data-href]")'), "누른 것을 받는 자리가 없다");

  /* `data-href` 가 없는 것(지금 서 있는 단계)은 안 따라간다 —
     제자리로 오는 링크가 가장 나쁘다 */
  const at = code.indexOf('closest(".tab[data-href]")');
  const body = code.slice(at, at + 200);
  assert.ok(body.includes("if (!step) return"), "지금 서 있는 단계를 눌러도 뭔가 한다");
});
