/* **판독 항목의 한글 이름표** — `js/field-labels.js`.
 *
 * 스탭이 판독 화면에서 「MEDICATION_NAME」을 읽고 있었다. 서버가 주는 코드를
 * 화면이 그대로 찍었기 때문이다.
 *
 * 목업(`ocr-api.js`)은 처음부터 한글을 줬다. 그래서 `?mock=1` 로 보면 멀쩡하고
 * 실서버에서만 영문이 떴다 — 구조 진단이 「목업이 자기 자신을 정본으로 삼는다」
 * 고 적은 그 모양이다. 그래서 이 파일은 **목업이 아니라 서버 코드**를 정본으로
 * 삼는다: `ai_worker/tasks/field_extractor.py` 가 실제로 만들어 내는 코드를
 * 읽어다 대조한다. 서버에 코드가 하나 늘면 이 검사가 먼저 깨진다.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const { load } = require("./browser-shim.js");

const ROOT = path.join(__dirname, "..");
const REPO = path.join(ROOT, "..");

function box() {
  return load("field-labels");
}

function read(rel) {
  return fs.readFileSync(path.join(REPO, rel), "utf8");
}

/** 서버가 실제로 붙이는 `field_type` 값을 추출기 원문에서 긁어 온다. */
function serverFieldTypes() {
  const source = read("ai_worker/tasks/field_extractor.py");

  /* `"MEDICATION_NAME"` 처럼 따옴표 안의 대문자 상수만 고른다. 주석은 뺀다 —
     내 설명글에 코드 이름이 있으면 있는 걸로 세어 버린다(이 함정에 이미 걸렸다). */
  const code = source
    .split("\n")
    .filter((line) => !line.trim().startsWith("#"))
    .join("\n");

  const found = new Set();
  /* `{2,}` 로 두었더니 **두 글자 코드를 못 봤다** — `E2` 가 그렇게 빠졌다.
     길이로 거르는 대신 「대문자로 시작하고 숫자·밑줄만 잇는다」로 본다. */
  for (const m of code.matchAll(/"([A-Z][A-Z0-9_]*)"/g)) {
    if (m[1].length < 2) continue; /* 한 글자는 코드가 아니다 */
    found.add(m[1]);
  }
  return found;
}

test("**서버가 주는 코드에 이름표가 다 있다** — 하나라도 빠지면 그 줄만 영문이 뜬다", () => {
  const { FIELD_LABELS } = box();
  const server = serverFieldTypes();

  assert.ok(server.size >= 10, `추출기에서 코드를 못 찾았다 (${server.size}개) — 검사가 헛돈다`);

  const missing = [...server].filter((code) => !(code in FIELD_LABELS));
  assert.deepEqual(missing, [], `이름표가 없다: ${missing.join(", ")}`);
});

test("**이름표가 한글이다** — 영문을 넣어 두면 고친 티가 안 난다", () => {
  const { FIELD_LABELS } = box();

  for (const [code, label] of Object.entries(FIELD_LABELS)) {
    /* AMH · CRP 처럼 한국 병원에서도 영문 약어로 부르는 것은 그대로 둔다.
       기준은 「의료진이 실제로 그렇게 부르는가」이지 문자 종류가 아니다. */
    if (["AMH", "CRP", "AST_ALT", "CA_125", "CA19_9"].includes(code)) continue;
    assert.match(label, /[가-힣]/, `「${code}」의 이름표가 한글이 아니다: ${label}`);
  }
});

test("**모르는 코드는 그대로 보여 준다** — 빈칸으로 두면 값이 있는데 없는 것처럼 보인다", () => {
  const { fieldLabel } = box();

  assert.equal(fieldLabel("NEW_THING"), "NEW_THING", "새 코드가 화면에서 사라졌다");
  assert.equal(fieldLabel("MEDICATION_NAME"), "약품명");
  assert.equal(fieldLabel(""), "", "빈 값은 빈 값이다");
  assert.equal(fieldLabel(null), "", "null 이 「null」로 찍히면 안 된다");
  assert.equal(fieldLabel(undefined), "");
});

test("**판독 화면이 이 이름표를 실제로 쓴다** — 규칙만 있고 안 쓰면 소용없다", () => {
  /* 그리는 코드는 shim 아래서 안 돌기 때문에 원문으로 잰다. 전에 이 자리가
     `escapeHtml(field.field_type)` 이었고, 그게 영문이 뜬 이유다. */
  const source = fs.readFileSync(path.join(ROOT, "js/ocr-review.js"), "utf8");

  const code = source
    .split("\n")
    .filter((line) => !line.trim().startsWith("/*") && !line.trim().startsWith("*"))
    .join("\n");

  assert.ok(code.includes("fieldLabel(field.field_type)"), "항목 이름을 이름표 없이 그린다");
  assert.ok(
    !/escapeHtml\(\s*field\.field_type\s*\)/.test(code),
    "서버 코드를 그대로 그리는 자리가 남았다 — 「MEDICATION_NAME」이 화면에 뜬다",
  );
});

test("**화면이 이름표 파일을 싣는다** — 안 실으면 브라우저에서 `fieldLabel is not defined`", () => {
  const page = fs.readFileSync(path.join(ROOT, "ocr-review.html"), "utf8");

  assert.ok(page.includes("/js/field-labels.js"), "ocr-review.html 이 field-labels.js 를 안 싣는다");

  /* 순서도 잰다 — 얹기만 하는 구조라 늦게 실리면 부를 때 없다. */
  assert.ok(
    page.indexOf("/js/field-labels.js") < page.indexOf("/js/ocr-review.js"),
    "이름표가 판독 화면보다 늦게 실린다",
  );
});

test("단위는 서버 값이 우선이다 — 여기 것은 없을 때만 쓴다", () => {
  const { fieldUnit } = box();

  assert.equal(fieldUnit("HEMOGLOBIN", "mg/dL"), "mg/dL", "서버가 준 단위를 덮어썼다");
  assert.equal(fieldUnit("HEMOGLOBIN", ""), "g/dL", "서버가 안 줬는데 기본값도 안 나온다");
  assert.equal(fieldUnit("NEW_THING", ""), "", "모르는 항목에 단위를 지어내면 안 된다");
});

/* ── 구버전 이름 ─────────────────────────────────────────────────────── */

test("**개명 이전 이름도 읽는다** — 그 행들이 DB 에 남아 있다", () => {
  /* 항목 이름이 2026-08-28(`82a2fc2`)에 바뀌었는데, 그 전에 쌓인 행은
     그대로 남는다 — `unique_together` 가 (결과, 항목이름) 이라 새 이름으로
     다시 넣어도 옛 행이 안 사라진다. 화면에 영문이 뜬 것이 이것이었다. */
  const { fieldLabel } = box();

  assert.equal(fieldLabel("PRESCRIPTION_NAME"), "약품명");
  assert.equal(fieldLabel("PRESCRIPTION_DURATION"), "처방일수");
});

test("구버전 이름이 **처방 묶음**으로 간다 — 검사값 사이에 약 이름이 끼면 안 된다", () => {
  const { splitFields } = load("ocr-groups");

  const split = splitFields([
    { field_type: "PRESCRIPTION_NAME", value: "비잔" },
    { field_type: "HEMOGLOBIN", value: "10.2" },
  ]);
  assert.deepEqual(
    split.prescription.map((f) => f.field_type),
    ["PRESCRIPTION_NAME"],
    "약품명이 처방 묶음에 없다",
  );
  assert.deepEqual(split.labs.map((f) => f.field_type), ["HEMOGLOBIN"]);
});

test("**옛 이름을 새로 만들지는 않는다** — 추출기가 안 만드는 것을 화면이 되살리면 안 된다", () => {
  /* 서버 어휘 대조 검사가 「추출기에 있는 것이 이름표에 다 있는가」를 보는데,
     그 반대(이름표에만 있는 것)는 **있어도 된다** — 읽기용이기 때문이다.
     다만 그것이 무엇인지는 적혀 있어야 한다. */
  const source = fs.readFileSync(path.join(ROOT, "js/field-labels.js"), "utf8");
  const at = source.indexOf("PRESCRIPTION_NAME:");
  assert.notEqual(at, -1, "구버전 이름이 없다 — 검사가 헛돈다");

  const before = source.slice(Math.max(0, at - 900), at);
  assert.match(before, /구버전|개명/, "왜 있는지가 안 적혀 있다 — 다음 사람이 지운다");
});
