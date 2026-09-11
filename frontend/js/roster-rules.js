/* 환자 관리 — 와이어프레임 S2-1 「★ 이탈을 잡는 자리」의 규칙들. KEY-234.
 *
 * 원문 캡션: 「오늘이 아닌 환자도 여기서 찾는다」.
 *
 * **현황(S1)이 칩으로 보이던 것을 여기서는 열로 보인다.** 원문 주석이 그렇게
 * 적는다 — 「같은 속성, 표기만 서식에 맞춘다」. 그래서 상태 이름을 새로 짓지
 * 않고 `patients-api.js` 의 `WORK_CATEGORIES` · `DETAIL_STATUS_LABEL` 을
 * 그대로 쓴다. 두 화면이 같은 환자를 다르게 부르면 어느 쪽이 맞는지 모른다.
 */

/* 상단 칩 다섯 — 원문 「전체 128명 · 진행 중 34 · ⚠ 챙겨주세요 7 ·
   수신 거부 4 · 6개월 이상 미내원 22」. 이름은 서버 분류 그대로다. */
var ROSTER_CHIPS = [
  { key: "ALL", say: "전체", unit: "명" },
  { key: "IN_TREATMENT", say: "진행 중" },
  { key: "NEEDS_ATTENTION", say: "⚠ 챙겨주세요", bad: true },
  { key: "SMS_OPT_OUT", say: "수신 거부" },
  { key: "INACTIVE_6_MONTHS", say: "6개월 이상 미내원" },
];

function rosterChips(counts, chosen) {
  return ROSTER_CHIPS.map(function (chip) {
    var count = (counts && counts[chip.key]) || 0;
    return {
      key: chip.key,
      say: chip.say + " " + count + (chip.unit || ""),
      on: chip.key === chosen,
      bad: !!chip.bad && count > 0,
    };
  });
}

/* 이탈 배지 — 원문의 셋. 서버가 코드로 주고 화면이 사람 말로 옮긴다. */
var FLAG_SAYING = {
  UNREAD_STREAK: "3회 연속 미열람",
  STOPPED_DOSING: "복약 중단 응답",
  RUN_OUT_OVERDUE: "소진 후 7일 경과",
};

function flagSaying(flag) {
  return FLAG_SAYING[flag] || "";
}

/* 줄에 붙는 배지 글. **모르는 코드는 적지 않는다** — 코드를 그대로 보이면
   사람 말이 아니고, 스탭이 무엇을 챙기라는 말인지 알 수 없다. */
function flagsSaying(flags) {
  var said = (flags || []).map(flagSaying).filter(Boolean);
  return said.length ? "⚠ " + said.join(" · ") : "";
}

/* 문자 동의 칸 — 원문 「동의 · 05-20」 · 「거부 · 07-28」.
   날짜를 붙이는 이유는 **언제부터인지가 곧 근거**이기 때문이다. 동의만 적혀
   있으면 오래된 동의인지 방금 받은 것인지 알 수 없다. */
function consentSaying(row) {
  if (!row) return "";
  var when = row.sms_consent ? row.sms_consented_at : row.sms_opted_out_at;
  var head = row.sms_consent ? "동의" : "거부";
  var day = monthDay(when);
  return day ? head + " · " + day : head;
}

function monthDay(iso) {
  var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(iso || ""));
  return m ? m[2] + "-" + m[3] : "";
}

function visitedDay(row) {
  var at = row && row.latest_visit && row.latest_visit.visited_at;
  var m = /^(\d{4}-\d{2}-\d{2})/.exec(String(at || ""));
  return m ? m[1] : "";
}

/* 펼친 카드의 버튼 넷 — 원문 「전체 이력 보기 · 지난 안내문 보기 ·
 * 정보 수정 · 재진 안내 발송」.
 *
 * **갈 데가 있는 것만 세운다.** 지금 서는 것은 둘이다 — 「정보 수정」과
 * 「현황 보기」. 뒤엣것은 원문에 없다. 관리 카드에서 현황 탭으로 가는 길이
 * 없어 그 환자를 현황에서 다시 찾아야 했다 (KEY-329).
 *
 *   전체 이력 보기   버튼이 아니라 **줄을 누르면** 이력 모달(S2-2)이 뜬다.
 *                    같은 자리에 버튼을 또 두면 누르는 길이 둘이 된다
 *   지난 안내문 보기  발송 이력을 그 환자로 거르는 것인데, 그 거르개가 없다
 *   재진 안내 발송   문자를 보내는 발송기가 없다
 *
 * **이 문단은 세 번 틀렸다.** 「지난 안내문 보기와 정보 수정 둘 다 간다」고
 * 적혀 있었는데 코드는 하나만 냈고, 「전체 이력 보기는 자리가 없다」고 적혀
 * 있었는데 실제로는 됐고, `status` 를 더한 뒤에도 「하나다」로 남아 있었다
 * (이희진 님 #292 리뷰). **버튼을 더하거나 뺄 때 이 목록을 같이 고친다.**
 */
function rosterActions(row) {
  if (!row) return [];
  var found = [];
  if (row.latest_visit && row.latest_visit.visit_id) {
    var at = "/patients.html?visit=" + encodeURIComponent(row.latest_visit.visit_id) + "&tab=";
    /* **같은 결로 간다** — 정보 수정이 기본정보 탭으로 가듯, 현황 보기는 현황
       탭으로 간다 (KEY-329). 탭 이름은 `step-nav.js` 의 `VISIT_STEPS` 가 정한
       그대로다 — 여기서 새로 짓지 않는다. */
    found.push({ key: "edit", say: "정보 수정", href: at + "basic" });
    found.push({ key: "status", say: "현황 보기", href: at + "status" });
  }
  return found;
}

/* 표 아래 한 줄. **보이는 수와 전체 수를 함께 말한다** — 한 쪽에 오십 명만
   보이는데 「전체 128명」만 적으면 나머지가 어디 갔는지 알 수 없다.

   **거른 상태에서 「전체」라고 하지 않는다.** 챙겨주세요로 좁혀 놓고 「전체
   5명」이라 적으면 의원에 환자가 다섯인 줄로 읽힌다. */
function rosterSummary(page) {
  if (!page || !page.counts) return "";
  var chosen = page.selected_category || "ALL";
  var total = page.counts[chosen] || 0;
  var shown = (page.items || []).length;
  var head = chosen === "ALL" ? "전체" : chipSaying(chosen);
  if (shown >= total) return head + " " + total + "명";
  return head + " " + total + "명 중 " + shown + "명 표시";
}

function chipSaying(key) {
  for (var i = 0; i < ROSTER_CHIPS.length; i++) {
    if (ROSTER_CHIPS[i].key === key) return ROSTER_CHIPS[i].say;
  }
  return key;
}

/** 세부 상태 칸 — **상태와 이탈 배지를 같은 칸에 나란히 둔다.**
 *
 * 원문 S2-1 설계 주석: 「세부 상태(12종)를 표기하고, 이탈 배지(⚠ 3회 연속
 * 미열람 · ⚠ 복약 중단 응답 · ⚠ 소진 후 7일 경과 · 6개월 이상 미내원)는
 * **상태가 아니므로 같은 칸에 병기한다**」.
 *
 * 배지로 상태를 덮고 있었다 — 그러면 「완료·열람인데 이탈 중」이라는 이 화면의
 * 핵심 신호가 절반 사라진다. 스탭은 그 환자가 어디까지 갔는지를 못 보고
 * 경고만 본다. 둘은 **다른 축**이라 하나가 다른 하나를 대신할 수 없다.
 */
function stateSaying(detail, badge) {
  var parts = [];
  if (detail) parts.push(String(detail));
  if (badge) parts.push(String(badge));
  return parts.join(" · ") || "—";
}
