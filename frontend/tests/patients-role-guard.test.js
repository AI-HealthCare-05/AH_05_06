/* 환자 목록·등록 화면(S1)은 스탭의 자리다 — `showsPatientList` (KEY-269 후속).
 *
 * `landingFor` 는 로그인하는 그 순간만 방향을 잡는다. 이미 세션이 살아 있는
 * 의사가 `/patients.html` 을 북마크·탭 복원·주소창으로 곧장 열면 착지점 규칙은
 * 지나간 뒤라 아무것도 못 막는다. 그 자리를 이 술어가 메운다: `session:ready`
 * 에서 스탭이 아니면 `landingFor` 로 제 화면에 돌려보낸다.
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

test("의사는 환자 목록 화면에서 밀려난다 — 승인이 첫 일이다", () => {
  const { showsPatientList } = box();

  assert.equal(showsPatientList(["doctor"]), false);
  assert.equal(showsPatientList(["doctor", "admin"]), false);
});

test("옛 겸직 계정이 손으로 만들어져도 — staff|doctor 는 밀려난다", () => {
  const { showsPatientList } = box();

  /* 이 조합은 유효 조합에서 빠졌지만(`VALID_COMBINATIONS` 다섯) DB 를 손대면
     생길 수 있다. 그때도 의사 롤이 있으면 스탭 화면에 두지 않는다. */
  assert.equal(showsPatientList(["staff", "doctor"]), false);
  assert.equal(showsPatientList(["doctor", "staff"]), false);
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

test("`landingFor` 에서 파생한다 — 두 규칙이 어긋날 수 없다", () => {
  const { showsPatientList, landingFor } = box();

  /* 가드가 하는 일: `if (!showsPatientList(roles)) location.replace(landingFor(roles))`.
     `showsPatientList` 가 `landingFor(roles) === "/patients.html"` 로 정의되므로
     「밀어낸 사람을 다시 목록으로 보내는」 무한 튕김이 원리상 불가능하다.
     그 등가를 역할 조합 전반에서 고정한다. */
  const combos = [["staff"], ["staff", "admin"], ["doctor"], ["doctor", "staff"], ["doctor", "admin"], ["admin"], []];
  for (const roles of combos) {
    assert.equal(
      showsPatientList(roles),
      landingFor(roles) === "/patients.html",
      `${JSON.stringify(roles)} — showsPatientList 와 landingFor 가 어긋난다`,
    );
    if (!showsPatientList(roles)) {
      assert.notEqual(landingFor(roles), "/patients.html", `${JSON.stringify(roles)} 를 다시 목록으로 보내면 안 된다`);
    }
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
