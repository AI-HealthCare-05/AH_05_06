/* 병원 승인 화면에서 환자 안내 화면까지 토큰을 노출하지 않고 잇는다 — KEY-205. */
const { test } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { load } = require("./browser-shim.js");

const FRONTEND = path.join(__dirname, "..");

function read(relative) {
  return fs.readFileSync(path.join(FRONTEND, relative), "utf8");
}

test("링크 발급은 동결된 POST 경로를 그대로 쓴다", async () => {
  const box = load("api", "doctor-api");
  const calls = [];
  box.mockDoctorRequest = function (requestPath, options) {
    calls.push({ path: requestPath, method: options.method });
    return Promise.resolve({ path: "/api/v1/guides/demo-key205-link", demo_only: true });
  };

  await box.doctorApi.issuePatientLink(205);

  assert.deepStrictEqual(calls, [{ path: "/visits/205/guide/link", method: "POST" }]);
});

test("목업도 승인 완료 건 한 번만 발급하고 중복은 안전하게 막는다", async () => {
  const box = load("api", "doctor-api");
  box.DOCTOR_CASE = "approved";

  const issued = await box.doctorApi.issuePatientLink(8801);
  assert.equal(issued.demo_only, true);
  assert.match(issued.path, /^\/api\/v1\/guides\/[A-Za-z0-9_-]+$/);
  const reloaded = await box.doctorApi.guide(8801);
  assert.ok(reloaded.approved_at, "링크 발급 뒤 승인 시각이 사라졌다");
  assert.ok(reloaded.scheduled_at, "링크 발급 뒤 예약 시각이 사라졌다");
  await assert.rejects(
    box.doctorApi.issuePatientLink(8801),
    (error) => error.code === "LINK_ALREADY_ISSUED" && error.status === 409,
  );
});

test("환자 주소는 API path를 본인 확인 화면의 fragment로 바꾼다", () => {
  /* `doctor.js` 없이도 선다 — 규칙이 `doctor-api.js` 로 옮겨졌기 때문이다
     (KEY-275). 스탭 화면이 그 파일까지만 싣는다. */
  const box = load("api", "session", "patients-api", "shell", "doctor-api");
  const token = "synthetic-key205-browser-token";

  const url = box.patientGuideUrl({ path: "/api/v1/guides/" + token });

  assert.equal(url, "/patient_wireframe/html/otp.html?mock=1#t=" + token);
  assert.throws(() => box.patientGuideUrl({ path: "https://outside.invalid/steal" }), /invalid patient guide link response/);
});

test("환자 화면은 fragment 토큰을 메모리로 옮긴 직후 주소에서 지운다", () => {
  const stored = new Map();
  const replaced = [];
  const context = vm.createContext({
    URLSearchParams,
    Promise,
    setTimeout,
    clearTimeout,
    sessionStorage: {
      getItem: (key) => (stored.has(key) ? stored.get(key) : null),
      setItem: (key, value) => stored.set(key, String(value)),
    },
    window: {
      location: {
        search: "?mock=0",
        hash: "#t=synthetic-key205-browser-token",
        pathname: "/guide.html",
      },
      history: { replaceState: (_state, _title, url) => replaced.push(url) },
    },
    document: { addEventListener() {} },
  });
  vm.runInContext(read("js/guide-api.js"), context);
  vm.runInContext(read("js/guide.js"), context);

  const token = context.takeGuideToken();

  assert.equal(token, "synthetic-key205-browser-token");
  assert.deepStrictEqual(replaced, ["/guide.html?mock=0"]);
  assert.equal(Array.from(stored.values()).includes(token), false, "링크 토큰을 sessionStorage에 남겼다");
});

test("병원 화면은 토큰을 DOM·console·브라우저 저장소에 쓰지 않는다", () => {
  const doctor = read("js/doctor.js");
  const launch = doctor.slice(
    doctor.indexOf("function openPatientGuide"),
    doctor.indexOf("function returnModal", doctor.indexOf("function openPatientGuide")),
  );
  /* **`doctor-api.js` 로 옮겼다** — KEY-275. 스탭 화면이 `doctor.js` 를 안
     싣는데 링크 블록이 그 화면에도 서기 때문이다.

     여기를 안 옮기면 `indexOf` 가 둘 다 `-1` 이라 슬라이스가 **빈 문자열**이
     되고, 아래 `doesNotMatch` 넷이 빈 문자열을 검사하며 **조용히 통과**한다 —
     토큰 유출을 막는 자리가 아무것도 안 막게 된다. */
  const api = read("js/doctor-api.js");
  const urlFn = api.slice(api.indexOf("function patientGuideUrl"), api.indexOf("var PATIENT_LINK_SAYINGS"));
  assert.ok(urlFn.length > 100, "규칙 함수를 못 찾았다 — 빈 문자열을 검사하고 있다");
  assert.ok(launch.length > 100, "발급 흐름을 못 찾았다 — 빈 문자열을 검사하고 있다");
  const html = read("doctor.html");

  assert.match(html, /id="patient-open"[^>]*hidden>환자 링크 발급<\/button>/);
  assert.doesNotMatch(launch, /console\.|localStorage|sessionStorage|innerHTML|textContent/);
  assert.doesNotMatch(urlFn, /console\.|localStorage|sessionStorage|innerHTML|textContent/);
  assert.match(launch, /patientLinkModal\(result/);
  assert.doesNotMatch(launch, /window\.open|popup/);
  assert.match(launch, /if \(patientLinkOpening \|\|/);
});

test("병원 링크 관리 API는 발급·교체·폐기 경로를 구분한다", async () => {
  const box = load("api", "doctor-api");
  const calls = [];
  box.mockDoctorRequest = function (requestPath, options) {
    calls.push({ path: requestPath, method: options.method });
    return Promise.resolve({});
  };

  await box.doctorApi.issuePatientLink(223);
  await box.doctorApi.reIssuePatientLink(223);
  await box.doctorApi.revokePatientLink(223);

  assert.deepStrictEqual(calls, [
    { path: "/visits/223/guide/link", method: "POST" },
    { path: "/visits/223/guide/link/re-issue", method: "POST" },
    { path: "/visits/223/guide/link", method: "DELETE" },
  ]);
});

test("발급 모달은 원문 링크를 HTML에 넣지 않고 메모리 복사·열기만 제공한다", () => {
  const source = read("js/doctor.js");
  const modal = source.slice(source.indexOf("function patientLinkModal"), source.indexOf("function openPatientGuide"));
  const events = source.slice(
    source.indexOf('if (target.id === "patient-link-open"'),
    source.indexOf('var reason = target.closest("[data-reason]")'),
  );

  assert.doesNotMatch(modal, /patientLinkUrl[^\n]*\+|innerHTML|localStorage|sessionStorage/);
  assert.match(events, /new URL\(patientLinkUrl, window\.location\.href\)[\s\S]*copyPatientLink\(navigator\.clipboard, copyUrl\)/);
  assert.match(events, /window\.open\(patientLinkUrl, "_blank", "noopener"\)/);
  assert.match(events, /reIssuePatientLink/);
  assert.match(events, /revokePatientLink/);
});

test("다른 환자로 전환된 뒤 도착한 링크 응답은 현재 화면에 표시하지 않는다", () => {
  const box = load("api", "session", "patients-api", "shell", "doctor-api", "doctor");

  assert.equal(box.isCurrentPatientLinkRequest({ visit_id: 223 }, 223, 8, 8), true);
  assert.equal(box.isCurrentPatientLinkRequest({ visit_id: 224 }, 223, 9, 8), false);
  assert.equal(box.isCurrentPatientLinkRequest({ visit_id: 223 }, 223, 9, 8), false);

  const source = read("js/doctor.js");
  const launch = source.slice(source.indexOf("function openPatientGuide"), source.indexOf("function returnModal"));
  assert.match(launch, /isCurrentPatientLinkRequest[\s\S]*openModal\(patientLinkModal/);
});

test("복사하거나 열지 않은 일회용 링크는 확인 없이 닫히지 않는다", () => {
  const box = load("api", "session", "patients-api", "shell", "doctor-api", "doctor");
  let confirmations = 0;
  const reject = () => {
    confirmations += 1;
    return false;
  };

  assert.equal(box.canDiscardPatientLink("/one-time", false, reject), false);
  assert.equal(confirmations, 1);
  assert.equal(box.canDiscardPatientLink("/one-time", true, reject), true);
  assert.equal(box.canDiscardPatientLink(null, false, reject), true);
  assert.equal(confirmations, 1);
});

test("clipboard API가 없거나 동기로 실패해도 복사 실패 Promise로 처리한다", async () => {
  const box = load("api", "session", "patients-api", "shell", "doctor-api", "doctor");

  await assert.rejects(box.copyPatientLink(undefined, "http://test/link"), /clipboard unavailable/);
  await assert.rejects(
    box.copyPatientLink({ writeText() { throw new Error("denied"); } }, "http://test/link"),
    /denied/,
  );
});

test("교체·폐기 응답은 시작한 모달이 닫힌 뒤 다시 모달을 열지 않는다", () => {
  const source = read("js/doctor.js");
  const events = source.slice(
    source.indexOf('if (target.id === "patient-link-reissue"'),
    source.indexOf('var reason = target.closest("[data-reason]")'),
  );

  assert.match(events, /reissuingModalSeq = patientLinkModalSeq/);
  assert.match(events, /patientLinkModalSeq === reissuingModalSeq/);
  assert.match(events, /revokingModalSeq = patientLinkModalSeq/);
  assert.match(events, /patientLinkModalSeq !== revokingModalSeq/);
});

test("클릭 가드에 걸려도 누른 버튼을 선행 비활성화해 고착시키지 않는다", () => {
  const doctor = read("js/doctor.js");
  const clickBranch = doctor.slice(
    doctor.indexOf('if (target.id === "patient-open"'),
    doctor.indexOf('if (target.id === "patient-link-open"', doctor.indexOf('if (target.id === "patient-open"')),
  );

  assert.match(clickBranch, /openPatientGuide\(\)/);
  assert.doesNotMatch(clickBranch, /target\.disabled\s*=\s*true/);
});

test("미승인·중복·권한 오류는 상태에 맞는 다음 행동을 안내한다", () => {
  const box = load("api", "session", "patients-api", "shell", "doctor-api", "doctor");

  assert.match(box.patientLinkSaying(new box.ApiError("GUIDE_NOT_APPROVED", 409, {})), /승인 완료/);
  assert.match(box.patientLinkSaying(new box.ApiError("LINK_ALREADY_ISSUED", 409, {})), /새 링크로 교체/);
  assert.match(box.patientLinkSaying(new box.ApiError("FORBIDDEN", 403, {})), /권한/);
});
