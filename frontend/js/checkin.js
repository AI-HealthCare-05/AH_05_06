/* P7 오늘 확인 — D+7 복약·통증 응답 (KEY-98)
 *
 * 환자가 문자로 받은 링크를 눌러 「약 잘 드시고 계신가요」에 답하는 화면이다.
 *
 * 이 화면의 어려움은 기능이 아니라 **말투**에 있다.
 *
 *   ① 책망하지 않는다. 「가끔 놓쳐요」에 「잘 챙기셔야 합니다」가 나오면,
 *      다음 회차부터는 「잘 먹고 있어요」를 고른다. 그러면 우리가 보는
 *      숫자가 거짓이 된다 — 기록이 있는데 쓸 수 없는 상태가 제일 나쁘다.
 *   ② 같은 「중단」을 둘로 나눈다. 불편해서 끊은 분께는 「흔한 반응입니다」를,
 *      좋아져서 끊은 분께는 복약 목적을 다시 말한다. 정반대의 설명이다.
 *   ③ 「가끔 놓쳐요」에는 🚨도 [문의하기]도 두지 않는다. 응급이 아니고,
 *      문의를 권하면 「이건 문제다」로 읽혀 다음엔 말하지 않게 된다.
 *
 * **문구는 화면이 만들지 않는다.** 전부 서버가 준다 — 승인된 주의사항에서
 * 가져온 문장이라야 하고, 약마다 다르다(`checkin-api.js` 참고).
 */


/* 이 답이 **병원에 알림을 보내야 하는 것인가.**
 *
 * 계약이 답마다 `notify` 를 정해 준다 — 화면이 판정하지 않는다. 모르는 답이
 * 오면 **안 보낸다**(`false`) — 알림은 사람을 부르는 일이라, 확실할 때만 한다.
 *
 * 닫힌 `data` 를 읽던 것을 인자로 바꿔 IIFE 밖으로 꺼냈다 (KEY-158).
 */
/* 서버가 선택지마다 내려준 `notify` 를 그대로 읽는다. 화면이 판단하지
   않는다 — 무엇이 알릴 일인지는 승인된 주의사항이 정한다. */
function notifyFor(answers, key) {
  var info = answers && answers[key];
  return info ? !!info.notify : false;
}

(function () {
  /* **자기 칸이 없는 페이지에서는 아무것도 하지 않는다.**
     이 파일은 `checkin.html` 에만 실린다. 뿌리가 없으면 조용히 돌아간다 —
     위 순수 규칙은 그대로 남아서 다른 파일도, 검사도 부를 수 있다 (KEY-158). */
  if (!document.getElementById("form")) return;

  var el = function (id) {
    return document.getElementById(id);
  };

  var data = null;
  /* 실제 화면에서 토큰이 없으면 합성 기본값으로 요청하지 않는다. 새로고침·
     잘못된 주소는 서버 인증 상태를 추측하지 않고 닫힌 링크 안내로 보낸다. */
  var token = new URLSearchParams(location.search).get("t") || "";

  var picked = null; // 복약 답
  /* 신호를 언제 보낼지 정하는 것은 `checkin-api.js` 의 `createSignalTracker` 다.
     이 파일은 IIFE 라 검사가 안을 못 부르는데, 그 판단이야말로 재야 하는
     자리라서 밖으로 꺼내 두었다 (`KEY-158` 참고). */
  var signals = createSignalTracker();
  var painHad = null; // true · false · null(아직 안 고름)
  var painScore = 4;
  var painTypes = [];
  var pendingAnswer = null;
  var authTimer = null;
  var otpResendAvailableAt = 0;


  var LABELS = {
    taking: "잘 먹고 있어요",
    uncomfortable: "먹고 있는데 불편해요",
    missing: "가끔 놓쳐요",
    stopped_side_effect: "불편해서 중단했어요",
    stopped_improved: "증상이 좋아져서 그만뒀어요",
  };

  /* ── 복약 ────────────────────────────────────────────── */

  /* 고른 것 바로 아래에서 펼친다 — 화면을 갈아끼우지 않는다.
     넘어가 버리면 다른 답으로 바꾸려 할 때 되돌아와야 한다. */
  function expansionHtml(answer) {
    var info = data.answers[answer];
    if (!info) return "";

    var html = '<div class="fold">';
    html += '<p class="fold__lead">' + esc(info.lead) + "</p>";
    if (info.body) html += '<p class="fold__body">' + esc(info.body) + "</p>";

    if (info.tips) {
      html += '<p class="fold__sub">잊지 않는 데 도움이 되는 것</p><ul class="fold__tips">';
      html += info.tips
        .map(function (t) {
          return "<li>" + esc(t) + "</li>";
        })
        .join("");
      html += "</ul>";
    }

    if (info.urgent) {
      html +=
        '<div class="urgent"><p class="urgent__title">' +
        esc(info.urgent.title) +
        "</p><ul>" +
        info.urgent.list
          .map(function (t) {
            return "<li>" + esc(t) + "</li>";
          })
          .join("") +
        "</ul></div>";
    }

    // 「가끔 놓쳐요」에는 문의하기를 두지 않는다 — 위 ③
    if (info.ask) html += '<button class="fold__ask" type="button" id="ask">💬 문의하기</button>';
    if (info.note) html += '<p class="fold__note">ⓘ ' + esc(info.note) + "</p>";

    html += "</div>";
    return html;
  }

  function renderMedication() {
    el("meds").innerHTML = MEDICATION_ANSWERS.map(function (key) {
      var on = key === picked;
      return (
        '<button class="pick' +
        (on ? " is-on" : "") +
        '" type="button" data-med="' +
        key +
        '" aria-pressed="' +
        on +
        '">' +
        esc(LABELS[key]) +
        "</button>" +
        (on ? expansionHtml(key) : "")
      );
    }).join("");
  }

  /* ── 통증 ────────────────────────────────────────────── */

  function renderPain() {
    var html =
      '<div class="two">' +
      '<button class="pick pick--half' +
      (painHad === true ? " is-on" : "") +
      '" type="button" data-pain="yes">있었어요</button>' +
      '<button class="pick pick--half' +
      (painHad === false ? " is-on" : "") +
      '" type="button" data-pain="no">없었어요</button>' +
      "</div>";

    // 아프다고 답했을 때만 더 묻는다 — 안 아픈 분께 10칸 눈금을 보이지 않는다
    if (painHad === true) {
      html +=
        '<div class="score"><span class="score__label">정도</span>' +
        '<input class="score__range" type="range" min="0" max="10" value="' +
        painScore +
        '" id="pain-score" aria-label="통증 정도" />' +
        '<span class="score__value" id="score-value">' +
        painScore +
        " / 10</span></div>" +
        '<div class="chips2">' +
        data.pain_types
          .map(function (t) {
            var on = painTypes.indexOf(t.key) !== -1;
            return (
              '<button class="chip2' +
              (on ? " is-on" : "") +
              '" type="button" data-type="' +
              t.key +
              '" aria-pressed="' +
              on +
              '">' +
              esc(t.label) +
              "</button>"
            );
          })
          .join("") +
        "</div>";
    }
    el("pain").innerHTML = html;
  }

  /* 복약 답 없이는 저장하지 않는다. 통증은 안 고를 수 있다 —
     아팠는지 기억이 안 나는 날도 있고, 그때 억지로 고르게 하면 아무 값이나 눌린다. */
  function renderSave() {
    el("save").disabled = picked === null;
  }

  /* ── 완료 ────────────────────────────────────────────── */

  function doneHtml(result) {
    var pain =
      painHad === true
        ? painScore +
          " / 10" +
          (painTypes.length
            ? " · " +
              painTypes
                .map(function (k) {
                  return data.pain_types.filter(function (t) {
                    return t.key === k;
                  })[0].label;
                })
                .join(" · ")
            : "")
        : painHad === false
          ? "없었어요"
          : "답하지 않음";

    /* 남은 확인 문자가 있으면 그것을, 없으면 다음 진료일을 알린다(P7-6). */
    var next = result.next_checkin
      ? "<dt>다음 확인</dt><dd>" + esc(result.next_checkin) + "에 문자로 여쭤볼게요</dd>"
      : "";

    return (
      '<div class="done">' +
      '<p class="done__mark">✓</p>' +
      '<h1 class="done__title">기록이 저장됐어요</h1>' +
      '<dl class="done__list"><dt>약</dt><dd>' +
      esc(LABELS[result.medication]) +
      "</dd><dt>통증</dt><dd>" +
      esc(pain) +
      "</dd>" +
      next +
      (result.next_visit ? "<dt>다음 진료</dt><dd>" + esc(result.next_visit) + "</dd>" : "") +
      "</dl>" +
      /* 예전에는 `/guide.html` 로만 보내서 식별자가 비었다 — 그 화면은
         `?visit=` 으로 `/api/v1/guides/{visit_id}` 를 부른다. 링크는 서버가
         내려준 것을 쓴다. 안 주면 **깨진 링크를 그리지 않는다** (`#55` 리뷰). */
      (result.guide_url ? '<a class="done__link" href="' + esc(result.guide_url) + '">복약지도 다시 보기</a>' : "") +
      '<p class="done__note">이 화면은 저절로 넘어가지 않아요 · 다 보시고 닫으셔도 됩니다</p>' +
      "</div>"
    );
  }

  function showOnly(html) {
    el("form").hidden = true;
    el("state").innerHTML = html;
    el("state").hidden = false;
    /* 폼이 통째로 사라진다. 초점을 옮기지 않으면 저장 버튼에 있던 커서가
       `body` 로 떨어져, 못 보는 사람은 **저장됐는지도 모른다** (KEY-129). */
    el("state").focus();
  }

  function clearAuthTimer() {
    if (authTimer !== null) {
      window.clearTimeout(authTimer);
      authTimer = null;
    }
  }

  function authCard(title, message, controls) {
    return (
      '<div class="auth-recovery">' +
      '<p class="auth-recovery__mark" aria-hidden="true">⚠</p>' +
      '<h1 class="auth-recovery__title">' +
      esc(title) +
      "</h1>" +
      '<p class="auth-recovery__message">' +
      esc(message) +
      "</p>" +
      (controls || "") +
      '<p class="auth-recovery__safe">ⓘ 링크와 인증번호 원문은 서버 응답이나 로그에 남기지 않아요.</p>' +
      "</div>"
    );
  }

  function renderAuthGuidance(error) {
    clearAuthTimer();
    var guide = patientAuthGuidance(error);
    var controls = "";

    if (guide.action === "issue" || guide.action === "retry") {
      controls = '<button class="auth-recovery__primary" type="button" id="auth-issue">인증번호 받기</button>';
    } else if (guide.action === "wait") {
      controls = '<button class="auth-recovery__primary" type="button" id="auth-issue" disabled>잠금 해제 기다리는 중</button>';
      if (guide.retryAfterSeconds) {
        authTimer = window.setTimeout(function () {
          renderAuthGuidance({ code: "PATIENT_SESSION_EXPIRED", data: {} });
        }, guide.retryAfterSeconds * 1000);
      }
    } else {
      controls = '<p class="auth-recovery__next">가장 최근 문자 링크를 다시 열거나 진료받으신 병원에 문의해 주세요.</p>';
    }
    showOnly(authCard(guide.title, guide.message, controls));
  }

  function renderOtpEntry(message, resendAfterSeconds) {
    clearAuthTimer();
    var requestedWait = Math.max(0, Number(resendAfterSeconds) || 0);
    if (requestedWait) otpResendAvailableAt = Date.now() + requestedWait * 1000;
    var wait = Math.max(0, Math.ceil((otpResendAvailableAt - Date.now()) / 1000));
    var controls =
      '<label class="auth-recovery__label" for="patient-otp">문자로 받은 6자리 인증번호</label>' +
      '<input class="auth-recovery__otp" id="patient-otp" name="one-time-code" type="text" inputmode="numeric" ' +
      'autocomplete="one-time-code" maxlength="6" pattern="[0-9]{6}" aria-describedby="auth-otp-help" />' +
      '<p class="auth-recovery__help" id="auth-otp-help">' +
      esc(message || "3분 안에 입력해 주세요.") +
      "</p>" +
      '<button class="auth-recovery__primary" type="button" id="auth-verify" disabled>확인</button>' +
      '<button class="auth-recovery__secondary" type="button" id="auth-issue"' +
      (wait ? " disabled" : "") +
      ">" +
      (wait ? "다시 받기 (" + wait + "초)" : "인증번호 다시 받기") +
      "</button>";
    showOnly(authCard("인증번호를 넣어주세요", "본인 확인이 끝나면 작성한 답을 바로 저장할게요.", controls));
    var input = el("patient-otp");
    if (input) input.focus();
    updateResendButton();
  }

  function updateResendButton() {
    var button = el("auth-issue");
    if (!button || !button.classList.contains("auth-recovery__secondary")) return;
    var remaining = Math.max(0, Math.ceil((otpResendAvailableAt - Date.now()) / 1000));
    button.disabled = remaining > 0;
    button.textContent = remaining ? "다시 받기 (" + remaining + "초)" : "인증번호 다시 받기";
    if (remaining) authTimer = window.setTimeout(updateResendButton, 1000);
  }

  function issueOtp() {
    var button = el("auth-issue");
    if (button) {
      button.disabled = true;
      button.textContent = "보내는 중…";
    }
    checkinApi
      .issueOtp(token)
      .then(function (result) {
        renderOtpEntry("인증번호는 3분 동안 사용할 수 있어요.", result.retry_after_seconds);
      })
      .catch(function (error) {
        if (error && error.code === "OTP_RESEND_TOO_SOON") {
          return renderOtpEntry(patientAuthGuidance(error).message, error.data && error.data.retry_after_seconds);
        }
        renderAuthGuidance(error);
      });
  }

  function verifyOtp() {
    var input = el("patient-otp");
    var code = input ? input.value.trim() : "";
    if (!/^\d{6}$/.test(code)) {
      if (el("auth-otp-help")) el("auth-otp-help").textContent = "숫자 6자리를 모두 입력해 주세요.";
      return;
    }
    var button = el("auth-verify");
    if (button) {
      button.disabled = true;
      button.textContent = "확인 중…";
    }
    checkinApi
      .verifyOtp(token, code)
      .then(function () {
        clearAuthTimer();
        var answer = pendingAnswer;
        pendingAnswer = null;
        if (answer) submitAnswer(answer);
      })
      .catch(function (error) {
        var guide = patientAuthGuidance(error);
        if (guide.action === "verify") return renderOtpEntry(guide.message, 0);
        if (guide.action === "retry") return renderOtpEntry(guide.message, 0);
        if (guide.action === "issue") return renderAuthGuidance(error);
        renderAuthGuidance(error);
      });
  }

  function submitAnswer(answer) {
    showOnly(authCard("기록을 저장하고 있어요", "잠시만 기다려 주세요.", ""));
    checkinApi
      .save(token, answer)
      .then(function (result) {
        pendingAnswer = null;
        showOnly(doneHtml(result));
      })
      .catch(function (error) {
        if (error && error.code === "PATIENT_SESSION_EXPIRED") {
          pendingAnswer = answer;
          return renderAuthGuidance(error);
        }
        if (error && (error.code === "LINK_EXPIRED" || error.code === "LINK_NOT_FOUND")) {
          pendingAnswer = null;
          return renderAuthGuidance(error);
        }
        el("state").hidden = true;
        el("form").hidden = false;
        el("save").disabled = false;
        el("error").textContent = "저장하지 못했어요. 인터넷 연결을 확인한 뒤 다시 눌러 주세요.";
        el("error").hidden = false;
      });
  }


  /* 고르는 즉시 의료진 화면에 「이 환자를 봐 주세요」를 보낸다 (KEY-138).

     **이것은 기록이 아니다.** 의무기록은 [저장] 이 남기는 답이다. 이 신호는
     「지금 이 환자가 중단을 눌렀다」는 사실일 뿐이라, 앞 신호를 지우지 않는다
     — `docs/api/patient.md` 3절.

     저장 전에 화면을 닫아도 의료진이 알 수 있게 하는 것이 전부다. 임의 중단은
     치료가 잘 듣는 2~3개월 차에 가장 많고(P7-5 노트), 그때 놓치면 다음 진료
     때까지 아무도 모른다.

     **고른 것을 그대로 보낸다 — 알릴지는 서버가 정한다.** 알림 대상만 걸러
     보내면 답을 바꿔도 앞 신호가 그대로 남는다. 「불편해서 중단했어요」를
     골랐다가 「잘 먹고 있어요」로 바꾸고 저장 없이 닫으면, 의원은 없는 문제를
     쫓는다. 옆에 저장된 답을 함께 보이는 것으로는 못 막는다 — **저장을 안 했으니
     옆에 놓일 답이 없다.** 마지막 신호가 지금 환자의 답이다.

     **실패해도 아무 말 하지 않는다.** 환자는 자기가 알림을 보내는 줄 모른다.
     여기서 오류를 띄우면 무엇을 잘못했는지 알 수 없는 사람에게 사과를 시킨다.
     못 간 것은 [저장] 이 받쳐 준다 — 서버가 저장된 답으로 신호 상태를 맞춘다. */
  function sendSignal(key) {
    var previous = signals.lastSent();
    var stamp = signals.next(key);
    if (!stamp) return; // 연달아 같은 답 — 보내지 않는다
    checkinApi.signal(token, key, stamp).catch(function () {
      /* **값이 아니라 이 호출을 넘긴다.** 늦게 실패한 옛 요청이 그 사이
         되살아난 같은 값을 지우지 않도록 (`#79` 리뷰). */
      signals.failed(stamp, previous);
    });
  }

  /* ── 이벤트 ─────────────────────────────────────────── */

  document.addEventListener("click", function (event) {
    if (event.target.id === "auth-issue") {
      issueOtp();
      return;
    }
    if (event.target.id === "auth-verify") {
      verifyOtp();
      return;
    }

    /* 눌러도 아무 일이 없었다 (`#55` 리뷰). 환자 안전과 닿은 버튼이라
       가만히 있는 것이 가장 나쁘다.

       문의 창구(P6 챗봇)는 아직 없다. 없는 것을 있는 척하지 않고, **지금
       할 수 있는 일**을 알려 준다 — 적어 둔 답은 이미 남았고, 급하면 의원에
       전화하는 길이 있다. */
    if (event.target.id === "ask") {
      var box = el("ask-note");
      if (box) {
        box.hidden = false;
        box.textContent = "문의 창구는 준비 중이에요. 급하시면 진료받으신 의원으로 전화해 주세요 — 여기 적으신 답은 그대로 전달돼요.";
        box.focus();
      }
      return;
    }

    var med = event.target.closest("[data-med]");
    if (med) {
      picked = med.getAttribute("data-med");
      renderMedication();
      renderSave();
      sendSignal(picked);
      return;
    }

    var pain = event.target.closest("[data-pain]");
    if (pain) {
      painHad = pain.getAttribute("data-pain") === "yes";
      if (!painHad) painTypes = [];
      renderPain();
      return;
    }

    var type = event.target.closest("[data-type]");
    if (type) {
      var key = type.getAttribute("data-type");
      var at = painTypes.indexOf(key);
      if (at === -1) painTypes.push(key);
      else painTypes.splice(at, 1);
      renderPain();
      return;
    }

    if (event.target.id === "save" && picked) {
      event.target.disabled = true;
      el("error").hidden = true;
      var saveStamp = signals.mark();
      submitAnswer({
        medication: picked,
        pain: painHad === null ? null : { had: painHad, score: painHad ? painScore : null, types: painTypes },
        note: el("note").value.trim() || null,
          /* 이 답이 의료진 알림을 만들어야 하는가. 서버가 정하는 값이지만
             화면이 **받은 그대로 되돌려** 준다 — 화면이 「원장님께 전해
             드릴게요」라고 말해 놓고 서버는 모르는 상태를 막는다 (`#55` 리뷰).

             다만 이건 **저장할 때**다. 와이어프레임은 고르는 즉시 알리라고
             하는데, 그러려면 계약이 하나 더 필요하다 — 아래 주석 참고. */
        notify: notifyFor(data && data.answers, picked),
          /* **저장도 신호와 같은 규칙으로 순번을 받는다.** 예전에는 서버가
             저장에 고정값(「늘 가장 나중」)을 박았는데, 그러면 저장을 두 번
             했을 때 둘이 같아져 뒤엣것이 앞엣것을 못 덮는다 — 지금은 도착
             차례가 받쳐 주고 있었을 뿐이라, 망이 뒤집히면 그대로 어긋난다
             (이희진 님 `#79` 리뷰). 순번은 **이 호출 시점에** 뗀다.

             답을 접지 않는 `mark()` 를 쓴다. 같은 답을 다시 저장해도 그것은
             새 저장이다. */
        client_id: saveStamp.clientId,
        client_session_id: saveStamp.session,
        client_sequence: saveStamp.sequence,
      });
    }
  });

  document.addEventListener("input", function (event) {
    if (event.target.id === "patient-otp") {
      event.target.value = event.target.value.replace(/\D/g, "").slice(0, 6);
      var verify = el("auth-verify");
      if (verify) verify.disabled = event.target.value.length !== 6;
      return;
    }
    if (event.target.id === "pain-score") {
      painScore = Number(event.target.value);
      el("score-value").textContent = painScore + " / 10";
    }
  });

  /* ── 시작 ───────────────────────────────────────────── */

  if (!token) {
    renderAuthGuidance({ code: "LINK_NOT_FOUND", data: {} });
    return;
  }

  checkinApi
    .read(token)
    .then(function (result) {
      data = result;
      el("round").textContent = data.round_label;
      if (data.answered) {
        /* 이미 답한 회차. 다시 묻지 않는다 — 두 번 답하면 어느 것이 맞는지
           의료진이 알 수 없고, 환자는 「저장이 안 됐나」로 읽는다. */
        return showOnly(
          '<div class="done"><p class="done__mark">✓</p>' +
            '<h1 class="done__title">이미 답해 주셨어요</h1>' +
            '<p class="done__note">다음 확인 문자가 오면 그때 다시 여쭤볼게요.</p></div>',
        );
      }
      renderMedication();
      renderPain();
      renderSave();
    })
    .catch(function (error) {
      /* 링크는 3일 뒤 닫힌다. **오류가 아니라 안내다** — 환자가 잘못한 것이
         아니므로 「오류」라고 말하지 않는다. */
      if (error && (error.code === "LINK_EXPIRED" || error.code === "LINK_NOT_FOUND")) {
        return renderAuthGuidance(error);
      }
      showOnly(
        '<div class="done"><h1 class="done__title">불러오지 못했어요</h1>' +
          '<p class="done__note">잠시 뒤 다시 열어 주세요.</p></div>',
      );
    });
})();
