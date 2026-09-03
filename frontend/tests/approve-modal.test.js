/* **승인 확인 모달** — 와이어프레임 D1-5.
 *
 * 원문 주석: 「화면을 갈아끼우지 않는다 — 뒤에 최종 확인 탭이 흐려진 채
 * 남는다」. 승인은 되돌리기 어려운 일이라, 무엇을 승인했는지 뒤에 그대로
 * 보이는 채로 결과를 말한다.
 *
 * 창은 `doctor.js` 안에만 있었다. 그래서 **최종 확인 탭에서 승인하면 아무
 * 창도 안 떴다** — 원장님이 실제로 일하는 자리가 그쪽인데도.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const { load } = require("./browser-shim.js");
const { read, codeOnly, markupOnly, rule } = require("./source.js");

function box() {
  return load("api", "session", "sms-plan", "guide-view");
}

/* ── 언제 나가는가 ──────────────────────────────────────────────────── */

test("**오늘·내일은 말로 적는다** — 날짜를 적으면 달력을 짚어야 한다", () => {
  const { sendWhenText } = box();
  const now = new Date(2026, 8, 1, 14, 0); // 2026-09-01

  assert.equal(sendWhenText("2026-09-01T18:00:00+09:00", now), "오늘 18:00");
  assert.equal(sendWhenText("2026-09-02T10:00:00+09:00", now), "내일 10:00");
  assert.equal(sendWhenText("2026-09-05T18:00:00+09:00", now), "9월 5일 18:00");

  /* 지난 것도 날짜로 — 「어제」라고 말할 자리가 아니다 */
  assert.equal(sendWhenText("2026-08-31T18:00:00+09:00", now), "8월 31일 18:00");
});

test("시각을 모르면 지어내지 않는다", () => {
  const { sendWhenText } = box();
  assert.equal(sendWhenText(null), "곧");
  assert.equal(sendWhenText(""), "곧");
  assert.equal(sendWhenText("망가진 값"), "곧");
});

test("**서버가 준 시각을 문자 그대로 읽는다** — 시간대로 하루가 밀리면 안 된다", () => {
  const { sendWhenText } = box();
  const code = codeOnly(read("js/guide-view.js"));
  const at = code.indexOf("function sendWhenText");
  const body = code.slice(at, at + 900);

  /* `new Date("2026-09-01T18:00:00+09:00")` 로 읽고 `getHours()` 를 쓰면 브라우저
     시간대에 따라 시각이 달라진다. 서버는 이미 KST 로 보내 준다. */
  assert.ok(!/new Date\(\s*iso/.test(body), "받은 문자열을 Date 로 넘긴다 — 시간대만큼 밀린다");

  const now = new Date(2026, 8, 1, 14, 0);
  assert.equal(sendWhenText("2026-09-01T18:00:00+09:00", now), "오늘 18:00", "시각이 밀렸다");
});

/* ── 무엇을 말하는가 ────────────────────────────────────────────────── */

test("**언제 · 누구에게**가 첫 줄이다", () => {
  const { approvedModalHtml } = box();
  const html = approvedModalHtml({
    scheduledAt: "2026-09-01T18:00:00+09:00",
    name: "김서연",
    now: new Date(2026, 8, 1, 14, 0),
  });

  assert.ok(html.includes("승인 완료"), "무엇이 끝났는지 안 말한다");
  assert.ok(html.includes("오늘 18:00"), "언제 나가는지 안 말한다");
  assert.ok(html.includes("김서연 님께 발송 예정"), "누구에게 가는지 안 말한다");
  assert.ok(html.includes("확인 문자"), "뒤이어 나갈 것을 안 말한다");
  assert.ok(html.includes("실패 처리하지 않고 발송 대기"), "보류를 실패로 오해하게 둔다");
});

test("이름을 모르면 지어내지 않는다", () => {
  const { approvedModalHtml } = box();
  const html = approvedModalHtml({ scheduledAt: "2026-09-01T18:00:00+09:00" });
  assert.ok(html.includes("발송 예정"), "발송 예정이라는 말이 사라졌다");
  assert.ok(!html.includes("님께"), "이름이 없는데 「 님께」가 남았다");
});

test("**없는 발송을 약속하지 않는다**", () => {
  const { approvedModalHtml } = box();
  const html = approvedModalHtml({ scheduledAt: "2026-09-01T18:00:00+09:00", name: "김서연" });

  /* 원문은 「자동 발송됩니다」라고 적지만 이 저장소에는 아직 문자를 보내는
     것이 없다. 그 문장만 읽고 「환자에게 갔다」고 믿으면, 안 간 것을 갔다고
     아는 상태가 된다 (KEY-148 §6 · KEY-160). */
  assert.match(html, /\[demo\]/, "아직 발송기가 없다는 것을 안 적는다");
  assert.ok(html.includes("발송 예약까지"), "승인이 어디까지인지 안 적는다");
});

test("**서버에 발송기가 생기면 이 검사가 먼저 깨진다**", () => {
  /* `[demo]` 문구는 발송기가 붙는 날 지워야 한다. 그때 지우는 것을 잊으면
     원장님은 계속 「아직 안 나간다」고 읽는다 — 이번엔 반대로 틀린다.
     발송기가 생겼는지는 `GuideMessage` 를 `SENT` 로 바꾸는 코드가 있는가로 본다. */
  const service = read("../app/services/guides.py");
  const sends = /GuideMessageStatus\.SENT/.test(service) && !/status=GuideMessageStatus\.SENT,\n\s*\)/.test(service);
  const html = codeOnly(read("js/guide-view.js"));
  if (sends) {
    assert.ok(!html.includes("[demo]"), "발송기가 붙었는데 아직 없다고 말한다");
  } else {
    assert.ok(html.includes("[demo]"), "발송기가 없는데 나간다고 말한다");
  }
});

/* ── 단추 ───────────────────────────────────────────────────────────── */

test("**개발용 환자 화면 열기는 창에 없다**", () => {
  const { approvedModalHtml } = box();
  const html = approvedModalHtml({ scheduledAt: "2026-09-01T18:00:00+09:00", name: "김" });

  assert.ok(!html.includes("개발용"), "창에 개발용 단추가 남아 있다");
  assert.ok(!html.includes("data-open-patient"), "창이 개발용 링크 발급을 부른다");

  assert.ok(html.includes("현황 보기"), "현황으로 가는 길이 없다");
  assert.ok(html.includes("닫기"), "닫을 수가 없다");
});

test("의사 화면의 창도 같은 것을 쓴다 — 두 벌이면 한쪽만 고쳐진다", () => {
  const code = codeOnly(read("js/doctor.js"));
  const at = code.indexOf("function approvedModal(");
  assert.notEqual(at, -1, "의사 화면에 승인 창이 없다");

  const body = code.slice(at, code.indexOf("\n  }", at));
  assert.ok(body.includes("approvedModalHtml("), "제 것으로 따로 그린다");
  assert.ok(!body.includes("개발용"), "의사 화면 창에 개발용 단추가 남아 있다");
});

/* ── 붙어 있는가 ────────────────────────────────────────────────────── */

test("**최종 확인 탭에서 승인하면 창이 뜬다**", () => {
  const code = codeOnly(read("js/visit-guide.js"));
  const at = code.indexOf("doctorApi\n      .approve(");
  assert.notEqual(at, -1, "승인을 서버에 안 보낸다 — 검사가 헛돈다");

  const stop = code.indexOf("\n  });", at);
  const around = code.slice(at, stop === -1 ? code.length : stop);
  assert.ok(around.includes("openModal("), "승인해도 창이 안 뜬다");
  assert.ok(around.includes("approvedModalHtml("), "다른 것을 그린다");

  /* 서버가 준 시각을 써야 한다. 화면이 「오늘 18시겠지」 하고 셈하면 두 곳이
     셈하게 되고, 어느 쪽이 진짜인지 알 수 없다. */
  assert.match(around, /result[\s\S]{0,40}scheduled_at/, "서버가 준 발송 시각을 안 쓴다");
});

test("창을 그릴 자리가 화면에 있다", () => {
  ["patients.html", "doctor.html"].forEach((page) => {
    const html = markupOnly(read(page));
    assert.match(html, /id="modal"/, `${page} 에 창 자리가 없다 — 승인해도 아무것도 안 뜬다`);
    assert.match(html, /id="modal-body"/, `${page} 에 창 본문 자리가 없다`);
  });
});

test("닫기와 현황 보기가 실제로 붙어 있다", () => {
  const code = codeOnly(read("js/visit-guide.js"));
  assert.match(code, /\[data-close\]/, "닫기를 받는 자리가 없다");

  const at = code.indexOf("[data-go-status]");
  assert.notEqual(at, -1, "현황 보기를 받는 자리가 없다");

  const around = code.slice(at, at + 500);
  /* 탭을 바꾸는 규칙은 `detail.js` 것이다 — 여기서 흉내내면 표시(✓ · ● · ○)가
     갈린다. 탭 단추를 대신 누른다. */
  assert.match(around, /\.tab\[data-tab="status"\]/, "탭 단추를 안 누른다");
  assert.ok(around.includes("closeModal("), "창을 안 닫는다");
});

test("모달 어휘는 공용 CSS 에 있다 — 두 화면이 같은 창을 쓴다", () => {
  const blocks = read("css/blocks.css");
  [".modal", ".modal__card", ".modal__box", ".modal__sub"].forEach((sel) => {
    rule(blocks, sel); // 없으면 던진다
  });

  const doctorCss = read("css/doctor.css");
  assert.ok(
    !/^\.modal\s*\{/m.test(doctorCss),
    "doctor.css 에 모달이 남아 있다 — 두 벌이면 한쪽만 고쳐진다",
  );
});
