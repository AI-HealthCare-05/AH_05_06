/* 환자 목록·등록 화면(S1)에 누가 머무는가 — `showsPatientList` (KEY-311).
 *
 * **의사는 스탭이 하는 모든 것을 한다** (2026-09-08 회의 결정). 환자를 더하고,
 * 안내문을 만들고, 현황을 본다. 승인·반려·기준선은 의사만 하므로 의사가 스탭을
 * **포함**한다. 서버는 이미 그랬다 — `app/core/rbac.py` 에서 `PATIENT_READ` ·
 * `PATIENT_WRITE` · `OCR_UPLOAD` · `GUIDE_DRAFT` · `SMS_SEND` 가 `{STAFF, DOCTOR}` 다.
 *
 * 이 술어는 **착지와 다른 물음**이다. `landingFor` 는 「로그인하면 어디에
 * 내려놓는가」(의사는 승인이 첫 일, KEY-269), 여기는 「일부러 찾아오면 볼 수
 * 있는가」. 전에는 둘을 한 낱말로 묶어, 의사의 첫 화면이 `/doctor.html` 이라는
 * 이유만으로 현황이 닫혔다.
 *
 * 두 갈래로 잰다.
 *   ① `showsPatientList` 규칙 — 픽스처 계정이 아니라 역할 배열로. 계정 목록이
 *      바뀌어도 규칙은 남는다.
 *   ② `patients.js` 배선 — 그리는 코드는 shim 아래서 안 돌기 때문에 원문으로.
 *      리스너에서 가드를 통째로 지워도 ① 은 전부 초록이다 (iljun-sys #225 리뷰).
 */
const { test } = require("node:test");
const assert = require("node:assert");
const { load } = require("./browser-shim.js");
const { read, codeOnly } = require("./source.js");

function box() {
  return load("api", "session");
}

/* ── ⓪ 두 술어가 한 몸을 본다 ──────────────────────────────────────── */

test("**`showsPatientList` 와 `opensSettings` 가 같은 답을 낸다** — 몸이 두 벌이면 한쪽만 고친다", () => {
  /* 둘 다 「어드민 권한만 가진 계정인가」를 가르는 물음이라 답이 같다. 전에는
     같은 줄이 두 벌 적혀 있었고(2heej, #269), KEY-311 이 정확히 그 모양의
     결함이었다 — 한 낱말을 고치면서 다른 자리를 못 봤다. 이제 `doesClinicWork`
     하나를 나눠 쓴다.

     언젠가 한 화면의 답이 갈리면 이 검사가 먼저 운다. 그때는 그 함수를 몸에서
     떼어 내고 여기에 「이제 다르다」를 적으면 된다. */
  const { showsPatientList, opensSettings } = box();

  const CASES = [
    [],
    ["staff"],
    ["doctor"],
    ["admin"],
    ["staff", "admin"],
    ["doctor", "admin"],
    ["staff", "doctor"],
    ["staff", "doctor", "admin"],
    ["nurse"],
  ];

  for (const roles of CASES) {
    assert.equal(
      showsPatientList(roles),
      opensSettings(roles),
      `역할 [${roles}] 에서 두 술어의 답이 갈렸다 — 몸이 두 벌로 돌아갔다`,
    );
  }

  /* 그리고 **실제로 한 몸을 부른다** — 우연히 같은 답을 내는 두 벌이 아니다. */
  const code = codeOnly(read("js/session.js"));
  for (const name of ["showsPatientList", "opensSettings"]) {
    const at = code.indexOf("function " + name);
    assert.notEqual(at, -1, `${name} 이 없다 — 검사가 헛돈다`);
    assert.match(code.slice(at, at + 160), /doesClinicWork\(roles\)/, `${name} 이 제 몸을 따로 가진다`);
  }
});

/* ── ① 규칙: 누가 환자 목록 화면에 머무는가 ─────────────────────────── */

test("스탭은 환자 목록 화면에 머문다", () => {
  const { showsPatientList } = box();

  assert.equal(showsPatientList(["staff"]), true);
});

test("스탭 + 어드민도 머문다 — 어드민 오버레이가 스탭 자리를 안 뺏는다", () => {
  const { showsPatientList } = box();

  assert.equal(showsPatientList(["staff", "admin"]), true);
  assert.equal(showsPatientList(["admin", "staff"]), true, "배열 순서가 결과를 바꾸면 안 된다");
});

test("**의사도 머문다** — 스탭이 하는 모든 것을 한다 (KEY-311)", () => {
  const { showsPatientList } = box();

  assert.equal(showsPatientList(["doctor"]), true);
  assert.equal(showsPatientList(["doctor", "admin"]), true);
});

test("**착지와 권한은 다른 물음이다** — 의사는 승인에 내려놓되 현황이 닫히지 않는다", () => {
  const { showsPatientList, landingFor } = box();

  /* 착지는 그대로다 (KEY-269) */
  assert.equal(landingFor(["doctor"]), "/doctor.html");
  /* 그래도 볼 수 있다 — 전에는 이 둘이 한 낱말이라 현황이 닫혔다 */
  assert.equal(showsPatientList(["doctor"]), true);
});

test("겸직 계정도 머문다 — 어느 쪽 롤이든 이 화면을 연다", () => {
  const { showsPatientList } = box();

  /* 이 조합은 유효 조합에서 빠졌지만(`VALID_COMBINATIONS` 다섯) DB 를 손대면
     생길 수 있다. 둘 다 이 화면을 여는 롤이므로 순서와 무관하게 머문다. */
  assert.equal(showsPatientList(["staff", "doctor"]), true);
  assert.equal(showsPatientList(["doctor", "staff"]), true);
});

test("어드민 전용 계정도 환자 목록 화면이 아니다", () => {
  const { showsPatientList } = box();

  assert.equal(showsPatientList(["admin"]), false);
});

test("역할이 없으면 들이지 않는다", () => {
  const { showsPatientList } = box();

  assert.equal(showsPatientList([]), false);
  assert.equal(showsPatientList(), false, "안 넘겨도 터지지 않아야 한다");
});

test("**밀어낸 사람을 다시 여기로 보내지 않는다** — 무한 튕김", () => {
  const { showsPatientList, landingFor } = box();

  /* 가드가 하는 일: `if (!showsPatientList(roles)) location.replace(landingFor(roles))`.
     전에는 `showsPatientList` 를 `landingFor(roles) === "/patients.html"` 로 **정의**해
     이 성질이 원리상 보장됐다. KEY-311 로 둘을 갈랐으니(착지와 권한은 다른 물음)
     이제는 **재서 지킨다** — 밀어낸 조합의 착지가 다시 이 화면이면 무한 튕김이다. */
  const combos = [["staff"], ["staff", "admin"], ["doctor"], ["doctor", "staff"], ["doctor", "admin"], ["admin"], []];
  for (const roles of combos) {
    if (showsPatientList(roles)) continue;
    assert.notEqual(
      landingFor(roles),
      "/patients.html",
      `${JSON.stringify(roles)} 를 밀어내 놓고 다시 목록으로 보낸다 — 무한 튕김`,
    );
  }
});

test("이 화면을 여는 롤은 착지가 어디든 밀려나지 않는다", () => {
  const { showsPatientList } = box();

  /* KEY-311 의 핵심 — 착지가 `/doctor.html` 이어도 현황이 닫히지 않는다. */
  for (const roles of [["staff"], ["doctor"], ["staff", "admin"], ["doctor", "admin"], ["doctor", "staff"]]) {
    assert.equal(showsPatientList(roles), true, `${JSON.stringify(roles)} 가 밀려난다`);
  }
  for (const roles of [["admin"], [], ["unknown"]]) {
    assert.equal(showsPatientList(roles), false, `${JSON.stringify(roles)} 가 들어온다`);
  }
});

/* ── ② 배선: patients.js 가 실제로 가드를 건다 ──────────────────────── */

/* 그리는 코드는 shim 아래서 안 돌아서 원문으로 잰다. 글자가 아니라 코드 줄을
   보고(`codeOnly` 로 주석·문자열을 지운 뒤), 자리가 없으면 검사가 헛도는 것을
   알 수 있게 가드를 둔다 — 이 폴더의 관례(`ocr-review-confirm-before-generate`). */
function sessionReadyHandler() {
  const code = codeOnly(read("js/patients.js"));
  const at = code.indexOf('addEventListener("session:ready"');
  assert.notEqual(at, -1, "patients.js 에 session:ready 리스너가 없다 — 검사가 헛돈다");
  /* 리스너는 파일 끝의 IIFE 가 닫히기 직전에 있다 — 끝까지 잘라도 그 핸들러뿐이다. */
  return code.slice(at);
}

test("session:ready 리스너가 showsPatientList 로 가드한다", () => {
  const handler = sessionReadyHandler();

  assert.match(handler, /showsPatientList\(/, "가드가 사라졌다 — showsPatientList 호출이 없다");
  assert.match(
    handler,
    /location\.replace\(\s*landingFor\(/,
    "밀어내기만 하고 갈 곳을 안 정한다 — location.replace(landingFor(...)) 가 없다",
  );
});

test("가드는 목록을 그리기 **전에** 돈다 — 밀려날 사람이 목록을 먼저 보면 안 된다", () => {
  const handler = sessionReadyHandler();

  const guardAt = handler.indexOf("showsPatientList(");
  const gotoAt = handler.search(/location\.replace\(\s*landingFor\(/);
  const drawAt = handler.indexOf("department_id");

  assert.notEqual(drawAt, -1, "리스너에서 목록 렌더(department_id)를 못 찾았다 — 검사가 헛돈다");
  assert.ok(guardAt > -1 && guardAt < drawAt, "showsPatientList 가드가 목록 렌더 뒤에 있다");
  assert.ok(gotoAt > -1 && gotoAt < drawAt, "리다이렉트가 목록 렌더 뒤에 있다");
});
