/* 관리 (S2) — 발송 예정(S2-3) · 발송 이력(S2-4). KEY-234.
 *
 * 원문은 두 프레임이지만 상단바도 세그먼트 탭도 같다. **한 화면 안에서
 * 갈래만 바꾼다** — 화면을 둘로 가르면 탭을 누를 때마다 골격을 다시 세우게
 * 되고, 그 사이 한 번 깜빡인다.
 *
 * 묻는 것이 다르다.
 *
 *   발송 예정   앞으로 무엇이 나가나 — 안 나간 것이 맨 위, 시각 오름차순
 *   발송 이력   무엇이 나갔나       — 실패가 맨 위, 최신순
 *
 * 규칙은 `js/schedule-rules.js` 와 `js/history-rules.js` 에 있다. 여기 있는
 * 것은 그리는 일뿐이다.
 */
(function () {
  /* **환자 관리가 첫 갈래다** — 원문의 세그먼트 탭 차례가 그렇고, 「오늘이
     아닌 환자도 여기서 찾는다」가 이 화면을 여는 까닭이다. */
  var view = "roster";
  var days = 7;
  var span = 7;
  var page = null;
  var saying = "불러오는 중…";
  var downloading = false;
  /* **여기 이름을 지역 변수와 겹치지 않게 둔다.** 기간 핸들러 안에서
     `var chosen` 을 다시 선언했더니 고른 칩이 그 안에 갇혔다 — 이 저장소에서
     `picked` 로 한 번 겪은 함정이다. */
  var chosen = "ALL";
  /* 갈래마다 고른 칩이 다르다 — 발송 예정에서 「실패」를 보다 이력으로
     넘어갔을 때 거기서도 「실패」가 골라져 있으면 놀란다. */
  var chip = { schedule: "total", history: "total" };
  var keyword = "";
  var opened = null; // 펼친 줄의 환자 번호
  var adjustingMessage = null;
  var adjustingMessageSaving = false;

  var ROSTER_PAGE = 50;
  var HISTORY_BLOCKS = 3;
  //: 글자를 멈춘 뒤 기다리는 시간(ms)
  var ROSTER_TYPING_WAIT = 250;

  function el(id) {
    return document.getElementById(id);
  }

  function range() {
    return historyRange(span);
  }

  /* ── 위쪽 줄 ──────────────────────────────────────── */

  /* **세 갈래가 같은 칩을 쓴다.** 셋 다 누르면 걸러지는 거르개다 — 원문이
     「전체 42」를 고른 상태로 그리고, 고른 상태가 있다는 것은 다른 것도 고를
     수 있다는 뜻이다. 그리는 자리를 하나로 두어 모양이 갈리지 않게 한다. */
  function chipsHtml() {
    var chips =
      view === "roster"
        ? rosterChips(page && page.counts, chosen)
        : view === "schedule"
          ? scheduleChips(page && page.counts, days, chip.schedule)
          : historyChips(page && page.counts, chip.history);
    return chips
      .map(function (one) {
        var mark = one.on ? " chip--on" : one.bad ? " chip--bad" : "";
        return (
          '<button class="chip' +
          mark +
          '" type="button" data-chip="' +
          esc(one.key) +
          '" aria-pressed="' +
          (one.on ? "true" : "false") +
          '">' +
          esc(one.say) +
          "</button>"
        );
      })
      .join("");
  }

  function spanHtml() {
    var options = view === "schedule" ? SCHEDULE_WINDOWS : HISTORY_SPANS;
    var now = view === "schedule" ? days : span;
    return options
      .map(function (option) {
        var say = view === "schedule" ? option.say : spanSaying(option.days);
        return (
          '<option value="' +
          option.days +
          '"' +
          (option.days === now ? " selected" : "") +
          ">" +
          esc(say) +
          "</option>"
        );
      })
      .join("");
  }

  /* ── 표 ───────────────────────────────────────────── */

  /* 「오늘 18:00」 · 「08-14 10:00」 — 오늘 것만 날짜를 지운다. 원문 표기다.
     오늘이 몇 건인지가 이 화면에서 가장 급한 물음이라 그 줄이 눈에 먼저
     걸려야 한다.

     **의원 시계로 읽는다**(`js/clinic-clock.js`) — `new Date(...).getHours()`
     로 읽으면 보는 사람의 시간대로 옮겨져, 시간대를 다르게 맞춘 노트북에서는
     같은 진료가 다른 시각으로 뜬다. */
  function whenSaying(iso) {
    var clock = clinicTime(iso);
    if (!clock) return String(iso || "");
    return isClinicToday(iso)
      ? "오늘 " + clock
      : clinicMonthDay(iso) + " " + clock;
  }

  function whoHtml(row) {
    return (
      "<td>" +
      esc(row.name) +
      ' <span class="send__chart">' +
      esc(row.hospital_patient_no) +
      '</span></td><td class="send__who">' +
      esc(identityOf(row)) +
      "</td><td>" +
      esc(row.prescription_set || "—") +
      "</td>"
    );
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

  function scheduleActionHtml(row) {
    if (!canAdjustScheduledMessage(row)) {
      return actionHtml(row);
    }

    return (
      '<button class="button-ghost button-ghost--sm" type="button" ' +
      'data-adjust-message="' +
      esc(row.guide_message_id) +
      '">' +
      "시각 변경" +
      "</button>"
    );
  }

    function scheduleInputValue(iso) {
    var day = clinicDay(iso);
    var time = clinicTime(iso);
    return day && time ? day + "T" + time : "";
  }

  function scheduleAdjustmentHtml(row) {
    return (
      '<form id="schedule-adjust-form">' +
      '<h2 class="modal__title" id="modal-title">예약 시각 변경</h2>' +
      '<p class="modal__note">' +
      esc(row.name) +
      " · " +
      esc(MESSAGE_SAYING[row.kind] || row.kind) +
      "</p>" +
      '<label for="schedule-adjust-at">새 발송 시각</label>' +
      '<input id="schedule-adjust-at" name="scheduled_at" ' +
      'type="datetime-local" step="60" required value="' +
      esc(scheduleInputValue(row.scheduled_at)) +
      '">' +
      '<p class="modal__note" id="schedule-adjust-error" ' +
      'role="alert" hidden></p>' +
      '<div class="modal__acts">' +
      '<button class="button-ghost" type="button" data-close>취소</button>' +
      '<button class="button-primary" type="submit" ' +
      'id="schedule-adjust-save">저장</button>' +
      "</div>" +
      "</form>"
    );
  }

  function openScheduleAdjustment(row) {
    adjustingMessage = row;
    adjustingMessageSaving = false;

    el("modal-body").innerHTML = scheduleAdjustmentHtml(row);
    el("modal").hidden = false;
    el("schedule-adjust-at").focus();
  }

  function stateHtml(row) {
    var state = messageState(row.status);
    return (
      '<td class="' +
      (state.bad ? "send__state send__state--bad" : "send__state") +
      '">' +
      esc(state.mark + " " + messageSaying(row)) +
      "</td>"
    );
  }

  function scheduleRowHtml(row) {
    return (
      '<tr class="' +
      (isUnsent(row) ? "send__row send__row--stuck" : "send__row") +
      '"><td>' +
      esc(whenSaying(row.scheduled_at)) +
      "</td>" +
      whoHtml(row) +
      "<td>" +
      esc(MESSAGE_SAYING[row.kind] || row.kind) +
      "</td>" +
      stateHtml(row) +
      "<td>" +
      scheduleActionHtml(row) +
      "</td></tr>"
    );
  }

  function historyRowHtml(row) {
    return (
      '<tr class="' +
      (isFailed(row) ? "send__row send__row--stuck" : "send__row") +
      '"><td>' +
      esc(whenSaying(row.happened_at)) +
      "</td>" +
      whoHtml(row) +
      stateHtml(row) +
      '<td class="send__read">' +
      esc(viewedSaying(row)) +
      "</td><td>" +
      actionHtml(row) +
      "</td></tr>"
    );
  }

  function rosterRowHtml(row) {
    var badge = flagsSaying(row.flags);
    var detail = statusLabel(row.detail_status);
    return (
      '<tr class="' +
      (badge ? "send__row send__row--stuck" : "send__row") +
      '" data-patient="' +
      esc(row.patient_id) +
      '"><td>' +
      esc(row.hospital_patient_no) +
      "</td><td>" +
      esc(row.name) +
      '</td><td class="send__who">' +
      esc(identityOf(row)) +
      "</td><td>" +
      esc(row.diagnosis_name || "—") +
      "</td><td>" +
      esc(row.doctor ? row.doctor.name : "—") +
      "</td><td>" +
      esc(formatPhone(row.phone)) +
      "</td><td>" +
      esc(consentSaying(row)) +
      "</td><td>" +
      esc(visitedDay(row) || "—") +
      "</td><td>" +
      esc(categoryLabel(row.work_category)) +
      '</td><td class="' +
      (badge ? "send__state send__state--bad" : "send__state") +
      '">' +
      esc(stateSaying(detail, badge)) +
      "</td></tr>" +
      (opened === row.patient_id ? cardHtml(row) : "")
    );
  }

  /* 펼친 카드 — 원문에서 줄을 누르면 아래에 그 환자가 선다. */
  function cardHtml(row) {
    var lines = [
      esc(row.name) +
        " · 차트 " +
        esc(row.hospital_patient_no) +
        " · " +
        esc(row.birth_date) +
        " · " +
        esc(formatPhone(row.phone)),
      esc(
        [row.diagnosis_name, visitedDay(row) ? visitedDay(row) + " 진료" : ""]
          .filter(Boolean)
          .join(" · "),
      ),
    ];
    var badge = flagsSaying(row.flags);
    if (badge)
      lines.push('<span class="send__state--bad">' + esc(badge) + "</span>");
    var buttons =
      '<button class="button-ghost button-ghost--sm" type="button" data-history="' +
      esc(row.patient_id) +
      '">전체 이력 보기</button>';
    buttons += rosterActions(row)
      .map(function (action) {
        return (
          '<a class="button-ghost button-ghost--sm" href="' +
          esc(action.href) +
          '">' +
          esc(action.say) +
          "</a>"
        );
      })
      .join("");
    return (
      '<tr class="send__card"><td colspan="10"><div class="rostercard"><div class="rostercard__lines">' +
      lines
        .map(function (line) {
          return "<p>" + line + "</p>";
        })
        .join("") +
      '</div><div class="rostercard__acts">' +
      buttons +
      "</div></div></td></tr>"
    );
  }

  var HEADS = {
    roster: [
      "차트",
      "이름",
      "식별정보",
      "질환",
      "담당",
      "전화번호",
      "문자 동의",
      "마지막 진료",
      "기본 상태",
      "세부 상태",
    ],
    schedule: [
      "예정 시각",
      "환자",
      "식별정보",
      "세트명",
      "종류",
      "상태",
      "할 일",
    ],
    history: [
      "발송일시",
      "환자",
      "식별정보",
      "세트명",
      "발송상태",
      "열람여부",
      "할 일",
    ],
  };

  var BLANK = {
    roster: "조회된 환자가 없습니다",
    schedule: "발송 예정인 문자가 없습니다",
  };

  function tableHtml() {
    var given = (page && page.items) || [];
    /* **환자 관리는 서버가 준 차례 그대로 그린다.** 여기서 다시 세우면
       다음 쪽이 앞 쪽과 겹치거나 빠진다 — 커서가 서버 차례를 따라간다. */
    var rows =
      view === "roster"
        ? given
        : view === "schedule"
          ? scheduleOrder(filterScheduled(given, chip.schedule))
          : historyOrder(filterHistory(given, chip.history));
    if (!rows.length) {
      var blank =
        BLANK[view] || rangeSaying(range()) + " 발송된 문자가 없습니다";
      return '<p class="send__blank">' + esc(saying || blank) + "</p>";
    }
    var draw =
      view === "roster"
        ? rosterRowHtml
        : view === "schedule"
          ? scheduleRowHtml
          : historyRowHtml;
    return (
      '<div class="table-wrap"><table class="past send"><thead><tr>' +
      HEADS[view]
        .map(function (head) {
          return "<th>" + esc(head) + "</th>";
        })
        .join("") +
      "</tr></thead><tbody>" +
      rows.map(draw).join("") +
      "</tbody></table></div>"
    );
  }

  /* ── 아래쪽 ───────────────────────────────────────── */

  function render() {
    el("chips").innerHTML = chipsHtml();
    el("days").innerHTML = spanHtml();
    el("table").innerHTML = tableHtml();

    /* 갈래마다 그 줄의 도구가 다르다 — 환자 관리는 검색과 등록, 나머지 둘은
       기간. 한 자리에서 갈아 끼우면 줄이 흔들리지 않는다. */
    el("roster-top").hidden = view !== "roster";
    el("period-top").hidden = view === "roster";

    var period = el("period");
    period.textContent = view === "history" ? rangeSaying(range()) : "";
    period.hidden = view !== "history";

    el("summary").textContent =
      view === "roster"
        ? rosterSummary(page)
        : view === "schedule"
          ? page
            ? scheduleSummary(page.counts, days)
            : ""
          : historySummary(page);

    var cut = view === "schedule" ? truncationNote(page) : "";
    el("cut").textContent = cut;
    el("cut").hidden = !cut;

    el("csv").hidden = view !== "history";
    el("csv").disabled = downloading || !page;
    el("csv").textContent = downloading ? "생성 중…" : "CSV 내려받기";

    el("note-roster").hidden = view !== "roster";
    el("note-schedule").hidden = view !== "schedule";
    el("note-history").hidden = view !== "history";

    var tabs = document.querySelectorAll("#tabs .tab");
    for (var i = 0; i < tabs.length; i++) {
      var name = tabs[i].getAttribute("data-view");
      if (name) tabs[i].setAttribute("aria-selected", String(name === view));
    }
  }

  /* ── 환자 이력 모달 (S2-2) ───────────────────────── */

  function blockHtml(block) {
    var lines = [
      guideSaying(block),
      checksSaying(block),
      courseEndSaying(block),
    ].filter(Boolean);
    return (
      '<section class="hist"><h3 class="hist__head">' +
      esc(courseSaying(block)) +
      "</h3>" +
      lines
        .map(function (line) {
          return '<p class="hist__line">' + esc(line) + "</p>";
        })
        .join("") +
      "</section>"
    );
  }

  function modalHtml(body) {
    var who = [
      body.hospital_patient_no ? "차트 " + body.hospital_patient_no : "",
      body.diagnosis_name,
      body.doctor ? body.doctor.name + " 원장" : "",
      formatPhone(body.phone),
    ]
      .filter(Boolean)
      .join(" · ");
    var blocks = (body.visits || []).map(blockHtml).join("");
    return (
      '<div class="modal__top"><div><h2 class="modal__title" id="modal-title">' +
      esc(body.name) +
      ' 님 이력</h2><p class="modal__note">' +
      esc(who) +
      "</p></div>" +
      '<button class="icon-button" type="button" data-close aria-label="닫기">✕</button></div>' +
      (blocks || '<p class="send__blank">지난 진료가 없습니다</p>') +
      '<p class="modal__note">' +
      esc(historyCountSaying(body)) +
      "</p>" +
      '<p class="note">ⓘ 발송 · 열람 · 응답 기록입니다 — 직원 열람 기록과 토큰 이력은 담지 않습니다</p>' +
      '<div class="modal__acts"><button class="button-ghost" type="button" data-close>닫기</button></div>'
    );
  }

  function openHistory(patientId) {
    var box = el("modal");
    el("modal-body").innerHTML = '<p class="send__blank">불러오는 중…</p>';
    box.hidden = false;
    patientsApi
      .history(patientId, HISTORY_BLOCKS)
      .then(function (body) {
        el("modal-body").innerHTML = modalHtml(body);
      })
      .catch(function (error) {
        el("modal-body").innerHTML =
          '<p class="modal__title">이력을 불러오지 못했습니다</p><p class="modal__note">' +
          esc(
            errorMessage(
              error,
              [{ status: 404, say: "환자를 찾을 수 없습니다." }],
              "잠시 후 다시 시도해 주세요.",
            ),
          ) +
          '</p><div class="modal__acts"><button class="button-ghost" type="button" data-close>닫기</button></div>';
      });
  }

  function closeHistory() {
    el("modal").hidden = true;
    el("modal-body").innerHTML = "";
    adjustingMessage = null;
    adjustingMessageSaving = false;
  }

  /* 배경을 눌러도 닫힌다 — 원문 「배경 클릭도 닫기」. */
  el("modal").addEventListener("click", function (event) {
    if (event.target === el("modal") || event.target.closest("[data-close]"))
      closeHistory();
  });

  el("modal").addEventListener("submit", function (event) {
    var form = event.target.closest("#schedule-adjust-form");
    if (!form) return;

    event.preventDefault();

    if (!adjustingMessage || adjustingMessageSaving) return;

    var input = el("schedule-adjust-at");
    var errorBox = el("schedule-adjust-error");
    var saveButton = el("schedule-adjust-save");
    var value = input.value;

    if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value)) {
      errorBox.hidden = false;
      errorBox.textContent = "발송 날짜와 시각을 입력해 주세요.";
      return;
    }

    adjustingMessageSaving = true;
    saveButton.disabled = true;
    errorBox.hidden = true;
    errorBox.textContent = "";

    messagesApi
      .update(adjustingMessage.guide_message_id, {
        scheduled_at: value + ":00+09:00",
      })
      .then(function () {
        closeHistory();
        return load();
      })
      .catch(function (error) {
        adjustingMessageSaving = false;
        saveButton.disabled = false;
        errorBox.hidden = false;
        errorBox.textContent = errorMessage(
          error,
          [
            {
              status: 404,
              say: "예약 문자를 찾을 수 없습니다.",
            },
            {
              status: 409,
              say: "이미 발송되었거나 상태가 변경되어 수정할 수 없습니다.",
            },
          ],
          "예약 시각을 저장하지 못했습니다. 잠시 뒤 다시 시도해 주세요.",
        );
      });
  });

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && !el("modal").hidden) closeHistory();
  });

  /* ── 불러오기 ─────────────────────────────────────── */

  function load() {
    saying = "불러오는 중…";
    page = null;
    render();
    var asked =
      view === "roster"
        ? patientsApi.roster(keyword, chosen, null, ROSTER_PAGE)
        : view === "schedule"
          ? messagesApi.scheduled(days)
          : messagesApi.history(range());
    return asked
      .then(function (data) {
        page = data;
        saying = "";
        render();
      })
      .catch(function (error) {
        saying = errorMessage(
          error,
          [{ status: 403, say: "스탭 또는 의사 계정만 조회할 수 있습니다." }],
          "목록을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.",
        );
        render();
      });
  }

  /* ── 손 ───────────────────────────────────────────── */

  el("tabs").addEventListener("click", function (event) {
    var tab = event.target.closest("[data-view]");
    if (!tab || tab.getAttribute("aria-disabled") === "true") return;
    var name = tab.getAttribute("data-view");
    if (name === view) return;
    view = name;
    load();
  });

  /* 칩을 누르면 그 분류만 본다 — 원문에서 상단 칩이 곧 거르개다. */
  el("chips").addEventListener("click", function (event) {
    var pressed = event.target.closest("[data-chip]");
    if (!pressed) return;
    var key = pressed.getAttribute("data-chip");

    /* **환자 관리만 서버에 다시 묻는다.** 저쪽은 의원 전체에서 골라 오는
       일이라 쪽이 달라지고, 나머지 둘은 이미 받은 창 안을 나누는 일이다. */
    if (view === "roster") {
      if (key === chosen) return;
      chosen = key;
      opened = null;
      return load();
    }
    if (chip[view] === key) return;
    chip[view] = key;
    render();
  });

  /* 줄을 누르면 아래에 그 환자가 선다. 다시 누르면 접힌다. */
  el("table").addEventListener("click", function (event) {
    var adjustButton = event.target.closest("[data-adjust-message]");

    if (adjustButton) {
      var messageId = Number(
        adjustButton.getAttribute("data-adjust-message"),
      );
      var rows = (page && page.items) || [];
      var message = rows.find(function (row) {
        return row.guide_message_id === messageId;
      });

      if (message && canAdjustScheduledMessage(message)) {
        openScheduleAdjustment(message);
      }
      return;
    }

    if (view !== "roster") return;
    var asked = event.target.closest("[data-history]");
    if (asked) return openHistory(Number(asked.getAttribute("data-history")));
    if (event.target.closest("a")) return; // 카드 안의 링크는 그대로 간다
    var row = event.target.closest("[data-patient]");
    if (!row) return;
    var id = Number(row.getAttribute("data-patient"));
    opened = opened === id ? null : id;
    render();
  });

  /* 검색은 **친 뒤 잠깐 기다렸다** 부른다 — 글자마다 부르면 한 이름에
     네댓 번 왕복한다. */
  var typing = null;
  el("roster-search").addEventListener("input", function () {
    var typed = this.value;
    clearTimeout(typing);
    typing = setTimeout(function () {
      keyword = typed.trim();
      opened = null;
      load();
    }, ROSTER_TYPING_WAIT);
  });

  el("days").addEventListener("change", function () {
    var picked = Number(this.value) || 7;
    if (view === "schedule") days = picked;
    else span = picked;
    load();
  });

  /* **받아 온 뒤 브라우저 안에서 파일로 만든다.** 주소에 토큰을 붙이지
     않으려는 것이다 — 주소는 브라우저 기록과 서버 접근 로그에 남는다. */
  el("csv").addEventListener("click", function () {
    if (downloading || !page) return;
    var asked = range();
    downloading = true;
    render();
    messagesApi
      .historyCsv(asked)
      .then(function (text) {
        var url = URL.createObjectURL(
          new Blob([text], { type: "text/csv;charset=utf-8" }),
        );
        var link = document.createElement("a");
        link.href = url;
        link.download =
          "send-history-" + asked.from + "-to-" + asked.to + ".csv";
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
      })
      .catch(function (error) {
        saying = errorMessage(error, [], "CSV 파일을 생성하지 못했습니다.");
        el("summary").textContent = saying;
      })
      .then(function () {
        downloading = false;
        render();
      });
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
