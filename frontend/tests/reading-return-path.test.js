/* **「진료기록」 칸은 판독 화면 하나다.**
 *
 * 전에는 그 칸에 화면이 둘이었다 — `patients.html` 의 업로드 판과
 * `ocr-review.html` 의 판독 화면. 판독이 끝난 환자를 눌러도 빈 업로드 판이
 * 떴고, 판독을 보려면 그 판 안의 「판독 결과 확인」을 한 번 더 눌러야 했다.
 * 올리는 일도 판독 화면 머리의 「OCR 업로드」가 한다.
 *
 * 그리고 그 길은 **날짜를 잃었다.** 목록은 하루 단위인데 처음 여는 날은 늘
 * 오늘이라, 어제 진료의 주소로 들어오면 오늘 목록에서 못 찾고 「환자가
 * 없습니다」가 떴다.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const { load } = require("./browser-shim.js");
const { read, codeOnly, markupOnly } = require("./source.js");

/* ── 칸이 하나다 ────────────────────────────────────────────────────── */

test("**「진료기록」은 판독 화면에 산다**", () => {
  const { VISIT_STEPS } = load("api", "session", "patients-api", "step-nav");
  const record = VISIT_STEPS.filter((s) => s.key === "record")[0];

  assert.ok(record, "진료기록 칸이 사라졌다");
  assert.equal(record.page, "/ocr-review.html", "아직 업로드 화면을 가리킨다");
});

test("환자 화면에는 그 판이 없다 — 같은 칸에 두 화면이 되지 않는다", () => {
  const html = markupOnly(read("patients.html"));
  assert.ok(!html.includes('id="panel-record"'), "업로드 판이 남아 있다");
  assert.ok(!html.includes("/js/upload.js"), "없어진 파일을 아직 싣는다");

  /* 탭 단추는 그대로 있어야 한다 — 다섯 칸이 보여야 어디까지 왔는지 읽힌다 */
  assert.ok(html.includes('data-tab="record"'), "진료기록 칸이 화면에서 사라졌다");
});

test("**그 칸을 누르면 판독 화면으로 간다**", () => {
  const code = codeOnly(read("js/detail.js"));

  const at = code.indexOf("var AWAY");
  assert.notEqual(at, -1, "다른 화면에 사는 칸을 모른다");
  assert.match(code.slice(at, at + 200), /record:\s*"\/ocr-review\.html"/, "갈 곳이 없다");

  /* `showTab` 이 먼저 보내야 한다 — TABS 검사에 먼저 걸리면 조용히 돌아간다 */
  const show = code.indexOf("function showTab");
  const body = code.slice(show, code.indexOf("\n  }", show));
  assert.ok(body.indexOf("AWAY[name]") !== -1, "showTab 이 다른 화면으로 안 보낸다");
  assert.ok(
    body.indexOf("AWAY[name]") < body.indexOf("TABS.indexOf"),
    "TABS 검사가 먼저다 — 모르는 이름으로 보고 조용히 돌아간다",
  );
});

test("**그 진료를 달고 간다** — 안 달면 도착한 화면이 다른 환자를 연다", () => {
  const code = codeOnly(read("js/detail.js"));
  const at = code.indexOf("function goAway");
  assert.notEqual(at, -1, "보내는 자리가 없다");

  const body = code.slice(at, code.indexOf("\n  }", at));
  assert.match(body, /visit=/, "진료를 안 달고 간다");
  assert.match(body, /encodeURIComponent\(row\.visit_id\)/, "진료 번호를 안 싣는다");
  assert.match(body, /if \(!row/, "고른 환자가 없을 때도 간다");
});

/* ── 날짜를 잃지 않는다 ─────────────────────────────────────────────── */

test("**주소로 찾아온 진료의 날짜로 옮긴다**", () => {
  const code = codeOnly(read("js/shell.js"));
  const at = code.indexOf("function openAsked");
  assert.notEqual(at, -1, "주소로 찾아온 진료를 여는 자리가 없다");

  const body = code.slice(at, code.indexOf("\n  }", at));

  /* 오늘 목록에 있으면 묻지 않는다 — 대부분은 오늘 진료다 */
  assert.match(body, /rowByVisit\(rows, asked\.visitId\)/, "오늘 목록을 먼저 안 본다");

  /* 없으면 그 진료를 물어 날짜를 옮긴다 */
  assert.match(body, /getVisit\(/, "그 진료를 안 물어본다 — 오늘 목록에 없으면 못 연다");
  assert.match(body, /visited_at/, "진료일을 안 읽는다");
  assert.match(body, /listDay\s*=/, "목록의 날짜를 안 옮긴다");
  assert.match(body, /loadDay\(\)/, "그 날 목록을 안 다시 읽는다");
});

test("못 찾으면 오늘을 보인다 — 빈 화면을 띄우지 않는다", () => {
  const code = codeOnly(read("js/shell.js"));
  const at = code.indexOf("function openAsked");
  const body = code.slice(at, code.indexOf("\n  }", at));
  assert.match(body, /\.catch\(/, "못 찾으면 그대로 죽는다");
});

test("주소는 한 번만 쓰고 지운다 — 새로고침할 때마다 되돌아가면 안 된다", () => {
  const code = codeOnly(read("js/shell.js"));
  assert.match(code, /function clearAsked/, "주소를 지우는 자리가 없다");
  assert.match(code, /history\.replaceState\(null, "", location\.pathname\)/, "주소가 남는다");

  /* 두 길 모두에서 지워야 한다 — 오늘 목록에 있을 때와 없을 때 */
  const at = code.indexOf("function openAsked");
  assert.match(code.slice(at, code.indexOf("\n  }", at)), /clearAsked/, "물어본 길에서 안 지운다");
  const open = code.indexOf("function openRow");
  assert.match(code.slice(open, code.indexOf("\n  }", open)), /clearAsked/, "바로 연 길에서 안 지운다");
});

/* ── 카드를 누르면 기본정보 ─────────────────────────────────────────── */

test("**환자 카드를 누르면 늘 기본정보가 열린다**", () => {
  /* `open_tab` 은 목록의 줄에 그대로 붙는다(`row.open_tab = ...`). 한 번 붙으면
     그 뒤로 그 환자를 누를 때마다 그 칸이 열렸다 — 「진료기록」이 붙어 있으면
     카드를 눌렀는데 판독 화면으로 튀어 나간다. */
  const code = codeOnly(read("js/shell.js"));
  const at = code.indexOf('getElementById("rows").addEventListener');
  assert.notEqual(at, -1, "줄 누름을 받는 자리가 없다");

  const handler = code.slice(at, at + 1600);

  /* **두 곳을 다 지워야 한다.** 넘겨 주는 사본과 목록이 들고 있는 원본이
     따로다 — 사본만 지우면 다음에 누를 때 원본에서 다시 붙는다. */
  assert.match(handler, /hit\.open_tab\s*=\s*null/, "넘겨 주는 것에 앞 칸이 남는다");
  assert.match(handler, /kept\.open_tab\s*=\s*null/, "목록 줄에 앞 칸이 남아 다음에 또 열린다");
});
