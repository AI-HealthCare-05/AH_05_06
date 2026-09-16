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

/* 리뷰(유가은 님, c1781ae 기준)에서 잡힌 두 가지 — `canSave` 만 켜고 실제
 * 저장 배선이 빠진 것과, 반려 뒤에도 승인·반려 버튼이 풀린 채로 남는 것.
 * `browser-shim` 은 그리는 코드를 못 돌리므로(`innerHTML` 이 터진다) 여기서는
 * 원문 패턴으로 다시 풀리지 않게 고정한다. */
test("이 환자만 적용은 실제로 saveMessagePlan 을 부르고 서버 응답을 다시 반영한다", () => {
  const code = codeOnly(read("js/doctor.js"));

  assert.match(
    code,
    /save:\s*function\s*\(plan\)[\s\S]*?doctorApi\s*\n?\s*\.saveMessagePlan\(/,
    "wireSmsSettings 에 save 콜백이 있어야 「이 환자만 적용」이 저장 요청을 보낸다",
  );
  assert.match(code, /doctorApi\s*\n?\s*\.messagePlan\(/, "문자 설정을 불러오는 자리가 있어야 한다");
  assert.match(code, /smsAdopt\(data\)/, "서버가 돌려준 값을 화면 상태로 다시 삼아야 한다");
});

test("반려가 성공하면 전역 안내문 상태도 같이 바뀌어 승인·반려 버튼이 다시 잠긴다", () => {
  const code = codeOnly(read("js/doctor.js"));

  assert.match(
    code,
    /returnToStaff\(returningId, text\)\s*\.then\(function \(result\) \{[\s\S]{0,300}?guide = result/,
    "return-go 성공 콜백이 guide 를 서버 응답으로 갱신해야 renderRole() 이 최신 상태를 본다",
  );
});

/* 2차 리뷰(유가은 님, 51fe39f 기준)에서 잡힌 세 가지 — 문자 설정을 실제로
 * 받기 전에도 저장이 열려 있던 것, 저장이 도는 중에도 재렌더링으로 버튼이
 * 다시 눌리던 것, 환자를 바꿔도 앞 환자의 저장 안내가 남던 것. */
test("문자 설정을 실제로 받아 오기 전(로딩·실패)에는 저장을 잠근다", () => {
  const code = codeOnly(read("js/doctor.js"));

  assert.match(code, /var smsPlanState = "loading"/, "환자마다 불러오기 상태를 loading 으로 시작해야 한다");
  assert.match(
    code,
    /var editable = roleEditable && smsPlanState === "ready" && !smsSaving/,
    "guideSmsPlan 의 canSave 가 smsPlanState==='ready' 를 요구해야 아직 못 받은 서버 값을 기본값으로 덮어쓰지 않는다",
  );
  const messagePlanBlock = code.slice(code.indexOf(".messagePlan("));
  assert.match(
    messagePlanBlock,
    /\.messagePlan\([\s\S]{0,20}\)\s*\.then\(function \(data\) \{[\s\S]{0,80}?smsPlanState = "ready"/,
    "messagePlan 응답이 와야 ready 로 열린다",
  );
  assert.match(
    messagePlanBlock,
    /\.catch\(function \(\) \{[\s\S]{0,600}?smsPlanState = "failed"/,
    "messagePlan 이 실패하면 failed 로 남아 저장이 잠긴 채여야 한다",
  );
});

test("저장이 도는 동안에는 재렌더링돼도 버튼이 다시 활성화되지 않는다", () => {
  const code = codeOnly(read("js/doctor.js"));

  assert.match(
    code,
    /save:\s*function\s*\(plan\)\s*\{[\s\S]{0,500}?smsSaving = true;[\s\S]{0,120}?renderPanel\(\);/,
    "save 콜백이 smsSaving 을 켠 뒤에 renderPanel() 을 불러야 새로 그려진 버튼도 잠긴다",
  );
  assert.match(code, /smsSaving = false;[\s\S]{0,300}?smsAdopt\(data\)/, "성공하면 smsSaving 을 풀어야 다음 저장이 된다");
  assert.match(code, /smsSaving = false;[\s\S]{0,300}?저장하지 못했습니다/, "실패해도 smsSaving 을 풀어야 다시 시도할 수 있다");
});

test("환자를 바꾸면 저장 안내·불러오기 상태를 새로 잰다", () => {
  const code = codeOnly(read("js/doctor.js"));

  assert.match(
    code,
    /smsForget\(\);[\s\S]{0,300}?smsSaying = "";[\s\S]{0,60}?smsPlanState = "loading";[\s\S]{0,60}?smsSaving = false;/,
    "load() 가 smsForget 뒤에 smsSaying·smsPlanState·smsSaving 을 모두 초기화해야 앞 환자의 안내가 안 남는다",
  );
});
