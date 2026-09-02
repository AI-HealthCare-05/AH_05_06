/* **현황** — 와이어프레임 D1-6.
 *
 * 승인 뒤에 무슨 일이 있었는지 볼 자리가 없었다 — 보냈는지 · 열었는지 ·
 * 답했는지 · 다음 문자가 언제 나가는지가 어디에도 안 보였다.
 *
 * 화면은 세 덩어리다 (원문 배치):
 *   위 2 : 1  ① 발송·예정  |  ② 환자 액션 현황 (안내문 읽음 + 확인 문자 응답)
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
  DOCUMENT_UPLOADED: "진료기록 업로드",
  OCR_STARTED: "판독 시작",
  OCR_COMPLETED: "판독 완료",
  OCR_FAILED: "판독 실패",
  OCR_CONFIRMED: "판독 확정",
  GUIDE_GENERATED: "안내문 생성",
  GUIDE_EDITED: "내용 수정",
  GUIDE_SUBMITTED: "스탭 확인 완료 · 승인 요청",
  GUIDE_APPROVED: "승인",
  GUIDE_UNAPPROVED: "승인 철회",
  GUIDE_RETURNED: "스탭에 되돌림",
  GUIDE_VIEWED: "안내문 열람",
  CHATBOT_ANSWERED: "챗봇 질문",
  CHECK_IN_SUBMITTED: "확인 문자 응답",
};

/* 누가 한 일인가. 셋을 가른다 — 사람 · 환자 · 시스템.
 *
 * 서버는 사람이 한 것에만 이름을 준다. 환자와 시스템은 비어 있는데, **그
 * 둘은 다른 것**이라 화면이 무슨 일이었는지를 보고 가른다. 서버가 「환자」를
 * 적어 보내면 이름이 「환자」인 직원과 구별할 수 없다. */
/* **서버가 갈래로 말해 준다.** 사건 이름을 하나씩 적어 두던 목록이었는데,
   `category` 가 생기면서 그 목록이 둘로 갈릴 자리가 됐다 — 환자가 하는 일이
   늘 때마다 여기도 같이 고쳐야 하고, 안 고치면 「시스템」으로 뜬다. */
function timelineActor(entry) {
  if (entry && entry.actor) return { name: entry.actor, who: "staff" };
  if (entry && (entry.category === "PATIENT" || entry.category === "CHECK_IN"))
    return { name: "환자", who: "patient" };
  return { name: "시스템", who: "system" };
}

/** 모르는 코드는 **그대로 보여 준다** — 빈칸으로 두면 일이 있었는데 없는
    것처럼 보인다 (판독 항목 이름표와 같은 판단). */
function timelineSaying(entry) {
  var event = String((entry && entry.event) || "");
  var base = TIMELINE_SAYING[event] || event;
  if (!entry) return base;
  /* 되돌린 사유·수정한 항목은 그 줄에 붙는다 — 흐름에서 보여야 알림을
     다시 찾아가지 않는다. */
  if (entry.note) return base + " · " + entry.note;
  if (entry.section_key) return base + " · " + entry.section_key;
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
    return e.event === "GUIDE_VIEWED";
  });
  if (!views.length) return { opened: false, read: 0, total: GUIDE_PAGES.length, last: "", first: "" };

  var seen = {};
  for (var i = 0; i < views.length; i++) {
    if (views[i].section_key) seen[views[i].section_key] = true;
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

/* ① 발송 · 예정 — **이제 서버가 준다.**
 *
 * 승인이 나갈 문자를 전부 세워 둔다(`GuideService._schedule_messages`).
 * 화면은 셈하지 않고 받은 것을 그린다 — 화면이 따로 셈하면 서버가 잡은
 * 날짜와 다른 날짜를 보여 주게 되고, 어느 쪽이 진짜인지 알 수 없다.
 */
var MESSAGE_SAYING = {
  GUIDE: "진료 안내문",
  CHECK_D7: "일주일 뒤 확인",
  CHECK_D15: "보름 뒤",
  CHECK_D30: "한 달 뒤",
  RUN_OUT: "소진 임박",
};

/* **못 나간 이유는 넷뿐이다** — 와이어프레임 D1-7 「실패 이유 넷 — 잘못된
   번호 · 수신 거부 · 통신사 오류 · 발신번호 미등록」. 발신번호 미등록만
   처리 경로가 다르다(어드민 A1-5 에서 등록한다). */
var FAILURE_SAYING = {
  INVALID_PHONE: "잘못된 번호",
  OPT_OUT: "수신 거부",
  CARRIER: "통신사 오류",
  SENDER_UNREGISTERED: "발신번호 미등록",
};

/* **붙들고 있는 이유는 둘뿐이다** — 와이어프레임 S2-3 「스탭이 손댈 일은
   보류 두 가지뿐이다 — 번호가 잘못됐을 때와 문자가 떨어졌을 때」.
   원문 표기가 「보류 · 번호」 · 「보류 · 문자 잔량」이라 짧게 적는다. */
var HOLD_SAYING = {
  INVALID_PHONE: "번호",
  NO_CREDIT: "문자 잔량",
};

/* 한 통이 지금 어디에 있는가. **「예정」과 「못 나감」과 「보류」를 또렷이
   가른다.**

   실패와 보류를 한 무더기로 뭉치면 「이미 벌어진 것」과 「고치면 아직 막을 수
   있는 것」이 섞인다 — 스탭이 무엇을 손대야 하는지 안 보인다. 와이어프레임
   S2-3 도 「안 나간 것 3건 (실패 1 · 보류 2)」로 합쳐 세면서 따로 적는다. */
var MESSAGE_STATE = {
  SCHEDULED: { say: "예정", mark: "○", done: false, bad: false },
  SENT: { say: "발송 완료", mark: "●", done: true, bad: false },
  FAILED: { say: "못 나감", mark: "⚠", done: false, bad: true },
  HELD: { say: "보류", mark: "⏸", done: false, bad: true },
  CANCELED: { say: "꺼짐", mark: "○", done: false, bad: false },
};

function messageState(status) {
  return MESSAGE_STATE[status] || { say: String(status || ""), mark: "○", done: false, bad: false };
}

/** 그 줄에 적을 한 마디 — 「못 나감 · 잘못된 번호」 · 「보류 · 문자 잔량」.
    모르는 코드는 **적지 않는다** — 코드를 그대로 보이면 사람 말이 아니다. */
function messageSaying(row) {
  var state = messageState(row && row.status);
  var why =
    row && row.status === "HELD"
      ? HOLD_SAYING[row.hold_reason]
      : row && row.status === "FAILED"
        ? FAILURE_SAYING[row.failure_code]
        : null;
  return why ? state.say + " · " + why : state.say;
}

/** 「08-20 10:00」 — 날짜와 시각을 함께 적는다. 회차는 며칠 뒤라 날짜가 있어야 한다. */
function messageWhen(iso) {
  var m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(String(iso || ""));
  return m ? m[2] + "-" + m[3] + " " + m[4] + ":" + m[5] : "";
}

function sendRowsHtml(messages) {
  var rows = messages || [];
  if (!rows.length) {
    /* 승인 전에는 아무것도 예약돼 있지 않다 — 예약은 승인이 만든다.
       빈 판으로 두면 「고장」으로 읽히므로 왜 비었는지 적는다. */
    return '<p class="st__note">승인하면 나갈 문자가 여기에 섭니다</p>';
  }

  return rows
    .map(function (row) {
      var state = messageState(row.status);
      return (
        '<div class="sd__row' +
        (state.bad ? " is-bad" : "") +
        '">' +
        /* **● 와 ○ 는 크기·색이 같다** — 원문이 그렇다. ⚠ 와 ⏸ 만 다르다:
           그 둘은 사람이 손대야 하는 줄이라 눈에 걸려야 한다. */
        '<span class="sd__dot" aria-hidden="true">' +
        esc(state.mark) +
        "</span>" +
        '<span class="sd__what' +
        (state.done ? " is-done" : "") +
        '">' +
        esc(MESSAGE_SAYING[row.kind] || row.kind) +
        "</span>" +
        '<span class="sd__when">' +
        esc(messageWhen(row.at)) +
        "</span>" +
        '<span class="sd__state">' +
        esc(messageSaying(row)) +
        (row.sent_at ? " \u00b7 " + esc(messageWhen(row.sent_at)) : "") +
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
    '<section class="box st__send">' +
    /* 철회는 **여기** 붙는다 — 무엇을 거두는지가 이 블록에 적혀 있다.
       최종 확인 탭의 승인 버튼 옆에 두면, 이미 승인된 뒤에 그 탭을 다시
       열 일이 없어서 찾지 못한다. */
    '<div class="box__head st__head"><span class="box__title">발송 · 예정</span>' +
    (view.canUnapprove
      ? '<button class="button-ghost button-ghost--sm st__act" type="button" id="status-unapprove">승인 철회</button>'
      : "") +
    "</div>" +
    sendRowsHtml(view.messages) +
    '<p class="st__note">ⓘ ⚠ 못 나감은 보내 봤는데 안 된 것, ⏸ 보류는 아직 안 보낸 것입니다 — 발송기가 붙으면 그 자리에서 고칩니다</p>' +
    "</section>" +
    '<section class="box st__side">' +
    '<div class="box__head st__head"><span class="box__title">환자 액션 현황</span></div>' +
    '<div class="st__body">' +
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
    "</p></div></section>" +
    "</div>" +
    /* 아래 전폭 */
    '<section class="box tl">' +
    '<div class="box__head tl__head"><span class="box__title tl__title">진료 처리 이력</span>' +
    '<span class="tl__tail">시스템 처리 내역 포함</span></div>' +
    (rows || '<p class="st__note">아직 기록이 없습니다</p>') +
    '<p class="st__note">ⓘ 열람 기록은 어드민 「전체 로그」에서 확인합니다 · 이 화면은 진료 흐름만 표시합니다</p>' +
    "</section></div>"
  );
}
