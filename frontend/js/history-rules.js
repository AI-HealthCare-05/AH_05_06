/* 발송 이력 — 와이어프레임 S2-4 의 규칙들 (KEY-234).
 *
 * 원문 캡션: 「기간으로 본다 · 실패 건은 맨 위에 고정」.
 *
 * **발송 예정(S2-3)과 묻는 것이 다르다.** 저쪽은 「앞으로 무엇이 나가나」라
 * 시각 오름차순이고, 이쪽은 「무엇이 나갔나」라 최신이 위다. 규칙을 한
 * 파일에 합치지 않는 것은 그래서다 — 합치면 「어느 쪽 순서였지」를 매번
 * 되짚어야 한다.
 *
 * 원문 견본 세 줄에서는 고정 표시가 실패가 아니라 완료 줄에 붙어 있는데,
 * 캡션과 설계 주석이 둘 다 「실패가 맨 위」라고 못박으므로 적힌 규칙을 따랐다.
 */

/* 기간 — 원문은 「2026-08-05 ~ 2026-08-11」처럼 시작과 끝을 보인다.
   고르는 것은 흔한 폭 몇 가지로 두고, 값은 날짜 둘로 보낸다. */
var HISTORY_SPANS = [
  { days: 7, say: "최근 7일" },
  { days: 1, say: "오늘" },
  { days: 30, say: "최근 30일" },
  { days: 90, say: "최근 90일" },
];

function spanSaying(days) {
  for (var i = 0; i < HISTORY_SPANS.length; i++) {
    if (HISTORY_SPANS[i].days === days) return HISTORY_SPANS[i].say;
  }
  return "최근 " + days + "일";
}

/** 「최근 N일」이 뜻하는 두 날짜. **오늘을 넣어 센다** — 7일이면 오늘까지
    이레지 오늘 빼고 이레가 아니다.

    **의원의 오늘이다**(`js/clinic-clock.js`). 보는 사람의 노트북 시간대로
    세면 자정 전후에 하루가 어긋나 「오늘 나간 문자」가 안 보인다. */
function historyRange(days, today) {
  return { from: clinicDayShift(-(days - 1), today), to: clinicToday(today) };
}

function rangeSaying(range) {
  if (!range) return "";
  return range.from + " ~ " + range.to;
}

function isFailed(row) {
  return !!row && row.status === "FAILED";
}

/* 줄 순서 — **실패가 맨 위, 그 다음 최신순.**
   서버도 같은 순서로 준다. 화면이 또 세우는 것은 목업과 서버가 갈라지지 않게
   하려는 것이다. */
function historyOrder(rows) {
  return (rows || []).slice().sort(function (a, b) {
    var side = (isFailed(a) ? 0 : 1) - (isFailed(b) ? 0 : 1);
    if (side !== 0) return side;
    return String(a.happened_at) > String(b.happened_at) ? -1 : 1;
  });
}

/* 원문의 칩 넷 — 「전체 210 · ⚠ 실패 1 · 미열람 34 · 열람 175」.
 **누르면 걸러진다** — 발송 예정 · 환자 관리와 같은 자리다. */
function historyChips(counts, chosen) {
  if (!counts) return [];
  var picked = chosen || "total";
  return [
    { key: "total", say: "전체 " + (counts.total || 0) + "건" },
    {
      key: "failed",
      say: "⚠ 실패 " + (counts.failed || 0),
      bad: counts.failed > 0,
    },
    { key: "unviewed", say: "미열람 " + (counts.unviewed || 0) },
    { key: "viewed", say: "열람 " + (counts.viewed || 0) },
  ].map(function (chip) {
    return {
      key: chip.key,
      say: chip.say,
      bad: !!chip.bad,
      on: chip.key === picked,
    };
  });
}

/* **열람은 나간 것 중에서만 묻는다** — 못 나간 문자에 열람을 묻는 것은 뜻이
   없고, 칩의 셈도 그렇게 세었다(175 + 34 = 210 − 1). */
function filterHistory(rows, chosen) {
  var given = rows || [];
  if (!chosen || chosen === "total") return given;
  if (chosen === "failed") return given.filter(isFailed);
  if (chosen === "viewed") {
    return given.filter(function (row) {
      return !isFailed(row) && row.viewed;
    });
  }
  if (chosen === "unviewed") {
    return given.filter(function (row) {
      return !isFailed(row) && !row.viewed;
    });
  }
  return given;
}

/* 아래 요약 줄 — 원문 「기간 내 발송 210건 · 열람 175 · 미열람 34 · 실패 1
   — 표에는 일부 행만 표시」. 마지막 마디는 **실제로 잘렸을 때만** 붙인다:
   다 보이는데 「일부만」이라고 적으면 없는 것을 있다고 믿게 된다. */
function historySummary(page) {
  if (!page || !page.counts) return "";
  var counts = page.counts;
  var said =
    "기간 내 발송 " +
    (counts.total || 0) +
    "건 · 열람 " +
    (counts.viewed || 0) +
    " · 미열람 " +
    (counts.unviewed || 0) +
    " · 실패 " +
    (counts.failed || 0);
  return page.truncated ? said + " — 표에는 일부 행만 표시" : said;
}

/* 열람 칸. **못 나간 줄에는 묻지 않는다** — 원문도 실패 줄에 「—」를 적는다.
   미열람을 빈칸으로 두지 않는 것은, 빈칸이 「모른다」로 읽히기 때문이다. */
function viewedSaying(row) {
  if (!row) return "";
  if (isFailed(row)) return "—";
  return row.viewed ? "● 열람" : "○ 미열람";
}

/* **CSV 는 표와 다르다 — 자르지 않는다.** 원문이 표를 「일부 행만 표시」라고
   적어 두었고, 이 받기가 그 나머지를 가져가는 자리다.
 *
 * 평범한 `<a href>` 로 걸 수 없다. 이 API 는 `Authorization` 헤더를 받는데
 * 링크는 헤더를 못 싣는다 — 주소에 토큰을 붙이면 브라우저 기록과 서버 접근
 * 로그에 환자 자료로 가는 열쇠가 남는다(AGENTS.md). 그래서 받아 온 뒤
 * 브라우저 안에서 파일로 만든다. */
function historyCsvPath(range) {
  if (!range) return "";
  return (
    "/messages/history.csv?from=" +
    encodeURIComponent(range.from) +
    "&to=" +
    encodeURIComponent(range.to)
  );
}
