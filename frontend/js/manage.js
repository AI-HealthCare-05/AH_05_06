/* 관리 (S2) — 지금 담는 것은 **발송 예정(S2-3)** 하나다. KEY-234.
 *
 * 와이어프레임 원문 캡션: 「앞으로 나갈 것 · 보류는 맨 위에서 이유와 함께」.
 *
 * **이 화면은 훑는 자리가 아니라 잡는 자리다.** 스탭이 묻는 것은 「지금
 * 무엇을 손대야 하나」 하나여서, 안 나간 것(실패 · 보류)을 맨 위에 놓고
 * 예정을 그 아래 잇는다. 두 화면으로 가르지 않는다.
 *
 * 규칙은 `js/schedule-rules.js` 에 있다 — 여기 있는 것은 그리는 일뿐이다.
 */
(function () {
  var days = 7;
  var page = null;
  var saying = "불러오는 중…";

  function el(id) {
    return document.getElementById(id);
  }

  /* ── 그리기 ───────────────────────────────────────── */

  function chipsHtml() {
    return scheduleChips(page && page.counts, days)
      .map(function (chip) {
        var mark = chip.strong ? " chip--all" : chip.bad ? " chip--bad" : "";
        return (
          '<span class="chip chip--count' +
          mark +
          '">' +
          esc(chip.say) +
          "</span>"
        );
      })
      .join("");
  }

  function windowHtml() {
    return SCHEDULE_WINDOWS.map(function (option) {
      return (
        '<option value="' +
        option.days +
        '"' +
        (option.days === days ? " selected" : "") +
        ">" +
        esc(option.say) +
        "</option>"
      );
    }).join("");
  }

  function actionHtml(row) {
    var action = rowAction(row);
    if (!action) return '<span class="send__none">—</span>';
    return (
      '<a class="button-ghost button-ghost--sm" href="' +
      esc(action.href) +
      '">' +
      esc(action.say) +
      "</a>"
    );
  }

  function rowHtml(row) {
    var stuck = isUnsent(row);
    var state = messageState(row.status);
    return (
      '<tr class="' +
      (stuck ? "send__row send__row--stuck" : "send__row") +
      '">' +
      "<td>" +
      esc(whenSaying(row.scheduled_at)) +
      "</td>" +
      "<td>" +
      esc(row.name) +
      ' <span class="send__chart">' +
      esc(row.hospital_patient_no) +
      "</span></td>" +
      '<td class="send__who">' +
      esc(identityOf(row)) +
      "</td>" +
      "<td>" +
      esc(row.prescription_set || "—") +
      "</td>" +
      "<td>" +
      esc(MESSAGE_SAYING[row.kind] || row.kind) +
      "</td>" +
      '<td class="' +
      (state.bad ? "send__state send__state--bad" : "send__state") +
      '">' +
      esc(state.mark + " " + messageSaying(row)) +
      "</td>" +
      "<td>" +
      actionHtml(row) +
      "</td>" +
      "</tr>"
    );
  }

  /* 「오늘 18:00」 · 「08-14 10:00」 — 오늘 것만 날짜를 지운다.
     원문 표기다. 오늘이 몇 건인지가 이 화면에서 가장 급한 물음이라, 그 줄이
     눈에 먼저 걸려야 한다. */
  function whenSaying(iso) {
    var at = new Date(iso);
    if (isNaN(at.getTime())) return String(iso || "");
    var pad = function (n) {
      return (n < 10 ? "0" : "") + n;
    };
    var clock = pad(at.getHours()) + ":" + pad(at.getMinutes());
    var today = new Date();
    var sameDay =
      at.getFullYear() === today.getFullYear() &&
      at.getMonth() === today.getMonth() &&
      at.getDate() === today.getDate();
    return sameDay
      ? "오늘 " + clock
      : pad(at.getMonth() + 1) + "-" + pad(at.getDate()) + " " + clock;
  }

  function tableHtml() {
    var rows = scheduleOrder((page && page.items) || []);
    if (!rows.length) {
      return (
        '<p class="send__blank">' +
        esc(saying || "나갈 문자가 없습니다") +
        "</p>"
      );
    }
    return (
      '<div class="table-wrap"><table class="past send">' +
      "<thead><tr>" +
      "<th>예정 시각</th><th>환자</th><th>식별정보</th><th>세트명</th><th>종류</th><th>상태</th><th>할 일</th>" +
      "</tr></thead><tbody>" +
      rows.map(rowHtml).join("") +
      "</tbody></table></div>"
    );
  }

  function render() {
    el("chips").innerHTML = chipsHtml();
    el("days").innerHTML = windowHtml();
    el("table").innerHTML = tableHtml();
    el("summary").textContent = page ? scheduleSummary(page.counts, days) : "";
    var cut = truncationNote(page);
    el("cut").textContent = cut;
    el("cut").hidden = !cut;
  }

  /* ── 불러오기 ─────────────────────────────────────── */

  function load() {
    saying = "불러오는 중…";
    page = null;
    render();
    return messagesApi
      .scheduled(days)
      .then(function (data) {
        page = data;
        saying = "";
        render();
      })
      .catch(function (error) {
        saying = errorMessage(
          error,
          [
            {
              status: 403,
              say: "이 화면은 스탭 또는 의사 계정으로 볼 수 있습니다.",
            },
          ],
          "발송 예정을 불러오지 못했습니다. 잠시 뒤 다시 시도해 주세요.",
        );
        render();
      });
  }

  /* ── 손 ───────────────────────────────────────────── */

  el("days").addEventListener("change", function () {
    days = Number(this.value) || 7;
    load();
  });

  var logout = document.getElementById("logout");
  if (logout) {
    logout.addEventListener("click", function () {
      session.clear();
      location.replace("/login.html");
    });
  }

  render();

  requireSession().then(function (who) {
    el("who-name").textContent = who.name;
    el("who-roles").textContent = roleLabel(who.roles);
    return load();
  });
})();
