/* KEY-128 링크·OTP·세션 오류 복구 계약. */

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const JS_DIR = path.join(__dirname, "..", "js");

function loadApi() {
  const calls = [];
  const context = vm.createContext({
    URLSearchParams,
    location: { search: "" },
    sessionStorage: { getItem: () => null, setItem() {} },
    setTimeout,
    Promise,
    Math,
    Date,
    JSON,
    crypto,
    console,
    MOCK: false,
    request(pathname, options) {
      calls.push({ pathname, options });
      return Promise.resolve({ verified: true });
    },
  });
  vm.runInContext(fs.readFileSync(path.join(JS_DIR, "checkin-api.js"), "utf8"), context);
  return { context, calls };
}

function plain(value) {
  return JSON.parse(JSON.stringify(value));
}

function loadMockApi(caseName) {
  const values = new Map();
  const context = vm.createContext({
    URLSearchParams,
    location: { search: `?case=${caseName}` },
    sessionStorage: {
      getItem: (key) => (values.has(key) ? values.get(key) : null),
      setItem: (key, value) => values.set(key, String(value)),
    },
    setTimeout: (fn) => setTimeout(fn, 0),
    Promise,
    Math,
    Date,
    JSON,
    crypto,
    console,
    MOCK: true,
    ApiError: class ApiError extends Error {
      constructor(code, status, data) {
        super(code);
        this.code = code;
        this.status = status;
        this.data = data;
      }
    },
  });
  vm.runInContext(fs.readFileSync(path.join(JS_DIR, "checkin-api.js"), "utf8"), context);
  return context;
}

test("세션 만료는 작성값 유지와 OTP 재인증을 다음 행동으로 안내한다", () => {
  const { context } = loadApi();
  const guidance = plain(
    context.patientAuthGuidance({ code: "PATIENT_SESSION_EXPIRED", data: {} }),
  );

  assert.equal(guidance.kind, "session");
  assert.equal(guidance.action, "issue");
  assert.match(guidance.message, /작성한 답.*그대로/);
});

test("만료 링크와 폐기·교체 가능 링크는 우회 동작 없이 서로 다른 안전 문구를 쓴다", () => {
  const { context } = loadApi();
  const expired = plain(context.patientAuthGuidance({ code: "LINK_EXPIRED", data: {} }));
  const unavailable = plain(context.patientAuthGuidance({ code: "LINK_NOT_FOUND", data: {} }));

  assert.equal(expired.action, "latest-link");
  assert.match(expired.message, /3일/);
  assert.equal(unavailable.action, "latest-link");
  assert.match(unavailable.message, /폐기.*새 링크/);
  assert.doesNotMatch(JSON.stringify([expired, unavailable]), /synthetic-link|link_token|patient_session/);
});

test("OTP 실패 횟수와 잠금 시간을 숨기지 않고 다음 행동을 구분한다", () => {
  const { context } = loadApi();
  const invalid = plain(
    context.patientAuthGuidance({ code: "OTP_INVALID", data: { remaining_attempts: 2 } }),
  );
  const locked = plain(
    context.patientAuthGuidance({ code: "OTP_LOCKED", data: { retry_after_seconds: 599 } }),
  );

  assert.equal(invalid.action, "verify");
  assert.match(invalid.message, /2번 더/);
  assert.equal(locked.action, "wait");
  assert.equal(locked.retryAfterSeconds, 599);
  assert.match(locked.message, /10분/);
});

test("만료·사용 완료 OTP는 이전 번호 재사용 대신 새 발급으로만 복구한다", () => {
  const { context } = loadApi();
  for (const code of ["OTP_EXPIRED", "OTP_ALREADY_USED", "OTP_NOT_ISSUED"]) {
    const guidance = plain(context.patientAuthGuidance({ code, data: {} }));
    assert.equal(guidance.action, "issue", `${code}가 새 발급으로 이어지지 않는다`);
  }
});

test("OTP API는 링크와 코드를 정해진 본문에만 싣고 URL에는 넣지 않는다", async () => {
  const { context, calls } = loadApi();

  await context.checkinApi.issueOtp("synthetic link token");
  await context.checkinApi.verifyOtp("synthetic link token", "123456");

  assert.deepEqual(plain(calls), [
    {
      pathname: "/patient-auth/otp/issue",
      options: { method: "POST", body: { link_token: "synthetic link token" } },
    },
    {
      pathname: "/patient-auth/otp/verify",
      options: { method: "POST", body: { link_token: "synthetic link token", code: "123456" } },
    },
  ]);
  assert.ok(calls.every((call) => !call.pathname.includes("synthetic") && !call.pathname.includes("123456")));
});

test("새로고침 때 인증 성공을 브라우저 저장소에서 추측하지 않고 서버 응답을 다시 확인한다", () => {
  const source = fs.readFileSync(path.join(JS_DIR, "checkin.js"), "utf8");

  assert.match(source, /checkinApi\s*\.read\(token\)/, "진입 때 서버의 링크 상태를 다시 확인하지 않는다");
  assert.doesNotMatch(
    source,
    /(?:localStorage|sessionStorage)\.setItem\([^\n]*(?:auth|session|otp)/i,
    "인증 성공을 화면 저장소에 남겨 서버 세션과 어긋날 수 있다",
  );
  assert.match(source, /pendingAnswer = answer;[\s\S]*renderAuthGuidance\(error\)/);
  assert.match(source, /if \(answer\) submitAnswer\(answer\)/, "재인증 뒤 보존한 답을 저장하지 않는다");
});

test("OTP 입력은 원문을 화면에 다시 출력하지 않고 숫자 6자리에서만 확인할 수 있다", () => {
  const source = fs.readFileSync(path.join(JS_DIR, "checkin.js"), "utf8");

  assert.match(source, /autocomplete=\"one-time-code\"/);
  assert.match(source, /maxlength=\"6\"/);
  assert.ok(source.includes('/^\\d{6}$/.test(code)'), "숫자 6자리 형식을 확인하지 않는다");
  assert.doesNotMatch(source, /textContent\s*=\s*code|innerHTML\s*=\s*code/);
  assert.doesNotMatch(source, /auth-recovery[^>]*aria-live/, "바깥 상태 영역과 중첩 낭독된다");
});

test("링크→OTP→세션 복구 뒤 같은 D+7 답을 저장하는 합성 흐름이 완주한다", async () => {
  const context = loadMockApi("session-expired");
  const answer = { medication: "taking", pain: null };

  await assert.rejects(context.checkinApi.save("synthetic-token", answer), (error) => {
    assert.equal(error.code, "PATIENT_SESSION_EXPIRED");
    return true;
  });
  const issued = await context.checkinApi.issueOtp("synthetic-token");
  assert.equal(issued.retry_after_seconds, 60);
  await assert.rejects(context.checkinApi.verifyOtp("synthetic-token", "000000"), (error) => {
    assert.equal(error.code, "OTP_INVALID");
    assert.equal(error.data.remaining_attempts, 4);
    return true;
  });
  await context.checkinApi.verifyOtp("synthetic-token", "123456");
  const saved = await context.checkinApi.save("synthetic-token", answer);
  assert.equal(saved.saved, true);
  assert.equal(saved.medication, "taking");
});
