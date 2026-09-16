/* KEY-353 — 상단에는 의사라고 나오는데 승인·문자 수정은 잠기는 회귀.
 *
 * 원인은 두 가지였다. `shell.js` 보다 늦게 실린 `doctor.js` 가 일회성
 * `session:ready` 이벤트를 놓칠 수 있었고, 비활성 사유를 전부 권한 문제로
 * 표시했다. 서버 RBAC는 이미 의사의 수정·승인을 허용하므로 프런트 계약만 잰다. */
const { test } = require("node:test");
const assert = require("node:assert");
const { load } = require("./browser-shim.js");
const { read, codeOnly } = require("./source.js");

test("확인한 세션은 늦게 로드된 화면도 다시 읽을 수 있다", async () => {
  const box = load("api", "session");
  const login = await box.api.login("doctor01", "valid-password");
  box.session.save(login.access_token);

  const who = await box.requireSession();

  assert.deepEqual(Array.from(who.roles), ["doctor"]);
  assert.strictEqual(box.session.current, who, "일회성 이벤트 밖에는 현재 사용자가 남지 않는다");

  box.session.clear();
  assert.equal(box.session.current, null, "로그아웃 뒤 이전 역할이 남는다");
});

test("의사는 승인 대기 안내문을 승인·반려할 수 있다", () => {
  const { doctorApprovalState } = load("api", "session", "doctor");

  assert.deepEqual(
    JSON.parse(JSON.stringify(doctorApprovalState({ roles: ["doctor"] }, { status: "APPROVAL_PENDING" }))),
    { canAct: true, why: "" },
  );
});

test("권한 없음과 아직 없음·이미 승인을 서로 다른 이유로 말한다", () => {
  const { doctorApprovalState } = load("api", "session", "doctor");

  assert.match(doctorApprovalState({ roles: ["staff"] }, { status: "APPROVAL_PENDING" }).why, /의사 권한/);
  assert.doesNotMatch(doctorApprovalState({ roles: ["doctor"] }, null).why, /권한/);
  assert.match(doctorApprovalState({ roles: ["doctor"] }, { status: "SCHEDULED_TO_SEND" }).why, /이미 승인/);
});

test("의사 단독 계정과 의사를 포함한 복수 역할 계정이 같게 판정된다 — 어드민을 더 얹었다고 막히지 않는다", () => {
  const { doctorApprovalState } = load("api", "session", "doctor");
  const pending = { status: "APPROVAL_PENDING" };

  assert.equal(doctorApprovalState({ roles: ["doctor"] }, pending).canAct, true);
  assert.equal(doctorApprovalState({ roles: ["doctor", "admin"] }, pending).canAct, true);
  assert.equal(doctorApprovalState({ roles: ["admin"] }, pending).canAct, false);
});

test("의사 화면은 늦게 등록돼도 저장된 세션을 복구하고 문자 저장 권한을 명시한다", () => {
  const code = codeOnly(read("js/doctor.js"));

  assert.match(code, /if \(session\.current\) acceptSession\(session\.current\)/);
  assert.match(code, /canSave:\s*editable/);
  assert.match(code, /APPROVAL_PENDING/);
});
