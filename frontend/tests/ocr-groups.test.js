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
  return load("field-labels", "ocr-groups");
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
    assert.ok(group.needs, `${group.key} 에 무엇이 필요한지 안 적혀 있다`);
  }

  /* ③ 은 아직 자리가 없다 — 되는 것처럼 말하면 안 된다 */
  const carried = GROUPS_WITHOUT_SERVER.filter((g) => g.key === "carried")[0];
  assert.match(carried.saying, /아직|없습니다/, "③ 이 되는 것처럼 말한다");

  /* **④ 는 이제 된다.** 답을 담는 표가 생겼으므로 「아직 없다」를 그대로 두면
     켜 놓고도 안 남는 줄 안다 — 안전에 걸리는 항목이라 그 오해가 가장 나쁘다. */
  const checks = GROUPS_WITHOUT_SERVER.filter((g) => g.key === "checks")[0];
  assert.equal(checks.saying, "", "④ 가 아직 저장 안 된다고 말한다 — 이제 저장된다");

  /* **막힌 곳이 서로 다르다.** 뭉뚱그려 「서버에 자리가 없습니다」로 두면
     판독 API 를 맡는 사람이 둘 다 표부터 만들어야 하는 줄 안다. */
  const byKey = Object.fromEntries(GROUPS_WITHOUT_SERVER.map((g) => [g.key, g]));

  assert.match(byKey.carried.saying, /저장돼 있고|이미/, "③ 은 값이 이미 있다는 것을 말해야 한다");
  assert.match(byKey.carried.needs, /길|꺼내/, "③ 에 필요한 것은 표가 아니라 길이다");

  /* **④ 에 남은 것은 표가 아니다.** 답을 담는 표(`visit_check_answer`)는
     생겼고, 남은 것은 무엇을 여쭐지가 처방에 따라 달라지는 것뿐이다 —
     그 자리(D2-3 처방 세트)가 아직 없다. 「표부터 없다」를 그대로 두면 다음
     사람이 이미 있는 표를 또 만든다. */
  assert.match(byKey.checks.needs, /처방 세트|D2-3/, "④ 에 무엇이 남았는지가 낡았다");
  assert.ok(!/표부터 없다/.test(byKey.checks.needs), "이미 만든 표를 아직 없다고 적어 뒀다");
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

test("**왼쪽 칸이 한 블록이다** — 오른쪽만 블록이면 두 칸이 다른 화면처럼 보인다", () => {
  const page = markupOnly(source("ocr-review.html"));
  const side = page.slice(page.indexOf('<section class="side"'), page.indexOf('class="main-col"'));

  const boxes = (side.match(/<section class="box/g) || []).length;
  assert.equal(boxes, 1, `왼쪽 칸에 블록이 ${boxes}개다 — 하나여야 한다`);

  /* 탭 · 미리보기 · 원문 · 안내가 모두 그 안에 있어야 한다 */
  const box = side.slice(side.indexOf('<section class="box'));
  for (const part of ['id="doc-tabs"', 'id="doc-view"', 'id="raw"', 'id="add-panel"']) {
    assert.ok(box.includes(part), `블록 밖에 남은 것이 있다: ${part}`);
  }
});

test("**블록 머리에 올리는 단추 하나** — 이 칸에서 할 수 있는 일이 맨 위에 보인다", () => {
  const page = markupOnly(source("ocr-review.html"));
  const side = page.slice(page.indexOf('<section class="side"'), page.indexOf('class="main-col"'));

  const head = side.indexOf('class="box__head"');
  const tabs = side.indexOf('id="doc-tabs"');
  const at = side.indexOf('id="add-doc"');
  assert.ok(at !== -1, "add-doc 버튼이 없다");
  assert.ok(head < at && at < tabs, "add-doc 가 블록 머리에 없다");

  /* 갈래를 묻던 옛 버튼은 사라져야 한다 — 그 답은 쓰이지도 않는다 */
  assert.ok(!page.includes("검사지 추가"), "「검사지 추가」가 아직 남아 있다");
  assert.ok(!page.includes("재업로드"), "「재업로드」가 아직 남아 있다");
});

/* **같은 일을 하는 단추를 둘 두지 않는다.** 머리의 「판독 결과 확인」과 알림의
   「다시 확인」이 똑같이 `loadVisit` 만 했다. 늘 떠 있는 쪽은 아무것도 더 해
   주지 않으면서 「눌러야 하나」를 묻게 만든다 — 2heej 님 `#176` 리뷰. */
test("**「판독 결과 확인」은 없다** — 「다시 확인」과 같은 일을 했다", () => {
  /* **화면 이름은 그대로 둔다.** 이 판의 제목과 낭독기 머리글이 「판독 결과
     확인」이다 — 걷은 것은 단추 하나지 화면 이름이 아니다. 그래서 글자를
     세지 않고 `<button>` 안에 들어 있는지를 본다. */
  const page = markupOnly(source("ocr-review.html"));
  const buttons = page.match(/<button[\s\S]*?<\/button>/g) || [];
  assert.ok(
    !buttons.some((one) => one.includes("판독 결과 확인")),
    "걷은 단추가 화면에 남아 있다",
  );
  assert.ok(!codeOnly(source("js/ocr-review.js")).includes("reread"), "손이 남아 있다");

  /* 없는 단추를 누르라고 안내하지 않는다 */
  /* 주석은 「예전에 이랬다」를 적을 수 있어야 하므로 코드만 본다 */
  assert.ok(
    !codeOnly(source("js/ocr-groups.js")).includes("판독 결과 확인"),
    "없는 단추를 가리키는 안내가 남아 있다",
  );
});

test("**「다시 확인」이 판독을 다시 불러온다** — 새로고침하면 화면을 벗어난다", () => {
  const code = codeOnly(source("js/ocr-review.js"));
  const at = code.indexOf('target.id === "recheck"');
  assert.notEqual(at, -1, "누른 것을 받는 자리가 없다");

  const body = code.slice(at, at + 200);
  assert.ok(body.includes("loadVisit"), "판독을 다시 안 부른다");
  assert.ok(!/location\.href/.test(body), "화면을 벗어난다 — 보던 값을 잃는다");
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

  /* 셋이다 — 서버가 필수로 보는 셋과 같다. 1회량·일일횟수·처방일은 못 읽었을
     때 물음표로 세우지 않는다: 맨 위 셋과 무게가 같아 보여 무엇을 먼저
     채워야 하는지가 흐려진다. 읽었으면 아래 줄로 그대로 보인다. */
  assert.equal(PRESCRIPTION_CORE.length, 3, "진단 · 약품명 · 처방일수");

  const rows = withMissingRows([{ field_type: "MEDICATION_NAME", value: "비잔" }], PRESCRIPTION_CORE);
  assert.equal(rows.length, 3, "세 줄이 다 서지 않았다");
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

test("**검사값도 자리를 세운다** — 안 세우면 못 읽은 것과 안 한 것을 구별할 수 없다", () => {
  const { LAB_CORE } = box();
  const code = codeOnly(source("js/ocr-review.js"));
  const at = code.indexOf("function groupsHtml");
  const body = code.slice(at, at + 700);

  assert.ok(body.includes("PRESCRIPTION_CORE"), "처방 셋을 안 세운다");
  assert.ok(/withMissingRows\(\s*split\.labs/.test(body), "검사값 자리를 안 세운다");

  /* 판독이 읽어야 하는 스물한 항목. 증상 · 초음파 · 혈액 세 묶음이다. */
  for (const type of [
    "PAIN_SCORE",
    "HEAVY_BLEEDING",
    "IRREGULAR_CYCLE",
    "ADENOMYOSIS_SIZE",
    "MYOMA_COUNT",
    "MYOMA_SIZE",
    "ENDOMETRIAL_THICKNESS",
    "ADNEXAL_CYST_LEFT",
    "ADNEXAL_CYST_RIGHT",
    "HEMOGLOBIN",
    "AST",
    "ALT",
    "LH_FSH_RATIO",
    "DHEA_S",
    "TESTOSTERONE",
    "PROLACTIN",
    "TSH",
    "T3",
    "T4",
    "E2",
    "PROGESTERONE",
  ]) {
    assert.ok(LAB_CORE.indexOf(type) !== -1, `${type} 자리가 없다`);
  }

  /* 검사일은 값 줄이 아니라 **묶음 머리**에 붙는다 — 줄로도 세우면 두 번 보인다 */
  assert.equal(LAB_CORE.indexOf("LAB_DATE"), -1, "검사일이 값 줄로도 선다");

  /* **옛 이름은 자리를 세우지 않는다.** DB 에 남은 값은 「그 밖에 읽은 값」으로
     보이지만, 없는 진료에까지 물음표로 세우면 봐야 할 줄이 그 안에 묻힌다. */
  for (const type of ["CA_125", "AST_ALT", "ENDOMETRIOMA_SIZE"]) {
    assert.equal(LAB_CORE.indexOf(type), -1, `${type} 까지 세운다 — 봐야 할 줄이 묻힌다`);
  }
});

test("**확인 항목은 이제 켜지고 저장된다**", () => {
  /* 담을 표가 없어 꺼 둔 자리였다(`visit_check_answer` 가 생겼다). 켤 수 없으면
     스탭이 여쭈고도 남길 데가 없고, 켜 두고 안 담기면 남았다고 믿는다 —
     안전에 걸리는 항목이라 둘 다 나쁘다. */
  const { checkItemsOf, checkItemLabel } = box();
  const code = codeOnly(source("js/ocr-review.js"));

  const sets = [{ name: "자궁내막증 · 비잔 (계속)", check_items: ["DEPRESSION", "DIABETES"] }];
  assert.deepEqual(
    checkItemsOf(sets, "자궁내막증 · 비잔 (계속)"),
    ["DEPRESSION", "DIABETES"],
    "고른 처방의 항목을 못 찾는다",
  );
  /* 서버는 코드로 주고 화면이 사람 말로 옮긴다 — 판독 항목과 같은 규칙 */
  assert.equal(checkItemLabel("DEPRESSION"), "우울증 병력");
  assert.equal(checkItemLabel("모르는코드"), "모르는코드", "모르는 코드가 사라진다");

  const at = code.indexOf("function checkListHtml");
  assert.notEqual(at, -1, "확인 항목을 세우는 자리가 없다");

  const body = code.slice(at, at + 1200);
  assert.ok(!body.includes("disabled"), "아직 꺼져 있다 — 여쭙고도 남길 데가 없다");
  assert.ok(body.includes("data-check"), "누름을 받는 자리가 없다");
  assert.ok(body.includes("checkItemsNow"), "항목을 여기서 지어낸다 — 처방이 정해야 한다");

  /* **끈 것은 「아직」이다.** 「아니오」라 적었더니 체크를 풀었을 때 글자가
     나타나는 꼴이라 더 헷갈렸다 — 켜면 예, 끄면 아직. */
  assert.ok(!body.includes("아니오"), "체크를 풀면 「아니오」가 나타난다");
  assert.match(body, /answer === true/, "켠 것을 켜진 채로 안 그린다");
});

test("**누르면 서버로 간다** — 「저장」을 따로 두면 눌러 놓고 안 누른 채 넘어간다", () => {
  const code = codeOnly(source("js/ocr-review.js"));

  const at = code.indexOf('getAttribute("data-check")');
  assert.notEqual(at, -1, "누름을 받는 자리가 없다");
  assert.match(code.slice(at, at + 300), /saveCheckItems\(\)/, "누르고도 안 보낸다");

  const save = code.indexOf("function saveCheckItems");
  assert.notEqual(save, -1, "보내는 자리가 없다");
  const body = code.slice(save, save + 900);
  assert.match(body, /saveCheckItems\(wanted, answers\)/, "서버로 안 보낸다");
  /* 한 판을 통째로 — 항목 하나씩 보내면 반쪽 상태가 남는다.
     다만 **보이는 것만** 보낸다: 처방이 안 여쭙는 항목까지 보내면 그 항목을
     빼는 순간 지난 답이 조용히 지워진다. */
  assert.match(body, /checkItemsNow\(\)\.map/, "누른 것 하나만 보내거나, 안 여쭙는 것까지 보낸다");
  /* 안 여쭌 것은 `null` 로 보낸다 — `false` 로 보내면 아니라고 답한 것이 된다 */
  assert.match(body, /=== undefined \? null/, "안 여쭌 것을 「아니오」로 보낸다");

  /* 늦게 온 답이 다른 환자 화면에 붙으면 안 된다 */
  assert.match(body, /visit\.visit_id !== wanted/, "다른 환자의 답이 붙는다");
});

test("확인 항목을 불러온다 — 새로고침하면 사라지면 안 된다", () => {
  const code = codeOnly(source("js/ocr-review.js"));
  assert.match(code, /loadCheckItems\(/, "안 불러온다");

  const at = code.indexOf("function loadCheckItems");
  assert.notEqual(at, -1, "불러오는 자리가 없다");
  const body = code.slice(at, at + 600);
  assert.match(body, /checkItems\(/, "서버에 안 묻는다");
  assert.match(body, /adoptCheckItems\(/, "받아서 화면에 안 넣는다");
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

test("**「저장」이라 쓰지 않는다** — 서버로 안 가는데 저장이라 하면 남았다고 믿는다", () => {
  const code = codeOnly(source("js/ocr-review.js"));
  const at = code.indexOf("data-local-keep=");
  assert.notEqual(at, -1, "적는 칸이 없다 — 검사가 헛돈다");

  const around = code.slice(at, at + 300);
  assert.ok(around.includes(">확인</button>"), "굳히는 버튼이 「확인」이 아니다");
  assert.ok(!around.includes(">저장</button>"), "「저장」이라 적었다 — 남았다고 믿는다");
});

test("**적은 값은 판독한 값과 달라 보인다** — 같아 보이면 어느 것이 기계 값인지 모른다", () => {
  const css = source("css/ocr-review.css");
  const rule = css.slice(css.indexOf(".field__value--local"), css.indexOf(".field__tag--local"));
  assert.match(rule, /dashed/, "판독한 값과 테두리가 같다");
});

test("**적은 값은 이제 실제로 담긴다** — 「저장 안 됨」 배지가 필요 없다", () => {
  /* 판독이 못 읽은 항목은 줄 자체가 없어 보낼 곳이 없었다. 이제 항목 이름으로
     짚어 만드는 길이 있다(`PUT /visits/{id}/ocr-fields/{type}`).
     배지를 그대로 두면 담기고도 「안 담겼다」고 말한다. */
  const code = codeOnly(source("js/ocr-review.js"));

  assert.ok(!code.includes('field__tag--local">저장 안 됨'), "담기는데 「저장 안 됨」이라 적는다");

  const at = code.indexOf('"#labs-save, #rx-save"');
  assert.notEqual(at, -1, "저장 단추를 받는 자리가 없다");
  const body = code.slice(at, at + 1600);
  assert.match(body, /writeField\(/, "서버로 안 보낸다");
  /* **한 번에 담는다** — 하나씩 저장하게 하면 어느 줄이 담겼는지 세어야 한다 */
  assert.match(body, /localOf\(isRx\)/, "적어 둔 것을 한 번에 안 보낸다");
  assert.match(body, /visit\.visit_id !== wanted/, "다른 환자 화면에 붙는다");

  /* **내 블록 것만 지운다** — 옆 블록은 아직 안 담겼는데 함께 지우면 사라진다 */
  assert.match(body, /typed\.forEach/, "담고 나서 옆 블록 값까지 지우거나 안 지운다");
  assert.ok(!body.includes("local = {}"), "옆 블록의 적어 둔 값까지 지운다");

  /* 적은 것이 없으면 누를 것도 없다 */
  assert.match(code, /localOf\(false\)\.length \?/, "판독 값 단추가 빈 채로 눌린다");
  assert.match(code, /localOf\(true\)\.length \|\| pickedSet\)/, "처방 단추가 빈 채로 눌린다");
});

/* ── 맨 위 진단 · 처방 줄 ────────────────────────────────────────────── */

test("**맨 위 줄에 서는 셋은 서버가 필수로 보는 셋과 같다**", () => {
  /* `ai_worker/tasks/ocr_task.py` 의 `_REQUIRED_OCR_FIELDS`. 이 셋이 없으면
     판독 작업 자체가 실패하고, 안내문도 「무슨 약을 며칠」을 못 쓴다.
     서버가 그 목록을 바꾸면 이 검사가 먼저 깨진다. */
  const fs2 = require("node:fs");
  const path2 = require("node:path");
  const worker = fs2.readFileSync(
    path2.join(__dirname, "..", "..", "ai_worker", "tasks", "ocr_task.py"),
    "utf8",
  );
  const m = /_REQUIRED_OCR_FIELDS[^=]*=\s*frozenset\(\{([^}]+)\}\)/.exec(worker);
  assert.ok(m, "서버의 필수 항목 목록을 못 찾았다 — 검사가 헛돈다");

  const required = [...m[1].matchAll(/"([A-Z_]+)"/g)].map((x) => x[1]).sort();

  const code = codeOnly(source("js/ocr-review.js"));
  const at = code.indexOf("var TOP_ROW");
  assert.notEqual(at, -1, "맨 위 줄 정의가 없다");
  const block = code.slice(at, code.indexOf("];", at));
  const shown = [...block.matchAll(/type:\s*"([A-Z_]+)"/g)].map((x) => x[1]).sort();

  assert.deepEqual(shown, required, "맨 위 줄과 서버 필수 항목이 어긋난다");
});

test("**같은 값을 두 번 세우지 않는다** — 맨 위에 선 것은 아래 줄에서 뺀다", () => {
  const code = codeOnly(source("js/ocr-review.js"));
  const at = code.indexOf("function prescriptionHtml");
  const body = code.slice(at, code.indexOf("function labsHtml"));

  assert.ok(body.includes("topRowHtml("), "맨 위 줄을 안 세운다");
  assert.ok(
    /topTypes\.indexOf\([^)]*\)\s*===\s*-1/.test(body),
    "맨 위에 선 것을 아래 줄에서 안 뺀다 — 같은 값이 두 번 보이고 어느 쪽을 고칠지 묻게 된다",
  );
});

test("**고치는 길이 한 벌이다** — 두 벌이면 한쪽만 고쳐진다", () => {
  /* 맨 위 줄이 `renderField` 의 몸통을 그대로 쓴다. 따로 그리면 「고치기」·
     「직접 입력」·충돌 처리가 두 벌이 되고, 그중 하나만 고쳐진다. */
  const code = codeOnly(source("js/ocr-review.js"));

  assert.ok(code.includes("function fieldBody"), "몸통을 꺼내는 자리가 없다");

  const at = code.indexOf("function topRowHtml");
  const body = code.slice(at, at + 1200);
  assert.ok(body.includes("fieldBody("), "맨 위 줄이 몸통을 따로 그린다");
  assert.ok(!body.includes("data-fill="), "맨 위 줄이 「직접 입력」을 따로 그린다");
  assert.ok(!body.includes("field__value"), "맨 위 줄이 값칸을 따로 그린다");
});

test("맨 위 줄에 없는 항목은 자리를 비우지 않는다", () => {
  /* `withMissingRows` 가 여섯을 다 세우므로 정상적으로는 늘 셋 다 있지만,
     방어로 둔다 — 없는 것을 `undefined` 로 그리면 화면이 깨진다. */
  const code = codeOnly(source("js/ocr-review.js"));
  const at = code.indexOf("function topRowHtml");
  const body = code.slice(at, at + 900);
  assert.ok(/if \(!field\) return ""/.test(body), "없는 항목을 그대로 그린다");
});

/* ── 할 일이 없으면 안 뜬다 ──────────────────────────────────────────── */

test("**「모두 읽혔습니다」 판을 두지 않는다** — 판을 차지하면서 아무 일도 안 시킨다", () => {
  const code = codeOnly(source("js/ocr-review.js"));
  const css = source("css/ocr-review.css");

  assert.ok(!code.includes("모두 읽혔습니다"), "할 일이 없는데 판이 뜬다");
  assert.ok(!css.includes(".summary--ok"), "쓰지 않는 초록 규칙이 남았다");

  /* 손봐야 하는 것이 있을 때는 **여전히 뜬다** — 충돌은 사람이 골라야 한다 */
  assert.ok(code.includes("다른 사람이 먼저 고친 항목"), "충돌 경고가 사라졌다");
  assert.ok(code.includes("확인할 항목 "), "확인할 항목 안내가 사라졌다");

  const at = code.indexOf("summary.hidden");
  assert.notEqual(at, -1, "감추는 자리가 없다");
  assert.match(
    code.slice(at, at + 60),
    /!\(total \|\| clashes\)/,
    "감추는 조건이 「할 일이 없을 때」가 아니다",
  );
});

test("**화면 제목은 소리로만 남는다** — 문서에 제목이 하나는 있어야 한다", () => {
  const page = markupOnly(source("ocr-review.html"));

  const h1 = /<h1[^>]*>/.exec(page);
  assert.ok(h1, "제목이 아예 없다 — 화면낭독기가 「이 화면이 무엇인가」를 못 읽는다");
  assert.match(h1[0], /sr-only/, "제목이 눈에 보인다 — 머리말과 단계 줄이 이미 같은 말을 한다");
});

test("**항목 이름과 상태가 한 줄에 선다** — 접히면 값 칸이 밀려 열이 안 맞는다", () => {
  /* 「1회량 ⚠ 인식 / 실패」처럼 접히면 줄마다 높이가 달라지고, 값이 세로로
     안 훑힌다 — 열을 고정 폭으로 세운 이유가 사라진다. */
  const css = source("css/ocr-review.css");

  for (const sel of [".field__name", ".field__tag"]) {
    const at = css.lastIndexOf(sel + " {");
    assert.notEqual(at, -1, `${sel} 규칙이 없다 — 검사가 헛돈다`);
    const rule = css.slice(at, css.indexOf("}", at));
    assert.match(rule, /white-space:\s*nowrap/, `${sel} 이 접힌다`);
  }
});

test("맨 위 줄 이름표는 와이어프레임을 따른다 — 「처방」", () => {
  const code = codeOnly(source("js/ocr-review.js"));
  const at = code.indexOf("var TOP_ROW");
  const block = code.slice(at, code.indexOf("];", at));

  assert.match(block, /type: "MEDICATION_NAME", label: "처방"/, "맨 위 줄이 「약품명」이라 적는다");

  /* 항목 이름표 자체는 그대로다 — 아래 값 줄에서는 「약품명」이 맞다 */
  const { fieldLabel } = load("field-labels");
  assert.equal(fieldLabel("MEDICATION_NAME"), "약품명");
});

/* ── 약속처방 고르기 ─────────────────────────────────────────────────── */

test("**하나로 좁혀질 때만 고른다** — 둘이면 사람이 골라야 한다", () => {
  const { guessPrescriptionSet } = box();

  const sets = [
    { prescription_set_id: 1, name: "자궁내막증 · 비잔 (처음)" },
    { prescription_set_id: 2, name: "자궁내막증 · 비잔 (계속)" },
    { prescription_set_id: 3, name: "PCOS · 야즈 (계속)" },
  ];

  /* 「비잔」은 둘에 걸린다 — 안내문이 다르고 기계가 고를 근거가 없다 */
  assert.equal(guessPrescriptionSet(sets, "비잔"), null, "둘 중 하나를 마음대로 골랐다");

  /* 「야즈」는 하나뿐이다 */
  assert.equal(guessPrescriptionSet(sets, "야즈").prescription_set_id, 3);

  assert.equal(guessPrescriptionSet(sets, ""), null);
  assert.equal(guessPrescriptionSet([], "비잔"), null);
  assert.equal(guessPrescriptionSet(sets, "없는약"), null);
});

test("글자 몇 개가 겹친다고 고르지 않는다", () => {
  const { guessPrescriptionSet } = box();
  const sets = [{ prescription_set_id: 5, name: "PCOS · 초진 (야즈 불가)" }];

  /* 「야즈」가 「야즈 불가」에 들어 있다 — 통째로 들어 있으면 후보다.
     그래도 하나뿐이라 고른다: 사람이 보고 바꿀 수 있는 자리다. */
  assert.equal(guessPrescriptionSet(sets, "야즈").prescription_set_id, 5);
});

test("**목록이 없으면 빈 드롭다운을 두지 않는다** — 열어도 아무것도 없으면 「고장」으로 읽힌다", () => {
  const { setsMissingSaying } = box();

  assert.match(setsMissingSaying([], false), /설정 · 처방/, "어디서 채우는지 안 알려 준다");
  assert.match(setsMissingSaying([], true), /불러오지 못했습니다/, "못 불러온 것과 없는 것을 안 가른다");
  assert.equal(setsMissingSaying([{ prescription_set_id: 1, name: "x" }], false), "");

  /* **부르는 것만으로는 모자란다.** 부르고 그 값을 버리면 검사가 안 문다 —
     돌연변이를 넣어 보고 알았다. 그 값으로 **갈라지는지**를 본다. */
  const code = codeOnly(source("js/ocr-review.js"));
  const at = code.indexOf("function setPickerHtml");
  const body = code.slice(at, at + 900);

  assert.match(
    body,
    /var note = setsMissingSaying\([\s\S]{0,80}if \(note\) \{/,
    "말할 것이 있는지 부르기만 하고 갈라지지 않는다 — 빈 드롭다운이 그대로 뜬다",
  );
  /* 그 갈래가 드롭다운 **대신** 서야 한다 */
  const branch = body.slice(body.indexOf("if (note) {"), body.indexOf("var options"));
  assert.ok(!branch.includes("<select"), "빈 목록인데도 드롭다운을 함께 그린다");
});

test("**판독이 읽은 약 이름을 버리지 않는다** — 어느 세트인지의 실마리다", () => {
  const code = codeOnly(source("js/ocr-review.js"));
  const at = code.indexOf("function setPickerHtml");
  const body = code.slice(at, at + 1400);

  assert.ok(body.includes("top__read"), "판독한 이름을 안 보여 준다");
  assert.ok(body.includes("판독:"), "그것이 판독한 값이라고 안 밝힌다");
});

test("**다른 환자로 옮기면 고른 처방도 지운다** — 남의 처방으로 안내문이 만들어진다", () => {
  const code = codeOnly(source("js/ocr-review.js"));
  const at = code.indexOf("function resetState");
  const body = code.slice(at, at + 500);
  assert.ok(/pickedSet\s*=\s*null/.test(body), "앞 환자에게 고른 처방이 남는다");
});

test("**무엇을 여쭐지는 처방이 정한다** — 처방 전에는 여쭐 것도 없다", () => {
  const { checkItemsOf } = box();
  const sets = [
    { name: "자궁내막증 · 비잔 (계속)", check_items: ["DEPRESSION", "OSTEOPOROSIS"] },
    { name: "PCOS · 야즈 (계속)", check_items: ["HYPERTENSION", "PREGNANCY_PLAN"] },
  ];

  assert.deepEqual(checkItemsOf(sets, "PCOS · 야즈 (계속)"), ["HYPERTENSION", "PREGNANCY_PLAN"]);

  /* **고른 세트를 통째로 받으면 그것이 답이다** — 화면이 들고 있는 것이 가장
     확실하다. 이름으로 되찾으면 목록을 못 불러온 사이에 빈 목록이 된다. */
  assert.deepEqual(
    checkItemsOf([], { name: "PCOS · 야즈 (계속)", check_items: ["HYPERTENSION"] }),
    ["HYPERTENSION"],
    "고른 세트를 그대로 안 읽는다",
  );

  /* **안 골랐으면 빈 목록이다.** 다섯을 미리 세워 두면 처방을 고르는 순간
     항목이 바뀌면서 이미 체크한 것이 사라진 것처럼 보인다. */
  assert.deepEqual(checkItemsOf(sets, ""), [], "처방 전에 항목을 세운다");
  assert.deepEqual(checkItemsOf(sets, null), []);

  /* 모르는 처방이면 지어내지 않는다 */
  assert.deepEqual(checkItemsOf(sets, "없는 처방"), [], "모르는 처방에 항목을 지어낸다");

  /* 목록을 못 불러왔을 때도 죽지 않는다 */
  assert.deepEqual(checkItemsOf(null, "PCOS · 야즈 (계속)"), []);
});

test("처방을 안 골랐으면 그렇다고 말한다 — 빈 칸으로 두면 고장으로 읽힌다", () => {
  const code = codeOnly(source("js/ocr-review.js"));
  const at = code.indexOf("function checkListHtml");
  const body = code.slice(at, at + 600);

  assert.match(body, /if \(!items\.length\)/, "안 골랐을 때를 안 가른다");
  assert.ok(body.includes("처방을 고르면"), "왜 비었는지 안 말한다");
});

test("목업이 서버와 같은 모양을 준다 — 다르면 목업에서만 되는 화면이 생긴다", () => {
  /* 카탈로그 목업은 `catalog-api.js` 것이다 — 설정 화면도 같은 값을 쓰는데,
     그쪽이 판독 API 파일을 실을 이유가 없어 옮겼다. */
  const api = codeOnly(source("js/catalog-api.js"));
  assert.match(api, /check_items: MOCK_CHECK_ITEMS/, "목업 세트에 확인 항목이 없다");

  /* 판독 화면은 카탈로그를 **빌려 쓴다** — 두 벌로 두면 목업이 갈린다 */
  const ocr = codeOnly(source("js/ocr-api.js"));
  assert.match(ocr, /catalogApi\.sets\(\)/, "판독 화면이 제 목록을 따로 갖는다");
  assert.ok(!ocr.includes("var MOCK_PRESCRIPTION_SETS"), "약속처방 목업이 두 벌이다");

  /* 서버 씨앗과 같은 다섯이어야 한다 */
  const at = api.indexOf("var MOCK_CHECK_ITEMS");
  const line = api.slice(at, api.indexOf("]", at));
  for (const key of ["DEPRESSION", "HYPERTENSION", "OSTEOPOROSIS", "DIABETES", "PREGNANCY_PLAN"]) {
    assert.ok(line.includes(key), `목업에 ${key} 이 없다`);
  }
});

test("**단위는 한 자리에서만 그린다** — 값 바로 뒤, 단추 앞", () => {
  /* 칸 밖에 두면 오른쪽 끝으로 떨어지고, 칸 안 끝에 두면 단추 뒤로 밀린다.
     값을 그리는 자리가 값 바로 뒤에 세우므로 그쪽 하나에 맡긴다. */
  const code = codeOnly(source("js/ocr-review.js"));

  const rows = code.split('top__unit">');
  assert.equal(rows.length, 1, "맨 위 줄이 단위를 따로 또 그린다");

  const at = code.indexOf("function unitHtml");
  assert.notEqual(at, -1, "단위를 그리는 자리가 없다");
  const body = code.slice(at, code.indexOf("\n  }", at));
  assert.match(body, /fieldUnit\(/, "단위표를 안 읽는다");
});

test("**맨 위 줄에서 단위가 값 앞으로 튀지 않는다**", () => {
  /* 값·단추의 줄바꿈 지점을 `order` 로 못박는데, 단위를 그 목록에서 빠뜨리면
     그것만 기본값(0)이 되어 맨 앞에 선다 — 「일 ? 직접 입력」이 됐다. */
  const css = source("css/ocr-review.css");
  const at = css.indexOf("/* 값칸과 단위는 첫 줄에");
  assert.notEqual(at, -1, "줄바꿈 규칙이 없다 — 검사가 헛돈다");

  const block = css.slice(at, css.indexOf("}", at));
  for (const sel of [".top .field__value", ".top .field__unit", ".top .field__pick"]) {
    assert.ok(block.includes(sel), `${sel} 가 차례에서 빠졌다 — 그 칸만 앞으로 튄다`);
  }
  assert.match(css.slice(at, css.indexOf("}", at) + 20), /order:\s*1/, "차례를 안 정한다");
});

test("**견줄 판독값이 없으면 「수정됨」을 적지 않는다**", () => {
  /* 기계가 아무것도 못 읽은 칸에 「수정됨 · 판독값 없음」을 붙이면, 사람이
     적었다는 뻔한 사실을 값보다 먼저 읽게 된다. */
  const code = codeOnly(source("js/ocr-review.js"));
  const at = code.indexOf("field__edited");
  assert.notEqual(at, -1, "고친 표시가 없다");

  const around = code.slice(Math.max(0, at - 300), at + 200);
  assert.match(around, /&&\s*field\.extracted_value/, "판독값이 없어도 「수정됨」을 적는다");
  assert.ok(!around.includes('|| "없음"'), "「판독값 없음」이라 적는다");
});

test("**값 뒤에 오는 것은 모두 값 뒤에 선다** — 하나만 빠져도 앞으로 튄다", () => {
  const css = source("css/ocr-review.css");
  const at = css.indexOf(".top .field__act");
  assert.notEqual(at, -1, "뒤에 세우는 규칙이 없다");

  const block = css.slice(at, css.indexOf("}", at));
  for (const sel of [".top .field__edited", ".top .field__date", ".top .field__save"]) {
    assert.ok(block.includes(sel), `${sel} 가 빠졌다 — 그것만 값 앞으로 튄다`);
  }
});

test("**고른 처방이 판독이 읽어 온 이름보다 앞선다**", () => {
  /* 판독이 읽어 온 이름은 스탭이 고르기 전의 값이다. 고른 뒤에는 그쪽이 맞다 —
     안 그러면 처방을 바꿔도 여쭐 항목이 앞 처방 것으로 남는다. */
  const code = codeOnly(source("js/ocr-review.js"));
  const at = code.indexOf("function checkItemsNow");
  assert.notEqual(at, -1, "여쭐 항목을 정하는 자리가 없다");

  const body = code.slice(at, code.indexOf("\n  }", at));
  assert.match(body, /pickedSet \|\|/, "고른 처방을 먼저 안 본다");
});

test("**두 블록이 각자 제 것만 담는다** — 안 만진 칸이 저장되면 안 된다", () => {
  const { PRESCRIPTION_TYPES } = box();
  const code = codeOnly(source("js/ocr-review.js"));

  const at = code.indexOf("function localOf");
  assert.notEqual(at, -1, "블록별로 가르는 자리가 없다");
  const body = code.slice(at, code.indexOf("\n  }", at));
  assert.match(body, /PRESCRIPTION_TYPES\.indexOf/, "처방 항목인지를 안 가른다");

  assert.ok(PRESCRIPTION_TYPES.indexOf("DIAGNOSIS") !== -1, "검사가 헛돈다");
  assert.equal(PRESCRIPTION_TYPES.indexOf("TSH"), -1, "혈액 항목이 처방으로 세어진다");
});

test("**고른 처방도 담긴다** — 화면이 기억만 하면 새로고침에 사라진다", () => {
  /* 안내문이 이 값으로 만들어진다. 화면에만 두면 「골랐는데 안 골라진」 채로
     승인까지 간다. */
  const code = codeOnly(source("js/ocr-review.js"));
  const at = code.indexOf('"#labs-save, #rx-save"');
  const body = code.slice(at, at + 1600);

  assert.match(body, /pickedSet \? \{ MEDICATION_NAME/, "고른 처방을 안 담는다");
});

test("**판독이 없으면 저장 단추가 잠긴다** — 눌러서 실패하면 적은 것이 날아간 줄 안다", () => {
  /* 적어 넣는 값은 판독 결과에 붙는다(`ocr_field` 는 `ocr_result` 의 것이다).
     아직 아무것도 안 올린 진료에는 붙일 자리가 없다 — 빈 판을 세우면서
     생긴 자리다. */
  const code = codeOnly(source("js/ocr-review.js"));

  const at = code.indexOf("function canSaveFields");
  assert.notEqual(at, -1, "담을 수 있는지 묻는 자리가 없다");
  assert.match(code.slice(at, at + 200), /result\.ocr_result_id/, "판독 결과가 있는지 안 본다");

  /* 두 단추 모두 그것을 본다 — 한쪽만 보면 그쪽만 잠긴다 */
  for (const id of ["rx-save", "labs-save"]) {
    const bat = code.indexOf('id="' + id + '"');
    assert.notEqual(bat, -1, `${id} 단추가 없다`);
    assert.match(code.slice(bat, bat + 220), /canSaveFields\(\)/, `${id} 가 잠기지 않는다`);
  }

  /* 왜 못 누르는지 말한다 — 잠긴 단추만 두면 고장으로 읽힌다 */
  assert.match(code, /SAVE_LOCKED\s*=\s*"진료기록을 올리면/, "왜 잠겼는지 안 말한다");
});
