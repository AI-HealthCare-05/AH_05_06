/* **현황** — 와이어프레임 D1-6.
 *
 * 승인 뒤에 무슨 일이 있었는지 볼 자리가 없었다 — 보냈는지 · 열었는지 ·
 * 답했는지 · 다음 문자가 언제 나가는지가 어디에도 안 보였다.
 *
 * 화면은 세 덩어리다 (원문 배치):
 *   위 2 : 1  ① 발송·예정  |  ② 안내문 읽음 + ③ 확인 문자 응답 (한 카드)
 *   아래 전폭 ④ 진료 처리 이력
 *   맨 아래  [링크 무효화] [재발송]
 *
 * ①과 하단 버튼은 **아직 프레임이다** — 발송 예정을 담는 표가 서버에 없다.
 * ②③④는 진짜 기록으로 찬다(`GET /visits/{id}/timeline`).
 */

/* 서버는 코드를 준다. 사람 말로 옮기는 것은 화면 몫이다 —
   판독 항목 이름표(`field-labels.js`)와 같은 이유로 한 곳에 둔다. */
var TIMELINE_SAYING = {
  VISIT_CREATED: "등록",
  EDITED: "내용 수정",
  SUBMITTED: "스탭 확인 완료 · 승인 요청",
  APPROVED: "승인",
  RETURNED: "스탭에 되돌림",
  GUIDE_VIEWED: "안내문 열람",
  CHATBOT_ANSWERED: "챗봇 질문",
  CHECK_IN: "확인 문자 응답",
};

/* 누가 한 일인가. 셋을 가른다 — 사람 · 환자 · 시스템.
 *
 * 서버는 사람이 한 것에만 이름을 준다. 환자와 시스템은 비어 있는데, **그
 * 둘은 다른 것**이라 화면이 무슨 일이었는지를 보고 가른다. 서버가 「환자」를
 * 적어 보내면 이름이 「환자」인 직원과 구별할 수 없다. */
var TIMELINE_BY_PATIENT = { GUIDE_VIEWED: true, CHATBOT_ANSWERED: true, CHECK_IN: true };

function timelineActor(entry) {
  if (entry && entry.actor) return { name: entry.actor, who: "staff" };
  if (entry && TIMELINE_BY_PATIENT[entry.kind]) return { name: "환자", who: "patient" };
  return { name: "시스템", who: "system" };
}

/** 모르는 코드는 **그대로 보여 준다** — 빈칸으로 두면 일이 있었는데 없는
    것처럼 보인다 (판독 항목 이름표와 같은 판단). */
function timelineSaying(entry) {
  var kind = String((entry && entry.kind) || "");
  var base = TIMELINE_SAYING[kind] || kind;
  if (!entry) return base;
  /* 되돌린 사유·수정한 항목은 그 줄에 붙는다 — 흐름에서 보여야 알림을
     다시 찾아가지 않는다. */
  if (entry.detail) return base + " · " + entry.detail;
  if (entry.section) return base + " · " + entry.section;
  return base;
}

/** 「10:32」 — 시각만 뗀다. 날짜는 진료 하루치라 줄마다 적으면 자리만 먹는다. */
function timelineClock(iso) {
  var m = /T(\d{2}):(\d{2})/.exec(String(iso || ""));
  return m ? m[1] + ":" + m[2] : "";
}

/* ── 안내문 읽음 ──────────────────────────────────────────────────────
 *
 * 「5장 중 2장 · 주의사항까지 읽고 멈췄습니다」.
 *
 * 서버는 열람 이벤트를 줄 뿐이라, **몇 장을 읽었는지는 화면이 센다** —
 * `grounded_section` 이 있는 열람만 「그 장을 읽었다」로 본다. 없는 것은
 * 어느 장인지 모르는 열람이라 장수에 넣지 않는다.
 */
var GUIDE_PAGES = ["medication", "caution", "life", "messages"];

function readProgress(entries) {
  var views = (entries || []).filter(function (e) {
    return e.kind === "GUIDE_VIEWED";
  });
  if (!views.length) return { opened: false, read: 0, total: GUIDE_PAGES.length, last: "", first: "" };

  var seen = {};
  for (var i = 0; i < views.length; i++) {
    if (views[i].section) seen[views[i].section] = true;
  }
  var read = 0;
  var lastRead = "";
  for (var p = 0; p < GUIDE_PAGES.length; p++) {
    if (seen[GUIDE_PAGES[p]]) {
      read += 1;
      lastRead = GUIDE_PAGES[p];
    }
  }

  return {
    opened: true,
    read: read,
    total: GUIDE_PAGES.length,
    lastSection: lastRead,
    first: views[0].at,
    last: views[views.length - 1].at,
  };
}

/** 「주의사항까지 읽고 멈췄습니다」 — 어디서 멈췄는지가 이 블록의 값이다.
    안 읽었으면 그렇게 말한다: 「아직 안 읽었습니다」와 「다 읽었습니다」는
    스탭이 할 일이 다르다. */
function readSaying(progress, label) {
  if (!progress.opened) return "아직 열지 않았습니다";
  if (progress.read >= progress.total) return "끝까지 읽었습니다";
  if (!progress.read) return "열었지만 어느 항목인지 남지 않았습니다";
  return (label(progress.lastSection) || progress.lastSection) + "까지 읽고 멈췄습니다";
}

/* ── 그리기 (원문 배치) ────────────────────────────────────────────────
 *
 * 위 2 : 1 — 왼쪽 발송·예정, 오른쪽에 「안내문 읽음」과 「확인 문자 응답」이
 * **한 카드 안에** 구분선으로 나뉜다. 아래는 전폭 이력.
 */

/* ① 발송 · 예정 — **아직 프레임이다.** 발송 예정을 담는 표가 서버에 없다.
   문자 설정(S1-14)에서 정한 회차를 화면이 셈해 보여 주되, 「보냈다」는 서버가
   말해 주기 전에는 못 적는다. */
function sendRowsHtml(plan) {
  var rows = [
    { label: "진료 안내문", when: plan.approvedAt || "", state: "승인 뒤 발송", done: false },
  ];
  for (var i = 0; i < SMS_ROUNDS.length; i++) {
    var r = SMS_ROUNDS[i];
    var on = r.fixed || (plan.on || {})[r.key] === true;
    if (!on) continue;
    rows.push({
      label: r.label + (r.key === "d7" ? " 확인" : ""),
      when: smsWhen(smsDateAfter(plan.startIso, r.days)) + " " + smsTimeLabel(plan.at).replace("오전 ", "").replace("오후 ", ""),
      state: "예정",
      done: false,
    });
  }
  if (plan.runOutIso) {
    var notice = smsRunOutNotice(plan.runOutIso, plan.runOutBefore || 3);
    if (notice) {
      rows.push({ label: "소진 임박", when: smsWhen(notice), state: "예정", done: false });
    }
  }

  return rows
    .map(function (row) {
      return (
        '<div class="sd__row">' +
        '<span class="sd__dot" aria-hidden="true">' +
        (row.done ? "●" : "○") +
        "</span>" +
        '<span class="sd__what' +
        (row.done ? " is-done" : "") +
        '">' +
        esc(row.label) +
        "</span>" +
        '<span class="sd__when">' +
        esc(row.when) +
        "</span>" +
        '<span class="sd__state">' +
        esc(row.state) +
        "</span></div>"
      );
    })
    .join("");
}

function statusScreenHtml(view) {
  var progress = readProgress(view.entries);
  var label = function (key) {
    return GUIDE_SECTION_LABEL[key];
  };

  var rows = (view.entries || [])
    .map(function (e) {
      var who = timelineActor(e);
      return (
        '<div class="tl__row">' +
        '<span class="tl__at">' +
        esc(timelineClock(e.at)) +
        "</span>" +
        '<span class="tl__what">' +
        esc(timelineSaying(e)) +
        "</span>" +
        '<span class="tl__who tl__who--' +
        who.who +
        '">' +
        esc(who.name) +
        "</span></div>"
      );
    })
    .join("");

  return (
    '<div class="st">' +
    /* 위 2 : 1 */
    '<div class="st__top">' +
    '<section class="st__send">' +
    '<div class="st__head">발송 · 예정</div>' +
    sendRowsHtml(view.plan || {}) +
    '<p class="st__note">발송 여부는 문자 발송이 붙으면 여기에 표시됩니다 — 지금은 예정만 셈합니다</p>' +
    "</section>" +
    '<section class="st__side">' +
    '<div class="st__label">안내문 읽음</div>' +
    '<div class="st__big">' +
    /* 원문 표기는 「5장 중 2장」 — 전체가 앞, 읽은 것이 뒤다 */
    (progress.opened ? esc(progress.total + "장 중 " + progress.read + "장") : "아직 열지 않음") +
    "</div>" +
    '<p class="st__sub">' +
    esc(readSaying(progress, label)) +
    (progress.opened && progress.first
      ? "<br />" + esc(timelineClock(progress.first) + " 열람 · " + timelineClock(progress.last) + " 마지막")
      : "") +
    "</p>" +
    '<div class="st__rule"></div>' +
    '<div class="st__label">확인 문자 응답</div>' +
    '<p class="st__sub">' +
    esc(view.checkInSaying || "아직 없음") +
    "</p></section>" +
    "</div>" +
    /* 아래 전폭 */
    '<section class="tl">' +
    '<div class="tl__head"><span class="tl__title">진료 처리 이력</span>' +
    '<span class="tl__tail">시스템 처리 내역 포함</span></div>' +
    (rows || '<p class="st__note">아직 기록이 없습니다</p>') +
    '<p class="st__note">ⓘ 열람 기록은 어드민 「전체 로그」에서 확인합니다 · 이 화면은 진료 흐름만 표시합니다</p>' +
    "</section></div>"
  );
}
