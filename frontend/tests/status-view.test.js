/* **현황** — 와이어프레임 D1-6.
 *
 * 승인 뒤에 무슨 일이 있었는지 볼 자리가 없었다 — 보냈는지 · 열었는지 ·
 * 답했는지가 어디에도 안 보였다.
 *
 * 여기서 재는 것은 **누가 무엇을 했는가를 어떻게 읽히게 하는가**다.
 * 사람과 시스템과 환자를 못 가르면, 「시스템이 지웠다」가 「누가 지웠다」로
 * 읽힌다.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const { load } = require("./browser-shim.js");
const { read, codeOnly, rule } = require("./source.js");

function box() {
  return load("api", "session", "sms-plan", "guide-view", "status-view");
}

/* ── 누가 한 일인가 ─────────────────────────────────────────────────── */

test("**사람 · 환자 · 시스템 셋을 가른다**", () => {
  const { timelineActor } = box();

  assert.deepEqual(timelineActor({ kind: "APPROVED", actor: "박연" }), { name: "박연", who: "staff" });
  assert.deepEqual(timelineActor({ kind: "GUIDE_VIEWED" }), { name: "환자", who: "patient" });
  assert.deepEqual(timelineActor({ kind: "CHECK_IN" }), { name: "환자", who: "patient" });

  /* 이름도 없고 환자 일도 아니면 시스템이다 — 발송·삭제·토큰 */
  assert.deepEqual(timelineActor({ kind: "SENT" }), { name: "시스템", who: "system" });
});

test("**서버가 「환자」를 적어 보내지 않는다** — 이름이 「환자」인 직원과 못 가른다", () => {
  /* 서버는 사람이 한 것에만 이름을 준다. 환자와 시스템은 비어 있고,
     그 둘을 가르는 것은 화면 몫이다 — 무슨 일이었는지를 보고 정한다. */
  const service = read("../app/timeline/service.py");
  assert.ok(!service.includes('actor="환자"'), "서버가 「환자」를 적어 보낸다");
  assert.ok(!service.includes('actor="시스템"'), "서버가 「시스템」을 적어 보낸다");
});

/* ── 무엇을 한 일인가 ───────────────────────────────────────────────── */

test("**서버 코드를 사람 말로 옮긴다**", () => {
  const { timelineSaying } = box();

  assert.equal(timelineSaying({ kind: "APPROVED" }), "승인");
  assert.equal(timelineSaying({ kind: "SUBMITTED" }), "스탭 확인 완료 · 승인 요청");
  assert.equal(timelineSaying({ kind: "GUIDE_VIEWED" }), "안내문 열람");
});

test("**모르는 코드는 그대로 보여 준다** — 빈칸이면 일이 있었는데 없어 보인다", () => {
  const { timelineSaying } = box();
  assert.equal(timelineSaying({ kind: "SOMETHING_NEW" }), "SOMETHING_NEW");
});

test("**되돌린 사유가 그 줄에 붙는다** — 알림을 다시 찾아가지 않게", () => {
  const { timelineSaying } = box();

  assert.equal(
    timelineSaying({ kind: "RETURNED", detail: "진료기록 재업로드 필요" }),
    "스탭에 되돌림 · 진료기록 재업로드 필요",
  );
  assert.equal(timelineSaying({ kind: "EDITED", section: "medication" }), "내용 수정 · medication");
});

test("시각만 뗀다 — 날짜는 진료 하루치라 줄마다 적으면 자리만 먹는다", () => {
  const { timelineClock } = box();

  assert.equal(timelineClock("2026-08-13T10:32:00+09:00"), "10:32");
  assert.equal(timelineClock(""), "");
  assert.equal(timelineClock(null), "");
});

/* ── 안내문을 어디까지 읽었나 ───────────────────────────────────────── */

test("**어느 장에서 멈췄는지가 이 블록의 값이다**", () => {
  const { readProgress, readSaying } = box();
  const label = (k) => ({ medication: "복약지도", caution: "주의사항", life: "생활지도" })[k];

  const p = readProgress([
    { kind: "GUIDE_VIEWED", section: "medication", at: "2026-08-13T19:14:00+09:00" },
    { kind: "GUIDE_VIEWED", section: "caution", at: "2026-08-13T19:22:00+09:00" },
  ]);

  assert.equal(p.opened, true);
  assert.equal(p.read, 2);
  assert.equal(p.total, 4);
  assert.equal(p.lastSection, "caution");
  assert.match(readSaying(p, label), /주의사항까지 읽고 멈췄습니다/);
});

test("**안 읽은 것과 다 읽은 것은 스탭이 할 일이 다르다**", () => {
  const { readProgress, readSaying } = box();
  const label = (k) => k;

  assert.match(readSaying(readProgress([]), label), /아직 열지 않았습니다/);

  const all = readProgress(
    ["medication", "caution", "life", "messages"].map((s) => ({
      kind: "GUIDE_VIEWED",
      section: s,
      at: "2026-08-13T19:00:00+09:00",
    })),
  );
  assert.match(readSaying(all, label), /끝까지 읽었습니다/);
});

test("**어느 장인지 모르는 열람은 장수에 안 넣는다** — 열긴 열었다고만 말한다", () => {
  const { readProgress, readSaying } = box();

  const p = readProgress([{ kind: "GUIDE_VIEWED", at: "2026-08-13T19:14:00+09:00" }]);
  assert.equal(p.opened, true, "열었는데 안 열었다고 한다");
  assert.equal(p.read, 0, "어느 장인지 모르는데 읽은 것으로 셌다");
  assert.match(readSaying(p, (k) => k), /어느 항목인지 남지 않았습니다/);
});

test("열람이 아닌 기록은 세지 않는다", () => {
  const { readProgress } = box();
  const p = readProgress([{ kind: "APPROVED", at: "2026-08-13T11:02:00+09:00" }]);
  assert.equal(p.opened, false, "승인을 열람으로 셌다");
});

/* ── 그리기 ──────────────────────────────────────────────────────────── */

test("**위 2 : 1, 아래 전폭** — 원문 배치", () => {
  const css = codeOnly(read("css/blocks.css"));

  assert.match(rule(css, ".st__send"), /flex:\s*2/, "발송 칸이 2가 아니다");
  assert.match(rule(css, ".st__side"), /flex:\s*1/, "오른쪽 칸이 1이 아니다");

  /* 「안내문 읽음」과 「확인 문자 응답」은 **한 카드**다 — 원문이 구분선으로 나눈다 */
  assert.ok(rule(css, ".st__rule"), "두 항목을 나누는 선이 없다");
});

test("**● 와 ○ 는 크기·색이 같다** — 예정을 흐리게 만들면 「안 될 것」으로 읽힌다", () => {
  const css = codeOnly(read("css/blocks.css"));
  const dot = rule(css, ".sd__dot");

  assert.match(dot, /color:\s*var\(--ink\)/, "표시가 흐리다");
  assert.ok(!/opacity/.test(dot), "예정을 투명도로 죽였다");
});

test("**시스템이 한 일을 글자색으로만 가른다** — 배지를 붙이면 사람 일보다 먼저 든다", () => {
  const css = codeOnly(read("css/blocks.css"));
  const system = rule(css, ".tl__who--system");

  assert.match(system, /color:/, "시스템 줄이 사람 줄과 같아 보인다");
  assert.ok(!/background|border|content/.test(system), "배지·아이콘을 붙였다");
});

test("**화면이 진짜 기록을 부른다** — 프레임으로 남겨 두지 않았다", () => {
  const code = codeOnly(read("js/visit-guide.js"));

  assert.ok(code.includes("doctorApi\n      .timeline("), "시간 흐름을 안 부른다");
  assert.ok(code.includes("statusScreenHtml("), "현황을 안 그린다");

  /* 옛 프레임 안내가 남아 있으면 안 된다 */
  assert.ok(!code.includes("이 화면이 되려면"), "「이 화면이 되려면」 안내가 남았다");
});

test("**현황은 자기 번호표를 쓴다** — 안내문과 나눠 쓰면 서로를 취소시킨다", () => {
  const code = codeOnly(read("js/visit-guide.js"));

  assert.ok(code.includes("timelineSeq"), "번호표를 나눠 쓴다");
  const at = code.indexOf("function loadTimeline");
  const body = code.slice(at, at + 600);
  assert.ok(!body.includes("loadSeq"), "현황이 안내문 번호표를 건드린다");
});

/* ── 발송 · 예정 ─────────────────────────────────────────────────────── */

test("**서버가 준 것을 그린다** — 화면이 따로 셈하지 않는다", () => {
  const { sendRowsHtml } = box();
  const html = sendRowsHtml([
    { kind: "GUIDE", status: "SENT", at: "2026-08-13T18:00:00+09:00", sent_at: "2026-08-13T18:00:00+09:00" },
    { kind: "CHECK_D7", status: "SCHEDULED", at: "2026-08-20T10:00:00+09:00" },
  ]);

  assert.ok(html.includes("진료 안내문"), "코드를 사람 말로 안 옮긴다");
  assert.ok(html.includes("일주일 뒤 확인"), "회차 이름이 없다");
  assert.ok(html.includes("08-20 10:00"), "언제 가는지 안 적는다");
  assert.ok(html.includes("발송 완료"), "보낸 것을 안 표시한다");
  assert.ok(html.includes("예정"), "예정을 안 표시한다");

  /* **두 곳이 셈하면 어느 쪽이 진짜인지 알 수 없다** — 화면은 받은 것만 쓴다 */
  const code = codeOnly(read("js/status-view.js"));
  const at = code.indexOf("function sendRowsHtml");
  const body = code.slice(at, at + 1400);
  assert.ok(!body.includes("smsDateAfter"), "화면이 발송일을 따로 셈한다");
});

test("**못 나간 것과 예정을 또렷이 가른다** — 못 나간 것은 사람이 손대야 한다", () => {
  const { sendRowsHtml, messageState } = box();

  assert.equal(messageState("FAILED").bad, true);
  assert.equal(messageState("SCHEDULED").bad, false);
  assert.equal(messageState("SENT").done, true);
  assert.equal(messageState("CANCELED").done, false, "끈 것을 보낸 것으로 본다");

  const html = sendRowsHtml([{ kind: "CHECK_D7", status: "FAILED", at: "2026-08-20T10:00:00+09:00" }]);
  assert.ok(html.includes("is-bad"), "못 나간 줄이 예정과 같아 보인다");
  assert.ok(html.includes("못 나감"), "무슨 일인지 안 말한다");

  const css = codeOnly(read("css/blocks.css"));
  assert.ok(rule(css, ".sd__row.is-bad"), "못 나간 줄의 모양이 없다");
});

test("**승인 전에는 왜 비었는지 말한다** — 빈 판은 「고장」으로 읽힌다", () => {
  const { sendRowsHtml } = box();

  const html = sendRowsHtml([]);
  assert.match(html, /승인하면/, "왜 비었는지 안 말한다");
  assert.ok(!html.includes("sd__row"), "빈 줄을 그렸다");
});

test("모르는 상태·회차도 그대로 보여 준다 — 빈칸이면 일이 있었는데 없어 보인다", () => {
  const { sendRowsHtml, messageState } = box();

  assert.equal(messageState("SOMETHING").say, "SOMETHING");
  const html = sendRowsHtml([{ kind: "NEW_KIND", status: "SCHEDULED", at: "2026-08-20T10:00:00+09:00" }]);
  assert.ok(html.includes("NEW_KIND"), "모르는 회차가 화면에서 사라졌다");
});

test("**화면이 서버의 발송 목록을 넘긴다**", () => {
  const code = codeOnly(read("js/visit-guide.js"));
  assert.ok(code.includes("messages: timeline.messages"), "서버가 준 목록을 안 넘긴다");
});
