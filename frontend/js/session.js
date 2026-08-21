/* 세션 유지 · 복원 · 로그아웃 — KEY-22
 *
 * 토큰 둘이 사는 곳이 다르다 (docs/api/hospital.md 4절 · KEY-8 v1 확정).
 *
 *   리프레시 토큰 — HttpOnly 쿠키. **이 파일이 만지지 않는다.**
 *                   스크립트가 못 읽으므로 XSS 로도 훔쳐 갈 수 없다.
 *                   「로그인 유지」는 이 쿠키가 얼마나 남는지를 서버가 정한다.
 *   액세스 토큰   — sessionStorage. 탭을 닫으면 사라진다.
 *
 * 액세스 토큰을 localStorage 에 두지 않는다. 「로그인 유지」를 켰어도 마찬가지다 —
 * 유지는 쿠키가 맡고, 새 탭에서는 refresh 로 다시 받으면 된다.
 * 의원 접수대는 여러 사람이 한 컴퓨터를 쓴다. 오래 남는 것을 늘리지 않는다.
 */

var TOKEN_KEY = "accessToken";

var session = {
  save: function (token) {
    sessionStorage.setItem(TOKEN_KEY, token);
  },

  token: function () {
    return sessionStorage.getItem(TOKEN_KEY);
  },

  clear: function () {
    sessionStorage.removeItem(TOKEN_KEY);
    /* 예전 판이 localStorage 에 남겨 둔 것을 걷어낸다 */
    localStorage.removeItem(TOKEN_KEY);
  },

  /* 서버에도 알리고 화면에서도 지운다.
   * 서버가 실패해도 이쪽은 반드시 지운다 — 로그아웃을 눌렀는데
   * 토큰이 남아 있는 것이 가장 나쁘다. */
  logout: function () {
    var token = this.token();
    var self = this;
    var done = function () {
      self.clear();
      location.replace("/login.html");
    };
    if (!token) return done();
    api.logout(token).then(done, done);
  },
};

/* 로그인한 사람이 갈 첫 화면. 계정에 붙은 역할이 정한다.
 * 화면을 고르게 하지 않는다 — 스탭은 환자 목록, 의사는 안내문 확인이 첫 일이다.
 * 관리자 권한은 별도 축이라 첫 화면을 바꾸지 않고 메뉴만 늘린다. */
function landingFor(roles) {
  roles = roles || [];
  if (roles.indexOf("staff") !== -1) return "/patients.html"; // S1
  if (roles.indexOf("doctor") !== -1) return "/doctor.html"; // D1
  if (roles.indexOf("admin") !== -1) return "/admin.html"; // A1 — 관리자 권한만 가진 계정
  return "/login.html";
}

/* 보호 화면 맨 위에서 부른다. 네 가지를 확인한다.
 *   1) 액세스 토큰이 있는가 — 없으면 쿠키로 재발급을 시도한다
 *   2) 서버가 아직 그 토큰을 인정하는가
 *   3) 만료됐다면 재발급으로 살릴 수 있는가
 *   4) 첫 로그인 비밀번호 변경을 마쳤는가
 *
 * 화면에서 감추는 것은 편의일 뿐이고 실제 차단은 서버가 한다(KEY-9).
 * 여기서 막는 이유는 안 될 화면을 잠깐이라도 보여 주지 않기 위해서다.
 */
function requireSession(options) {
  options = options || {};

  function bounce(reason) {
    session.clear();
    location.replace("/login.html" + (reason || ""));
    return Promise.reject();
  }

  function check(me) {
    if (me.must_change_password && !options.allowPasswordChange) {
      location.replace("/password.html");
      return Promise.reject();
    }
    return me;
  }

  /* 액세스 토큰은 sessionStorage 라 새 탭에서는 비어 있다.
     리프레시 쿠키가 살아 있으면 다시 로그인할 이유가 없다. */
  function renew(reason) {
    return api.refresh().then(
      function (res) {
        session.save(res.access_token);
        return api.me(res.access_token).then(check, function () {
          return bounce(reason);
        });
      },
      function (err) {
        /* 쿠키가 만료됐거나 유휴 30분이 지났다는 뜻이다.
           처음 오는 사람과 구분해 「시간이 지났다」고 알려 준다 —
           점심 먹고 와서 아무 말 없이 로그인 화면을 만나면
           자기가 로그아웃한 줄 안다. */
        var why = reason || (err && err.code === ERROR.TOKEN_EXPIRED ? "?expired=1" : "");
        return bounce(why);
      }
    );
  }

  var token = session.token();
  if (!token) return renew("");

  return api.me(token).then(check, function (err) {
    /* 만료면 되살려 본다. 그 밖의 실패는 곧장 로그인 화면으로 —
       만료와 인증 실패를 구분해야 화면이 다른 문구를 낼 수 있다. */
    if (err && err.code === ERROR.TOKEN_EXPIRED) return renew("?expired=1");
    return bounce("");
  });
}
