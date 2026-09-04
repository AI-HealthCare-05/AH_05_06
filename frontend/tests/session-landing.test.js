/* 로그인한 사람이 갈 첫 화면 — `landingFor` (KEY-269).
 *
 * **의사를 먼저 본다.** 예전에는 스탭이 앞이라 `staff|doctor` 계정이 환자
 * 목록으로 떨어졌고, 승인하러 들어온 원장이 주소창을 손으로 고쳐야 했다.
 *
 * 그 조합은 이제 유효 조합에서 빠졌지만(`VALID_COMBINATIONS` 다섯) 이 차례는
 * **방어선**으로 남는다 — 옛 데이터나 손으로 고친 DB 에서 생겨도 의사 화면으로
 * 보낸다. 그래서 픽스처 계정이 아니라 **역할 배열로** 잰다: 계정이 사라졌다고
 * 이 규칙까지 함께 사라지면 안 된다.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const { load } = require("./browser-shim.js");

function box() {
  return load("api", "session");
}

test("의사는 안내문 확인이 첫 일이다", () => {
  const { landingFor } = box();

  assert.equal(landingFor(["doctor"]), "/doctor.html");
});

test("스탭은 환자 목록이 첫 일이다", () => {
  const { landingFor } = box();

  assert.equal(landingFor(["staff"]), "/patients.html");
});

test("어드민 권한만 가진 계정은 어드민 화면으로", () => {
  const { landingFor } = box();

  assert.equal(landingFor(["admin"]), "/admin.html");
});

test("**의사가 스탭보다 앞이다** — 옛 겸직 계정이 남아 있어도 승인 화면으로 보낸다", () => {
  const { landingFor } = box();

  /* 이 조합은 이제 만들어지지 않는다. 그래도 규칙을 고정해 둔다 —
     차례를 되돌리면 승인하러 들어온 원장이 다시 환자 목록으로 떨어진다. */
  assert.equal(landingFor(["staff", "doctor"]), "/doctor.html");
  assert.equal(landingFor(["doctor", "staff"]), "/doctor.html", "배열 순서가 결과를 바꾸면 안 된다");
});

test("admin 오버레이가 임상 축을 안 덮는다", () => {
  const { landingFor } = box();

  assert.equal(landingFor(["doctor", "admin"]), "/doctor.html");
  assert.equal(landingFor(["staff", "admin"]), "/patients.html");
});

test("역할이 없으면 로그인으로 되돌린다", () => {
  const { landingFor } = box();

  assert.equal(landingFor([]), "/login.html");
  assert.equal(landingFor(), "/login.html", "안 넘겨도 터지지 않아야 한다");
});
