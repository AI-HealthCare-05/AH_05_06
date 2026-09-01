/* 발송 예정 (S2-3) — KEY-234.
 *
 * 원문 캡션: 「앞으로 나갈 것 · 보류는 맨 위에서 이유와 함께」.
 *
 * **두 규칙이 이 화면의 전부다.**
 *
 *   1. 안 나간 것(실패 · 보류)은 고른 기간 밖이어도 보인다
 *   2. 예정은 고른 기간 안의 것만
 *
 * 화면을 그리는 코드는 shim 아래서 안 돌기 때문에, 규칙은 IIFE 밖
 * (`js/schedule-rules.js`)에 두었고 여기서 그것을 잰다. 그리는 자리는
 * 원문으로 잰다.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const { load } = require("./browser-shim.js");
const { read, codeOnly, markupOnly } = require("./source.js");

function rules() {
  return load("api", "message-words", "schedule-rules");
}

function a_row(over) {
  return Object.assign(
    {
      guide_message_id: 1,
      visit_id: 11,
      patient_id: 21,
      scheduled_at: "2026-09-01T18:00:00+09:00",
      kind: "GUIDE",
      status: "SCHEDULED",
      hold_reason: null,
      failure_code: null,
      name: "김서연",
      hospital_patient_no: "12345",
      gender: "FEMALE",
      birth_date: "1990-01-01",
      age: 36,
      prescription_set: "자궁내막증 · 비잔",
    },
    over || {},
  );
}

/* ── 줄 순서 ─────────────────────────────────────────────────────────── */

test("안 나간 것이 맨 위에 선다 — 예정이 더 이른 시각이어도", () => {
  const { scheduleOrder } = rules();

  const order = scheduleOrder([
    a_row({ name: "예정", scheduled_at: "2026-09-01T09:00:00+09:00" }),
    a_row({
      name: "보류",
      status: "HELD",
      hold_reason: "NO_CREDIT",
      scheduled_at: "2026-11-06T10:00:00+09:00",
    }),
    a_row({
      name: "실패",
      status: "FAILED",
      failure_code: "INVALID_PHONE",
      scheduled_at: "2026-08-11T18:00:00+09:00",
    }),
  ]).map((row) => row.name);

  assert.deepStrictEqual(order, ["실패", "보류", "예정"]);
});

test("안 나간 것 안에서는 실패와 보류를 다시 가르지 않는다 — 시각만 본다", () => {
  const { scheduleOrder } = rules();

  const order = scheduleOrder([
    a_row({
      name: "늦은실패",
      status: "FAILED",
      failure_code: "CARRIER",
      scheduled_at: "2026-09-01T18:00:00+09:00",
    }),
    a_row({
      name: "이른보류",
      status: "HELD",
      hold_reason: "NO_CREDIT",
      scheduled_at: "2026-09-01T09:00:00+09:00",
    }),
  ]).map((row) => row.name);

  assert.deepStrictEqual(
    order,
    ["이른보류", "늦은실패"],
    "요약이 「안 나간 것 3건」으로 한 무더기를 먼저 말한다",
  );
});

test("원래 배열을 흔들지 않는다", () => {
  const { scheduleOrder } = rules();
  const given = [
    a_row({ name: "가" }),
    a_row({ name: "나", status: "HELD", hold_reason: "NO_CREDIT" }),
  ];

  scheduleOrder(given);

  assert.strictEqual(
    given[0].name,
    "가",
    "받은 것을 제자리에서 뒤집으면 부른 쪽이 놀란다",
  );
});

/* ── 셈 ──────────────────────────────────────────────────────────────── */

test("안 나간 것은 실패와 보류를 합친 수다", () => {
  const { unsentCount } = rules();

  assert.strictEqual(unsentCount({ failed: 1, held: 2 }), 3);
  assert.strictEqual(unsentCount({ failed: 0, held: 0 }), 0);
  assert.strictEqual(unsentCount(null), 0, "아직 안 왔을 때도 답해야 한다");
});

test("요약 줄이 원문대로 읽힌다", () => {
  const { scheduleSummary } = rules();

  assert.strictEqual(
    scheduleSummary({ total: 42, failed: 1, held: 2, today: 2, window: 18 }, 7),
    "안 나간 것 3건 (실패 1 · 보류 2) · 앞으로 7일 예정 18건 · 오늘 2건",
  );
});

test("안 나간 것이 없으면 그 마디를 아예 뺀다", () => {
  const { scheduleSummary } = rules();

  const said = scheduleSummary(
    { total: 18, failed: 0, held: 0, today: 2, window: 18 },
    7,
  );

  assert.ok(
    said.indexOf("안 나간 것") === -1,
    "「안 나간 것 0건」은 알려 주는 것이 없다",
  );
  assert.strictEqual(said, "앞으로 7일 예정 18건 · 오늘 2건");
});

test("칩은 서버가 준 셈을 그대로 쓴다", () => {
  const { scheduleChips } = rules();

  const said = scheduleChips(
    { total: 42, failed: 1, held: 2, today: 2, window: 18 },
    7,
  ).map((chip) => chip.say);

  /* `join` 으로 견준다 — shim 은 다른 realm 이라 배열끼리는 모양이 같아도
     `deepStrictEqual` 이 걸린다. */
  assert.strictEqual(
    said.join(" | "),
    "전체 42 | ⚠ 실패 1 | ⏸ 보류 2 | 오늘 2 | 앞으로 7일 18",
  );
});

test("실패·보류가 0이면 눈에 걸리지 않는다", () => {
  const { scheduleChips } = rules();

  const chips = scheduleChips(
    { total: 18, failed: 0, held: 2, today: 2, window: 18 },
    7,
  );

  assert.strictEqual(
    chips[1].bad,
    false,
    "0건인데 굵게 세우면 늘 빨간 화면이 된다",
  );
  assert.strictEqual(chips[2].bad, true);
});

test("정해 두지 않은 기간도 사람 말로 적는다", () => {
  const { windowSaying, scheduleSummary } = rules();

  assert.strictEqual(windowSaying(7), "앞으로 7일");
  assert.strictEqual(windowSaying(14), "앞으로 14일");
  assert.ok(
    scheduleSummary({ failed: 0, held: 0, today: 0, window: 3 }, 14).indexOf(
      "앞으로 14일",
    ) !== -1,
  );
});

/* ── 식별정보 ────────────────────────────────────────────────────────── */

test("식별정보는 원문대로 「여 · 34세 · 1992-05-20」", () => {
  const { identityOf } = rules();

  assert.strictEqual(
    identityOf(a_row({ gender: "FEMALE", age: 34, birth_date: "1992-05-20" })),
    "여 · 34세 · 1992-05-20",
  );
});

test("모르는 성별은 적지 않는다", () => {
  const { identityOf } = rules();

  const said = identityOf(
    a_row({ gender: "UNKNOWN", age: 34, birth_date: "1992-05-20" }),
  );

  assert.strictEqual(
    said,
    "34세 · 1992-05-20",
    "코드를 그대로 보이면 사람 말이 아니고, 「기타」로 옮기면 없는 것을 지어낸다",
  );
});

/* ── 할 일 ───────────────────────────────────────────────────────────── */

test("번호가 잘못된 줄만 갈 곳이 있다", () => {
  const { rowAction } = rules();

  const held = rowAction(
    a_row({ visit_id: 8802, status: "HELD", hold_reason: "INVALID_PHONE" }),
  );
  const failed = rowAction(
    a_row({ visit_id: 8801, status: "FAILED", failure_code: "INVALID_PHONE" }),
  );

  assert.strictEqual(held.say, "번호 수정");
  assert.strictEqual(
    held.href,
    "/patients.html?visit=8802&tab=basic",
    "그 환자의 기본정보로 간다",
  );
  assert.strictEqual(
    failed.href,
    "/patients.html?visit=8801&tab=basic",
    "지난 실패도 같은 번호를 고쳐야 한다",
  );
});

test("발송기가 없는 일에는 버튼을 세우지 않는다", () => {
  const { rowAction } = rules();

  assert.strictEqual(
    rowAction(a_row({ status: "SCHEDULED" })),
    null,
    "시각 변경 · 즉시 발송은 API 가 없다",
  );
  assert.strictEqual(
    rowAction(a_row({ status: "HELD", hold_reason: "NO_CREDIT" })),
    null,
    "문자 충전도 없다",
  );
  assert.strictEqual(
    rowAction(a_row({ status: "FAILED", failure_code: "CARRIER" })),
    null,
  );
  assert.strictEqual(rowAction(null), null);
});

/* ── 잘림 ────────────────────────────────────────────────────────────── */

test("조용히 자르지 않는다", () => {
  const { truncationNote } = rules();

  assert.strictEqual(
    truncationNote({
      truncated: false,
      counts: { window: 3 },
      items: [1, 2, 3],
    }),
    "",
  );
  assert.strictEqual(
    truncationNote({ truncated: true, counts: { window: 30 }, items: [1, 2] }),
    "예정 30건 중 2건만 보입니다",
  );
});

/* ── 목업이 서버와 같은 모양인가 ──────────────────────────────────────── */

test("목업도 안 나간 것을 창 밖에서 데려온다", async () => {
  const api = load("api", "message-words", "schedule-rules", "messages-api");
  api.MOCK = true;

  const page = await api.mockScheduled(7, 200);
  const stuck = page.items.filter(api.isUnsent);

  assert.ok(stuck.length >= 2, "실패·보류가 안 보이면 이 화면의 요점이 없다");
  assert.ok(
    stuck.some(
      (row) => new Date(row.scheduled_at) > new Date(Date.now() + 8 * 86400000),
    ),
    "창 밖의 보류가 있어야 규칙이 눈에 보인다",
  );
  assert.strictEqual(page.counts.failed, 1);
  assert.strictEqual(page.counts.held, 2);
});

test("목업의 예정은 창을 지킨다", async () => {
  const api = load("api", "message-words", "schedule-rules", "messages-api");
  api.MOCK = true;

  const seven = await api.mockScheduled(7, 200);
  const thirty = await api.mockScheduled(30, 200);

  assert.ok(
    thirty.counts.window > seven.counts.window,
    "창을 넓혀도 그대로면 목업이 규칙을 안 보여 준다",
  );
  assert.ok(thirty.items.length > seven.items.length, "눌러 봐도 표가 그대로면 되는지 알 수 없다");
  assert.strictEqual(
    seven.counts.total,
    thirty.counts.total,
    "전체는 창과 무관하다",
  );
});

test("목업이 서버 응답과 같은 칸을 갖는다", async () => {
  const api = load("api", "message-words", "schedule-rules", "messages-api");
  api.MOCK = true;

  const page = await api.mockScheduled(7, 200);

  assert.deepStrictEqual(Object.keys(page).sort(), [
    "counts",
    "days",
    "items",
    "timezone",
    "truncated",
  ]);
  assert.deepStrictEqual(Object.keys(page.counts).sort(), [
    "failed",
    "held",
    "today",
    "total",
    "window",
  ]);
  assert.deepStrictEqual(
    Object.keys(page.items[0]).sort(),
    [
      "age",
      "birth_date",
      "failure_code",
      "gender",
      "guide_message_id",
      "hold_reason",
      "hospital_patient_no",
      "kind",
      "name",
      "patient_id",
      "prescription_set",
      "scheduled_at",
      "status",
      "visit_id",
    ].sort(),
    "목업만 다른 칸을 가지면 목업에서만 되는 화면이 생긴다",
  );
});

/* ── 화면이 실제로 그 규칙을 쓰는가 ──────────────────────────────────── */

test("화면이 스스로 세지 않고 서버 셈을 그린다", () => {
  const code = codeOnly(read("js/manage.js"));

  assert.ok(
    code.indexOf("scheduleChips(") !== -1,
    "칩을 손으로 만들면 창 밖의 것을 못 센다",
  );
  assert.ok(code.indexOf("scheduleSummary(") !== -1);
  assert.ok(code.indexOf("scheduleOrder(") !== -1);
  assert.ok(code.indexOf("rowAction(") !== -1);
});

test("이름과 세트명은 반드시 막고 그린다", () => {
  const code = codeOnly(read("js/manage.js"));
  const drawn = code.slice(
    code.indexOf("function rowHtml"),
    code.indexOf("function whenSaying"),
  );

  for (const field of [
    "row.name",
    "row.hospital_patient_no",
    "row.prescription_set",
    "identityOf(row)",
  ]) {
    const at = drawn.indexOf(field);
    assert.notStrictEqual(at, -1, `${field} 를 안 그린다 — 검사가 헛돈다`);
    assert.ok(
      drawn.slice(Math.max(0, at - 24), at).indexOf("esc(") !== -1,
      `${field} 를 막지 않고 그린다 — 환자 이름에 꺾쇠가 들어오면 뚫린다`,
    );
  }
});

test("문자 어휘를 여기서 다시 적지 않는다", () => {
  const code =
    codeOnly(read("js/schedule-rules.js")) + codeOnly(read("js/manage.js"));

  for (const word of ["진료 안내문", "소진 임박", "잘못된 번호", "문자 잔량"]) {
    assert.ok(
      code.indexOf(word) === -1,
      `「${word}」를 여기 다시 적었다 — 같은 문자가 화면마다 다른 이름으로 뜬다 (js/message-words.js 것을 쓴다)`,
    );
  }
});

test("눌러도 아무 일 없는 버튼을 두지 않는다", () => {
  const markup = markupOnly(read("manage.html"));
  const body = markup.slice(markup.indexOf("</header>"));

  /* **줄이 아니라 여는 태그 단위로 본다.** 처음에는 줄로 걸렀는데, 속성이
     길어 줄이 나뉘자 `<button` 만 있는 줄이 되어 통과했다. */
  const dead = [];
  for (let at = 0; ; ) {
    const open = body.indexOf("<button", at);
    if (open === -1) break;
    const close = body.indexOf(">", open);
    const tag = body.slice(open, close + 1);
    at = close;
    /* 손이 붙은 버튼은 `id` 로 찾아 붙인다. 나머지는 셋 중 하나여야 한다 —
       여기(`aria-current`)이거나, 아직(`tab--later`)이거나, 없거나. */
    const alive =
      tag.includes("id=") || tag.includes('aria-selected="true"') || tag.includes("tab--later");
    if (!alive) dead.push(tag);
  }

  assert.strictEqual(dead.join("\n"), "", "시각 변경 · 즉시 발송 · 문자 충전은 아직 API 가 없다");
});

test("아직 없는 것을 화면이 말한다", () => {
  const markup = markupOnly(read("manage.html"));

  assert.ok(
    markup.indexOf("발송기가 아직 없습니다") !== -1,
    "왜 버튼이 없는지 적지 않으면 고장으로 읽힌다",
  );
  assert.ok(
    markup.indexOf("환자 관리") !== -1 && markup.indexOf("발송 이력") !== -1,
    "S2 의 세 갈래는 보여야 한다",
  );
});
