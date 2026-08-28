/* 업로드를 마치고 넘어갈 때 **그 진료를 데려가는가** — KEY-204 후속.
 *
 * 증상: OCR 업로드 뒤 「다음」을 누르면 **다른 환자의 판독 화면**이 열렸다.
 *
 * 원인은 한 줄이었다.
 *
 *     location.href = "/ocr-review.html";      ← 진료 번호가 없다
 *
 * 새 화면의 `shell.js` 는 목록을 받아 **맨 위 줄**을 고른다. 올린 사람이
 * 맨 위가 아니면 남의 판독 화면이 열린다.
 *
 * 게다가 올리고 나면 그 진료의 분류가 바뀐다 — 「진료기록 없음」에서 「판독
 * 확인」으로. 고른 칩이 옛 분류면 그 줄은 목록에서 걸러져 **맨 위가 남의 것일
 * 수밖에 없다.**
 *
 * 화면 코드라 검사에서 부를 수 없다(껍데기의 `getElementById` 가 `null` 이면
 * IIFE 가 안 돈다). 그래서 **글자가 아니라 그 분기의 짜임**을 본다.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");

const ROOT = path.join(__dirname, "..");
const read = (rel) => fs.readFileSync(path.join(ROOT, rel), "utf8");

/** 「다음」 버튼이 하는 일만 잘라 낸다. */
function nextBranch() {
  const src = read("js/upload.js");
  const at = src.indexOf('next.addEventListener("click"');
  assert.ok(at !== -1, "「다음」 버튼 분기를 못 찾았다 — 검사가 헛돈다");
  const end = src.indexOf("var visit = null", at);
  return src.slice(at, end === -1 ? src.length : end);
}

test("**진료 번호를 실어 보낸다** — 맨몸으로 가지 않는다", () => {
  const branch = nextBranch();

  assert.ok(
    !/location\.href\s*=\s*["']\/ocr-review\.html["']\s*;/.test(branch),
    "진료 번호 없이 판독 화면으로 간다 — 목록의 맨 위 줄, 즉 남의 환자가 열린다",
  );
  assert.match(branch, /ocr-review\.html\?visit=/, "`?visit=` 을 안 붙인다");
});

test("붙잡아 둔 그 진료를 넘긴다 — 딴 값을 보내지 않는다", () => {
  const branch = nextBranch();

  /* 업로드가 붙는 자리와 같은 것을 넘겨야 한다. `upload.js` 는 `visit` 하나로
     올릴 곳을 정하는데(174행), 넘어갈 때 다른 것을 쓰면 두 곳이 갈린다. */
  assert.match(
    branch,
    /ocr-review\.html\?visit="\s*\+\s*encodeURIComponent\(\s*visit\.visit_id\s*\)/,
    "올릴 때 쓴 `visit.visit_id` 를 그대로 안 넘긴다",
  );
});

test("고른 진료가 없으면 아무 데도 안 간다", () => {
  const branch = nextBranch();

  /* 없는 채로 보내면 `?visit=undefined` 가 붙고, `shell.js` 의 `entry` 가
     `Number(undefined)` → `NaN` 으로 아무 줄도 못 찾는다. 그러면 예전과 똑같이
     맨 위 줄이 열린다 — 고친 뜻이 없어진다. */
  assert.match(branch, /if\s*\(\s*!visit\s*\|\|\s*!visit\.visit_id\s*\)\s*return/, "빈 진료를 안 막는다");
});

test("받는 쪽이 `?visit=` 을 읽는다 — 보내기만 하면 소용없다", () => {
  const shell = read("js/shell.js");
  const html = read("ocr-review.html");

  assert.match(shell, /q\.get\("visit"\)/, "`shell.js` 가 `?visit=` 을 안 읽는다");
  assert.match(html, /src="\/js\/shell\.js"/, "판독 화면이 `shell.js` 를 안 읽는다 — 실어 보내도 받을 곳이 없다");
});

test("올린 뒤 바뀐 분류의 칩을 켠다 — 안 켜면 그 줄이 목록에서 걸러진다", () => {
  const shell = read("js/shell.js");

  assert.match(shell, /function showTabOf\(/, "지목한 진료의 칩을 켜는 자리가 없다");
  const loadDay = shell.slice(shell.indexOf("function loadDay("));
  assert.match(loadDay.slice(0, 800), /showTabOf\(/, "목록을 받은 뒤 칩을 안 켠다");
});
