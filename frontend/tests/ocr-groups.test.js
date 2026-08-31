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
const { markupOnly } = require("./source.js");

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

  /* **막힌 곳이 서로 다르다.** 뭉뚱그려 「서버에 자리가 없습니다」로 두면
     판독 API 를 맡는 사람이 둘 다 표부터 만들어야 하는 줄 안다. */
  const byKey = Object.fromEntries(GROUPS_WITHOUT_SERVER.map((g) => [g.key, g]));

  assert.match(byKey.carried.saying, /저장돼 있고|이미/, "③ 은 값이 이미 있다는 것을 말해야 한다");
  assert.match(byKey.carried.needs, /길|꺼내/, "③ 에 필요한 것은 표가 아니라 길이다");

  assert.match(byKey.checks.needs, /표부터|표가 없다/, "④ 는 표부터 없다는 것을 말해야 한다");
  assert.ok(
    byKey.carried.saying !== byKey.checks.saying,
    "두 문구가 같다 — 막힌 곳이 다른데 같은 말을 한다",
  );
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

test("**「재업로드」와 「검사지 추가」가 하나로 합쳐졌다** — 같은 일이었다", () => {
  /* 둘 다 사진을 한 장 더 보내는 일이다. 갈래를 물으면 스탭이 매번 어느
     칸인지 고민하고, 그 답은 쓰이지도 않는다 — 문서를 「이미지1 · 이미지2」로
     부르는 것과 같은 판단이다. */
  const page = markupOnly(source("ocr-review.html"));

  /* 클래스 이름으로 찾지 않는다 — 이름을 바꾸면 검사가 조용히 0개를 세고
     통과한다(그렇게 한 번 새어 나갔다). **자리로** 찾는다. */
  const acts = page.slice(page.indexOf('<div class="raw-acts">'));
  const inPanel = acts.slice(0, acts.indexOf("</div>")).split("\n").filter((line) => line.includes("<button"));
  assert.equal(inPanel.length, 1, `왼쪽 판의 버튼이 ${inPanel.length}개다 — 하나여야 한다`);
  assert.ok(!page.includes("검사지 추가"), "「검사지 추가」가 아직 남아 있다");
});

test("**그 자리에서 올린다** — 업로드 화면으로 보내면 보던 값을 잃는다", () => {
  const page = markupOnly(source("ocr-review.html"));
  const code = codeOnly(source("js/ocr-review.js"));

  assert.ok(page.includes('id="add-panel"'), "올리는 판이 없다");
  assert.ok(page.includes('id="drop2"'), "끌어다 놓을 자리가 없다");
  assert.ok(page.includes('id="pick2"'), "파일을 고를 길이 없다");

  /* 판이 처음부터 펴져 있으면 원문 칸이 밀린다 — 주인공은 판독 값이다 */
  const at = page.indexOf('id="add-panel"');
  assert.match(page.slice(at, at + 40), /hidden/, "판이 처음부터 펴져 있다");

  assert.ok(code.includes("wireAddPanel"), "판을 배선하는 자리가 없다");
  assert.ok(code.includes("aria-expanded"), "펴졌는지를 화면낭독기가 모른다");

  /* **업로드 화면으로 보내지 않는다** — 옛 길이 남아 있으면 안 된다 */
  assert.ok(
    !/data-go=/.test(page),
    "아직 업로드 화면으로 보내는 버튼이 있다 — 갔다 오면 보던 값을 잃는다",
  );
});

test("**올리는 사이 다른 환자를 골라도 남의 진료에 안 붙는다**", () => {
  const code = codeOnly(source("js/ocr-review.js"));
  const at = code.indexOf("function send(");
  assert.notEqual(at, -1, "보내는 자리가 없다 — 검사가 헛돈다");

  const body = code.slice(at, at + 1400);
  assert.ok(body.includes("var wantedId"), "어느 진료에 올리는지 안 붙잡는다");
  assert.ok(
    /postDocument\(wantedId/.test(body),
    "붙잡은 것을 안 쓰고 그때그때의 visit 을 쓴다 — 남의 진료에 사진이 붙는다",
  );
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

/* ── 문서 이름 ───────────────────────────────────────────────────────── */

test("**올린 차례로 번호를 매긴다** — 종류는 짐작이라 틀리면 값보다 이름을 의심하게 된다", () => {
  const { documentName } = box();

  const docs = [{ document_id: 7 }, { document_id: 3 }, { document_id: 11 }];
  assert.equal(documentName(docs, 7), "이미지1", "첫 번째로 올린 것이 이미지1 이다");
  assert.equal(documentName(docs, 3), "이미지2");
  assert.equal(documentName(docs, 11), "이미지3");
});

test("모르는 문서에는 이름을 지어내지 않는다", () => {
  const { documentName } = box();

  assert.equal(documentName([{ document_id: 1 }], 99), "", "없는 문서에 번호를 붙였다");
  assert.equal(documentName(null, 1), "");
  assert.equal(documentName([], 1), "");
});

test("**종류 이름을 쓰지 않는다** — 업로드에서 종류 고르기를 없앤 것과 같은 판단", () => {
  const code = codeOnly(source("js/ocr-review.js"));

  assert.ok(
    !/doc\.label\s*\|\|\s*doc\.document_type/.test(code),
    "문서 종류를 이름으로 쓰는 자리가 남았다 — 짐작이 틀리면 스탭이 값을 의심한다",
  );
  assert.ok(code.includes("documentName("), "번호를 안 쓴다");
});

test("탭 이름도 값 옆 출처도 **같은 이름**이다 — 다르면 같은 사진인지 알 수 없다", () => {
  const code = codeOnly(source("js/ocr-review.js"));

  /* 탭(renderDocTabs) · 값 옆 배지(sourceChip) · 후보 줄(candidateRows) 셋 다 */
  const uses = (code.match(/documentName\(/g) || []).length;
  assert.ok(uses >= 3, `문서 이름을 짓는 자리가 ${uses}곳이다 — 탭·출처·후보 셋 모두여야 한다`);
});

/* ── 없는 줄도 세운다 ────────────────────────────────────────────────── */

test("**판독이 못 찾은 처방 항목도 자리에 선다** — 안 세우면 빠진 채로 안내문이 만들어진다", () => {
  const { withMissingRows, PRESCRIPTION_CORE } = box();

  assert.equal(PRESCRIPTION_CORE.length, 6, "진단·약품명·1회량·일일횟수·처방일수·처방일");

  const rows = withMissingRows([{ field_type: "MEDICATION_NAME", value: "비잔" }], PRESCRIPTION_CORE);
  assert.equal(rows.length, 6, "여섯 줄이 다 서지 않았다");
  assert.equal(rows.map((r) => r.field_type).join(","), PRESCRIPTION_CORE.join(","), "차례가 다르다");

  const med = rows.find((r) => r.field_type === "MEDICATION_NAME");
  assert.equal(med.value, "비잔", "찾은 값이 덮였다");
  assert.ok(!med.is_absent, "찾은 줄이 없는 줄로 표시됐다");

  const diag = rows.find((r) => r.field_type === "DIAGNOSIS");
  assert.equal(diag.value, null, "못 찾은 줄에 값이 생겼다");
  assert.equal(diag.is_absent, true, "못 찾은 줄이 표시가 안 됐다");
});

test("**못 찾은 줄에 가짜 번호를 주지 않는다** — 저장하려 들다가 404 를 받는다", () => {
  const { withMissingRows } = box();

  const rows = withMissingRows([], ["DIAGNOSIS"]);
  assert.equal(rows[0].ocr_field_id, undefined, "없는 항목에 번호가 붙었다");
});

test("검사값은 늘 세우지 않는다 — 안 한 검사를 열 줄씩 `?` 로 세우면 진짜 못 읽은 줄이 묻힌다", () => {
  const code = codeOnly(source("js/ocr-review.js"));
  const at = code.indexOf("function groupsHtml");
  const body = code.slice(at, at + 600);

  assert.ok(body.includes("PRESCRIPTION_CORE"), "처방 여섯을 안 세운다");
  assert.ok(
    !/withMissingRows\(\s*split\.labs/.test(body),
    "검사값까지 늘 세운다 — 안 한 검사가 못 읽은 줄처럼 보인다",
  );
});

test("**확인 항목은 꺼진 채로 세운다** — 켤 수 있으면 저장됐다고 믿는다", () => {
  const { CHECK_ITEMS } = box();
  const code = codeOnly(source("js/ocr-review.js"));

  assert.ok(CHECK_ITEMS.length >= 4, "세울 항목이 없다");

  const at = code.indexOf("function checkListHtml");
  assert.notEqual(at, -1, "확인 항목을 세우는 자리가 없다");

  const body = code.slice(at, at + 700);
  assert.ok(body.includes("disabled"), "체크할 수 있게 두었다 — 저장되지 않는데 저장됐다고 믿는다");
  assert.ok(body.includes("CHECK_ITEMS"), "항목을 여기서 지어낸다");
});

test("**원문 칸이 몇 번째 이미지인지 말한다** — 출처 배지와 같은 이름이어야 한다", () => {
  const { rawTextNote } = box();

  const docs = [{ document_id: 4 }, { document_id: 9 }];
  assert.equal(rawTextNote(docs, 4), "이미지1 에서 판독한 원문");
  assert.equal(rawTextNote(docs, 9), "이미지2 에서 판독한 원문");
});

test("이름을 못 찾으면 앞이 빈 말을 내보내지 않는다", () => {
  const { rawTextNote } = box();

  assert.equal(rawTextNote([], 1), "현재 화면에서 판독한 원문");
  assert.equal(rawTextNote(null, 1), "현재 화면에서 판독한 원문");
  assert.ok(!rawTextNote([], 1).startsWith(" "), "「 에서 판독한 원문」이 나갔다");
});

test("**화면이 그 곁말을 실제로 갈아 끼운다** — 붙박이로 두면 이미지를 옮겨도 안 바뀐다", () => {
  const code = codeOnly(source("js/ocr-review.js"));
  const page = markupOnly(source("ocr-review.html"));

  assert.ok(page.includes('id="raw-note"'), "곁말에 이름이 없다 — 갈아 끼울 수 없다");

  /* 문서를 다시 그릴 때마다 함께 바뀌어야 한다 */
  const at = code.indexOf("function renderRaw");
  const body = code.slice(at, at + 500);
  assert.ok(body.includes("rawTextNote("), "원문을 다시 그려도 곁말이 그대로다");
});

/* ── 화면에서 직접 적은 값 ───────────────────────────────────────────── */

test("**적어 넣은 값이 몇 개인지 센다** — 빈 값은 세지 않는다", () => {
  const { localFilled } = box();

  assert.deepEqual(localFilled({}), []);
  assert.deepEqual(localFilled(null), []);
  assert.deepEqual(localFilled({ DIAGNOSIS: "자궁내막증" }), ["DIAGNOSIS"]);
  assert.deepEqual(localFilled({ DIAGNOSIS: "  " }), [], "공백만 적은 것을 「적었다」로 셌다");
  assert.deepEqual(localFilled({ DIAGNOSIS: "" }), []);
});

test("**안내문에 안 실린다는 것을 말한다** — 말 안 하면 실린 줄 안다", () => {
  const { localSaying } = box();

  const say = localSaying({ DIAGNOSIS: "자궁내막증", DOSAGE: "1" });
  assert.match(say, /2/, "몇 개인지 안 말한다");
  assert.match(say, /안내문에 실리지 않습니다/, "무슨 일이 일어날지 안 말한다");
  assert.match(say, /저장되지 않아|아직/, "왜 그런지 안 말한다");

  assert.equal(localSaying({}), "", "적은 것이 없으면 할 말이 없다");
});

test("**막지 않는다** — 막으면 화면이 거기서 끝난다", () => {
  /* 판독 API 가 새 값을 못 받는 동안에도 스탭은 다음 단계로 가야 한다.
     못 읽은 값이 길을 막지 않는 것(S1-7)과 같은 판단이다. */
  const { generateBlocked } = load("api", "session", "patients-api", "shell", "ocr-api", "ocr-review");
  assert.equal(generateBlocked({ missing: 3 }, 0, false), false);

  const code = codeOnly(source("js/ocr-review.js"));
  const at = code.indexOf("localSaying(local)");
  assert.notEqual(at, -1, "알리는 자리가 없다 — 검사가 헛돈다");
  assert.ok(
    !/generateBlocked\([^)]*local/.test(code),
    "적어 넣은 값으로 생성을 막는다 — 화면이 거기서 끝난다",
  );
});

test("**다른 환자로 옮기면 지운다** — 남의 값이 「저장 안 됨」으로 뜬다", () => {
  const code = codeOnly(source("js/ocr-review.js"));
  const at = code.indexOf("function resetState");
  const body = code.slice(at, at + 400);

  assert.ok(/local\s*=\s*\{\}/.test(body), "앞 환자에게 적은 값을 안 지운다");
  assert.ok(/localEditing\s*=\s*null/.test(body), "적던 칸이 남는다");
});

test("**저장된 값과 달라 보인다** — 같아 보이면 저장된 줄 안다", () => {
  const code = codeOnly(source("js/ocr-review.js"));
  const css = source("css/ocr-review.css");

  assert.ok(code.includes("field__tag--local"), "「저장 안 됨」 표시가 없다");
  assert.ok(code.includes("저장 안 됨"), "무엇이 안 됐는지 안 적는다");

  const rule = css.slice(css.indexOf(".field__value--local"), css.indexOf(".field__tag--local"));
  assert.match(rule, /dashed/, "판독한 값과 테두리가 같다");
});
