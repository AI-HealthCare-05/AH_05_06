/* 발송 예정 — 와이어프레임 S2-3 의 규칙들 (KEY-234).
 *
 * **IIFE 밖에 둔다.** 화면을 그리는 코드는 `browser-shim` 아래서 안 돌아
 * 검사가 닿지 않지만, 여기 있는 것들은 닿는다.
 *
 * 문자 어휘(`MESSAGE_SAYING` · `HOLD_SAYING` · `messageSaying`)는 여기서
 * 다시 적지 않는다 — `js/status-view.js` 것을 그대로 쓴다. 같은 낱말을 두
 * 곳에 두면 한쪽만 고쳐지고, 같은 문자가 화면마다 다른 이름으로 뜬다.
 */

/* 기간 — 원문의 「앞으로 7일 ▾」. 서버가 1~90 만 받는다.
   오늘만 보는 자리를 첫째로 두지 않는다: 이 화면은 「앞으로 무엇이 나가나」를
   묻는 자리라, 하루만 보이면 내일 나갈 것을 놓친다. */
var SCHEDULE_WINDOWS = [
  { days: 7, say: "앞으로 7일" },
  { days: 1, say: "오늘" },
  { days: 30, say: "앞으로 30일" },
];

function windowSaying(days) {
  for (var i = 0; i < SCHEDULE_WINDOWS.length; i++) {
    if (SCHEDULE_WINDOWS[i].days === days) return SCHEDULE_WINDOWS[i].say;
  }
  return "앞으로 " + days + "일";
}

/* **안 나간 것** — 실패와 보류를 합쳐 센다.
   원문 요약이 「안 나간 것 3건 (실패 1 · 보류 2)」로 합쳐 말하고 괄호로 쪼갠다.
   합친 수가 먼저다: 스탭이 손댈 일이 몇 건인가가 물음이고, 그중 몇이 지난
   일이고 몇이 앞일인가는 그다음이다. */
function unsentCount(counts) {
  if (!counts) return 0;
  return (counts.failed || 0) + (counts.held || 0);
}

function isUnsent(row) {
  return !!row && (row.status === "FAILED" || row.status === "HELD");
}

/* 줄 순서 — **안 나간 것이 먼저, 그 안에서는 시각순.**
 *
 * 서버도 같은 순서로 준다. 화면이 또 세우는 이유는 목업과 서버가 갈라지지
 * 않게 하려는 것이다 — 목업만 순서가 다르면 화면에서만 되는 일이 생긴다.
 */
function scheduleOrder(rows) {
  return (rows || []).slice().sort(function (a, b) {
    var side = (isUnsent(a) ? 0 : 1) - (isUnsent(b) ? 0 : 1);
    if (side !== 0) return side;
    return String(a.scheduled_at) < String(b.scheduled_at) ? -1 : 1;
  });
}

/* 화면 위의 칩. **셈은 서버 것을 그대로 쓴다** — 화면이 따로 세면 창 밖의
   것을 못 세어 「전체」가 「보이는 것」이 된다. */
function scheduleChips(counts, days) {
  if (!counts) return [];
  return [
    { key: "total", say: "전체 " + (counts.total || 0), strong: true },
    {
      key: "failed",
      say: "⚠ 실패 " + (counts.failed || 0),
      bad: counts.failed > 0,
    },
    { key: "held", say: "⏸ 보류 " + (counts.held || 0), bad: counts.held > 0 },
    { key: "today", say: "오늘 " + (counts.today || 0) },
    { key: "window", say: windowSaying(days) + " " + (counts.window || 0) },
  ];
}

/* 아래 요약 줄 — 원문 「안 나간 것 3건 (실패 1 · 보류 2) · 앞으로 7일 예정
   18건 · 오늘 2건」. 안 나간 것이 0이면 그 마디를 **아예 뺀다**: 「안 나간 것
   0건」은 읽는 사람 눈에 걸리기만 하고 알려 주는 것이 없다. */
function scheduleSummary(counts, days) {
  if (!counts) return "";
  var parts = [];
  var stuck = unsentCount(counts);
  if (stuck > 0) {
    parts.push(
      "안 나간 것 " +
        stuck +
        "건 (실패 " +
        (counts.failed || 0) +
        " · 보류 " +
        (counts.held || 0) +
        ")",
    );
  }
  parts.push(windowSaying(days) + " 예정 " + (counts.window || 0) + "건");
  parts.push("오늘 " + (counts.today || 0) + "건");
  return parts.join(" · ");
}

/* 식별정보 칸 — 원문 「여 · 34세 · 1992-05-20」.
   모르는 성별은 **적지 않는다**. `UNKNOWN` 을 그대로 보이면 사람 말이 아니고,
   「기타」로 옮기면 없는 정보를 있는 것처럼 만든다. */
var GENDER_SAYING = { FEMALE: "여", MALE: "남" };

function identityOf(row) {
  if (!row) return "";
  var parts = [];
  if (GENDER_SAYING[row.gender]) parts.push(GENDER_SAYING[row.gender]);
  if (row.age || row.age === 0) parts.push(row.age + "세");
  if (row.birth_date) parts.push(row.birth_date);
  return parts.join(" · ");
}

/* **할 일 칸에는 실제로 가는 것만 둔다.**
 *
 * 원문은 넷을 그린다 — 고치기 · 문자 충전 · 시각 변경 · 즉시 발송. 그중
 * 지금 갈 데가 있는 것은 하나뿐이다: 번호가 잘못됐을 때 그 환자의 기본정보로
 * 가는 것. 나머지 셋은 **API 도 발송기도 없다.**
 *
 * 눌러도 아무 일 없는 버튼은 「된다」고 말한다. 그래서 세우지 않고, 화면
 * 아래에 무엇이 아직 없는지 한 줄로 적는다.
 */
function rowAction(row) {
  if (!row) return null;
  var phoneIsWrong =
    (row.status === "HELD" && row.hold_reason === "INVALID_PHONE") ||
    (row.status === "FAILED" && row.failure_code === "INVALID_PHONE");
  if (!phoneIsWrong) return null;
  return {
    say: "번호 수정",
    href:
      "/patients.html?visit=" + encodeURIComponent(row.visit_id) + "&tab=basic",
  };
}

/* 예정이 잘렸을 때 할 말. **조용히 자르지 않는다** — 다 보이는 줄 알면
   없는 것을 없다고 믿는다. */
function truncationNote(page) {
  if (!page || !page.truncated) return "";
  return (
    "예정 " +
    ((page.counts && page.counts.window) || 0) +
    "건 중 " +
    (page.items || []).length +
    "건만 표시됩니다"
  );
}
