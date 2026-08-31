/* **판독 확인 화면의 네 묶음** — 와이어프레임 S1-6 · S1-7.
 *
 * 서버는 값을 한 줄로 준다. 와이어프레임은 넷으로 세운다. 가르는 규칙이
 * 이 화면의 실체라, 여기서 잰다.
 *
 * 항목 목록의 정본은 `docs/decisions/KEY-234-ocr-review-fields.md` 다.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const { load } = require("./browser-shim.js");

function box() {
  return load("ocr-groups");
}

function field(type, value) {
  return { field_type: type, value: value === undefined ? "x" : value };
}

/* ── 가르기 ─────────────────────────────────────────────────────────── */

test("**처방과 검사를 가른다** — 한 줄로 두면 처방일수를 검사값처럼 훑는다", () => {
  const { splitFields } = box();

  const split = splitFields([
    field("HEMOGLOBIN", "10.2"),
    field("DURATION_DAYS", "84"),
    field("CA_125", "48"),
    field("MEDICATION_NAME", "비잔"),
  ]);

  assert.deepEqual(
    split.prescription.map((f) => f.field_type),
    ["MEDICATION_NAME", "DURATION_DAYS"],
    "처방 묶음이 틀렸다",
  );
  assert.deepEqual(
    split.labs.map((f) => f.field_type),
    ["HEMOGLOBIN", "CA_125"],
    "검사 묶음이 틀렸다",
  );
});

test("**처방은 와이어프레임 차례로 선다** — 서버 차례는 정규식 훑은 차례라 뜻이 없다", () => {
  const { splitFields } = box();

  /* 일부러 거꾸로 넣는다 */
  const split = splitFields([
    field("PRESCRIPTION_DATE"),
    field("DOSAGE"),
    field("DIAGNOSIS"),
    field("MEDICATION_NAME"),
  ]);

  assert.deepEqual(
    split.prescription.map((f) => f.field_type),
    ["DIAGNOSIS", "MEDICATION_NAME", "DOSAGE", "PRESCRIPTION_DATE"],
    "진단 → 약품명 → 1회량 → 처방일 차례여야 한다",
  );
});

test("**검사일은 줄이 아니라 묶음 머리다** — 줄로도 세우면 두 번 보인다", () => {
  const { splitFields, labDateOf } = box();

  const rows = [field("LAB_DATE", "2026-08-05"), field("HEMOGLOBIN", "10.2")];

  assert.equal(labDateOf(rows), "2026-08-05");
  assert.deepEqual(
    splitFields(rows).labs.map((f) => f.field_type),
    ["HEMOGLOBIN"],
    "검사일이 값 줄로도 섰다",
  );
});

test("모르는 항목은 검사 묶음으로 간다 — 화면에서 사라지면 안 된다", () => {
  const { splitFields } = box();

  const split = splitFields([field("NEW_MARKER", "7")]);
  assert.equal(split.labs.length, 1, "새 항목이 어느 묶음에도 안 들어갔다");
});

test("빈 목록에도 안 넘어진다", () => {
  const { splitFields, labDateOf } = box();

  assert.deepEqual(splitFields([]), { prescription: [], labs: [] });
  assert.deepEqual(splitFields(null), { prescription: [], labs: [] });
  assert.equal(labDateOf(null), "", "검사일이 없으면 빈 문자열이다");
});

/* ── 소진 예정일 ────────────────────────────────────────────────────── */

test("**소진 예정일 = 처방일 + 처방일수**", () => {
  const { runOutDate } = box();

  assert.equal(runOutDate("2026-08-13", "84"), "2026-11-05", "와이어프레임의 그 날짜다");
  assert.equal(runOutDate("2026-08-13", 84), "2026-11-05", "숫자로 와도 같아야 한다");
});

test("해를 넘기고 윤년도 센다", () => {
  const { runOutDate } = box();

  assert.equal(runOutDate("2026-01-01", "1"), "2026-01-02");
  assert.equal(runOutDate("2026-12-31", "1"), "2027-01-01", "해를 넘길 때");
  assert.equal(runOutDate("2028-02-28", "1"), "2028-02-29", "윤년");
});

test("**날짜를 `new Date(문자열)` 로 읽지 않는다** — 시간대에 따라 하루 밀린다", () => {
  /* `new Date("2026-08-13")` 은 **UTC 자정**으로 읽힌다. 한국(UTC+9)과
     UTC 에서는 그 뒤 `getDate()` 가 여전히 13 이라 답이 같지만, 미국
     (UTC-5)에서는 현지시각이 전날 19시라 12 가 나오고 **답이 하루 밀린다.**
     이 함정에 이미 한 번 걸렸다 (`shell.js` 의 `dayFromInput`).
     값으로는 우리 시간대에서 못 잡으므로 **원문으로 박는다.** */
  const fs = require("node:fs");
  const path = require("node:path");
  const source = fs.readFileSync(path.join(__dirname, "..", "js", "ocr-groups.js"), "utf8");

  const code = source
    .split("\n")
    .filter((line) => !line.trim().startsWith("/*") && !line.trim().startsWith("*"))
    .join("\n");

  assert.ok(
    !/new Date\(\s*[A-Za-z_$][\w$]*\s*\)/.test(code),
    "날짜 문자열을 그대로 `new Date()` 에 넣는 자리가 있다 — 시간대에 따라 하루 밀린다",
  );
  assert.ok(code.includes("new Date(Number("), "숫자로 뜯어 만드는 자리가 없다 — 검사가 헛돈다");
});

test("셀 수 없으면 지어내지 않는다", () => {
  const { runOutDate } = box();

  assert.equal(runOutDate("", "84"), "", "처방일이 없다");
  assert.equal(runOutDate("2026-08-13", ""), "", "처방일수가 없다");
  assert.equal(runOutDate("2026-08-13", "0"), "", "0일 처방은 없다");
  assert.equal(runOutDate("몰라", "84"), "", "날짜가 아니다");
});

/* ── 28일 미만 ──────────────────────────────────────────────────────── */

test("**총투가 알 수로 찍혀 오는 일이 있다** — 28 미만이면 여쭙는다", () => {
  const { courseWarn } = box();

  assert.match(courseWarn("14"), /28/, "짧은 처방을 안 짚는다");
  assert.equal(courseWarn("84"), "", "정상 처방에 경고를 띄우면 아무도 안 읽는다");
  /* 경계를 박는다. 이 줄이 없으면 `n < 27` 로 바꿔도 검사가 안 문다. */
  assert.equal(courseWarn("28"), "", "28 은 미만이 아니다");
  assert.match(courseWarn("27"), /28/, "27 은 미만이다 — 경계가 28 이어야 한다");
  assert.equal(courseWarn(""), "", "값이 없으면 할 말이 없다");
});

test("여쭙는 것이지 막는 것이 아니다 — 짧은 처방도 있다", () => {
  const { courseWarn } = box();

  /* 문구가 「확인해 주세요」여야 한다. 「잘못됐습니다」로 쓰면 스탭이
     맞는 값을 고치려 든다. */
  assert.match(courseWarn("14"), /확인/);
  assert.ok(!/잘못|오류|실패/.test(courseWarn("14")), "맞는 값을 틀렸다고 말한다");
});

/* ── ③④ 아직 없는 묶음 ─────────────────────────────────────────────── */

test("**서버에 자리가 없는 묶음은 그렇다고 말한다** — 목업으로 채우지 않는다", () => {
  const { GROUPS_WITHOUT_SERVER } = box();

  assert.equal(GROUPS_WITHOUT_SERVER.length, 2, "③ 이전 값 유지 · ④ 확인 항목");

  for (const group of GROUPS_WITHOUT_SERVER) {
    assert.ok(group.title, `${group.key} 에 이름이 없다`);
    assert.match(group.saying, /아직|없습니다/, `${group.key} 가 되는 것처럼 말한다`);
    assert.ok(group.needs, `${group.key} 에 무엇이 필요한지 안 적혀 있다`);
  }
});

test("채울 것이 생기면 채운다 — 영영 점선으로 두는 자리가 아니다", () => {
  const { groupIsReady } = box();

  assert.equal(groupIsReady("carried", {}), false);
  assert.equal(groupIsReady("carried", { carried: [] }), false, "빈 배열은 아직 없는 것이다");
  assert.equal(groupIsReady("carried", { carried: [{}] }), true);
});

/* ── 화면에 실제로 서는가 ──────────────────────────────────────────── */

const fs = require("node:fs");
const path = require("node:path");

const ROOT = path.join(__dirname, "..");

function source(rel) {
  return fs.readFileSync(path.join(ROOT, rel), "utf8");
}

/** 주석 줄을 뺀 코드만. 내 설명글에 이름이 있으면 있는 걸로 세어 버린다. */
function codeOnly(text) {
  return text
    .split("\n")
    .filter((line) => {
      const t = line.trim();
      return !t.startsWith("//") && !t.startsWith("/*") && !t.startsWith("*") && !t.startsWith("<!--");
    })
    .join("\n");
}

test("**판독 화면이 이 규칙으로 묶음을 세운다** — 규칙만 있고 안 쓰면 소용없다", () => {
  const code = codeOnly(source("js/ocr-review.js"));

  assert.ok(code.includes("splitFields("), "값을 가르지 않고 한 줄로 그린다");
  assert.ok(code.includes("runOutDate("), "소진 예정일을 안 센다");

  /* 세는 것과 보여 주는 것은 다르다 — `runOutDate` 를 부르고 그 값을 버려도
     위 줄은 통과한다. 계산한 값이 실제로 머리줄에 실리는지 본다.
     이 프로그램이 하는 일 자체가 「소진 임박에 안내를 보낸다」라, 이 날짜가
     화면에 없으면 스탭이 무엇을 확인해야 하는지 모른다. */
  assert.match(
    code,
    /until[\s\S]{0,200}meta\.push\([^)]*소진 예정일/,
    "소진 예정일을 세기만 하고 화면에 안 싣는다",
  );
  /* 갈래(`|`)를 느슨하게 두면 「계산」이 아무 데나 있어도 통과한다 — 처음에
     그렇게 썼고 돌연변이가 살아남았다. 붙어 있는 것만 본다. */
  assert.ok(code.includes('" (계산)"'), "계산한 값이라고 안 밝힌다 — 스탭이 원문에서 찾으려 든다");
  assert.ok(code.includes("courseWarn("), "28일 미만을 안 짚는다");
  assert.ok(code.includes("GROUPS_WITHOUT_SERVER"), "아직 없는 묶음을 안 세운다");

  /* 예전처럼 목록을 통째로 map 하는 자리가 남으면 묶음이 무너진다 */
  assert.ok(
    !/result\.fields\s*\n?\s*\.map\(/.test(code),
    "값 목록을 통째로 그리는 자리가 남았다 — 묶음이 안 선다",
  );
});

test("**화면이 두 파일을 싣는다** — 안 실으면 브라우저에서 함수가 없다", () => {
  const page = source("ocr-review.html");

  assert.ok(page.includes("/js/ocr-groups.js"), "ocr-groups.js 를 안 싣는다");
  assert.ok(
    page.indexOf("/js/ocr-groups.js") < page.indexOf("/js/ocr-review.js"),
    "판독 화면보다 늦게 실린다 — 부를 때 없다",
  );
});

test("**눌러도 아무 일 없는 버튼을 두지 않는다** — 왼쪽 판의 두 버튼", () => {
  /* 「된다」고 말해 놓고 아무 데도 안 가는 버튼이 1차 시연을 멈춘 방식이다.
     이 화면에 새로 놓은 버튼은 모두 갈 곳이 있어야 한다. */
  const page = codeOnly(source("ocr-review.html"));
  const code = codeOnly(source("js/ocr-review.js"));

  const buttons = page.split("\n").filter((line) => line.includes("<button"));
  const inPanel = buttons.filter((line) => line.includes("button--quiet"));
  assert.equal(inPanel.length, 2, "왼쪽 판의 버튼이 둘이 아니다 — 검사가 헛돈다");

  for (const line of inPanel) {
    const m = /data-go="([^"]+)"/.exec(line);
    assert.ok(m, `갈 곳이 없는 버튼이다: ${line.trim()}`);
    assert.ok(code.includes('data-go'), "누른 것을 받는 자리가 없다");
  }
});

test("**같은 `id` 를 두 번 만들지 않는다** — 판독 실패 상자가 「재업로드」를 또 만든다", () => {
  /* `#work` 는 숨겨져도 문서에 남는다. 왼쪽 판과 상태 상자가 같은 `id` 를
     쓰면 한 문서에 이름이 둘이 되고, `getElementById` 는 앞의 것만 준다. */
  const page = source("ocr-review.html");
  const code = source("js/ocr-review.js");

  const madeByJs = [...code.matchAll(/id="([a-z-]+)"/g)].map((m) => m[1]);
  const inPage = [...page.matchAll(/\bid="([a-z-]+)"/g)].map((m) => m[1]);

  const clash = madeByJs.filter((id) => inPage.includes(id));
  assert.deepEqual(clash, [], `화면과 스크립트가 같은 id 를 만든다: ${clash.join(", ")}`);
});
