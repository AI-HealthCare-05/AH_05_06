/* 링크 블록이 **서버에 붙었다** — KEY-275 연결 단계.
 *
 * 목업 단계에서는 블록이 늘 「아직 없음」이었다. 상태를 물을 길이 없었기
 * 때문이다(`GuideResponse` 에도 없고 조회 API 도 없었다).
 *
 * 여기서 재는 것은 **화면 둘이 같은 상태를 본다**는 것이다. 화면은 상태를
 * 저장하지 않고 서버에 다시 묻는다 — 그래서 한쪽에서 새로 만들면 다른 쪽도
 * 새 만료일을 읽는다(인수조건 ①).
 *
 * 그리는 것은 여기서 안 잰다. `load()` 로 불러서 **상태만 보고** 판정할 수
 * 있는 것만 담는다(`docs/qa/frontend-manual-browser-check.md` 의 첫 물음).
 */
const { test } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const { load } = require("./browser-shim.js");
const { codeOnly } = require("./source.js");

const ROOT = path.join(__dirname, "..");
const read = (f) => codeOnly(fs.readFileSync(path.join(ROOT, f), "utf8"));

test("상태를 묻는 길이 GET 하나다 — 발급(POST)과 같은 주소를 method 로 가른다", async () => {
  const box = load("api", "doctor-api");
  const calls = [];
  box.mockDoctorRequest = function (requestPath, options) {
    calls.push({ path: requestPath, method: options.method });
    return Promise.resolve({});
  };

  await box.doctorApi.readPatientLink(4242);

  assert.deepEqual(calls, [{ path: "/visits/4242/guide/link", method: "GET" }]);
});

test("목업이 서버와 같은 답을 한다 — 없음 · 발급 · 폐기", async () => {
  const box = load("api", "doctor-api");
  box.DOCTOR_CASE = "approved"; // 목업의 승인 완료 갈래 — `key205` 검사와 같은 손잡이
  const visitId = 8801;

  /* **없는 것은 오류가 아니다.** 목업이 404 를 주면 화면은 오류를 정상으로
     삼키는 갈래를 갖게 되고, 그 갈래가 진짜 오류까지 삼킨다. */
  const before = await box.doctorApi.readPatientLink(visitId);
  assert.deepEqual(before, { issued: false, expires_at: null }, "발급 전인데 오류이거나 있다고 답했다");

  const issued = await box.doctorApi.issuePatientLink(visitId);
  const live = await box.doctorApi.readPatientLink(visitId);
  assert.equal(live.issued, true);
  assert.equal(live.expires_at, issued.expires_at, "발급 답과 상태 답의 만료가 다르다");

  /* 폐기는 행을 지우지 않고 만료를 지금으로 당긴다 — 서버가 하는 그대로.
     「없음」으로 돌아가면 화면에서 [새 링크] 가 사라진다. */
  await box.doctorApi.revokePatientLink(visitId);
  const dead = await box.doctorApi.readPatientLink(visitId);
  assert.equal(dead.issued, true, "폐기를 「아직 없음」으로 답하면 되돌릴 길이 화면에서 사라진다");
  assert.ok(new Date(dead.expires_at).getTime() <= Date.now());
});

test("목업의 만료가 **박힌 날짜가 아니다** — 그 날이 지나면 태어나자마자 기한 지남", async () => {
  const box = load("api", "doctor-api");
  box.DOCTOR_CASE = "approved"; // 목업의 승인 완료 갈래 — `key205` 검사와 같은 손잡이
  const visitId = 8801;

  const issued = await box.doctorApi.issuePatientLink(visitId);
  const left = new Date(issued.expires_at).getTime() - Date.now();

  assert.ok(left > 0, "목업이 만든 링크가 이미 만료돼 있다");
  /* 서버의 `LINK_TTL` 은 168 시간이다(KEY-223). 목업이 더 짧으면 `?mock=1` 로
     본 화면이 실제와 다른 날짜를 말한다. */
  assert.ok(left > 160 * 3600000, "목업 수명이 서버(168시간)보다 짧다");
});

test("재발급하면 상태 조회도 새 만료일을 준다 — 두 화면이 맞는 까닭", async () => {
  const box = load("api", "doctor-api");
  box.DOCTOR_CASE = "approved"; // 목업의 승인 완료 갈래 — `key205` 검사와 같은 손잡이
  const visitId = 8801;

  await box.doctorApi.issuePatientLink(visitId);
  await box.doctorApi.revokePatientLink(visitId);
  const closed = await box.doctorApi.readPatientLink(visitId);

  const again = await box.doctorApi.reIssuePatientLink(visitId);
  const reopened = await box.doctorApi.readPatientLink(visitId);

  assert.notEqual(reopened.expires_at, closed.expires_at, "재발급했는데 다른 화면은 옛 만료일을 읽는다");
  assert.equal(reopened.expires_at, again.expires_at);
});

test("재발급 응답에서 주소를 꺼내 쥔다 — 그 응답 말고는 나올 데가 없다", () => {
  const box = load("api", "session", "patients-api", "shell", "doctor-api", "patient-link-view");
  const token = "synthetic-key275-token";

  const held = box.patientLinkFromIssue({ path: "/api/v1/guides/" + token, expires_at: "2026-09-14T18:00:00+09:00" });

  assert.equal(held.fresh, true);
  assert.equal(held.expiresAt, "2026-09-14T18:00:00+09:00");
  assert.ok(held.url.indexOf("#t=" + token) !== -1, "본인 확인 화면의 fragment 로 안 옮겼다");
});

test("문자 설정 재료가 링크 둘을 통과시킨다 — 안 흘리면 블록이 늘 「아직 없음」", () => {
  const box = load("api", "sms-plan", "guide-view");

  const plan = box.smsStateNow({ guideStatus: "SCHEDULED_TO_SEND", link: { expiresAt: "2026-09-14T18:00:00+09:00" } });

  assert.equal(plan.guideStatus, "SCHEDULED_TO_SEND");
  assert.equal(plan.link.expiresAt, "2026-09-14T18:00:00+09:00");
});

test("링크 관리 화면만 상태를 읽고 배선한다", () => {
  for (const screen of ["visit-guide.js"]) {
    const source = read("js/" + screen);
    assert.ok(source.includes("patientLinkLoad"), `${screen} 이 링크 상태를 안 읽는다`);
    assert.ok(source.includes("wirePatientLink"), `${screen} 이 블록 단추를 안 건다 — 눌러도 아무 일 없다`);
    assert.ok(source.includes("patientLinkForget"), `${screen} 이 환자를 옮길 때 앞 사람 주소를 안 놓는다`);
    assert.ok(source.includes("patientLinkOf"), `${screen} 이 쥔 링크를 블록에 안 넘긴다`);
  }
});

test("**읽는 배선은 한 벌이다** — 두 화면이 각자 부르면 한쪽만 고쳐진다", () => {
  /* 이 배선이 두 화면에 거의 그대로 두 번 있었다 (이희진 님 `#250` 리뷰 ⑤).
     `patient-link-view.js` 가 정확히 그 중복을 막으려고 있는 파일인데 로드만
     빠져 있었다. 부르는 자리를 여기 한 곳으로 못 박는다. */
  assert.ok(read("js/patient-link-view.js").includes("readPatientLink"), "공용 모듈이 상태를 안 읽는다");
  for (const screen of ["visit-guide.js", "doctor.js"]) {
    assert.ok(
      !read("js/" + screen).includes("readPatientLink"),
      `${screen} 이 아직 제 손으로 읽는다 — 규칙이 두 벌이 된다`,
    );
  }
});

test("읽다 막힌 것을 「아직 없음」으로 삼키지 않는다 — 이희진 님 `#250` 리뷰 ④", () => {
  /* 두 `.catch` 가 인자조차 안 받고 통째로 삼켰다. 서버는 「없다」(200 ·
     issued:false)와 「못 준다」(403 · 404 · 연결 실패)를 갈라 놓았는데 화면이
     둘을 같은 그림으로 뭉갰다 — 권한이 없어 못 읽은 것도 「아직 발급 안 함」
     으로 보였다. */
  const src = read("js/patient-link-view.js");
  const at = src.indexOf("function patientLinkLoad");
  assert.notEqual(at, -1, "공용 로더가 없다");
  const body = src.slice(at, src.indexOf("\n}", at));

  assert.match(body, /\.catch\(function \(error\)/, "오류를 받지도 않는다");
  assert.match(body, /say\(patientLinkSaying\(error\)\)/, "못 읽은 것을 말하지 않는다");
});

test("문자 설정의 만료 안내가 실제 수명과 같다 — 같은 화면에서 어긋나면 안 된다", () => {
  /* `LINK_TTL` 이 168 시간(7일)으로 올랐다(KEY-223). 블록이 실제 만료일을
     띄우는데 옆줄이 「3일」이라고 하면 스탭이 한 화면에서 두 값을 본다. */
  assert.ok(read("js/guide-view.js").includes("(7일 만료)"), "미리보기 안내가 아직 3일이라고 한다");
  assert.ok(read("js/sms-template-rules.js").includes("만료는 발송 후 7일"), "문구 규칙이 아직 3일이라고 한다");
});
