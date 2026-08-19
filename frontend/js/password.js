/* L-3 첫 로그인 — 비밀번호 바꾸기 · KEY-22 */

(function () {
  var form = document.getElementById("password-form");
  var submit = document.getElementById("submit");
  var next = document.getElementById("new-password");
  var confirm = document.getElementById("confirm-password");
  var box = document.getElementById("error");
  var line = document.getElementById("error-line");

  var MIN_LENGTH = 8;

  /* 이 화면 자체는 첫 로그인 상태에서 열려야 하므로 통과시킨다.
     토큰이 없거나 만료면 로그인 화면으로 되돌린다. */
  requireSession({ allowPasswordChange: true }).catch(function () {});

  /* 로그인 화면에서 넘어온 직후라 브라우저가 autofocus 를 무시한다. 직접 준다. */
  next.focus();

  function show(message, focusOn) {
    line.textContent = message;
    box.hidden = false;
    if (focusOn) {
      focusOn.setAttribute("aria-invalid", "true");
      focusOn.focus();
    }
  }

  function hide() {
    box.hidden = true;
    next.removeAttribute("aria-invalid");
    confirm.removeAttribute("aria-invalid");
  }

  form.addEventListener("input", hide);

  /* 비밀번호 보기 — 길게 친 것을 확인하려는 것이므로 칸마다 따로 둔다.
     기본은 가려 둔다. 접수대 화면은 뒤에서 보인다. */
  form.addEventListener("click", function (event) {
    var button = event.target.closest("[data-reveal]");
    if (!button) return;
    var input = document.getElementById(button.dataset.reveal);
    var shown = input.type === "text";
    input.type = shown ? "password" : "text";
    button.textContent = shown ? "보기" : "가리기";
    button.setAttribute("aria-pressed", String(!shown));
  });

  /* 영문 · 숫자 · 기호를 섞어 8자 이상 — 화면에 적힌 그대로 검사한다.
     적어 놓고 다르게 검사하면 왜 막히는지 알 수 없다. */
  function tooWeak(value) {
    if (value.length < MIN_LENGTH) return "비밀번호는 " + MIN_LENGTH + "자 이상이어야 해요";
    var kinds = [/[A-Za-z]/, /[0-9]/, /[^A-Za-z0-9]/].filter(function (re) {
      return re.test(value);
    }).length;
    if (kinds < 3) return "영문 · 숫자 · 기호를 모두 섞어 주세요";
    return null;
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    var value = next.value;
    var again = confirm.value;

    var weak = tooWeak(value);
    if (weak) return show(weak, next);
    if (value !== again) return show("두 번 넣으신 비밀번호가 달라요", confirm);

    hide();
    submit.disabled = true;
    submit.textContent = "설정 중…";

    /* 첫 비밀번호는 방금 로그인에 쓴 것이다. current_password 를 보내지 않는다 —
       한 화면에서 같은 값을 두 번 넣게 하면 그것부터 막힌다.
       일반 비밀번호 변경 화면은 세 번째 인자로 현재 비밀번호를 함께 보낸다. */
    api.changePassword(session.token(), value).then(
      function () {
        /* 비밀번호를 바꾸면 서버가 기존 토큰을 끊는다.
           바꾼 이유가 「남이 알고 있다」이므로 그 남의 세션도 함께 끊어야 한다.
           그래서 이쪽도 지우고 로그인부터 다시 한다. */
        session.clear();
        location.replace("/login.html?changed=1");
      },
      function (err) {
        submit.disabled = false;
        submit.textContent = "설정 완료";
        if (err && err.code === ERROR.TOKEN_EXPIRED) {
          session.clear();
          return location.replace("/login.html?expired=1");
        }
        show("비밀번호를 바꾸지 못했습니다. 잠시 후 다시 시도해 주세요");
      }
    );
  });
})();
