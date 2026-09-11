/* 환자 관리 표의 **차례** — KEY-327.
 *
 * 표가 등록 과거순으로 서서, 방금 등록한 환자가 맨 뒤 쪽에 있었다. 이제 기본이
 * 최근 등록순이고 차트번호로도 세울 수 있다.
 *
 * **정렬은 서버가 한다.** 화면이 받은 쪽만 다시 세우면 그 쪽 안에서만 맞고,
 * 쪽을 넘기면 앞 쪽과 겹치거나 빠진다. 그래서 화면이 재는 것은 「무엇을
 * 요청하는가」와 「지금 기준이 무엇인지 보이는가」다.
 */
const { test } = require("node:test");
const assert = require("node:assert/strict");
const { load } = require("./browser-shim");
const { read, codeOnly } = require("./source");

function rules() {
  return load("roster-rules");
}

test("표 머리를 누르면 그 기준으로, 다시 누르면 방향만 뒤집는다", () => {
  const box = rules();

  //: 기본은 최근 등록순 — 「등록」을 누르면 반대쪽으로 간다
  assert.equal(box.rosterSortNext("registered", "registered_desc"), "registered_asc");
  assert.equal(box.rosterSortNext("registered", "registered_asc"), "registered_desc");
  //: 다른 기준에서 누르면 **그 기준의 기본 방향**으로 간다 — 한 번 고른 기준에
  //: 갇히지 않는다
  assert.equal(box.rosterSortNext("chart", "registered_desc"), "chart_desc");
});

test("화살표가 지금 기준과 방향을 말한다", () => {
  const box = rules();

  assert.equal(box.rosterSortArrow("registered", "registered_desc"), " ▼");
  assert.equal(box.rosterSortArrow("registered", "registered_asc"), " ▲");
  //: 그 기준이 아닐 때는 아무 표시도 없다 — 둘 다 화살표를 달면 무엇이
  //: 지금 기준인지 알 수 없다
  assert.equal(box.rosterSortArrow("chart", "registered_desc"), "");
});

test("등록 시점은 날짜까지만 보인다", () => {
  const box = rules();

  assert.equal(box.registeredDay({ created_at: "2026-09-11T09:00:00+09:00" }), "2026-09-11");
  //: 서버가 안 준 줄에서 화면이 깨지지 않는다
  assert.equal(box.registeredDay({}), "");
  assert.equal(box.registeredDay(null), "");
});

test("화면은 받은 쪽을 **다시 세우지 않는다**", () => {
  /* 받은 쪽만 세우면 그 쪽 안에서만 맞는다 — 2쪽의 첫 줄이 1쪽 끝줄보다
     앞에 설 수 있다. 차례는 서버에서 오고 화면은 그대로 그린다. */
  const code = codeOnly(read("js/manage.js"));
  const table = code.slice(code.indexOf("function tableHtml"), code.indexOf("function tableHtml") + 900);

  assert.ok(!/\.sort\(/.test(table), "관리 표를 화면에서 다시 세운다");
  assert.match(code, /rosterSort/, "차례를 서버에 안 보낸다");
});

test("차례를 바꾸면 첫 쪽부터 다시 본다", () => {
  /* 3쪽에서 차례를 바꾸면 그 자리의 3쪽이 무엇인지 아무도 모른다. */
  const code = codeOnly(read("js/manage.js"));
  const handler = code.slice(code.indexOf('closest("[data-sort]")'));

  assert.match(handler.slice(0, 300), /rosterOffset = 0/, "차례만 바꾸고 쪽은 그대로 둔다");
});

test("목업도 최근 등록순 — **번호**로 센다", async () => {
  const api = load("api", "patients-api");

  const page = await api.patientsApi.roster("", "ALL", 40, 0, "registered_desc");
  const ids = page.items.map((row) => row.patient_id);

  assert.ok(ids.length > 1, "목업 표가 비었다 — 검사가 헛돈다");
  assert.ok(
    page.items.every((row) => typeof row.created_at === "string" && row.created_at),
    "목업 줄에 등록 시점이 없다 — 「등록」 열이 통째로 비어 보인다",
  );
  ids.forEach(function (id, i) {
    if (i === 0) return;
    assert.ok(ids[i - 1] > id, `${ids[i - 1]} 다음에 ${id} 가 왔다 — 번호 내림차순이 아니다`);
  });
});

test("목업 차트번호도 **길이를 먼저** 본다 — 10 이 7 보다 앞에 서지 않게", () => {
  /* 목업 자료는 전부 다섯 자리라 이 규칙이 안 드러난다 — **자리수를 섞어**
     세우는 함수에 직접 물어야 잰다. 의원이 `7` 을 그대로 넣는 순간 이 규칙이
     없으면 표가 뒤집힌다. */
  const api = load("api", "patients-api");
  const rows = ["7", "10", "9", "09948", "100"].map(function (no, i) {
    return { hospital_patient_no: no, patient_id: i + 1 };
  });

  const rising = api.mockSorted(rows, "chart_asc").map((row) => row.hospital_patient_no);

  assert.equal(rising.join(","), "7,9,10,100,09948");
  assert.equal(
    api
      .mockSorted(rows, "chart_desc")
      .map((row) => row.hospital_patient_no)
      .join(","),
    "09948,100,10,9,7",
  );
});

test("목업의 오름·내림은 서로의 거울이다", async () => {
  const api = load("api", "patients-api");

  const rising = await api.patientsApi.roster("", "ALL", 40, 0, "chart_asc");
  const falling = await api.patientsApi.roster("", "ALL", 40, 0, "chart_desc");

  assert.equal(
    falling.items.map((row) => row.hospital_patient_no).join(","),
    rising.items
      .map((row) => row.hospital_patient_no)
      .reverse()
      .join(","),
  );
});

test("등록 화면의 찾기는 **등록 오름차순**을 함께 말한다", () => {
  /* 이어 보기(`cursor`)는 `patient_id >` 로 앞으로만 간다. 안 말하면 첫 쪽이
     관리 표의 기본(최근순)으로 와서, 둘째 쪽부터 이미 본 사람이 다시 나온다. */
  const api = read("js/patients-api.js");

  assert.match(api, /cursor: cursor, sort: "registered_asc"/);
});
