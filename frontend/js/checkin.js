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

(function () {
  var el = function (id) {
    return document.getElementById(id);
  };

  var data = null;
  var token = new URLSearchParams(location.search).get("t") || "synthetic-link-token";

  var picked = null; // 복약 답
  var painHad = null; // true · false · null(아직 안 고름)
  var painScore = 4;
  var painTypes = [];

  function esc(text) {
    return String(text == null ? "" : text).replace(/[&<>"]/g, function (ch) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[ch];
    });
  }

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
    if (info.ask) html += '<button class="fold__ask" type="button">💬 문의하기</button>';
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
      "<dt>다음 진료</dt><dd>" +
      esc(result.next_visit) +
      "</dd></dl>" +
      '<a class="done__link" href="/guide.html">복약지도 다시 보기</a>' +
      '<p class="done__note">이 화면은 저절로 넘어가지 않아요 · 다 보시고 닫으셔도 됩니다</p>' +
      "</div>"
    );
  }

  function showOnly(html) {
    el("form").hidden = true;
    el("state").innerHTML = html;
    el("state").hidden = false;
  }

  /* ── 이벤트 ─────────────────────────────────────────── */

  document.addEventListener("click", function (event) {
    var med = event.target.closest("[data-med]");
    if (med) {
      picked = med.getAttribute("data-med");
      renderMedication();
      renderSave();
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
      checkinApi
        .save(token, {
          medication: picked,
          pain: painHad === null ? null : { had: painHad, score: painHad ? painScore : null, types: painTypes },
          note: el("note").value.trim() || null,
        })
        .then(function (result) {
          showOnly(doneHtml(result));
        })
        .catch(function () {
          event.target.disabled = false;
          el("error").textContent = "저장하지 못했어요. 잠시 뒤 다시 눌러 주세요.";
          el("error").hidden = false;
        });
    }
  });

  document.addEventListener("input", function (event) {
    if (event.target.id !== "pain-score") return;
    painScore = Number(event.target.value);
    el("score-value").textContent = painScore + " / 10";
  });

  /* ── 시작 ───────────────────────────────────────────── */

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
      if (error && error.code === "LINK_EXPIRED") {
        return showOnly(
          '<div class="done"><h1 class="done__title">링크가 만료됐어요</h1>' +
            '<p class="done__note">보내드린 링크는 3일 동안 열려 있어요.<br />' +
            "다음 확인 문자가 오면 그때 답해 주셔도 괜찮습니다.</p></div>",
        );
      }
      showOnly(
        '<div class="done"><h1 class="done__title">불러오지 못했어요</h1>' +
          '<p class="done__note">잠시 뒤 다시 열어 주세요.</p></div>',
      );
    });
})();
