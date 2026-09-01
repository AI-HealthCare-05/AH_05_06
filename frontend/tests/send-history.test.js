/* 발송 이력 (S2-4) — KEY-234.
 *
 * 원문 캡션: 「기간으로 본다 · 실패 건은 맨 위에 고정」.
 *
 * **발송 예정(S2-3)과 묻는 것이 다르다.** 저쪽은 「앞으로 무엇이 나가나」라
 * 시각 오름차순이고, 이쪽은 「무엇이 나갔나」라 최신이 위다. 두 순서가
 * 뒤바뀌면 화면이 조용히 거짓말한다 — 그래서 둘을 나란히 잰다.
 *
 * 원문 견본 세 줄에서는 고정 표시가 실패가 아니라 완료 줄에 붙어 있는데,
 * 캡션과 설계 주석이 둘 다 「실패가 맨 위」라고 못박으므로 적힌 규칙을 따랐다.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const { load } = require("./browser-shim.js");
const { read, codeOnly, markupOnly } = require("./source.js");

function rules() {
  return load("api", "message-words", "schedule-rules", "history-rules");
}

function a_row(over) {
  return Object.assign(
    {
      guide_message_id: 1,
      visit_id: 11,
      patient_id: 21,
      happened_at: "2026-08-11T18:00:00+09:00",
      kind: "GUIDE",
      status: "SENT",
      failure_code: null,
      name: "강예린",
      hospital_patient_no: "11902",
      gender: "FEMALE",
      birth_date: "1997-04-22",
      age: 29,
      prescription_set: "자궁내막증 · 비잔",
      viewed: false,
      viewed_at: null,
    },
    over || {},
  );
}

/* ── 기간 ────────────────────────────────────────────────────────────── */

test("「최근 N일」은 오늘을 넣어 센다", () => {
  const { historyRange } = rules();

  const week = historyRange(7, new Date("2026-08-11T12:00:00+09:00"));

  assert.strictEqual(week.to, "2026-08-11");
  assert.strictEqual(week.from, "2026-08-05", "7일이면 오늘까지 이레지 오늘 빼고 이레가 아니다");
});

test("오늘만 보면 시작과 끝이 같다", () => {
  const { historyRange } = rules();

  const day = historyRange(1, new Date("2026-08-11T12:00:00+09:00"));

  assert.strictEqual(day.from, day.to);
});

test("고른 폭이 실제로 어느 날짜인지 보인다", () => {
  const { historyRange, rangeSaying } = rules();

  const said = rangeSaying(historyRange(7, new Date("2026-08-11T12:00:00+09:00")));

  assert.strictEqual(said, "2026-08-05 ~ 2026-08-11", "「최근 7일」만으로는 경계를 모른다");
  assert.strictEqual(rangeSaying(null), "");
});

/* ── 줄 순서 ─────────────────────────────────────────────────────────── */

test("실패가 맨 위에 고정된다 — 더 오래된 것이어도", () => {
  const { historyOrder } = rules();

  const order = historyOrder([
    a_row({ name: "최근완료", happened_at: "2026-08-11T18:00:00+09:00" }),
    a_row({ name: "옛실패", status: "FAILED", failure_code: "CARRIER", happened_at: "2026-08-06T10:00:00+09:00" }),
  ]).map((row) => row.name);

  assert.deepStrictEqual(order.join(" "), "옛실패 최근완료");
});

test("이력은 최신이 위다 — 발송 예정과 반대 방향이다", () => {
  const { historyOrder, scheduleOrder } = rules();

  const rows = [
    a_row({ name: "어제", happened_at: "2026-08-10T10:00:00+09:00" }),
    a_row({ name: "오늘", happened_at: "2026-08-11T10:00:00+09:00" }),
  ];
  const history = historyOrder(rows).map((row) => row.name);
  const schedule = scheduleOrder(
    rows.map((row) => ({ ...row, status: "SCHEDULED", scheduled_at: row.happened_at })),
  ).map((row) => row.name);

  assert.strictEqual(history.join(" "), "오늘 어제", "방금 무슨 일이 있었나를 먼저 묻는다");
  assert.strictEqual(schedule.join(" "), "어제 오늘", "앞으로 나갈 것은 이른 것이 먼저다");
});

test("원래 배열을 흔들지 않는다", () => {
  const { historyOrder } = rules();
  const given = [a_row({ name: "가" }), a_row({ name: "나", status: "FAILED" })];

  historyOrder(given);

  assert.strictEqual(given[0].name, "가");
});

/* ── 셈 ──────────────────────────────────────────────────────────────── */

test("칩은 원문의 넷이다", () => {
  const { historyChips } = rules();

  const said = historyChips({ total: 210, failed: 1, viewed: 175, unviewed: 34 }).map((chip) => chip.say);

  assert.strictEqual(said.join(" | "), "전체 210 | ⚠ 실패 1 | 미열람 34 | 열람 175");
});

test("요약 줄이 원문대로 읽힌다", () => {
  const { historySummary } = rules();

  assert.strictEqual(
    historySummary({ counts: { total: 210, failed: 1, viewed: 175, unviewed: 34 }, truncated: true }),
    "기간 내 발송 210건 · 열람 175 · 미열람 34 · 실패 1 — 표에는 일부 행만 표시",
  );
});

test("다 보이면 「일부 행만」이라고 하지 않는다", () => {
  const { historySummary } = rules();

  const said = historySummary({ counts: { total: 3, failed: 0, viewed: 2, unviewed: 1 }, truncated: false });

  assert.ok(said.indexOf("일부 행만") === -1, "다 보이는데 일부라고 적으면 없는 것을 있다고 믿는다");
  assert.strictEqual(said, "기간 내 발송 3건 · 열람 2 · 미열람 1 · 실패 0");
});

/* ── 열람 ────────────────────────────────────────────────────────────── */

test("못 나간 줄에는 열람을 묻지 않는다", () => {
  const { viewedSaying } = rules();

  assert.strictEqual(viewedSaying(a_row({ status: "FAILED", failure_code: "OPT_OUT" })), "—");
  assert.strictEqual(viewedSaying(a_row({ viewed: true })), "● 열람");
  assert.strictEqual(viewedSaying(a_row({ viewed: false })), "○ 미열람", "빈칸은 「모른다」로 읽힌다");
});

/* ── CSV ─────────────────────────────────────────────────────────────── */

test("CSV 주소에 토큰을 싣지 않는다", () => {
  const { historyCsvPath } = rules();

  const path = historyCsvPath({ from: "2026-08-05", to: "2026-08-11" });

  assert.strictEqual(path, "/messages/history.csv?from=2026-08-05&to=2026-08-11");
  assert.ok(path.indexOf("token") === -1 && path.indexOf("Bearer") === -1);
});

test("받기는 헤더로 신원을 보낸다 — 주소는 기록에 남는다", () => {
  const code = codeOnly(read("js/messages-api.js"));
  const at = code.indexOf("historyCsv:");
  assert.notStrictEqual(at, -1, "historyCsv 가 없다 — 검사가 헛돈다");
  const body = code.slice(at, code.indexOf("},", at));

  assert.ok(body.indexOf("Authorization") !== -1, "토큰을 안 보내면 401 이다");
  assert.ok(body.indexOf("historyCsvPath") !== -1, "주소를 손으로 이으면 규칙이 갈라진다");
});

test("표는 잘려도 받기는 자르지 않는다", () => {
  const code = codeOnly(read("js/messages-api.js"));
  const at = code.indexOf("historyCsv:");
  const body = code.slice(at, code.indexOf("},", at));

  assert.ok(body.indexOf("limit") === -1, "표의 나머지를 가져가는 자리인데 여기서도 자르면 둘 다 일부다");
});

/* ── 목업이 서버와 같은 모양인가 ──────────────────────────────────────── */

test("목업이 서버 응답과 같은 칸을 갖는다", async () => {
  const api = load("api", "message-words", "schedule-rules", "history-rules", "messages-api");
  api.MOCK = true;

  const page = await api.mockHistory(api.historyRange(30), 200);

  assert.deepStrictEqual(Object.keys(page).sort().join(","), "counts,from_date,items,timezone,to_date,truncated");
  assert.deepStrictEqual(Object.keys(page.counts).sort().join(","), "failed,total,unviewed,viewed");
  assert.deepStrictEqual(
    Object.keys(page.items[0]).sort().join(","),
    [
      "age", "birth_date", "failure_code", "gender", "guide_message_id", "happened_at",
      "hospital_patient_no", "kind", "name", "patient_id", "prescription_set",
      "status", "viewed", "viewed_at", "visit_id",
    ]
      .sort()
      .join(","),
  );
});

test("목업의 셈이 원문의 규칙대로 맞는다", async () => {
  const api = load("api", "message-words", "schedule-rules", "history-rules", "messages-api");
  api.MOCK = true;

  const page = await api.mockHistory(api.historyRange(30), 200);
  const counts = page.counts;

  assert.strictEqual(
    counts.viewed + counts.unviewed,
    counts.total - counts.failed,
    "못 나간 문자에 열람을 묻는 것은 뜻이 없다 — 원문도 175 + 34 = 210 − 1 이다",
  );
});

test("목업의 기간이 실제로 걸러진다", async () => {
  const api = load("api", "message-words", "schedule-rules", "history-rules", "messages-api");
  api.MOCK = true;

  const week = await api.mockHistory(api.historyRange(7), 200);
  const month = await api.mockHistory(api.historyRange(30), 200);

  assert.ok(month.counts.total > week.counts.total, "기간을 넓혀도 그대로면 규칙을 눈으로 못 본다");
});

test("목업도 실패는 자르지 않는다", async () => {
  const api = load("api", "message-words", "schedule-rules", "history-rules", "messages-api");
  api.MOCK = true;

  const page = await api.mockHistory(api.historyRange(30), 1);

  const failed = page.items.filter(api.isFailed);
  assert.ok(failed.length >= 1, "맨 위에 고정하라 해 놓고 잘라 내면 까닭이 없어진다");
  assert.strictEqual(page.items.length, failed.length + 1, "잘리는 것은 나간 것뿐이다");
  assert.strictEqual(page.truncated, true);
});

test("목업 CSV 가 서버와 같은 열이다", async () => {
  const api = load("api", "message-words", "schedule-rules", "history-rules", "messages-api");
  api.MOCK = true;

  const text = api.mockHistoryCsv(api.historyRange(30));
  const head = text.replace(/^﻿/, "").split("\n")[0];

  assert.strictEqual(head, "발송일시,환자,차트번호,식별정보,세트명,종류,발송상태,실패사유,열람여부,열람일시");
  assert.ok(text.charCodeAt(0) === 0xfeff, "BOM 이 없으면 엑셀에서 한글이 깨진다");
});

test("쉼표가 든 값은 감싼다 — 안 그러면 열이 밀린다", () => {
  const api = load("api", "message-words", "schedule-rules", "history-rules", "messages-api");

  assert.strictEqual(api.csvCell("김서연"), "김서연");
  assert.strictEqual(api.csvCell("김, 서연"), '"김, 서연"');
  assert.strictEqual(api.csvCell('그는 "예"라 했다'), '"그는 ""예""라 했다"');
  assert.strictEqual(api.csvCell(null), "");
});

/* ── 화면이 실제로 그 규칙을 쓰는가 ──────────────────────────────────── */

test("화면이 두 갈래를 각자의 순서로 세운다", () => {
  const code = codeOnly(read("js/manage.js"));
  const table = code.slice(code.indexOf("function tableHtml"), code.indexOf("function render"));

  assert.ok(table.indexOf("scheduleOrder(") !== -1, "예정을 안 세우면 목업과 서버가 갈라진다");
  assert.ok(table.indexOf("historyOrder(") !== -1, "이력을 안 세우면 실패가 묻힌다");
});

test("이력 표의 열이 원문과 같다", () => {
  const code = codeOnly(read("js/manage.js"));
  const heads = code.slice(code.indexOf("var HEADS"), code.indexOf("function tableHtml"));

  assert.ok(heads.indexOf("발송일시") !== -1 && heads.indexOf("열람여부") !== -1);
  assert.ok(heads.indexOf("예정 시각") !== -1, "예정 쪽 열이 사라졌다");
});

test("아직 없는 것을 화면이 말한다", () => {
  const markup = markupOnly(read("manage.html"));

  assert.ok(markup.indexOf("재승인") !== -1, "왜 재승인 버튼이 없는지 적지 않으면 고장으로 읽힌다");
  assert.ok(markup.indexOf("열람 여부는 안내문 단위") !== -1, "한 번 열면 다섯 줄이 다 열람인 까닭을 적는다");
});

test("낱말을 여기서 다시 적지 않는다", () => {
  const code = codeOnly(read("js/history-rules.js"));

  for (const word of ["진료 안내문", "소진 임박", "잘못된 번호", "수신 거부"]) {
    assert.ok(code.indexOf(word) === -1, `「${word}」를 여기 다시 적었다 — js/message-words.js 것을 쓴다`);
  }
});
