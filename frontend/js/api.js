/* API 호출 한 겹 — KEY-22
 *
 * 계약은 docs/api/hospital.md 4·5절 — KEY-8 v1 확정본을 따른다.
 *   POST  /api/v1/auth/login     { login_id, password }
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

/* **서버에 닿지도 못한 것** — KEY-211.
 *
 * HTTP 응답이 온 오류는 서버가 `status` 와 `code` 를 준다. 그런데 오프라인 ·
 * DNS 실패 · 연결 끊김 · CORS 차단은 `fetch` 자체가 거절하고, 브라우저가 주는 것은
 * `.status` 도 `.code` 도 없는 날것 `TypeError` 다. 그대로 올려 보내면 화면은 그것을
 * 「서버가 거절했다」와 구별할 수 없어 제 기본 문구를 낸다 — 시연·Pilot 에서 원인을
 * 찾는 시간이 여기서 늘어난다.
 *
 * `status = 0` 은 「HTTP 왕복이 아예 없었다」는 뜻이다. 화면의 문구 표가 이미 그
 * 규칙 모양을 다룰 줄 안다(`errorMessage`). */
var NETWORK_ERROR_CODE = "NETWORK_UNREACHABLE";

/* **말은 한 곳에서 정한다.** 네 화면에 같은 문장을 따로 적으면 한쪽만 고쳐진다. */
var NETWORK_SAYING = { status: 0, say: "서버에 닿지 못했습니다 — 연결을 확인하고 다시 눌러 주세요" };

/* 목업 — 로컬 개발 중에만 쓴다.
 * localhost/file 미리보기에서 ?mock=1 로 켜며 같은 탭의 화면 이동 동안 유지한다.
 * 배포/Pilot 호스트에서는 저장된 값이 있어도 무조건 꺼진다. */
function localMockRequested(target) {
  target = target || location;
  try {
    var host = String(target.hostname || "").toLowerCase();
    var local = target.protocol === "file:" || host === "localhost" || host === "127.0.0.1" || host === "[::1]";
    if (!local) return false;
    var query = new URLSearchParams(target.search).get("mock");
    if (query !== null) sessionStorage.setItem("useMock", query === "1" ? "1" : "0");
    return sessionStorage.getItem("useMock") === "1";
  } catch (_error) {
    return false;
  }
}

function showMockBanner() {
  if (!MOCK || !document.body || !document.body.dataset || document.getElementById("mock-mode-banner")) return;
  var banner = document.createElement("div");
  banner.id = "mock-mode-banner";
  banner.setAttribute("role", "status");
  banner.textContent = "개발용 MOCK 모드 — 실제 서버 데이터가 아닙니다";
  banner.style.cssText = "position:fixed;inset:0 0 auto;z-index:10000;padding:8px 16px;background:#7a2e00;color:#fff;text-align:center;font:700 14px/1.4 sans-serif";
  document.body.prepend(banner);
  document.body.style.paddingTop = Math.max(36, parseInt(document.body.style.paddingTop || "0", 10) || 0) + "px";
}

var MOCK = (function () {
  return localMockRequested(location);
})();

showMockBanner();

function request(path, options) {
  options = options || {};
  if (MOCK) return mockRequest(path, options);

  var headers = { Accept: "application/json" };
  if (options.body) headers["Content-Type"] = "application/json";
  /* **환자 화면은 `session.js` 를 안 싣는다** — KEY-211.
   *
   * 체크인(`checkin.html`)은 의료진 세션 없이 링크 토큰으로 들어온다. 그런데
   * 여기서 `session` 을 곧장 부르면 `ReferenceError` 가 나고, 그건 프라미스 거절이
   * 아니라 **동기 예외**라 부르는 쪽의 `.catch` 가 아예 안 걸린다. 환자는 내용이 빈
   * 반쪽 화면을 보고, 왜 안 되는지는 콘솔에만 남는다.
   *
   * 이 종점들은 주소의 링크 토큰으로 스스로를 증명하므로 `Authorization` 이
   * 필요 없다. 없으면 없는 대로 보낸다. */
  var token = options.token || (typeof session !== "undefined" ? session.token() : null);
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
    })
    .catch(function (error) {
      /* 서버가 답한 오류는 그대로 올린다 — `code` 와 `status` 가 이미 붙어 있다. */
      if (error instanceof ApiError) throw error;
      /* 여기 오는 것은 `fetch` 단계의 거절뿐이다. 브라우저마다 말이 달라서
         (`Failed to fetch` · `NetworkError when attempting to fetch resource`)
         메시지를 화면에 올리지 않는다 — 어차피 사람이 읽을 말이 아니고,
         무엇보다 그 문장이 주소를 담을 수 있다. */
      throw new ApiError(NETWORK_ERROR_CODE, 0, {});
    });
}

var api = {
  login: function (clinicCode, loginId, password) {
    return request("/auth/login", {
      method: "POST",
      body: { clinic_code: clinicCode, login_id: loginId, password: password },
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
//: 목업 의원. 이관 마이그레이션이 짓는 것과 같은 꼴이다 (KEY-324).
var MOCK_CLINIC_CODES = { clinic0001: "도로시여성의원" };

var MOCK_STAFF = {
  staff01: { id: 101, name: "한소영", roles: ["staff"], must_change_password: false },
  doctor01: { id: 900, name: "박연", roles: ["doctor"], must_change_password: false },
  adminstaff01: { id: 102, name: "서지원", roles: ["staff", "admin"], must_change_password: false },
  newbie01: { id: 103, name: "임채운", roles: ["staff"], must_change_password: true },
  left01: { id: 104, name: "문가람", roles: ["staff"], status: "left" },
};
/* 합성 감사 기록. **원문이 하나도 없다** — 링크 토큰도 전화번호도 환자 이름도
   담지 않는다. 서버 계약이 그렇고, 목업이 그것을 어기면 화면이 있지도 않은
   값을 그리는 연습을 하게 된다. */
var MOCK_AUDIT = [
  { event_id: "staff_account:3", occurred_at: "2026-09-10T09:41:00+09:00", source: "staff_account",
    event_type: "STAFF_CREATED", actor_staff_id: 102, actor_name: "서지원", visit_id: null,
    summary: "직원 계정을 만들었습니다" },
  { event_id: "patient_usage:7", occurred_at: "2026-09-10T09:12:00+09:00", source: "patient_usage",
    event_type: "GUIDE_VIEWED", actor_staff_id: null, actor_name: null, visit_id: 1204,
    summary: "환자가 안내를 열어 봤습니다" },
  { event_id: "message:5", occurred_at: "2026-09-10T09:05:00+09:00", source: "message",
    event_type: "SENT", actor_staff_id: null, actor_name: null, visit_id: 1204,
    summary: "문자를 보냈습니다" },
  { event_id: "otp:4", occurred_at: "2026-09-10T09:02:00+09:00", source: "otp",
    event_type: "VERIFIED", actor_staff_id: null, actor_name: null, visit_id: 1204,
    summary: "환자가 본인 확인을 마쳤습니다" },
  { event_id: "guide:12", occurred_at: "2026-09-10T08:58:00+09:00", source: "guide",
    event_type: "APPROVED", actor_staff_id: 900, actor_name: "박연", visit_id: 1204,
    summary: "안내문을 승인했습니다" },
  { event_id: "guide:11", occurred_at: "2026-09-10T08:40:00+09:00", source: "guide",
    event_type: "SUBMITTED", actor_staff_id: 101, actor_name: "한소영", visit_id: 1204,
    summary: "안내문을 의사에게 넘겼습니다" },
  { event_id: "guide:10", occurred_at: "2026-09-09T17:20:00+09:00", source: "guide",
    event_type: "GENERATED", actor_staff_id: 101, actor_name: "한소영", visit_id: 1198,
    summary: "안내문을 생성했습니다" },
];

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
        /* **목업도 의원 코드를 본다** (KEY-324). 안 보면 「목업에서는 아무 코드나
           되는데 실서버에서는 안 되는」 거리가 생긴다 — 갈래를 두지 않는다. */
        if (!MOCK_CLINIC_CODES[String(body.clinic_code || "").toLowerCase()]) {
          return reject(new ApiError(ERROR.INVALID_CREDENTIALS, 401, { fail_count: 1, max_failures: MOCK_MAX_FAILURES }));
        }
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
          id: who.id,
          name: who.name,
          login_id: sessionStorage.getItem("mockUser"),
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

      /* A1-1 · A1-2 — KEY-321. 목업도 **서버와 같은 규칙**을 지킨다:
         조합 다섯만, 아이디는 전체에서 유일, 만든 계정은 첫 로그인 전. */
      if (path === "/admin/staffs" && (options.method || "GET") === "GET") {
        var listed = [];
        for (var loginId in MOCK_STAFF) {
          if (!Object.prototype.hasOwnProperty.call(MOCK_STAFF, loginId)) continue;
          var one = MOCK_STAFF[loginId];
          listed.push({
            staff_id: one.id,
            login_id: loginId,
            name: one.name,
            roles: one.roles,
            status: one.status || "active",
            must_change_password: !!one.must_change_password,
            last_login_at: null,
            created_at: null,
          });
        }
        return resolve({ staffs: listed });
      }

      if (path === "/admin/staffs" && options.method === "POST") {
        if (!/^[a-z0-9]{4,}$/.test(body.login_id || "")) {
          return reject(new ApiError("INVALID_REQUEST", 400, {}));
        }
        if (MOCK_STAFF[body.login_id]) {
          return reject(new ApiError("LOGIN_ID_TAKEN", 409, {}));
        }
        var wanted = (body.roles || []).slice().sort().join("|");
        if (["staff", "doctor", "admin", "admin|staff", "admin|doctor"].indexOf(wanted) === -1) {
          return reject(new ApiError("INVALID_ROLE_COMBINATION", 400, {}));
        }
        MOCK_STAFF[body.login_id] = {
          id: 900 + Object.keys(MOCK_STAFF).length,
          name: body.name,
          roles: body.roles,
          must_change_password: true,
        };
        return resolve({
          staff_id: MOCK_STAFF[body.login_id].id,
          login_id: body.login_id,
          name: body.name,
          roles: body.roles,
          status: "active",
          must_change_password: true,
        });
      }

      /* A1-6 · A1-7 — KEY-322. 목업도 **서버와 같은 모양**으로 답한다:
         유형 다섯이 섞이고, 최신순이고, 거르개가 듣고, 쪽이 나뉜다. */
      if (path.indexOf("/admin/audit-logs") === 0) {
        var asked = new URLSearchParams(path.split("?")[1] || "");
        var rows = MOCK_AUDIT.slice();
        if (asked.get("source")) rows = rows.filter(function (r) { return r.source === asked.get("source"); });
        if (asked.get("actor_staff_id")) {
          rows = rows.filter(function (r) { return String(r.actor_staff_id) === asked.get("actor_staff_id"); });
        }
        if (asked.get("visit_id")) {
          rows = rows.filter(function (r) { return String(r.visit_id) === asked.get("visit_id"); });
        }
        if (asked.get("occurred_from")) {
          rows = rows.filter(function (r) { return r.occurred_at >= asked.get("occurred_from"); });
        }
        if (asked.get("occurred_to")) {
          rows = rows.filter(function (r) { return r.occurred_at <= asked.get("occurred_to"); });
        }
        /* **서버와 같은 규칙으로 줄을 세운다** — `(시각, 표, 번호)` 내림차순.
           처음에는 시각만 보고 커서도 정수 오프셋이었는데, 그러면 목업이
           실서버가 겪은 정렬 결함(`"guide:9" > "guide:10"`)을 **재현하지
           못한다.** 목업으로 확인한 것이 실물을 보증하려면 규칙이 같아야
           한다 (이희진 님 `#287` 리뷰 ④). */
        var keyOf = function (row) {
          var cut = row.event_id.lastIndexOf(":");
          return [row.occurred_at, row.event_id.slice(0, cut), Number(row.event_id.slice(cut + 1))];
        };
        var before = function (a, b) {
          for (var i = 0; i < 3; i++) {
            if (a[i] < b[i]) return -1;
            if (a[i] > b[i]) return 1;
          }
          return 0;
        };
        rows.sort(function (a, b) { return before(keyOf(b), keyOf(a)); });
        /* 커서도 **자리**를 담는다. 정수 오프셋은 그 사이에 줄이 늘면 어긋난다. */
        var after = asked.get("cursor") ? JSON.parse(atob(asked.get("cursor"))) : null;
        if (after) rows = rows.filter(function (row) { return before(keyOf(row), after) < 0; });
        var size = Number(asked.get("limit") || 50);
        var slice = rows.slice(0, size);
        var left = rows.length > size;
        var next = left && slice.length ? btoa(JSON.stringify(keyOf(slice[slice.length - 1]))) : null;
        return resolve({ entries: slice, next_cursor: next, has_more: left });
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
/* 오류 하나를 **사람 말 한 줄**로 옮긴다 — KEY-126.
 *
 * `detail.js` 의 `messageFor()`, `doctor.js` 의 `guideLoadSaying()`,
 * `ocr-review.js` 의 실패 사유가 셋 다 「status·code 를 보고 문장을 고르고,
 * 못 고르면 기본 문구」라는 같은 모양을 각자 적고 있었다. 기본 문구를 바꾸거나
 * 상태코드를 더할 때 세 곳을 따로 고쳐야 하고, 조용히 어긋난다
 * (이희진 님 `#121` 리뷰).
 *
 * 규칙은 **적은 순서대로** 본다. 좁은 것을 먼저 적는다.
 *
 *     errorMessage(error, [
 *       { status: 404, say: "…" },
 *       { code: "VISIT_LOCKED", say: "…" },
 *     ], "기본 문구")
 */
function errorMessage(error, rules, fallback) {
  if (!error) return fallback;
  for (var i = 0; i < rules.length; i += 1) {
    var rule = rules[i];
    if (rule.status !== undefined && error.status === rule.status) return rule.say;
    if (rule.code !== undefined && error.code === rule.code) return rule.say;
  }
  return fallback;
}

function esc(text) {
  return String(text == null ? "" : text).replace(/[&<>"']/g, function (c) {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
  });
}
