/* L-1 로그인 · L-2 오류 — KEY-22 */

(function () {
  var form = document.getElementById("login-form");
  var submit = document.getElementById("submit");
  var idInput = document.getElementById("login-id");
  var pwInput = document.getElementById("password");
  var remember = document.getElementById("remember");
  var box = document.getElementById("error");
  var line = document.getElementById("error-line");
  var count = document.getElementById("error-count");

  var query = new URLSearchParams(location.search);

  /* 화면이 열리면 아이디 칸에 커서를 둔다. Tab → 비밀번호 → Enter로 끝난다.
     HTML의 autofocus 는 다른 화면에서 넘어온 경우 브라우저가 무시하기도 한다.
     접수대에서 하루에 수십 번 여는 화면이라 매번 마우스를 잡게 두면 안 된다. */
  if (!idInput.value) idInput.focus();

  /* 만료돼서 튕겨 온 경우. 「틀렸다」와 다른 말을 해야 한다 —
     사용자는 아무것도 틀리지 않았고, 그냥 시간이 지났을 뿐이다. */
  if (query.get("expired")) {
    show("로그인 시간이 지났습니다. 다시 로그인해 주세요");
  }

  /* L-3을 막 마치고 온 경우. 오류가 아니라 안내다. */
  if (query.get("changed")) {
    notice("비밀번호를 바꿨습니다. 새 비밀번호로 로그인해 주세요");
  }

  function show(message, sub) {
    line.textContent = message;
    /* 숨기는 것으로 끝내지 않고 지운다. 이 상자는 aria-live 라서
       낭독기가 영역 전체를 읽을 수 있고, 그러면 지난 횟수까지 따라 읽힌다. */
    count.textContent = sub || "";
    count.hidden = !sub;
    box.hidden = false;
    idInput.setAttribute("aria-invalid", "true");
    pwInput.setAttribute("aria-invalid", "true");
  }

  /* 잘못된 것이 없을 때. 빨간 상자를 쓰면 방금 뭘 틀린 것처럼 읽힌다. */
  function notice(message) {
    line.textContent = message;
    count.hidden = true;
    box.classList.add("alert--notice");
    box.hidden = false;
  }

  function hide() {
    box.hidden = true;
    box.classList.remove("alert--notice");
    idInput.removeAttribute("aria-invalid");
    pwInput.removeAttribute("aria-invalid");
  }

  /* 다시 입력하기 시작하면 지난 오류를 치운다. 고쳐 쓰는 중에
     빨간 글씨가 남아 있으면 방금 또 틀린 것처럼 보인다. */
  form.addEventListener("input", hide);

  function minutes(seconds) {
    return Math.max(1, Math.ceil((seconds || 600) / 60));
  }

  function explain(err) {
    if (!err || !err.code) return show("잠시 후 다시 시도해 주세요");

    if (err.code === ERROR.ACCOUNT_LOCKED) {
      /* 몇 번 틀렸는지는 이제 의미가 없다. 언제 풀리는지만 알려준다. */
      return show("잠시 뒤 다시 시도해 주세요. (" + minutes(err.data.retry_after_seconds) + "분)");
    }

    if (err.code === ERROR.INVALID_CREDENTIALS) {
      /* 어느 쪽이 틀렸는지 쓰지 않는다 — 아이디가 있는지 없는지가 드러나면 안 된다.
         대신 몇 번째인지 알려 준다. 잠기기 전에 멈출 수 있어야 한다. */
      var n = err.data.fail_count;
      var max = err.data.max_failures || 5;
      return show("⚠ 아이디 또는 비밀번호가 맞지 않습니다", n ? max + "회 오류 시 일시 잠금 (" + n + "회)" : "");
    }

    if (err.status === 0 || err.status >= 500) {
      return show("서버에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요");
    }
    return show("로그인하지 못했습니다. 잠시 후 다시 시도해 주세요");
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    var loginId = idInput.value.trim();
    var password = pwInput.value;

    /* 빈 칸은 서버까지 가지 않는다. 그래도 어느 칸이 비었는지는 말해 준다 —
       여기서는 아이디 존재 여부가 드러날 일이 없다. */
    if (!loginId || !password) {
      show(!loginId ? "아이디를 입력해 주세요" : "비밀번호를 입력해 주세요");
      (!loginId ? idInput : pwInput).focus();
      return;
    }

    hide();
    submit.disabled = true;
    submit.textContent = "확인 중…";

    api.login(loginId, password, remember.checked).then(
      function (res) {
        session.save(res.access_token);
        /* 첫 로그인은 L-3을 지나야 한다. 건너뛸 수 없다. */
        if (res.must_change_password) return location.replace("/password.html");
        return api.me(res.access_token).then(function (me) {
          location.replace(landingFor(me.roles));
        });
      },
      function (err) {
        submit.disabled = false;
        submit.textContent = "로그인";
        explain(err);
        pwInput.value = "";
        pwInput.focus();
      }
    );
  });
})();
