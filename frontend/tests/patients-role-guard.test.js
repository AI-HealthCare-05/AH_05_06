/* 환자 목록·등록 화면(S1)은 스탭의 자리다 — `showsPatientList` (KEY-269 후속).
 *
 * `landingFor` 는 로그인하는 그 순간만 방향을 잡는다. 이미 세션이 살아 있는
 * 의사가 `/patients.html` 을 북마크·탭 복원·주소창으로 곧장 열면 착지점 규칙은
 * 지나간 뒤라 아무것도 못 막는다. 그 자리를 이 술어가 메운다: `session:ready`
 * 에서 스탭이 아니면 `landingFor` 로 제 화면에 돌려보낸다.
 *
 * 픽스처 계정이 아니라 **역할 배열로** 잰다 — 계정 목록이 바뀌어도 규칙은 남는다.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const { load } = require("./browser-shim.js");

function box() {
  return load("api", "session");
}

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

test("밀려나는 사람은 `landingFor` 가 정한 제 화면으로 간다 — 짝이 맞는다", () => {
  const { showsPatientList, landingFor } = box();

  /* 가드가 하는 일: `if (!showsPatientList(roles)) location.replace(landingFor(roles))`.
     두 술어가 어긋나면(예: 의사를 밀어내면서 다시 목록으로 보내면) 무한 튕김이 된다. */
  for (const roles of [["doctor"], ["doctor", "admin"], ["admin"], []]) {
    assert.equal(showsPatientList(roles), false);
    assert.notEqual(landingFor(roles), "/patients.html", `${JSON.stringify(roles)} 를 다시 목록으로 보내면 안 된다`);
  }
});
