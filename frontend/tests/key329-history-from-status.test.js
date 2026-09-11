/* 현황 탭에서도 **그 환자의 지난 진료 전부**를 연다 — KEY-329.
 *
 * 현황 탭이 보여 주는 「진료 처리 이력」은 **이 진료 하나**의 흐름이다. 지난
 * 진료까지 보려면 관리 화면으로 나갔다가 그 환자를 다시 찾아야 했다.
 *
 * **모달은 한 벌이다.** 두 화면이 `js/history-modal.js` 의 같은 함수를 부른다 —
 * 두 벌이면 한쪽만 고쳐지고, 어느 화면에서 봤느냐로 같은 환자의 이력이 갈린다.
 */
const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { load } = require("./browser-shim");
const { read, bareCode, codeOnly, markupOnly, scriptsOf } = require("./source");

function box() {
  return load("api", "checkin-words", "message-words", "history-modal");
}

test("모달을 그리는 코드가 **한 곳**이다", () => {
  /* 옮기기 전에는 `manage.js` 안에 있었다. 현황 탭이 쓰려고 복사했다면
     그때부터 둘이 갈리기 시작한다. */
  const shared = bareCode(read("js/history-modal.js"));
  const manage = bareCode(read("js/manage.js"));

  assert.match(shared, /function historyModalHtml\(/, "공용 파일이 모달을 안 그린다");
  assert.match(shared, /function openPatientHistory\(/, "공용 파일이 모달을 안 연다");
  assert.ok(
    !/function modalHtml\(|function blockHtml\(/.test(manage),
    "관리 화면이 아직 제 몫의 이력 모달을 들고 있다 — 두 벌이면 갈린다",
  );
  assert.match(manage, /openPatientHistory\(/, "관리 화면이 공용 것을 안 쓴다");
});

test("현황 탭이 [전체 이력 보기] 를 세운다", () => {
  const view = load("api", "message-words", "clinic-clock", "patient-link-view", "status-view");
  const html = view.statusScreenHtml({
    canUnapprove: false,
    entries: [],
    messages: [],
    guideStatus: "SCHEDULED_TO_SEND",
    link: null,
    patientId: 1003,
  });

  assert.match(html, /data-history="1003"/);
  assert.match(html, /전체 이력 보기/);
});

test("환자 번호를 모르면 단추를 아예 안 세운다", () => {
  /* 눌러도 아무 일 없는 단추보다 없는 편이 낫다 — 이 저장소가 여러 번
     밟은 자리다(KEY-236). */
  const view = load("api", "message-words", "clinic-clock", "patient-link-view", "status-view");
  const html = view.statusScreenHtml({
    canUnapprove: false,
    entries: [],
    messages: [],
    guideStatus: "",
    link: null,
    patientId: null,
  });

  assert.ok(!/data-history=/.test(html), "번호도 없는데 단추가 섰다");
});

test("스탭 화면이 공용 파일을 **기대는 것보다 뒤에** 싣는다", () => {
  /* 파일은 모듈이 아니라 전역에 얹히는 스크립트라, 차례가 곧 의존성이다. */
  const loaded = scriptsOf("patients.html");
  const at = (name) => loaded.indexOf(name);

  assert.ok(at("history-modal.js") >= 0, "이력 모달을 안 싣는다 — 현황 탭이 브라우저에서 터진다");
  assert.ok(at("checkin-words.js") >= 0 && at("checkin-words.js") < at("history-modal.js"));
  assert.ok(at("patients-api.js") >= 0 && at("patients-api.js") < at("history-modal.js"));
  assert.ok(at("history-modal.js") < at("status-view.js"), "현황 탭보다 늦게 실린다");
});

test("스탭 화면이 **번호를 넘기고 그 단추를 받는다**", () => {
  /* `visit-guide.js` 는 IIFE 라 shim 아래서 안 돈다 — 원문으로 잰다.
     이 두 줄이 없으면 단추는 서는데 아무 일도 안 일어나거나, 서지도 않는다. */
  const bare = bareCode(read("js/visit-guide.js"));
  /* 선택자는 **글자열 안**에 있다 — `bareCode` 는 글자열을 걷어 내므로 못 본다.
     주석만 걷는 `codeOnly` 로 본다(이 파일 주석에 그 선택자는 없다). */
  const withStrings = codeOnly(read("js/visit-guide.js"));

  assert.match(bare, /patientId:\s*\(\(guide && guide\.patient\) \|\| \{\}\)\.patient_id/, "현황에 환자 번호를 안 넘긴다");
  assert.match(withStrings, /closest\("\[data-history\]"\)/, "단추를 안 받는다");
  assert.match(bare, /openPatientHistory\(/, "공용 모달을 안 연다");
});

test("모달의 **모양도 한 벌**이다 — 두 화면이 같은 규칙을 받는다", () => {
  /* `.modal__top` · `.modal__card--wide` 가 `manage.css` 에만 있던 동안,
     현황 탭의 모달은 머리가 flex 가 아니라 ✕ 가 제목 아래로 떨어졌고
     넓이·스크롤도 안 먹었다. 공용 화면이 다 싣는 `blocks.css` 에 둔다. */
  const shared = read("css/blocks.css");
  assert.match(shared, /\n\.modal__card--wide \{/, "넓은 카드가 공용 자리에 없다");
  assert.match(shared, /\n\.modal__top \{/, "모달 머리가 공용 자리에 없다");

  /* 그리고 **두 화면이 그 껍데기를 실제로 쓴다.** 규칙만 있고 클래스를 안
     붙이면 아무 일도 안 일어난다. */
  ["patients.html", "manage.html"].forEach(function (page) {
    assert.match(
      markupOnly(read(page)),
      /id="modal-body"[^>]*>|class="modal__card modal__card--wide"/,
      page + " 에 모달 껍데기가 없다",
    );
    assert.ok(
      /modal__card--wide/.test(markupOnly(read(page))),
      page + " 의 모달이 좁은 카드다 — 진료 줄이 접힌다",
    );
  });
});

test("서버가 안내문 머리에 환자 번호를 싣는다", () => {
  /* 이력은 `GET /patients/{patient_id}/history` 로 부른다. 이 값이 없으면
     현황 탭이 그 환자를 가리킬 수가 없다. */
  const openapi = JSON.parse(
    fs.readFileSync(path.join(__dirname, "..", "..", "docs/api/openapi.json"), "utf8"),
  );
  const head = openapi.components.schemas.PatientHead;

  assert.ok(head.properties.patient_id, "PatientHead 에 환자 번호가 없다");
  assert.ok(head.required.includes("patient_id"), "있을 수도 없을 수도 있는 값이면 화면이 매번 확인해야 한다");
});

test("두 목업의 환자 번호가 갈리지 않는다", async () => {
  /* 안내문 목업은 번호를 제 안에 적어 두고, 환자 목록 목업은 제 줄에 갖고
     있다. **갈리면 `?mock=1` 에서만** 「전체 이력 보기」가 404 가 된다. */
  const api = load("api", "patients-api", "doctor-api");
  const roster = api.mockRoster();

  const charts = Object.keys(api.MOCK_GUIDE_PATIENTS).map(function (visitId) {
    return api.MOCK_GUIDE_PATIENTS[visitId].patient;
  });
  assert.ok(charts.length >= 3, "안내문 목업이 비었다 — 검사가 헛돈다");

  charts.forEach(function (patient) {
    const row = roster.filter(function (item) {
      return item.hospital_patient_no === patient.hospital_patient_no;
    })[0];
    assert.ok(row, `환자 목록 목업에 차트 ${patient.hospital_patient_no} 가 없다`);
    assert.equal(
      patient.patient_id,
      row.patient_id,
      `차트 ${patient.hospital_patient_no} 의 환자 번호가 두 목업에서 다르다`,
    );
  });
});

test("목업으로도 현황의 이력이 실제로 열린다", async () => {
  const api = load("api", "patients-api", "doctor-api");
  const guide = await api.doctorApi.guide(8801);

  const history = await api.patientsApi.history(guide.patient.patient_id, 3);

  assert.equal(history.hospital_patient_no, guide.patient.hospital_patient_no, "다른 환자의 이력이 왔다");
});
