/* KEY-274: 실판독 OCR 필수 필드 미인식 → 판독 확인 화면 확정 불가 버그
 *
 * 버그 두 건을 원문으로 재고, 순수 규칙은 직접 부른다.
 *
 * (a) renderFields() 가 2.5초 자동저장 타이머로 재호출될 때
 *     data-manual-drug-name / data-manual-drug-days 입력칸의 포커스를
 *     [data-input] 처럼 복원하는지 — 안 하면 글자마다 커서가 빠진다.
 *
 * (b) topRowHtml() 이 OCR 미인식 상황에서 DURATION_DAYS 미확정 값이 있으면
 *     셀을 숨기지 않는지 — 숨기면 확정할 경로가 없고 generate 가 영구 422 다.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const { load } = require("./browser-shim.js");

const ROOT = path.join(__dirname, "..");

function source() {
  return fs.readFileSync(path.join(ROOT, "js", "ocr-review.js"), "utf8");
}

function box() {
  return load("api", "session", "patients-api", "shell", "ocr-api", "ocr-review");
}

/* ── (a) 수동 입력칸 포커스 복원 ───────────────────────────────────────── */

test("renderFields 가 data-manual-drug-name 속성을 포커스 복원 대상으로 본다", () => {
  const src = source();
  const rfStart = src.indexOf("function renderFields()");
  assert.notEqual(rfStart, -1, "renderFields 함수가 없다 — 검사가 헛돈다");

  /* 다음 function 선언 전까지를 함수 바디로 본다 */
  const rfBody = src.slice(rfStart, src.indexOf("\n  function ", rfStart + 1));

  assert.ok(
    rfBody.includes("data-manual-drug-name"),
    "renderFields 가 data-manual-drug-name 을 모른다 — 타이머 재렌더 시 포커스가 빠진다",
  );
  assert.ok(
    rfBody.includes("data-manual-drug-days"),
    "renderFields 가 data-manual-drug-days 를 모른다 — 타이머 재렌더 시 포커스가 빠진다",
  );
});

test("renderFields 가 수동 입력칸 복원 후 조기 return 한다 — 일반 칸 복원과 겹치지 않는다", () => {
  const src = source();
  const rfStart = src.indexOf("function renderFields()");
  const rfBody = src.slice(rfStart, src.indexOf("\n  function ", rfStart + 1));

  /* isManualTyping 이 참일 때 return 하는 분기가 있어야 한다 */
  assert.ok(
    rfBody.includes("isManualTyping"),
    "수동 입력 여부를 판단하는 변수가 없다",
  );

  /* 수동 입력칸 복원 분기 안에 return 이 있는지 — 없으면 일반 [data-input] 복원도 이어진다.
     if (wanted === null && isManualTyping) { ... return; } 형태여야 한다. */
  const manualBranchStart = rfBody.lastIndexOf("isManualTyping");
  assert.notEqual(manualBranchStart, -1, "수동 입력 복원 분기를 못 찾았다 — 검사가 헛돈다");
  const manualBranch = rfBody.slice(manualBranchStart, manualBranchStart + 450);
  assert.ok(manualBranch.includes("return"), "수동 입력 복원 후 return 이 없다 — 일반 복원이 덮어쓴다");
});

/* ── (b) DURATION_DAYS 미확정 값 있을 때 셀 표시 ───────────────────────── */

test("topRowHtml 이 anySetDrugInOcr 만으로 DURATION_DAYS 를 무조건 숨기지 않는다", () => {
  const src = source();

  /* 수정 전 패턴 — 이 줄이 그대로 남아 있으면 버그가 다시 생긴 것이다 */
  const oldPattern = /if\s*\(\s*spec\.type\s*===\s*["']DURATION_DAYS["']\s*&&\s*!anySetDrugInOcr\s*\)\s*return\s*""\s*;/;
  assert.ok(
    !oldPattern.test(src),
    "anySetDrugInOcr 만으로 DURATION_DAYS 를 무조건 숨긴다 — 미확정 값이 있으면 확정할 경로가 없다",
  );
});

test("topRowHtml 이 DURATION_DAYS 미확정 여부를 확인한다 — 미확정 값이 있으면 셀을 표시해야 한다", () => {
  const src = source();
  const topRowStart = src.indexOf("function topRowHtml(");
  assert.notEqual(topRowStart, -1, "topRowHtml 이 없다 — 검사가 헛돈다");

  const topRowBody = src.slice(topRowStart, src.indexOf("\n  function ", topRowStart + 1));

  assert.ok(
    topRowBody.includes("durationNeedsConfirm"),
    "DURATION_DAYS 미확정 여부를 계산하지 않는다 — 미인식 케이스에서 영구 422 가 된다",
  );
  assert.ok(
    topRowBody.includes("!durationNeedsConfirm"),
    "durationNeedsConfirm 을 조건에 쓰지 않는다 — 미확정 값이 있어도 셀을 숨긴다",
  );
});

test("is_confirmed 와 value 를 함께 본다 — 값 없는 미확정은 generate 를 막지 않는다", () => {
  /* read_but_unconfirmed(Python) 은 value AND !is_confirmed 를 조건으로 쓴다.
     값이 없으면 게이트를 안 막으므로, 화면도 값이 있을 때만 표시하면 된다. */
  const src = source();
  const topRowStart = src.indexOf("function topRowHtml(");
  const topRowBody = src.slice(topRowStart, src.indexOf("\n  function ", topRowStart + 1));

  /* durationNeedsConfirm 계산식에 .value 와 .is_confirmed 가 모두 있어야 한다 */
  const declStart = topRowBody.indexOf("durationNeedsConfirm");
  const declLine = topRowBody.slice(declStart, topRowBody.indexOf(";", declStart) + 1);

  assert.ok(declLine.includes(".value"), `durationNeedsConfirm 이 value 를 안 본다: 「${declLine.trim()}」`);
  assert.ok(
    declLine.includes(".is_confirmed") || declLine.includes("is_confirmed"),
    `durationNeedsConfirm 이 is_confirmed 를 안 본다: 「${declLine.trim()}」`,
  );
});

/* ── fieldsToConfirm — 값 있는 미확정만 확정한다 (기존 규칙 회귀 방지) ─── */

test("DURATION_DAYS 에 값이 있으면 확정 목록에 올라간다", () => {
  const { fieldsToConfirm } = box();

  const fields = [
    { ocr_field_id: 1, field_type: "DIAGNOSIS", value: "자궁내막증", is_confirmed: false },
    { ocr_field_id: 2, field_type: "DURATION_DAYS", value: "84", is_confirmed: false },
    { ocr_field_id: 3, field_type: "MEDICATION_NAME", value: null, is_confirmed: false },
  ];

  const ids = fieldsToConfirm(fields).map((f) => f.ocr_field_id);
  assert.ok(ids.includes(2), "DURATION_DAYS(값 있음, 미확정)이 확정 목록에 없다 — generate 가 영구 422 다");
  assert.ok(!ids.includes(3), "MEDICATION_NAME(값 없음)이 확정 목록에 들어갔다 — 빈 값이 안내문에 실린다");
});

test("DURATION_DAYS 가 이미 확정됐으면 다시 보내지 않는다", () => {
  const { fieldsToConfirm } = box();

  const fields = [
    { ocr_field_id: 2, field_type: "DURATION_DAYS", value: "84", is_confirmed: true },
  ];

  const ids = fieldsToConfirm(fields).map((f) => f.ocr_field_id);
  assert.ok(!ids.includes(2), "이미 확정된 DURATION_DAYS 를 다시 보낸다 — 서버가 409 를 낸다");
});
