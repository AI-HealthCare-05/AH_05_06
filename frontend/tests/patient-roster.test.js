/* 환자 관리 (S2-1) — KEY-234.
 *
 * 원문 캡션: 「★ 이탈을 잡는 자리 · 오늘이 아닌 환자도 여기서 찾는다」.
 *
 * **현황(S1)이 칩으로 보이던 것을 여기서는 열로 보인다.** 원문 주석이 그렇게
 * 적는다 — 「같은 속성, 표기만 서식에 맞춘다」. 그래서 여기서 가장 크게 재는
 * 것은 **같은 이름을 쓰는가** 다. 두 화면이 같은 환자를 다르게 부르면 어느
 * 쪽이 맞는지 알 수 없다.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const { load } = require("./browser-shim.js");
const { read, codeOnly, markupOnly } = require("./source.js");

function rules() {
  return load("api", "clinic-clock", "session", "patients-api", "roster-rules");
}

function a_row(over) {
  return Object.assign(
    {
      patient_id: 2001,
      hospital_patient_no: "10118",
      name: "유지수",
      birth_date: "1996-04-10",
      gender: "FEMALE",
      age: 30,
      phone: "01031414410",
      sms_consent: true,
      sms_consented_at: "2026-05-20T10:00:00+09:00",
      sms_opted_out_at: null,
      diagnosis_name: "자궁내막증",
      doctor: { doctor_id: 2, name: "김연우" },
      latest_visit: { visit_id: 9101, visited_at: "2026-05-20T10:00:00+09:00", status: "COMPLETED" },
      work_category: "COMPLETED",
      detail_status: "VIEWED",
      flags: [],
    },
    over || {},
  );
}

/* ── 이탈 배지 ──────────────────────────────────────────────────────── */

test("배지를 사람 말로 옮긴다", () => {
  const { flagsSaying } = rules();

  assert.strictEqual(flagsSaying(["UNREAD_STREAK"]), "⚠ 3회 연속 미열람");
  assert.strictEqual(flagsSaying(["STOPPED_DOSING"]), "⚠ 복약 중단 응답");
  assert.strictEqual(flagsSaying(["RUN_OUT_OVERDUE"]), "⚠ 소진 후 7일 경과");
});

test("배지가 둘이면 나란히 적는다", () => {
  const { flagsSaying } = rules();

  assert.strictEqual(flagsSaying(["UNREAD_STREAK", "RUN_OUT_OVERDUE"]), "⚠ 3회 연속 미열람 · 소진 후 7일 경과");
});

test("배지가 없으면 아무 말도 하지 않는다", () => {
  const { flagsSaying } = rules();

  assert.strictEqual(flagsSaying([]), "", "빈 목록이 정상이다 — 챙길 일이 없다는 뜻이다");
  assert.strictEqual(flagsSaying(null), "");
});

test("모르는 배지 코드는 적지 않는다", () => {
  const { flagsSaying } = rules();

  assert.strictEqual(
    flagsSaying(["NEW_KIND_OF_TROUBLE"]),
    "",
    "코드를 그대로 보이면 스탭이 무엇을 챙기라는 말인지 알 수 없다",
  );
});

/* ── 문자 동의 ──────────────────────────────────────────────────────── */

test("동의는 언제부터인지와 함께 적는다", () => {
  const { consentSaying } = rules();

  assert.strictEqual(consentSaying(a_row()), "동의 · 05-20");
});

test("거부도 날짜와 함께 적는다", () => {
  const { consentSaying } = rules();

  const said = consentSaying(a_row({ sms_consent: false, sms_consented_at: null, sms_opted_out_at: "2026-07-28T10:00:00+09:00" }));

  assert.strictEqual(said, "거부 · 07-28");
});

test("날짜를 모르면 날짜만 뺀다", () => {
  const { consentSaying } = rules();

  assert.strictEqual(consentSaying(a_row({ sms_consented_at: null })), "동의", "지어내지 않는다");
});

/* ── 칩 ─────────────────────────────────────────────────────────────── */

test("칩 다섯이 원문대로 선다", () => {
  const { rosterChips } = rules();

  const said = rosterChips(
    { ALL: 128, IN_TREATMENT: 34, NEEDS_ATTENTION: 7, SMS_OPT_OUT: 4, INACTIVE_6_MONTHS: 22 },
    "ALL",
  ).map((chip) => chip.say);

  assert.strictEqual(
    said.join(" | "),
    "전체 128명 | 진행 중 34 | ⚠ 챙겨주세요 7 | 수신 거부 4 | 6개월 이상 미내원 22",
  );
});

test("고른 칩만 켜진다", () => {
  const { rosterChips } = rules();

  const on = rosterChips({ ALL: 3 }, "NEEDS_ATTENTION").filter((chip) => chip.on).map((chip) => chip.key);

  assert.deepStrictEqual(on.join(), "NEEDS_ATTENTION");
});

test("챙길 일이 0이면 눈에 걸리지 않는다", () => {
  const { rosterChips } = rules();

  const chips = rosterChips({ ALL: 3, NEEDS_ATTENTION: 0 }, "ALL");

  assert.strictEqual(chips[2].bad, false, "0인데 굵게 세우면 늘 빨간 화면이 된다");
});

/* ── 요약 ───────────────────────────────────────────────────────────── */

test("거른 상태에서 「전체」라고 하지 않는다", () => {
  const { rosterSummary } = rules();

  const said = rosterSummary({
    counts: { ALL: 128, NEEDS_ATTENTION: 5 },
    selected_category: "NEEDS_ATTENTION",
    items: [1, 2, 3, 4, 5],
  });

  assert.strictEqual(said, "⚠ 챙겨주세요 5명", "「전체 5명」이면 의원에 다섯 명뿐인 줄로 읽힌다");
});

test("한 쪽에 다 안 들어가면 그렇다고 말한다", () => {
  const { rosterSummary } = rules();

  const said = rosterSummary({ counts: { ALL: 128 }, selected_category: "ALL", items: new Array(50) });

  assert.strictEqual(said, "전체 128명 중 50명 표시", "나머지가 어디 갔는지 알 수 있어야 한다");
});

/* ── 갈 곳 ──────────────────────────────────────────────────────────── */

test("정보 수정은 그 환자의 기본정보로 간다", () => {
  const { rosterActions } = rules();

  const found = rosterActions(a_row());

  assert.strictEqual(found.length, 1);
  assert.strictEqual(found[0].href, "/patients.html?visit=9101&tab=basic");
});

test("진료가 없으면 갈 곳도 없다", () => {
  const { rosterActions } = rules();

  assert.deepStrictEqual(rosterActions(a_row({ latest_visit: null })).length, 0);
  assert.deepStrictEqual(rosterActions(null).length, 0);
});

/* ── 이름을 현황과 나눠 쓰는가 ──────────────────────────────────────── */

test("상태 이름을 여기서 다시 짓지 않는다", () => {
  const { categoryLabel, statusLabel } = rules();

  assert.strictEqual(categoryLabel("NEEDS_ATTENTION"), "보완");
  assert.strictEqual(categoryLabel("COMPLETED"), "완료");
  assert.strictEqual(statusLabel("INVALID_PHONE"), "번호 오류");

  /* **칩 이름은 여기 있는 것이 맞다.** 분류(`PatientCategory`)와 세부
     상태(`DetailStatus`)는 다른 축인데 「수신 거부」라는 낱말을 나눠 쓴다 —
     그래서 그 낱말은 여기서 재지 않는다. 재는 것은 상태 이름뿐이다. */
  const code = codeOnly(read("js/roster-rules.js"));
  for (const word of ["작성 중", "승인 요청", "발송 대기", "번호 오류", "진료기록 없음"]) {
    assert.ok(
      code.indexOf(word) === -1,
      `「${word}」를 여기 다시 적었다 — 같은 환자가 두 화면에서 다르게 뜬다 (js/patients-api.js 것을 쓴다)`,
    );
  }
});

/* ── 목업이 서버와 같은 규칙인가 ────────────────────────────────────── */

test("목업이 서버와 같은 규칙으로 거른다", async () => {
  const api = rules();
  api.MOCK = true;

  const all = await api.patientsApi.roster("", "ALL", null, 50);
  const attention = await api.patientsApi.roster("", "NEEDS_ATTENTION", null, 50);

  /* **수를 못 박는다.** 「거른 것과 센 것이 같다」로만 재면 둘을 함께 틀리게
     고쳐도 통과한다 — 실제로 그렇게 두었더니 돌연변이가 안 물었다.

     아홉인 까닭: 현황 목록의 다섯 줄이 차트번호로 넷으로 접히고(김서연이 두
     번 뜬다), 오늘이 아닌 다섯 중 넷이 더해진다. */
  assert.strictEqual(all.counts.ALL, 9);
  assert.strictEqual(all.counts.IN_TREATMENT, 4, "완료가 다섯이라 진행 중은 넷이다");
  assert.strictEqual(all.counts.NEEDS_ATTENTION, 4, "보완 하나 + 이탈 배지 셋");
  assert.strictEqual(attention.items.length, 4);

  const finished = attention.items.filter((row) => row.work_category === "COMPLETED");
  assert.strictEqual(
    finished.length,
    3,
    "원문에서 「완료 · 열람」인 줄에 ⚠ 배지가 붙어 있다 — 이탈도 챙길 일이다",
  );
  assert.ok(finished.every((row) => row.flags.length > 0));

  const treating = await api.patientsApi.roster("", "IN_TREATMENT", null, 50);
  assert.strictEqual(treating.items.length, 4);
  assert.ok(
    treating.items.every((row) => row.work_category !== "COMPLETED"),
    "끝난 진료는 진행 중이 아니다",
  );
});

test("셈은 거른 뒤에도 의원 전체를 말한다", async () => {
  const api = rules();
  api.MOCK = true;

  const attention = await api.patientsApi.roster("", "NEEDS_ATTENTION", null, 50);

  assert.strictEqual(attention.counts.ALL, 9, "보이는 쪽만 세면 스탭이 일이 없다고 믿는다");
});

test("검색은 이름 · 차트번호 · 휴대폰 셋을 다 본다", async () => {
  const api = rules();
  api.MOCK = true;

  for (const keyword of ["유지수", "10118", "01031414410"]) {
    const found = await api.patientsApi.roster(keyword, "ALL", null, 50);
    assert.strictEqual(found.items.length, 1, `${keyword} 로 못 찾는다`);
    assert.strictEqual(found.items[0].name, "유지수");
  }
});

test("빈 검색어에도 표는 답한다", async () => {
  const api = rules();
  api.MOCK = true;

  const found = await api.patientsApi.roster("", "ALL", null, 50);

  assert.ok(found.items.length > 0, "등록 화면의 찾기와 달리 이쪽은 의원 전체를 훑는 자리다");
});

/* ── 화면이 실제로 그 규칙을 쓰는가 ────────────────────────────────── */

test("표의 열이 원문과 같다", () => {
  const code = codeOnly(read("js/manage.js"));
  const heads = code.slice(code.indexOf("var HEADS"), code.indexOf("var BLANK"));

  for (const head of ["차트", "식별정보", "질환", "담당", "전화번호", "문자 동의", "마지막 진료", "기본 상태", "세부 상태"]) {
    assert.ok(heads.indexOf(head) !== -1, `${head} 열이 없다`);
  }
});

test("환자 이름과 진단을 막고 그린다", () => {
  const code = codeOnly(read("js/manage.js"));
  const drawn = code.slice(code.indexOf("function rosterRowHtml"), code.indexOf("function cardHtml"));

  for (const field of ["row.name", "row.diagnosis_name", "row.hospital_patient_no"]) {
    const at = drawn.indexOf(field);
    assert.notStrictEqual(at, -1, `${field} 를 안 그린다 — 검사가 헛돈다`);
    assert.ok(
      drawn.slice(Math.max(0, at - 24), at).indexOf("esc(") !== -1,
      `${field} 를 막지 않고 그린다`,
    );
  }
});

test("환자 관리가 첫 갈래다", () => {
  const markup = markupOnly(read("manage.html"));
  const nav = markup.slice(markup.indexOf('id="tabs"'), markup.indexOf("</div>", markup.indexOf('id="tabs"')));

  assert.ok(nav.indexOf("환자 관리") < nav.indexOf("발송 예정"), "원문 세그먼트 탭 차례다");
  assert.ok(
    /data-view="roster"[^>]*aria-selected="true"/.test(nav),
    "「오늘이 아닌 환자도 여기서 찾는다」가 이 화면을 여는 까닭이다",
  );
});

test("고른 칩이 지역 변수에 갇히지 않는다", () => {
  const code = codeOnly(read("js/manage.js"));
  const handlers = code.slice(code.indexOf('el("days").addEventListener'));

  assert.ok(
    handlers.indexOf("var chosen") === -1,
    "기간 핸들러 안에서 `var chosen` 을 다시 선언하면 고른 칩이 그 안에 갇힌다 — `picked` 로 한 번 겪었다",
  );
});

/* **현황과 관리가 같은 사람을 보인다** (팀장 지적 2026-09-01).
 *
 * 관리 표를 손으로 따로 적어 두었더니 두 화면에 다른 사람들이 떴다 — 같은
 * 의원인데 현황에는 김서연이, 관리에는 유지수가 있었다. 누가 있는지는 한
 * 곳(`MOCK_TODAY`)에서만 정하고 관리 표는 거기서 만든다.
 */
test("현황에 있는 환자는 관리에도 있다", async () => {
  const api = rules();
  api.MOCK = true;

  const roster = await api.patientsApi.roster("", "ALL", null, 50);
  const charts = roster.items.map((row) => row.hospital_patient_no);

  for (const visit of api.MOCK_TODAY) {
    assert.ok(
      charts.indexOf(visit.hospital_patient_no) !== -1,
      `현황의 ${visit.name}(${visit.hospital_patient_no}) 이 관리에 없다`,
    );
  }
});

test("같은 환자가 두 줄로 뜨지 않는다", async () => {
  const api = rules();
  api.MOCK = true;

  const charts = (await api.patientsApi.roster("", "ALL", null, 50)).items.map(
    (row) => row.hospital_patient_no,
  );

  assert.strictEqual(
    charts.length,
    new Set(charts).size,
    "현황은 진료 한 줄이고 관리는 환자 한 줄이다 — 김서연이 두 번 진료했다",
  );
});

test("오늘이 아닌 환자도 관리에는 있다", async () => {
  const api = rules();
  api.MOCK = true;

  const roster = await api.patientsApi.roster("", "ALL", null, 50);
  const today = api.MOCK_TODAY.map((visit) => visit.hospital_patient_no);
  const past = roster.items.filter((row) => today.indexOf(row.hospital_patient_no) === -1);

  assert.ok(past.length >= 3, "원문 캡션: 「오늘이 아닌 환자도 여기서 찾는다」");
  assert.ok(past.some((row) => row.flags.length), "이탈 배지가 붙는 줄이 바로 이들이다");
});
