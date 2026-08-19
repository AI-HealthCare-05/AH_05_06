/* API 호출 한 겹 — KEY-22
 *
 * 계약은 docs/auth-contract.md 4·5절을 따른다.
 *   POST /api/v1/auth/login     { login_id, password, remember }
 *   GET  /api/v1/auth/me
 *   POST /api/v1/auth/logout
 *   POST /api/v1/auth/password  { current_password, new_password }
 *
 * 서버는 아직 이 넷을 갖고 있지 않다(지금은 email 로그인뿐이다).
 * 계약대로 짜 두고, 서버가 붙기 전까지는 아래 목업으로 화면을 확인한다.
 */

var API_BASE = "/api/v1";

/* 서버가 코드로 구분해 준다. 화면 문구가 코드마다 다르기 때문이다.
 * 특히 「인증정보가 틀렸다」와 「세션이 만료됐다」는 둘 다 401이지만
 * 사용자가 해야 할 일이 다르다 — 다시 입력할 것인가, 다시 로그인할 것인가. */
var ERROR = {
  INVALID_CREDENTIALS: "invalid_credentials",
  ACCOUNT_LOCKED: "account_locked",
  TOKEN_EXPIRED: "token_expired",
  PASSWORD_CHANGE_REQUIRED: "password_change_required",
};

function ApiError(code, status, data) {
  this.name = "ApiError";
  this.code = code;
  this.status = status;
  this.data = data || {};
}
ApiError.prototype = Object.create(Error.prototype);

/* 목업 — 개발 중에만 쓴다.
 * 주소에 ?mock=1 을 붙이면 켜지고, 한 번 켜면 그 탭에서 유지된다.
 * 서버가 붙으면 ?mock=0 으로 끄거나 이 파일에서 지운다. */
var MOCK = (function () {
  var q = new URLSearchParams(location.search).get("mock");
  if (q !== null) sessionStorage.setItem("useMock", q === "1" ? "1" : "0");
  return sessionStorage.getItem("useMock") === "1";
})();

function request(path, options) {
  options = options || {};
  if (MOCK) return mockRequest(path, options);

  var headers = { Accept: "application/json" };
  if (options.body) headers["Content-Type"] = "application/json";
  var token = options.token;
  if (token) headers["Authorization"] = "Bearer " + token;

  return fetch(API_BASE + path, {
    method: options.method || "GET",
    headers: headers,
    body: options.body ? JSON.stringify(options.body) : undefined,
  }).then(function (res) {
    return res
      .json()
      .catch(function () {
        return {};
      })
      .then(function (data) {
        if (res.ok) return data;
        throw new ApiError(data.code || data.detail || "unknown", res.status, data);
      });
  });
}

var api = {
  login: function (loginId, password, remember) {
    return request("/auth/login", {
      method: "POST",
      body: { login_id: loginId, password: password, remember: !!remember },
    });
  },
  me: function (token) {
    return request("/auth/me", { token: token });
  },
  logout: function (token) {
    return request("/auth/logout", { method: "POST", token: token });
  },
  changePassword: function (token, currentPassword, newPassword) {
    return request("/auth/password", {
      method: "POST",
      token: token,
      body: { current_password: currentPassword, new_password: newPassword },
    });
  },
};

/* ── 목업 ──────────────────────────────────────────────────────
 * 계정은 docs/data/synthetic-staff.csv 를 따른다. 비밀번호는 아무거나 통하되
 * "wrong" 으로 시작하면 실패한다 — L-2 와 잠금을 눈으로 보려는 것이다.
 * 실패 횟수는 서버와 같은 규칙으로 센다: 계정이 아니라 입력된 아이디 문자열에 붙인다.
 * (없는 아이디에서 횟수가 안 오르면 그 사실이 「없는 아이디」라는 답이 된다) */
var MOCK_STAFF = {
  staff01: { name: "한소영", roles: ["staff"], must_change_password: false },
  doctor01: { name: "박연", roles: ["doctor"], must_change_password: false },
  adminstaff01: { name: "서지원", roles: ["staff", "admin"], must_change_password: false },
  newbie01: { name: "임채운", roles: ["staff"], must_change_password: true },
  left01: { name: "문가람", roles: ["staff"], status: "left" },
};
var MOCK_MAX_FAILURES = 5;
var MOCK_LOCK_SECONDS = 600;

/* 실패 횟수는 서버와 같은 규칙으로 10분 뒤 저절로 풀린다.
   만료가 없으면 개발 중에 한 번 잠근 아이디를 그 탭에서 영영 못 쓰고,
   「왜 로그인이 안 되지」로 시간을 쓴다. */
function mockFailures(loginId, bump) {
  var key = "mockFail:" + loginId;
  var saved = JSON.parse(sessionStorage.getItem(key) || "null");
  var now = Date.now();
  if (saved && now - saved.at > MOCK_LOCK_SECONDS * 1000) saved = null;
  var n = saved ? saved.n : 0;
  if (bump) sessionStorage.setItem(key, JSON.stringify({ n: ++n, at: now }));
  return n;
}

function mockRequest(path, options) {
  var body = options.body || {};
  return new Promise(function (resolve, reject) {
    setTimeout(function () {
      if (path === "/auth/login") {
        var id = body.login_id;
        if (mockFailures(id) >= MOCK_MAX_FAILURES) {
          return reject(new ApiError(ERROR.ACCOUNT_LOCKED, 423, { retry_after_seconds: MOCK_LOCK_SECONDS }));
        }
        var staff = MOCK_STAFF[id];
        var wrong = !staff || staff.status === "left" || /^wrong/.test(body.password || "");
        if (wrong) {
          var n = mockFailures(id, true);
          if (n >= MOCK_MAX_FAILURES) {
            return reject(new ApiError(ERROR.ACCOUNT_LOCKED, 423, { retry_after_seconds: MOCK_LOCK_SECONDS }));
          }
          return reject(new ApiError(ERROR.INVALID_CREDENTIALS, 401, { fail_count: n, max_failures: MOCK_MAX_FAILURES }));
        }
        sessionStorage.removeItem("mockFail:" + id);
        sessionStorage.setItem("mockUser", id);
        return resolve({ access_token: "mock." + id, must_change_password: !!staff.must_change_password });
      }

      if (path === "/auth/me") {
        var who = MOCK_STAFF[sessionStorage.getItem("mockUser")];
        if (!who) return reject(new ApiError(ERROR.TOKEN_EXPIRED, 401, {}));
        return resolve({
          name: who.name,
          roles: who.roles,
          must_change_password: !!who.must_change_password,
          clinic_name: "여성의원",
        });
      }

      if (path === "/auth/logout") {
        sessionStorage.removeItem("mockUser");
        return resolve({});
      }

      if (path === "/auth/password") {
        var current = MOCK_STAFF[sessionStorage.getItem("mockUser")];
        if (current) current.must_change_password = false;
        return resolve({});
      }

      return reject(new ApiError("unknown", 404, {}));
    }, 180);
  });
}
