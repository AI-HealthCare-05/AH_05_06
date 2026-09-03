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
  /* 어휘는 `message-words.js` 로 옮겼다 — 화면 둘(현황 탭 · 관리 · 발송 예정)이
     같은 낱말을 쓰는데, 현황 탭을 그리는 파일에 두면 관리 화면이 `guide-view.js`
     까지 물고 와야 했다. 그리는 자리(`sendRowsHtml`)는 아직 저쪽에 있다. */
  return load("api", "session", "sms-plan", "guide-view", "message-words", "status-view");
}

/* ── 누가 한 일인가 ─────────────────────────────────────────────────── */

test("**사람 · 환자 · 시스템 셋을 가른다**", () => {
  const { timelineActor } = box();

  assert.deepEqual(timelineActor({ category: "GUIDE", event: "GUIDE_APPROVED", actor: "박연" }), { name: "박연", who: "staff" });
  assert.deepEqual(timelineActor({ category: "PATIENT", event: "GUIDE_VIEWED" }), { name: "환자", who: "patient" });
  assert.deepEqual(timelineActor({ category: "CHECK_IN", event: "CHECK_IN_SUBMITTED" }), { name: "환자", who: "patient" });

  /* 이름도 없고 환자 일도 아니면 시스템이다 — 발송·삭제·토큰 */
  assert.deepEqual(timelineActor({ category: "GUIDE", event: "GUIDE_GENERATED" }), { name: "시스템", who: "system" });
});

test("**서버가 「환자」를 적어 보내지 않는다** — 이름이 「환자」인 직원과 못 가른다", () => {
  /* 서버는 사람이 한 것에만 이름을 준다. 환자와 시스템은 비어 있고,
     그 둘을 가르는 것은 화면 몫이다 — 무슨 일이었는지를 보고 정한다. */
  const service = read("../app/services/visit_timeline.py");
  assert.ok(!service.includes('actor="환자"'), "서버가 「환자」를 적어 보낸다");
  assert.ok(!service.includes('actor="시스템"'), "서버가 「시스템」을 적어 보낸다");

  /* **갈래로 가른다.** 사건 이름을 하나씩 적어 두면 환자가 하는 일이 늘 때마다
     화면 목록도 같이 고쳐야 하고, 안 고치면 조용히 「시스템」으로 뜬다. */
  const view = read("js/status-view.js");
  assert.match(view, /entry\.category === "PATIENT"/, "갈래를 안 보고 사건 이름을 센다");
});

/* ── 무엇을 한 일인가 ───────────────────────────────────────────────── */

test("**서버 코드를 사람 말로 옮긴다**", () => {
  const { timelineSaying } = box();

  assert.equal(timelineSaying({ event: "GUIDE_APPROVED" }), "승인");
  assert.equal(timelineSaying({ event: "GUIDE_SUBMITTED" }), "스탭 확인 완료 · 승인 요청");
  assert.equal(timelineSaying({ event: "GUIDE_VIEWED" }), "안내문 열람");
});

test("**모르는 코드는 그대로 보여 준다** — 빈칸이면 일이 있었는데 없어 보인다", () => {
  const { timelineSaying } = box();
  assert.equal(timelineSaying({ event: "SOMETHING_NEW" }), "SOMETHING_NEW");
});

test("**되돌린 사유가 그 줄에 붙는다** — 알림을 다시 찾아가지 않게", () => {
  const { timelineSaying } = box();

  assert.equal(
    timelineSaying({ event: "GUIDE_RETURNED", note: "진료기록 재업로드 필요" }),
    "스탭에 되돌림 · 진료기록 재업로드 필요",
  );
  assert.equal(timelineSaying({ event: "GUIDE_EDITED", section_key: "medication" }), "내용 수정 · medication");
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
    { event: "GUIDE_VIEWED", section_key: "medication", at: "2026-08-13T19:14:00+09:00" },
    { event: "GUIDE_VIEWED", section_key: "caution", at: "2026-08-13T19:22:00+09:00" },
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
      event: "GUIDE_VIEWED",
      section_key: s,
      at: "2026-08-13T19:00:00+09:00",
    })),
  );
  assert.match(readSaying(all, label), /끝까지 읽었습니다/);
});

test("**어느 장인지 모르는 열람은 장수에 안 넣는다** — 열긴 열었다고만 말한다", () => {
  const { readProgress, readSaying } = box();

  const p = readProgress([{ event: "GUIDE_VIEWED", at: "2026-08-13T19:14:00+09:00" }]);
  assert.equal(p.opened, true, "열었는데 안 열었다고 한다");
  assert.equal(p.read, 0, "어느 장인지 모르는데 읽은 것으로 셌다");
  assert.match(readSaying(p, (k) => k), /어느 항목인지 남지 않았습니다/);
});

test("열람이 아닌 기록은 세지 않는다", () => {
  const { readProgress } = box();
  const p = readProgress([{ event: "GUIDE_APPROVED", at: "2026-08-13T11:02:00+09:00" }]);
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
  assert.ok(html.includes("발송 실패"), "무슨 일인지 안 말한다");

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

/* ── 세 블록이 블록으로 보이는가 ────────────────────────────────────────
 *
 * 회색 바닥 위에 테두리만 있으면 카드가 바닥에 잠긴다. 흰 바탕이 있어야
 * 블록으로 읽힌다 — 화면에서 「배경이 없다」로 되돌아온 자리다.
 */
test("**현황의 세 블록이 기본정보와 같은 상자를 쓴다**", () => {
  /* 담는 모양을 제 어휘로 따로 두면, 한 화면에서 탭을 옮길 때마다 블록 모양이
     바뀌어 눈이 자리를 새로 찾는다. `.box` 하나가 갖는다. */
  const code = codeOnly(read("js/status-view.js"));
  ["st__send", "st__side", "tl"].forEach((name) => {
    assert.ok(
      code.includes('"box ' + name + '"'),
      `.${name} 이 공용 상자를 안 쓴다 — 기본정보와 모양이 갈린다`
    );
  });

  /* 그 상자가 흰 바탕과 테두리를 갖는지도 여기서 못 박는다 */
  const box = rule(read("css/blocks.css"), ".box");
  assert.match(box, /background:\s*var\(--card\)/, "상자에 바탕이 없다 — 회색 바닥에 잠긴다");
  assert.match(box, /border:\s*1px solid var\(--line\)/, "상자에 테두리가 없다");
  assert.match(box, /padding:/, "상자에 여백이 없다");
});

test("블록 제목도 기본정보와 같다", () => {
  const code = codeOnly(read("js/status-view.js"));
  ["발송 · 예정", "환자 액션 현황", "진료 처리 이력"].forEach((title) => {
    const at = code.indexOf(title);
    assert.notEqual(at, -1, `${title} 이 없다`);
    assert.match(
      code.slice(at - 200, at),
      /box__title/,
      `${title} 이 공용 제목이 아니다 — 크기와 굵기가 갈린다`
    );
  });
});

test("줄이 좌우 여백을 또 주지 않는다 — 상자가 이미 물고 있다", () => {
  /* 상자(`.box`)가 24px 을 물고 있어서, 줄이 또 주면 두 겹이 된다.
     예전에는 상자에 여백이 없어 줄이 스스로 벌렸다. */
  const css = read("css/blocks.css");
  [".tl__row", ".sd__row"].forEach((sel) => {
    const pad = /padding:\s*[\w.]+\s+([\w.]+)/.exec(rule(css, sel));
    assert.ok(pad, `${sel} 에 여백이 안 적혀 있다`);
    assert.equal(parseFloat(pad[1]) || 0, 0, `${sel} 이 좌우 여백을 또 준다 — 두 겹이 된다: ${pad[1]}`);
  });
});

test("환자 액션 블록에는 제목이 있다", () => {
  const code = codeOnly(read("js/status-view.js"));
  assert.ok(
    code.includes("환자 액션 현황"),
    "블록에 이름이 없다 — 안내문 읽음과 확인 문자 응답이 무엇의 현황인지 안 보인다"
  );
  /* 제목이 카드 머리띠로 그려져야 발송·예정 블록과 같은 모양이 된다 */
  const at = code.indexOf("환자 액션 현황");
  assert.match(
    code.slice(at - 120, at),
    /st__head/,
    "제목이 머리띠(.st__head)가 아니다 — 왼쪽 블록과 모양이 어긋난다"
  );
  assert.ok(code.includes("st__body"), "머리띠를 넣었으면 본문에 여백을 주는 칸이 있어야 한다");
});

/* ── 승인 철회 버튼 ─────────────────────────────────────────────────── */

test("승인된 뒤에는 발송 블록 머리에 철회 버튼이 선다", () => {
  const { statusScreenHtml } = box();
  const view = { entries: [], messages: [], checkInSaying: "아직 없음" };

  const off = statusScreenHtml(view);
  assert.ok(!off.includes('id="status-unapprove"'), "승인 전인데 철회 버튼이 있다");

  const on = statusScreenHtml(Object.assign({ canUnapprove: true }, view));
  assert.ok(on.includes('id="status-unapprove"'), "철회 버튼이 안 그려진다 — 누를 것이 없다");
  assert.ok(on.includes("승인 철회"), "버튼에 이름이 없다");

  /* 발송·예정 머리띠 **안**이어야 한다 — 무엇을 거두는지가 거기 적혀 있다 */
  const head = on.indexOf("st__head");
  assert.ok(head !== -1 && on.indexOf('id="status-unapprove"') > head, "머리띠 밖에 있다");
  assert.ok(
    on.indexOf('id="status-unapprove"') < on.indexOf("</div>", head),
    "발송 블록 머리띠를 벗어났다",
  );
});

test("철회 버튼은 블록 머리 오른쪽 끝으로 밀린다", () => {
  const css = read("css/blocks.css");
  assert.match(rule(css, ".st__act"), /margin-left:\s*auto/, "제목에 붙어 버린다");
  /* 줄로 세우는 것은 공용 머리(`.box__head`)가 한다 — 기본정보의 「수정」과 같다 */
  assert.match(rule(css, ".box__head"), /display:\s*flex/, "블록 머리가 줄이 아니다");
});

/* ── 열람이 타임라인을 도배하지 않는다 (`#189` 리뷰) ──────────────────── */

test("**같은 장을 여러 번 읽어도 한 줄이다** — 탭마다 쌓이면 이력이 도배된다", () => {
  const { foldViews } = box();

  /* 환자가 링크로 들어와 탭 넷을 넘기고 복약지도로 돌아온 경우 */
  const raw = [
    { event: "GUIDE_APPROVED", at: "2026-09-01T09:00:00+09:00" },
    { event: "GUIDE_VIEWED", at: "2026-09-01T10:00:00+09:00" },
    { event: "GUIDE_VIEWED", at: "2026-09-01T10:01:00+09:00", section_key: "medication" },
    { event: "GUIDE_VIEWED", at: "2026-09-01T10:02:00+09:00", section_key: "caution" },
    { event: "GUIDE_VIEWED", at: "2026-09-01T10:03:00+09:00", section_key: "life" },
    { event: "GUIDE_VIEWED", at: "2026-09-01T10:04:00+09:00", section_key: "medication" },
  ];

  const kept = foldViews(raw);
  const views = kept.filter((e) => e.event === "GUIDE_VIEWED");

  assert.equal(views.length, 4, "장마다 한 줄 + 장 없는 열람 한 줄이어야 한다");
  assert.equal(kept.length, 5, "열람 아닌 사건은 그대로 남아야 한다");

  /* 같은 장은 **마지막** 것을 남긴다 — 「언제까지 보고 있었나」에 가깝다 */
  const med = views.filter((e) => e.section_key === "medication");
  assert.equal(med.length, 1);
  assert.match(med[0].at, /10:04/, "먼저 읽은 것이 남았다");
});

test("**접는 것은 목록뿐** — 진도의 처음·마지막 시각은 원본으로 센다", () => {
  const { readProgress, foldViews } = box();

  const raw = [
    { event: "GUIDE_VIEWED", at: "2026-09-01T10:00:00+09:00", section_key: "medication" },
    { event: "GUIDE_VIEWED", at: "2026-09-01T10:05:00+09:00", section_key: "caution" },
    { event: "GUIDE_VIEWED", at: "2026-09-01T10:09:00+09:00", section_key: "medication" },
  ];

  const p = readProgress(raw);
  assert.match(p.first, /10:00/, "처음 열람이 접힌 목록에서 왔다");
  assert.match(p.last, /10:09/, "마지막 열람이 접힌 목록에서 왔다");

  /* 접힌 목록으로 세면 값이 달라진다 — 그래서 원본을 봐야 한다 */
  assert.notEqual(foldViews(raw).length, raw.length, "접히긴 해야 한다");
});

test("**분모는 서버가 준다** — 장이 늘면 화면과 서버가 갈린다", () => {
  const { readProgress } = box();

  const views = [{ event: "GUIDE_VIEWED", at: "2026-09-01T10:00:00+09:00", section_key: "medication" }];

  assert.equal(readProgress(views, 6).total, 6, "서버가 준 분모를 안 썼다");
  assert.equal(readProgress(views).total, 4, "안 오면 제 목록으로 물러서야 한다");
  assert.equal(readProgress([], 6).total, 6, "안 열었을 때도 서버 분모를 쓴다");
});

test("**화면이 실제로 접어서 그린다** — 접기 함수만 있고 안 쓰면 소용없다", () => {
  const { statusScreenHtml } = box();

  const view = {
    visit_id: 1,
    guide_pages_total: 4,
    messages: [],
    entries: [
      { category: "PATIENT", event: "GUIDE_VIEWED", at: "2026-09-01T10:01:00+09:00", section_key: "medication" },
      { category: "PATIENT", event: "GUIDE_VIEWED", at: "2026-09-01T10:02:00+09:00", section_key: "medication" },
      { category: "PATIENT", event: "GUIDE_VIEWED", at: "2026-09-01T10:03:00+09:00", section_key: "medication" },
    ],
  };

  const html = statusScreenHtml(view);
  const rows = (html.match(/class="tl__row"/g) || []).length;

  assert.equal(rows, 1, `같은 장 세 번을 세 줄로 그렸다 — ${rows}줄`);
});
