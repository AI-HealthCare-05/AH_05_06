/* **보류와 실패는 다른 축이다** — 와이어프레임 S2-3 · D1-7.
 *
 *   실패  보내려 했고 안 됐다.        지난 일.
 *   보류  아직 안 보냈고, 지금 보내면 안 될 것을 안다.  앞일.
 *
 * S2-3 에서 박수빈의 08-11 진료 안내문은 실패했고, 같은
 * 번호로 예약된 08-14 것은 「⏸ 보류 · 번호」다 — **같은 원인인데 상태가
 * 다르다.** 한 무더기로 뭉치면 「이미 벌어진 것」과 「고치면 아직 막을 수
 * 있는 것」이 섞여, 스탭이 무엇을 손대야 하는지 안 보인다.
 *
 * 사유 목록도 갈린다. 보류는 둘, 실패는 넷이다.
 *
 * **아직 아무것도 이 상태를 만들지 않는다** — 문자를 보내는 것이 없다.
 * 여기서 정하는 것은 낱말이고, 발송기가 붙을 때 다시 정하지 않기 위한 것이다.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const { load } = require("./browser-shim.js");
const { read } = require("./source.js");

function box() {
  /* 어휘는 `message-words.js` 로 옮겼다 — 화면 둘(현황 탭 · 관리 · 발송 예정)이
     같은 낱말을 쓰는데, 현황 탭을 그리는 파일에 두면 관리 화면이 `guide-view.js`
     까지 물고 와야 했다. 그리는 자리(`sendRowsHtml`)는 아직 저쪽에 있다. */
  return load("api", "session", "sms-plan", "guide-view", "message-words", "status-view");
}

/* ── 두 목록이 다르다 ───────────────────────────────────────────────── */

test("**실패 이유는 넷이다** — D1-7 이 못박는다", () => {
  const { FAILURE_SAYING } = box();
  assert.deepEqual(Object.keys(FAILURE_SAYING).sort(), [
    "CARRIER",
    "INVALID_PHONE",
    "OPT_OUT",
    "SENDER_UNREGISTERED",
  ]);
  assert.equal(FAILURE_SAYING.INVALID_PHONE, "잘못된 번호");
  assert.equal(FAILURE_SAYING.SENDER_UNREGISTERED, "발신번호 미등록");
});

test("**보류 이유는 다섯이다** — S2-3의 원문 둘에 KEY-250이 발송 직전 게이트 셋을 더했다", () => {
  const { HOLD_SAYING } = box();
  assert.deepEqual(Object.keys(HOLD_SAYING).sort(), [
    "INVALID_PHONE",
    "NOT_APPROVED",
    "NO_CREDIT",
    "SAFETY_CHECK_FAILED",
    "SOURCE_NOT_DELETED",
  ]);
  /* 원문 표기는 「⏸ 보류 · 번호」 · 「⏸ 보류 · 문자 잔량」이다 — 원문의 둘은
     그대로 짧게 적는다. KEY-250이 더한 셋은 원문에 표기가 없어 사람 말로
     새로 옮겼다. */
  assert.equal(HOLD_SAYING.INVALID_PHONE, "번호");
  assert.equal(HOLD_SAYING.NO_CREDIT, "문자 잔량");
});

test("**두 목록을 하나로 합치지 않았다**", () => {
  const { FAILURE_SAYING, HOLD_SAYING } = box();
  assert.notDeepEqual(Object.keys(FAILURE_SAYING).sort(), Object.keys(HOLD_SAYING).sort());
  /* 겹치는 낱말이 있어 합치고 싶어지는 자리다 — 재는 것이 다르다 */
  assert.ok(FAILURE_SAYING.INVALID_PHONE && HOLD_SAYING.INVALID_PHONE, "겹치는 낱말이 사라졌다");
  assert.notEqual(FAILURE_SAYING.INVALID_PHONE, HOLD_SAYING.INVALID_PHONE, "같은 말로 적는다");
});

/* ── 화면이 가른다 ──────────────────────────────────────────────────── */

test("**같은 원인이라도 지난 것과 앞일을 다르게 적는다**", () => {
  const { messageSaying } = box();

  assert.equal(
    messageSaying({ status: "FAILED", failure_code: "INVALID_PHONE" }),
    "발송 실패",
  );
  assert.equal(messageSaying({ status: "HELD", hold_reason: "INVALID_PHONE" }), "보류 · 번호");
});

test("모르는 코드는 적지 않는다 — 코드를 그대로 보이면 사람 말이 아니다", () => {
  const { messageSaying } = box();
  assert.equal(messageSaying({ status: "FAILED", failure_code: "WAT" }), "발송 실패");
  assert.equal(messageSaying({ status: "HELD", hold_reason: "WAT" }), "보류");
  assert.equal(messageSaying({ status: "HELD" }), "보류");
});

test("**보류를 실패의 사유로 읽지 않는다**", () => {
  /* 두 칸을 섞으면 「보류 · 잘못된 번호」처럼 적힌다 — 보내 본 적이 없는데
     보내 봤다는 말이 된다. */
  const { messageSaying } = box();
  assert.equal(
    messageSaying({ status: "HELD", failure_code: "SENDER_UNREGISTERED" }),
    "보류",
    "실패 사유를 보류 줄에 적는다",
  );
  assert.equal(
    messageSaying({ status: "FAILED", hold_reason: "NO_CREDIT" }),
    "발송 실패",
    "보류 사유를 실패 줄에 적는다",
  );
});

test("**둘 다 사람이 손대야 하는 줄이다**", () => {
  const { messageState } = box();
  assert.equal(messageState("FAILED").bad, true);
  assert.equal(messageState("HELD").bad, true, "보류가 그냥 지나가는 줄로 보인다");

  /* 예정과 꺼짐은 아니다 — 두면 되는 것과 사람이 손댈 것을 가른다 */
  assert.equal(messageState("SCHEDULED").bad, false);
  assert.equal(messageState("CANCELED").bad, false);
});

test("표시가 원문과 같다 — ⚠ 와 ⏸ 만 눈에 걸린다", () => {
  const { messageState } = box();
  assert.equal(messageState("FAILED").mark, "⚠");
  assert.equal(messageState("HELD").mark, "⏸");
  /* ● 와 ○ 는 크기·색이 같다(원문). 예정을 흐리게 두면 「안 될 것」으로 읽힌다 */
  assert.equal(messageState("SENT").mark, "●");
  assert.equal(messageState("SCHEDULED").mark, "○");
});

test("발송 줄이 실제로 그 말을 쓴다", () => {
  const { sendRowsHtml } = box();
  const html = sendRowsHtml([
    { kind: "GUIDE", status: "FAILED", failure_code: "INVALID_PHONE", at: "2026-08-11T18:00:00+09:00" },
    { kind: "CHECK_D7", status: "HELD", hold_reason: "NO_CREDIT", at: "2026-08-14T10:00:00+09:00" },
  ]);

  assert.ok(html.includes("발송 실패"), "실패한 줄이 그렇게 안 적힌다");
  assert.ok(html.includes("보류 · 문자 잔량"), "보류 사유가 줄에 안 적힌다");
  assert.ok(html.includes("⚠") && html.includes("⏸"), "표시가 안 붙는다");
});

/* ── 서버와 같은 낱말인가 ───────────────────────────────────────────── */

test("**화면과 서버가 같은 낱말을 쓴다**", () => {
  const { FAILURE_SAYING, HOLD_SAYING } = box();
  const models = read("../app/models/visits.py");

  const fail = models.slice(models.indexOf("class GuideMessageFailure"), models.indexOf("class GuideMessageStatus"));
  Object.keys(FAILURE_SAYING).forEach((code) => {
    assert.ok(fail.includes(`${code} = "${code}"`), `서버에 실패 사유 ${code} 이 없다`);
  });

  const hold = models.slice(models.indexOf("class GuideMessageHold"), models.indexOf("class GuideMessageFailure"));
  Object.keys(HOLD_SAYING).forEach((code) => {
    assert.ok(hold.includes(`${code} = "${code}"`), `서버에 보류 사유 ${code} 이 없다`);
  });

  const status = models.slice(models.indexOf("class GuideMessageStatus"), models.indexOf("class GuideMessageSetting"));
  assert.ok(status.includes('HELD = "HELD"'), "서버에 보류 상태가 없다");
});

test("서버가 그 두 칸을 화면에 준다", () => {
  const schemas = read("../app/dtos/visits.py");
  assert.match(schemas, /hold_reason: str \| None/, "보류 사유를 안 준다");
  assert.match(schemas, /failure_code: str \| None/, "실패 사유를 안 준다");

  const service = read("../app/services/visit_timeline.py");
  assert.match(service, /hold_reason=row\.hold_reason/, "읽어 놓고 안 싣는다");
});

/* **실패에는 까닭을 붙이지 않는다** (팀장 지적 2026-09-01).
 *
 * 「잘못된 번호」는 그 번호가 정말 틀렸다는 뜻으로 읽히는데, 우리가 아는 것은
 * **나간 것이 안 됐다**는 사실뿐이다. 확인할 방법이 없는 것을 화면이 단정하면
 * 스탭이 멀쩡한 번호를 고치러 간다.
 *
 * 보류는 다르다 — 우리가 붙들기로 정한 것이라 그 까닭을 우리가 안다.
 */
test("**실패에 까닭을 붙이지 않는다** — 번호가 틀렸는지는 알 수 없다", () => {
  const { messageSaying } = load("api", "session", "sms-plan", "guide-view", "message-words", "status-view");

  for (const code of ["INVALID_PHONE", "OPT_OUT", "CARRIER", "SENDER_UNREGISTERED"]) {
    assert.strictEqual(
      messageSaying({ status: "FAILED", failure_code: code }),
      "발송 실패",
      `${code} 를 화면이 단정한다`,
    );
  }
});

test("보류에는 붙인다 — 우리가 붙들기로 정한 까닭이다", () => {
  const { messageSaying } = load("api", "session", "sms-plan", "guide-view", "message-words", "status-view");

  assert.strictEqual(messageSaying({ status: "HELD", hold_reason: "NO_CREDIT" }), "보류 · 문자 잔량");
  assert.strictEqual(messageSaying({ status: "HELD", hold_reason: "INVALID_PHONE" }), "보류 · 번호");
});

test("실패 사유 코드는 계속 담아 둔다 — 화면이 안 보일 뿐이다", () => {
  const { FAILURE_SAYING } = load("api", "session", "sms-plan", "guide-view", "message-words", "status-view");

  assert.strictEqual(Object.keys(FAILURE_SAYING).length, 4, "D1-7 의 넷은 그대로다");
  assert.strictEqual(FAILURE_SAYING.SENDER_UNREGISTERED, "발신번호 미등록", "CSV 와 어드민이 쓴다");
});

/* ── 다시 보내기 — KEY-306·D1-7 ──────────────────────────────────────── */

test("**실패·보류만 다시 보낼 수 있다** — canResend", () => {
  const { canResend } = load("api", "session", "sms-plan", "guide-view", "message-words", "status-view");

  assert.equal(canResend("FAILED"), true);
  assert.equal(canResend("HELD"), true);
  /* 예정은 아직 나갈 차례를 기다리는 중이고, 완료·꺼짐은 다시 보낼 대상이
     아니다 — 실패/보류가 아닌 상태에 단추가 뜨면 무엇을 다시 보내는지
     흐려진다. */
  assert.equal(canResend("SCHEDULED"), false);
  assert.equal(canResend("SENT"), false);
  assert.equal(canResend("CANCELED"), false);
});

test("발송 줄이 실패·보류에만 [다시 보내기]를 단다", () => {
  const { sendRowsHtml } = load("api", "session", "sms-plan", "guide-view", "message-words", "status-view");
  const html = sendRowsHtml([
    { guide_message_id: 501, kind: "GUIDE", status: "SENT", at: "2026-08-11T18:00:00+09:00" },
    { guide_message_id: 502, kind: "CHECK_D7", status: "FAILED", failure_code: "INVALID_PHONE", at: "2026-08-14T10:00:00+09:00" },
    { guide_message_id: 503, kind: "CHECK_D15", status: "HELD", hold_reason: "NOT_APPROVED", at: "2026-08-21T10:00:00+09:00" },
    { guide_message_id: 504, kind: "RUN_OUT", status: "SCHEDULED", at: "2026-09-01T10:00:00+09:00" },
  ]);

  /* 실패·보류 두 줄에만 단추가 있고, 각자 자기 번호를 심는다 — 다른
     줄의 번호를 잘못 심으면 엉뚱한 문자를 다시 보낸다. */
  assert.ok(html.includes('data-resend="502"'), "실패 줄에 다시 보내기가 없다");
  assert.ok(html.includes('data-resend="503"'), "보류 줄에 다시 보내기가 없다");
  assert.ok(!html.includes('data-resend="501"'), "이미 보낸 줄에 다시 보내기가 붙었다");
  assert.ok(!html.includes('data-resend="504"'), "예정 줄에 다시 보내기가 붙었다");
});

test("병원이 새로 늘린 보류 사유도 화면이 사람 말로 옮긴다 — KEY-250", () => {
  const { messageSaying } = load("api", "session", "sms-plan", "guide-view", "message-words", "status-view");

  assert.strictEqual(messageSaying({ status: "HELD", hold_reason: "NOT_APPROVED" }), "보류 · 안내 미승인");
  assert.strictEqual(messageSaying({ status: "HELD", hold_reason: "SAFETY_CHECK_FAILED" }), "보류 · 안전검증 미통과");
  assert.strictEqual(messageSaying({ status: "HELD", hold_reason: "SOURCE_NOT_DELETED" }), "보류 · 원본 문서 미삭제");
});

test("서버는 이제 guide_message_id도 준다 — 다시 보내기가 대상을 안다", () => {
  const schemas = read("../app/dtos/visits.py");
  assert.match(schemas, /guide_message_id: int/, "발송·예정 표가 어느 문자인지 모른다");

  const service = read("../app/services/visit_timeline.py");
  assert.match(service, /guide_message_id=row\.guide_message_id/, "읽어 놓고 안 싣는다");
});
