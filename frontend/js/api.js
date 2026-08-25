/* API 호출 한 겹 — KEY-22
 *
 * 계약은 docs/api/hospital.md 4·5절 — KEY-8 v1 확정본을 따른다.
 *   POST  /api/v1/auth/login     { login_id, password, remember }
 *   GET   /api/v1/auth/me
 *   POST  /api/v1/auth/refresh   본문 없음. 쿠키만 본다
 *   POST  /api/v1/auth/logout
 *   PATCH /api/v1/auth/password  최초 로그인이면 new_password 만
 *
 * 리프레시 토큰은 HttpOnly 쿠키로만 오간다 — 이 파일이 만지지 않는다.
 * 그래서 모든 요청에 credentials: "include" 를 붙인다.
 *
 * 서버는 아직 이 다섯을 갖고 있지 않다(지금은 email 로그인뿐이다).
 * 계약대로 짜 두고, 서버가 붙기 전까지는 아래 목업으로 화면을 확인한다.
 */

var API_BASE = "/api/v1";

/* 날짜 하나를 「2026-08-19」로. 화면 여러 곳이 쓴다 —
   골격(shell.js)의 날짜 축도 여기에 기댄다. 환자 전용 파일에 두면
   shell.js 만 부르는 화면(관리자 A1 등)에서 그대로 깨진다. */
function toIsoDate(date) {
  var m = String(date.getMonth() + 1).padStart(2, "0");
  var d = String(date.getDate()).padStart(2, "0");
  return date.getFullYear() + "-" + m + "-" + d;
}

/* 서버가 코드로 구분해 준다. 화면 문구가 코드마다 다르기 때문이다.
 * 특히 「인증정보가 틀렸다」와 「세션이 만료됐다」는 둘 다 401이지만
 * 사용자가 해야 할 일이 다르다 — 다시 입력할 것인가, 다시 로그인할 것인가. */
var ERROR = {
  INVALID_CREDENTIALS: "invalid_credentials",
  ACCOUNT_LOCKED: "ACCOUNT_LOCKED",
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
  var token = options.token || session.token();
  if (token) headers["Authorization"] = "Bearer " + token;

  return fetch(API_BASE + path, {
    method: options.method || "GET",
    headers: headers,
    // 리프레시 토큰이 HttpOnly 쿠키라 이게 없으면 재발급이 통째로 안 된다
    credentials: "include",
    body: options.body ? JSON.stringify(options.body) : undefined,
  }).then(function (res) {
    return res
      .json()
      .catch(function () {
        return {};
      })
      .then(function (data) {
        if (res.ok) return data;
        /* Retry-After 는 표준 헤더라 서버가 본문에 안 담아도 여기서 읽힌다.
           본문 값이 있으면 그쪽을 쓴다 — 서버가 초 단위를 더 정확히 안다. */
        var retry = Number(res.headers.get("Retry-After"));
        if (retry && !data.retry_after_seconds) data.retry_after_seconds = retry;
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
  refresh: function () {
    // 본문도 헤더도 없다. 쿠키만으로 돈다.
    return request("/auth/refresh", { method: "POST" });
  },
  logout: function (token) {
    return request("/auth/logout", { method: "POST", token: token });
  },
  /* 최초 로그인(L-3)은 current_password 를 보내지 않는다.
     방금 그 비밀번호로 로그인했는데 한 화면에서 또 넣게 하면 거기서부터 막힌다. */
  changePassword: function (token, newPassword, currentPassword) {
    var body = { new_password: newPassword };
    if (currentPassword) body.current_password = currentPassword;
    return request("/auth/password", { method: "PATCH", token: token, body: body });
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
          return reject(new ApiError(ERROR.ACCOUNT_LOCKED, 429, { retry_after_seconds: MOCK_LOCK_SECONDS }));
        }
        var staff = MOCK_STAFF[id];
        var wrong = !staff || staff.status === "left" || /^wrong/.test(body.password || "");
        if (wrong) {
          var n = mockFailures(id, true);
          if (n >= MOCK_MAX_FAILURES) {
            return reject(new ApiError(ERROR.ACCOUNT_LOCKED, 429, { retry_after_seconds: MOCK_LOCK_SECONDS }));
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

      if (path === "/auth/refresh") {
        /* 실제로는 HttpOnly 쿠키를 본다. 목업은 그 자리를 mockUser 로 대신한다. */
        var who = sessionStorage.getItem("mockUser");
        if (!who) return reject(new ApiError(ERROR.TOKEN_EXPIRED, 401, {}));
        return resolve({ access_token: "mock." + who });
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

/* HTML 로 나갈 글자를 막는다. **한 곳에만 둔다.**
 *
 * 예전에는 `shell.js` · `checkin.js` · `doctor.js` 셋에 같은 이름이 각각 있었고
 * 구현이 조금씩 달랐다 — `shell.js` 만 홑따옴표까지 막았다. KEY-158 이
 * `checkin.js` 의 것을 전역으로 꺼내면서 **같은 이름이 부딪히게** 됐다.
 * 함께 실리면 나중 선언이 조용히 이긴다 (이희진 님 `#103` 리뷰).
 *
 * 가장 엄한 것(`shell.js` 판)을 남긴다. 홑따옴표 속성에 쓰는 자리가 지금은
 * 없지만, 생기는 날 덜 엄한 판이 남아 있으면 그때는 구멍이다.
 *
 * `api.js` 에 두는 까닭은 **`esc()` 를 쓰는 다섯 파일이 실리는 화면이 모두
 * 이 파일을 먼저 부르기** 때문이다. `shell.js` 는 `checkin.html` 이 안 부른다.
 */
function esc(text) {
  return String(text == null ? "" : text).replace(/[&<>"']/g, function (c) {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
  });
}
