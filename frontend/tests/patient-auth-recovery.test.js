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
  assert.match(guidance.message, /새로고침.*다시 입력/);
});

test("화면 복구 상태는 세션 만료 답을 재전송하고 죽은 링크에서는 즉시 버린다", () => {
  const { context } = loadApi();
  const recovery = context.createPatientAuthRecovery();
  const answer = plain({ medication: "uncomfortable", pain: { had: true, score: 4 }, note: "합성 메모" });
  let retried = null;

  assert.equal(recovery.onSaveFailed({ code: "PATIENT_SESSION_EXPIRED" }, answer), "reauth");
  assert.equal(
    recovery.retryAfterVerification((saved) => {
      retried = plain(saved);
    }),
    true,
  );
  assert.deepEqual(retried, answer, "재인증 뒤 같은 작성값을 다시 저장하지 않는다");

  recovery.complete();
  assert.equal(
    recovery.retryAfterVerification(() => assert.fail("이미 저장한 답을 또 보내면 안 된다")),
    false,
  );

  recovery.onSaveFailed({ code: "PATIENT_SESSION_EXPIRED" }, answer);
  assert.equal(recovery.onSaveFailed({ code: "LINK_EXPIRED" }, answer), "link-closed");
  assert.equal(recovery.retryAfterVerification(() => assert.fail("죽은 링크의 답을 다시 보내면 안 된다")), false);
});

test("만료 링크와 폐기·교체 가능 링크는 우회 동작 없이 서로 다른 안전 문구를 쓴다", () => {
  const { context } = loadApi();
  const apiSource = fs.readFileSync(path.join(JS_DIR, "checkin-api.js"), "utf8");
  const expired = plain(context.patientAuthGuidance({ code: "LINK_EXPIRED", data: {} }));
  const unavailable = plain(context.patientAuthGuidance({ code: "LINK_NOT_FOUND", data: {} }));

  assert.equal(expired.action, "latest-link");
  assert.match(expired.message, /3일/);
  assert.equal(unavailable.action, "latest-link");
  assert.match(unavailable.message, /폐기.*새 링크/);
  for (const code of ["LINK_EXPIRED", "LINK_NOT_FOUND", "LINK_REVOKED", "LINK_REISSUED"]) {
    assert.equal(context.isPatientLinkClosed({ code }), true, `${code}를 닫힌 링크로 분류하지 않는다`);
  }
  assert.equal(apiSource.match(/LINK_REVOKED/g)?.length, 1, "닫힌 링크 코드 목록을 여러 곳에 복제한다");
  assert.equal(apiSource.match(/LINK_REISSUED/g)?.length, 1, "닫힌 링크 코드 목록을 여러 곳에 복제한다");
  assert.doesNotMatch(JSON.stringify([expired, unavailable]), /synthetic-link|link_token|patient_session/);
});

test("재인증 중 링크가 닫히면 보류 답을 지우고 OTP 오류는 답을 유지한다", () => {
  const { context } = loadApi();
  const recovery = context.createPatientAuthRecovery();
  const answer = plain({ medication: "taking", pain: null });

  recovery.onSaveFailed({ code: "PATIENT_SESSION_EXPIRED" }, answer);
  assert.equal(recovery.discardIfLinkClosed({ code: "OTP_INVALID" }), false);
  assert.equal(recovery.retryAfterVerification(() => {}), true, "일반 OTP 오류에서 보류 답을 지운다");

  recovery.onSaveFailed({ code: "PATIENT_SESSION_EXPIRED" }, answer);
  assert.equal(recovery.discardIfLinkClosed({ code: "LINK_REISSUED" }), true);
  assert.equal(recovery.retryAfterVerification(() => assert.fail("닫힌 링크의 답을 다시 보내면 안 된다")), false);
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

  const unknownWait = plain(context.patientAuthGuidance({ code: "OTP_LOCKED", data: {} }));
  assert.equal(unknownWait.action, "retry", "남은 잠금 시간이 없는데 환자를 비활성 버튼에 가둔다");
  assert.match(unknownWait.message, /다시 눌러.*확인/);
});

test("저장 실패는 검증·중복·알 수 없는 원인을 인터넷 장애로 오인하지 않는다", () => {
  const { context } = loadApi();

  assert.match(context.patientCheckinSaveFailureMessage({ code: "INVALID_REQUEST" }), /입력한 내용/);
  assert.match(context.patientCheckinSaveFailureMessage({ code: "CHECKIN_ALREADY_ANSWERED" }), /이미 저장/);
  const unknown = context.patientCheckinSaveFailureMessage({ code: "FUTURE_ERROR" });
  assert.match(unknown, /잠시 뒤.*병원/);
  assert.doesNotMatch(unknown, /인터넷/);
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
  assert.match(source, /authRecovery\.onSaveFailed\(error, answer\)/, "화면이 검증된 복구 상태 전이를 사용하지 않는다");
  assert.match(
    source,
    /authRecovery\.retryAfterVerification\(submitAnswer\)/,
    "재인증 뒤 보존한 답을 저장하지 않는다",
  );
  assert.match(
    source,
    /\.save\(token, answer\)\s*\.then\(function \(result\) \{\s*authRecovery\.complete\(\);/,
    "저장 성공 블록에서 보류 답을 비우지 않는다",
  );
  assert.equal(
    source.match(/authRecovery\.complete\(\)/g)?.length,
    1,
    "저장 성공 외의 갈래에서 보류 답을 지우면 안 된다",
  );
  assert.equal(
    source.match(/authRecovery\.discardIfLinkClosed\(error\)/g)?.length,
    2,
    "OTP 발급·검증 중 닫힌 링크의 보류 답을 모두 폐기하지 않는다",
  );
  assert.match(source, /if \(isPatientLinkClosed\(error\)\)/, "초기 조회가 공통 닫힌 링크 분류를 사용하지 않는다");
});

test("KEY-178 초기 조회에서 세션 만료를 받으면 오류 대신 OTP 화면으로 보낸다", () => {
  const source = fs.readFileSync(path.join(JS_DIR, "checkin.js"), "utf8");

  assert.match(source, /function otpEntryUrl\(\)/, "checkin.js에 OTP 진입 주소 헬퍼가 없다");
  assert.match(source, /"\/patient_wireframe\/html\/otp\.html"/, "OTP 화면 경로가 guide.js와 다르다");
  assert.match(
    source,
    /error && error\.code === "PATIENT_SESSION_EXPIRED"[\s\S]{0,80}location\.replace\(otpEntryUrl\(\)\)/,
    "세션 만료를 받아도 OTP 화면으로 보내지 않는다",
  );
  assert.match(
    source,
    /new URLSearchParams\(String\(location\.hash \|\| ""\)\.replace\(\/\^#\/, ""\)\)\.get\("t"\)/,
    "토큰을 fragment(#t=)에서 먼저 읽지 않는다 (KEY-267)",
  );
});

test("정상 저장은 라이브 상태를 두 번 읽지 않고 버튼에서 진행 상태를 알린다", () => {
  const source = fs.readFileSync(path.join(JS_DIR, "checkin.js"), "utf8");

  assert.doesNotMatch(source, /showOnly\(authCard\("기록을 저장하고 있어요"/);
  assert.match(source, /el\("save"\)\.textContent = "저장 중…"/);
  assert.match(source, /el\("save"\)\.textContent = "저장"/);
});

test("잠금 프리뷰와 잠금 해제 안내는 실제 복구 흐름으로 이어진다", async () => {
  const locked = loadMockApi("locked");
  const answer = { medication: "taking", pain: null };

  await assert.rejects(locked.checkinApi.save("synthetic-token", answer), (error) => {
    assert.equal(error.code, "PATIENT_SESSION_EXPIRED");
    return true;
  });
  await assert.rejects(locked.checkinApi.issueOtp("synthetic-token"), (error) => {
    assert.equal(error.code, "OTP_LOCKED");
    assert.equal(error.data.retry_after_seconds, 600);
    return true;
  });

  const noRetry = loadMockApi("locked-no-retry");
  await assert.rejects(noRetry.checkinApi.issueOtp("synthetic-token"), (error) => {
    assert.equal(error.code, "OTP_LOCKED");
    assert.equal(error.data.retry_after_seconds, undefined);
    return true;
  });

  const source = fs.readFileSync(path.join(JS_DIR, "checkin.js"), "utf8");
  assert.match(source, /MOCK && CHECKIN_CASE \? "synthetic-link-token"/);
  assert.match(source, /renderAuthGuidance\(\{ code: "OTP_NOT_ISSUED", data: \{\} \}\)/);
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
