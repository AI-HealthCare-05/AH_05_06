/* 세션 유지 · 복원 · 로그아웃 — KEY-22
 *
 * 「이 컴퓨터에서 로그인 유지」가 저장 위치를 정한다.
 *
 *   해제(기본) → sessionStorage : 탭을 닫으면 사라진다
 *   체크       → localStorage   : 다음에 와도 남아 있다
 *
 * 의원 접수대는 여러 사람이 한 컴퓨터를 쓴다. 기본이 「유지 안 함」인 이유다.
 * 다음 사람이 앞사람 계정으로 환자 기록을 열면 안 된다.
 */

var TOKEN_KEY = "accessToken";

var session = {
  save: function (token, remember) {
    this.clear();
    (remember ? localStorage : sessionStorage).setItem(TOKEN_KEY, token);
  },

  token: function () {
    return sessionStorage.getItem(TOKEN_KEY) || localStorage.getItem(TOKEN_KEY);
  },

  clear: function () {
    sessionStorage.removeItem(TOKEN_KEY);
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
  if (roles.indexOf("doctor") !== -1) return "/approvals.html"; // D1
  if (roles.indexOf("admin") !== -1) return "/admin.html"; // A1 — 관리자 권한만 가진 계정
  return "/login.html";
}

/* 보호 화면 맨 위에서 부른다. 세 가지를 확인한다.
 *   1) 토큰이 있는가
 *   2) 서버가 아직 그 토큰을 인정하는가
 *   3) 첫 로그인 비밀번호 변경을 마쳤는가
 *
 * 화면에서 감추는 것은 편의일 뿐이고 실제 차단은 서버가 한다(KEY-9).
 * 여기서 막는 이유는 안 될 화면을 잠깐이라도 보여 주지 않기 위해서다.
 */
function requireSession(options) {
  options = options || {};
  var token = session.token();
  if (!token) {
    location.replace("/login.html");
    return Promise.reject();
  }
  return api.me(token).then(
    function (me) {
      if (me.must_change_password && !options.allowPasswordChange) {
        location.replace("/password.html");
        return Promise.reject();
      }
      return me;
    },
    function (err) {
      session.clear();
      /* 만료와 인증 실패를 구분해 로그인 화면이 다른 문구를 낼 수 있게 한다 */
      var reason = err && err.code === ERROR.TOKEN_EXPIRED ? "?expired=1" : "";
      location.replace("/login.html" + reason);
      return Promise.reject();
    }
  );
}
