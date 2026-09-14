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
  /* **실리는 파일에서 잰다.** 전에는 `js/guide.js` 를 통째로 vm 에 올렸는데,
     그 파일은 아무 화면도 안 싣는 고아였다 (KEY-281). `guide.html` 이 싣는
     것은 `patient_wireframe/js/guide.js` 이고, 거기 `takeGuideToken` 은 IIFE
     안에 있어 통째로는 못 올린다 — 그 함수와 그것이 쓰는 규칙(`link-token.js`)
     만 떼어 돌린다. 원문 대조가 아니라 **돌려 보는 것**을 지킨다. */
  const rule = read("js/link-token.js");
  const shipped = read("patient_wireframe/js/guide.js");
  const at = shipped.indexOf("function takeGuideToken()");
  assert.notStrictEqual(at, -1, "토큰을 떼어 내는 자리를 못 찾았다 — 검사가 헛돈다");
  const body = shipped.slice(at, shipped.indexOf("\n  }", at) + 4);

  const stored = new Map();
  const replaced = [];
  const context = vm.createContext({
    URLSearchParams,
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
  });
  vm.runInContext(rule + "\n" + body + "\nthis.takeGuideToken = takeGuideToken;", context);

  const token = context.takeGuideToken();

  assert.equal(token, "synthetic-key205-browser-token");
  assert.deepStrictEqual(replaced, ["/guide.html?mock=0"]);
  assert.equal(Array.from(stored.values()).includes(token), false, "링크 토큰을 sessionStorage에 남겼다");
});


test("KEY-307 안내문 확인 화면에서는 환자 링크를 발급하거나 관리하지 않는다", () => {
  const html = read("doctor.html");
  const source = read("js/doctor.js");

  assert.doesNotMatch(html, /patient-open|환자 링크 발급/);
  assert.doesNotMatch(
    source,
    /patient-open|patient-link-(?:copy|open|reissue|revoke)|issuePatientLink\(|reIssuePatientLink\(|revokePatientLink\(|patientLinkLoad\(|wirePatientLink\(/,
  );
  assert.match(source, /doctorApi[\s\S]*\.approve\(approvingId\)/);
  assert.match(source, /showPatientLink:\s*false/);
  assert.match(read("js/guide-view.js"), /showPatientLink === false \? "" : patientLinkBlockHtml/);
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

test("미승인·중복·권한 오류는 상태에 맞는 다음 행동을 안내한다", () => {
  const box = load("api", "session", "patients-api", "shell", "doctor-api", "doctor");

  assert.match(box.patientLinkSaying(new box.ApiError("GUIDE_NOT_APPROVED", 409, {})), /승인 완료/);
  assert.match(box.patientLinkSaying(new box.ApiError("LINK_ALREADY_ISSUED", 409, {})), /새 링크로 교체/);
  assert.match(box.patientLinkSaying(new box.ApiError("FORBIDDEN", 403, {})), /권한/);
});
