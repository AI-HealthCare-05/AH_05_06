/* **목록 줄은 서버가 준 줄이어야 한다** — 등록 직후 이름이 비던 버그.
 *
 * 환자를 등록하면 목록 줄에 이름이 안 뜨고 머리말이 「차트 undefined」로 떴다.
 * 「환자 정보」 카드에는 이름·차트번호가 제대로 있었다 — 같은 데이터를 다른
 * 이름으로 읽고 있었다.
 *
 * 원인: `addVisit()` 이 `POST /visits` 응답을 그대로 목록에 밀어 넣었다.
 * 두 응답의 모양이 다르다.
 *
 *     오늘 목록  FrontDeskVisitItem   name · hospital_patient_no · age ·
 *                                     diagnosis_name · work_category · detail_status
 *     진료 생성  VisitResponse        doctor_id · department · status · planned_stop …
 *
 * 이 파일은 **화면이 읽는 칸이 어느 DTO 에 있는지**를 서버 원문과 대조한다.
 * 구조 진단 §5.2 의 「응답 구조에 대한 단일 기준 부재」가 이 버그의 뿌리이고,
 * 여기가 그 대조를 붙이는 첫 자리다.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const { load } = require("./browser-shim.js");

const ROOT = path.join(__dirname, "..");
const DTOS = path.join(ROOT, "..", "app", "dtos");

function read(rel) {
  return fs.readFileSync(path.join(ROOT, rel), "utf8");
}

/* 서버 DTO 의 필드 이름을 뽑는다. `이름: 타입` 꼴만 센다 — 메서드·주석은 뺀다. */
function dtoFields(file, className) {
  const source = fs.readFileSync(path.join(DTOS, file), "utf8");
  const at = source.indexOf(`class ${className}(`);
  assert.notEqual(at, -1, `${className} 이 ${file} 에 없다 — 검사가 헛돈다`);

  const body = source.slice(source.indexOf("\n", at), source.indexOf("\nclass ", at + 1) + 1 || undefined);
  const names = [];
  for (const line of body.split("\n")) {
    const m = /^ {4}([a-z_][a-z0-9_]*)\s*:/.exec(line);
    if (m) names.push(m[1]);
  }
  assert.ok(names.length > 3, `${className} 필드를 못 읽었다 — 검사가 헛돈다`);
  return names;
}

/* 화면 코드에서 `r.` · `row.` 로 읽는 칸을 뽑는다. */
function fieldsReadFrom(source, holder) {
  const found = new Set();
  for (const m of source.matchAll(new RegExp(`\\b${holder}\\.([a-z_][a-z0-9_]*)`, "g"))) {
    found.add(m[1]);
  }
  return [...found];
}

const FRONT_DESK = dtoFields("front_desk.py", "FrontDeskVisitItem");
const VISIT = dtoFields("visits.py", "VisitResponse");

/* ── 두 응답이 실제로 다른가 ──────────────────────────────────────────── */

test("**진료 생성 응답에는 목록 줄이 읽는 칸이 없다** — 그래서 밀어 넣으면 빈다", () => {
  for (const field of ["name", "hospital_patient_no", "work_category", "detail_status"]) {
    assert.ok(FRONT_DESK.includes(field), `오늘 목록에 ${field} 가 없다 — 계약이 바뀌었다`);
    assert.ok(
      !VISIT.includes(field),
      `진료 생성 응답에 ${field} 가 생겼다 — 이 검사의 전제가 바뀌었으니 다시 보라`,
    );
  }
});

/* ── 화면이 읽는 칸이 목록 계약에 다 있는가 ───────────────────────────── */

test("목록 줄이 읽는 칸이 모두 오늘 목록 계약에 있다", () => {
  const rowHtml = read("js/shell.js");
  const start = rowHtml.indexOf("function rowHtml(");
  assert.notEqual(start, -1, "rowHtml 이 없다 — 검사가 헛돈다");

  const body = rowHtml.slice(start, rowHtml.indexOf("\nfunction ", start + 10));
  const reads = fieldsReadFrom(body, "r").filter((f) => f !== "dataset");

  assert.ok(reads.length > 3, "읽는 칸을 못 뽑았다 — 검사가 헛돈다");
  for (const field of reads) {
    assert.ok(FRONT_DESK.includes(field), `목록 줄이 계약에 없는 칸을 읽는다: r.${field}`);
  }
});

test("환자 머리말이 읽는 칸도 오늘 목록 계약에 있다", () => {
  const detail = read("js/detail.js");
  const start = detail.indexOf("function renderHead(");
  assert.notEqual(start, -1, "renderHead 가 없다 — 검사가 헛돈다");

  const body = detail.slice(start, detail.indexOf("\n  function ", start + 10));
  const reads = fieldsReadFrom(body, "row");

  assert.ok(reads.length > 2, "읽는 칸을 못 뽑았다 — 검사가 헛돈다");
  for (const field of reads) {
    assert.ok(FRONT_DESK.includes(field), `머리말이 계약에 없는 칸을 읽는다: row.${field}`);
  }
});

/* ── 등록 직후 목록을 서버에서 다시 받는가 ────────────────────────────── */

test("**`addVisit` 이 진료 생성 응답을 목록에 밀어 넣지 않는다**", () => {
  const source = read("js/shell.js");
  const start = source.indexOf("function addVisit(");
  assert.notEqual(start, -1, "addVisit 이 없다 — 검사가 헛돈다");

  const body = source.slice(start, source.indexOf("\n/* 오늘 목록에 이 환자", start));

  assert.ok(
    !/rows\.unshift\(/.test(body),
    "생성 응답을 목록에 그대로 넣는다 — 이름·차트번호·상태가 빈다",
  );
  assert.ok(body.includes("loadDay()"), "목록을 서버에서 다시 받지 않는다");
});

test("탭을 켤 때 쓰는 상태도 서버가 준 줄에서 읽는다", () => {
  const source = read("js/shell.js");
  const start = source.indexOf("function addVisit(");
  const body = source.slice(start, source.indexOf("\n/* 오늘 목록에 이 환자", start));

  /* `visit.work_category` 는 생성 응답의 칸이라 늘 undefined 다.
     서버에서 다시 받은 줄(`made`)에서 읽어야 한다. */
  assert.ok(
    !/visit\.work_category/.test(body),
    "생성 응답에서 상태를 읽는다 — 그 칸은 계약에 없어 늘 undefined 다",
  );
});

/* ── 줄 찾기 ─────────────────────────────────────────────────────────── */

test("진료 번호로 서버가 준 줄을 찾는다", () => {
  const { rowByVisit } = load("api", "session", "patients-api", "shell");

  const rows = [
    { visit_id: 1, name: "김서연" },
    { visit_id: 2, name: "서연수" },
  ];
  assert.strictEqual(rowByVisit(rows, 2).name, "서연수");
  assert.strictEqual(rowByVisit(rows, 9), null, "없는 번호에 엉뚱한 줄을 준다");
  assert.strictEqual(rowByVisit([], 1), null);
  assert.strictEqual(rowByVisit(null, 1), null);
});
