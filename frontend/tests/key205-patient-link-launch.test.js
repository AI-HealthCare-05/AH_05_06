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

test("환자 주소는 API path를 서버 로그에 남지 않는 fragment로 바꾼다", () => {
  const box = load("api", "session", "patients-api", "shell", "doctor-api", "doctor");
  const token = "synthetic-key205-browser-token";

  const url = box.patientGuideUrl({ path: "/api/v1/guides/" + token });

  assert.equal(url, "/guide.html?mock=1#t=" + token);
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

test("병원 화면은 토큰을 DOM·console·localStorage에 쓰지 않는다", () => {
  const doctor = read("js/doctor.js");
  const launch = doctor.slice(
    doctor.indexOf("function openPatientGuide"),
    doctor.indexOf("function returnModal", doctor.indexOf("function openPatientGuide")),
  );
  const urlFn = doctor.slice(
    doctor.indexOf("function patientGuideUrl"),
    doctor.indexOf("function patientLinkSaying"),
  );
  const html = read("doctor.html");

  assert.match(html, /id="patient-open"[^>]*hidden>개발용 환자 화면 열기<\/button>/);
  assert.doesNotMatch(launch, /console\.|localStorage|sessionStorage|innerHTML|textContent/);
  assert.doesNotMatch(urlFn, /console\.|localStorage|sessionStorage|innerHTML|textContent/);
  assert.match(launch, /if \(!popup\)[\s\S]*return;/);
  assert.ok(
    launch.indexOf("if (!popup)") < launch.indexOf("doctorApi") && launch.indexOf("doctorApi") < launch.indexOf("issuePatientLink"),
    "팝업 차단을 링크 발급 뒤에 판정해 일회용 링크를 소진한다",
  );
  assert.match(launch, /popup\.location\.replace\(url\)/);
  assert.doesNotMatch(launch, /window\.open\(url/);
  assert.match(launch, /if \(patientLinkOpening \|\|/);
});

test("클릭 가드에 걸려도 누른 버튼을 선행 비활성화해 고착시키지 않는다", () => {
  const doctor = read("js/doctor.js");
  const clickBranch = doctor.slice(
    doctor.indexOf('if (target.id === "patient-open"'),
    doctor.indexOf("var reason", doctor.indexOf('if (target.id === "patient-open"')),
  );

  assert.match(clickBranch, /openPatientGuide\(\)/);
  assert.doesNotMatch(clickBranch, /target\.disabled\s*=\s*true/);
});

test("미승인·중복·권한 오류는 재발급 없이 다음 행동만 안내한다", () => {
  const box = load("api", "session", "patients-api", "shell", "doctor-api", "doctor");

  assert.match(box.patientLinkSaying(new box.ApiError("GUIDE_NOT_APPROVED", 409, {})), /승인 완료/);
  assert.match(box.patientLinkSaying(new box.ApiError("LINK_ALREADY_ISSUED", 409, {})), /기존 환자 화면/);
  assert.match(box.patientLinkSaying(new box.ApiError("FORBIDDEN", 403, {})), /권한/);
});
