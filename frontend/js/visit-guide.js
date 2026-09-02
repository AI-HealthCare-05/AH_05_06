/* 환자 카드의 「안내문」·「최종 확인」·「현황」 탭 — S1-11~13 · D1-1~7.
 *
 * **와이어프레임에서 의사 화면은 별도 페이지가 아니다.** `D1-1` 골격이
 * 「좌 320 목록 / 우 960 본문 → 5단계 탭」이라고 적어 두었고, `D1-5` 는
 * 「5단계 탭은 여전히 최종 확인 ●」, `D1-6` 은 「5단계 탭에서 현황 ●」이다.
 * 21프레임(S1-1~14 · D1-1~7)이 이 한 화면에 있다.
 *
 * 1차 시연에서 의사와 스탭이 서로의 화면을 못 봐서 막힌 자리가 여기다.
 * 서버는 처음부터 그렇게 되어 있지 않았다 — `app/core/rbac.py` 에서
 *
 *     PATIENT_READ · PATIENT_WRITE · OCR_UPLOAD · GUIDE_DRAFT · SMS_SEND
 *         staff · doctor 둘 다
 *     GUIDE_APPROVE · GUIDE_RETURN
 *         doctor 만
 *
 * **가르는 것은 버튼이지 화면이 아니다.** 화면에서 감추는 것은 편의일 뿐이고
 * 실제 차단은 서버가 한다(KEY-9).
 */

/* 「최종 확인」 탭에서 무엇을 누를 수 있는가 — 역할이 정한다.
   IIFE 밖에 둔다. 화면을 그리는 코드는 검사가 못 닿지만 이 규칙은 닿는다. */
function finalActionsFor(roles) {
  var list = roles || [];
  var isDoctor = list.indexOf("doctor") !== -1;
  return {
    canApprove: isDoctor,
    canReturn: isDoctor,
    /* 못 누르는 이유를 말한다. 이유 없이 안 눌리는 버튼은 「고장났다」로 읽힌다. */
    why: isDoctor ? "" : "승인과 반려는 의사 계정에서 할 수 있습니다",
  };
}

/* 안내문이 아직 없을 때 무슨 말을 할 것인가. 진료 상태마다 다음 할 일이 다르다. */
function guideMissingSaying(error) {
  var code = error && error.code;
  if (code === "GUIDE_NOT_FOUND" || code === "NOT_FOUND") {
    return "아직 안내문이 없습니다 — 「진료기록」 탭에서 판독을 확정하면 만들어집니다";
  }
  if (code === "FORBIDDEN") return "이 안내문을 볼 권한이 없습니다";
  return "안내문을 불러오지 못했습니다 — 잠시 뒤 다시 열어 주세요";
}

(function () {
  "use strict";

  if (!document.getElementById("panel-guide")) return;

  var guide = null;
  var visitId = null;
  var me = null;
  var loadSeq = 0;
  /* **현황은 자기 번호표를 쓴다.** 안내문과 나눠 쓰면 서로를 취소시킨다 —
     둘을 같이 부르므로 뒤에 부른 쪽이 앞의 것을 늘 죽인다. */
  var timelineSeq = 0;
  var section = { guide: "medication", final: "medication" };

  function el(id) {
    return document.getElementById(id);
  }

  /* **누가 고칠 수 있나** — 서버와 같은 규칙을 화면도 쓴다.
   *
   * 스탭 확인 중이면 스탭이, 의사에게 넘긴 뒤에는 의사가 고친다
   * (`app/services/guides.py` 의 `edit_section`). 화면이 다른 규칙을 쓰면
   * 눌리는데 저장이 403 으로 떨어져, 스탭은 「내가 뭘 잘못했나」로 읽는다.
   *
   * 최종 확인 탭은 의사 차례라 의사만 고친다. */
  function canEditNow(prefix) {
    var isDoctor = ((me && me.roles) || []).indexOf("doctor") !== -1;
    if (prefix === "final") return isDoctor;
    /* 안내문 탭 — 넘기기 전이면 스탭도 고친다.
       **반려된 것도 스탭 차례다.** 반려는 「고쳐서 다시 올려라」는 뜻이라,
       이 자리에 그 상태가 빠지면 화면이 위에서는 「고친 뒤 다시 넘겨
       주세요」라 하고 아래서는 「의사 계정에서 할 수 있습니다」라 한다 —
       한 화면이 두 가지로 말한다 (Gomin-art 님 `#176` 리뷰). */
    return (
      isDoctor ||
      (guide && (guide.status === "STAFF_REVIEW" || guide.status === "APPROVAL_RETURNED"))
    );
  }

  /* 두 탭이 같은 안내문을 그린다 — 다른 것은 편집 권한과 아래 버튼뿐이다. */
  /* 문구를 치는 사이 다시 그리면 커서가 사라진다 — `innerHTML` 이 통째로
     바뀌기 때문이다. 치던 자리를 되돌려 준다 (판독 화면이 값 칸에 한 것과
     같은 처리다). */
  function keepCaretAround(box, run) {
    var live = box.querySelector("[data-sms-text]");
    var at = live && typeof live.selectionStart === "number" ? live.selectionStart : null;
    run();
    if (at === null) return;
    var next = box.querySelector("[data-sms-text]");
    if (!next) return;
    next.focus();
    next.setSelectionRange(at, at);
  }

  function renderOne(prefix, canEdit, keepCaret) {
    var vtabs = el(prefix + "-vtabs");
    var panel = el(prefix + "-panel");
    var warn = el(prefix + "-warn");
    if (!vtabs || !panel) return;

    if (!guide) {
      vtabs.innerHTML = "";
      panel.innerHTML = "";
      if (warn) warn.textContent = "";
      return;
    }

    var now = guideCurrentSection(guide.sections, section[prefix]);
    if (!now) return;
    section[prefix] = now.key;

    /* **한 판으로 그린다** — 제목 · 가로 탭 · 원문 · 미리보기가 한 덩어리다
       (와이어프레임 S1-11 · D1-1). 전에는 세로 탭과 본문이 따로 떠 있었다. */
    vtabs.innerHTML = "";
    var draw = function () {
      panel.innerHTML = guideScreenHtml(guide.sections, now.key, prefix, canEdit, guideEditingNow());
    };
    if (keepCaret) keepCaretAround(panel, draw);
    else draw();

    if (warn) {
      var line = guideWarnLine(guide.sections);
      warn.className = line.className;
      warn.textContent = line.text;
    }
  }

  /* 문자 설정(S1-14)에 넘길 값. **화면이 아는 것만** 모은다 — 서버가 회차·문구를
     주지 않으므로, 진료일과 환자 번호처럼 이미 손에 있는 것으로 셈한다.
     처방일수·소진 예정일은 판독 값에서 오는데 그 자리가 아직 없어 비워 둔다. */
  window.guideSmsPlan = function (mode) {
    var p = (guide && guide.patient) || {};
    /* **고칠 수 있는 때는 안내문 본문과 같은 규칙이다.** 두 규칙이 갈리면
       「문구는 고쳐지는데 본문은 403」 같은 화면이 나온다. */
    var canSave = !!guide && canEditNow(mode === "final" ? "final" : "guide");
    return {
      startIso: guide && guide.visited_at ? String(guide.visited_at).slice(0, 10) : "",
      runOutIso: "",
      phone: p.phone || "",
      values: { 환자명: p.name || "", 일차: 7, 의원명: "" },
      canSave: canSave,
      lockedSaying:
        guide && guide.status === "SCHEDULED_TO_SEND"
          ? "승인된 뒤에는 고칠 수 없습니다 — 현황에서 승인을 거두고 고쳐 주세요"
          : "지금은 고칠 수 없습니다",
      saying: smsSaying,
    };
  };

  /* 누른 뒤에 무슨 일이 일어났는지 한 줄. 작아서 화면낭독기가 읽어도
     시끄럽지 않다 — 다른 화면들과 같은 자리다. */
  function say(text) {
    /* **두 탭 모두에 쓴다.** 안내문 탭과 최종 확인 탭이 각자 알림 줄을
       갖는데, 한쪽에만 쓰면 다른 탭에서 누른 결과가 어디에도 안 보인다 —
       승인하고 「됐나?」를 묻게 된다. */
    ["guide-say", "final-say"].forEach(function (id) {
      var box = el(id);
      if (box) box.textContent = text;
    });
  }

  /* S1-11 하단 — 스탭이 확인을 마치고 의사에게 넘긴다. */
  function renderGuideActions() {
    var box = el("guide-actions");
    if (!box) return;
    if (!guide) {
      box.innerHTML = "";
      return;
    }

    var can = guideActionsFor(guide.status, me && me.roles, guide.returned_reason);
    box.innerHTML =
      '<button class="button-ghost button-ghost--sm" type="button" id="guide-reupload">진료기록 재업로드</button>' +
      '<span class="grow"></span>' +
      '<span class="note">' +
      esc(can.say) +
      /* **반려 사유를 그 자리에 붙인다.** 「고친 뒤 다시 넘겨 주세요」만 보고는
         무엇을 고쳐야 하는지 알 길이 없어 의사에게 다시 물어야 한다. */
      (can.why ? ' <span class="note__why">「' + esc(can.why) + "」</span>" : "") +
      "</span>" +
      (can.canSubmit
        ? '<button class="button-primary button-primary--sm" type="button" id="guide-submit">의사 승인 요청</button>'
        : "");
  }

  function renderFinalActions() {
    var box = el("final-actions");
    if (!box) return;
    if (!guide) {
      box.innerHTML = "";
      return;
    }

    var can = finalActionsFor(me && me.roles);
    if (!can.canApprove) {
      box.innerHTML = '<p class="note">' + esc(can.why) + "</p>";
      return;
    }

    /* **스탭이 넘긴 것만 승인한다.** 서버가 그렇게 막는데(GUIDE_NOT_PENDING),
       화면이 그대로 두면 눌러서 409 를 받고 「내가 뭘 잘못했나」로 읽힌다.
       왜 지금 못 누르는지를 대신 적는다. */
    var ready = guide.status === "APPROVAL_PENDING";
    box.innerHTML =
      '<button class="button-ghost" type="button" id="final-return"' +
      (ready ? "" : " disabled") +
      ">스탭에게 되돌리기</button>" +
      '<span class="grow"></span>' +
      (ready
        ? ""
        : '<span class="note">' +
          esc(
            guide.status === "STAFF_REVIEW"
              ? "스탭이 확인 중입니다 — 넘어오면 승인할 수 있습니다"
              : guide.status === "SCHEDULED_TO_SEND"
                ? "이미 승인되어 발송을 기다립니다"
                : "지금은 승인할 수 없습니다",
          ) +
          "</span>") +
      '<button class="button-primary" type="button" id="final-approve"' +
      (ready ? "" : " disabled") +
      ">승인</button>";
  }

  /* 「현황」 — 와이어프레임 D1-6. 이제 **진짜 기록**으로 찬다.
     사람이 한 일 · 환자가 한 일 · 확인 응답이 `GET /visits/{id}/timeline` 로
     한 줄기로 온다. 발송 예정만 아직 프레임이다 — 담는 표가 서버에 없다. */
  var timeline = null;

  function renderStatus() {
    var body = el("status-body");
    if (!body) return;

    if (!timeline) {
      body.innerHTML = '<p class="note">현황을 불러오는 중입니다…</p>';
      return;
    }

    var answer = null;
    for (var i = 0; i < timeline.entries.length; i++) {
      if (timeline.entries[i].event === "CHECK_IN_SUBMITTED") answer = timeline.entries[i];
    }

    /* 철회는 의사만, 그리고 **승인된 뒤에만** 보인다. 아직 승인 안 한 것에
       철회 버튼이 있으면 무엇을 되돌리는지가 흐려진다. */
    var canUnapprove =
      ((me && me.roles) || []).indexOf("doctor") !== -1 && !!guide && guide.status === "SCHEDULED_TO_SEND";

    body.innerHTML = statusScreenHtml({
      canUnapprove: canUnapprove,
      entries: timeline.entries,
      checkInSaying: answer
        ? timelineClock(answer.at) + " 응답 · " + (answer.note || "")
        : "아직 없음",
      /* **화면이 따로 셈하지 않는다.** 승인이 잡아 둔 날짜를 그대로 쓴다 —
         두 곳이 셈하면 어느 쪽이 진짜인지 알 수 없다. */
      messages: timeline.messages || [],
    });

    wireUnapprove();
  }

  /* 승인 철회 — 승인했는데 잘못된 것을 발견했을 때. */
  function wireUnapprove() {
    var back = el("status-unapprove");
    if (!back) return;

    back.addEventListener("click", function () {
      var wantedId = visitId;
      if (!confirm("승인을 거두면 예약된 문자가 모두 꺼집니다. 철회하시겠습니까?")) return;

      back.disabled = true;
      back.textContent = "철회하는 중…";

      doctorApi
        .unapprove(wantedId)
        .then(function () {
          /* 사이에 다른 환자로 옮겼으면 그 화면을 건드리지 않는다 */
          if (visitId !== wantedId) return;
          say("승인을 거뒀습니다 — 예약된 문자를 껐습니다");
          loadGuide(wantedId);
          loadTimeline(wantedId);
          /* 목록의 상태도 「발송 대기」에서 「승인 요청」으로 되돌아가야 한다 */
          document.dispatchEvent(new CustomEvent("visit:changed"));
        })
        .catch(function (err) {
          if (visitId !== wantedId) return;
          back.disabled = false;
          back.textContent = "승인 철회";
          say(
            err && err.code === "GUIDE_ALREADY_SENT"
              ? "이미 환자에게 나간 문자가 있어 철회할 수 없습니다 — 새 안내를 보내 주세요"
              : "철회하지 못했습니다. 잠시 뒤 다시 시도해 주세요",
          );
        });
    });
  }

  /* 현황은 안내문과 **따로 불러온다.** 안내문이 없어도 등록·열람 기록은
     있을 수 있고, 한 요청이 실패해도 다른 하나는 보여야 한다. */
  function loadTimeline(id) {
    var mine = ++timelineSeq;
    timeline = null;
    renderStatus();
    doctorApi
      .timeline(id)
      .then(function (data) {
        if (mine !== timelineSeq) return; // 늦게 온 답이 새 환자 화면에 붙으면 안 된다
        timeline = data;
        renderStatus();
      })
      .catch(function () {
        if (mine !== timelineSeq) return;
        var body = el("status-body");
        if (body) body.innerHTML = '<p class="note">현황을 불러오지 못했습니다. 잠시 뒤 다시 시도해 주세요.</p>';
      });
  }

  function renderAll() {
    /* 「안내문」은 스탭 차례, 「최종 확인」은 의사 차례다 — `canEditNow` 가
       서버와 같은 규칙으로 정한다. 화면이 다른 규칙을 쓰면 눌리는데 저장이
       403 으로 떨어진다. */
    renderOne("guide", canEditNow("guide"));
    renderOne("final", canEditNow("final"));
    renderGuideActions();
    renderFinalActions();
    renderStatus();
  }

  function loadGuide(id) {
    visitId = id;
    var mySeq = ++loadSeq;
    guide = null;
    renderAll();
    if (!id) return;

    /* 문자 설정은 **따로 불러온다.** 안내문과 한 요청으로 묶으면 한쪽이
       실패할 때 둘 다 못 보고, 설정이 없어도 안내문은 보여야 한다. */
    doctorApi
      .messagePlan(id)
      .then(function (data) {
        if (mySeq !== loadSeq) return;
        smsAdopt(data);
        renderAll();
      })
      .catch(function () {
        /* 못 읽으면 화면 기본값으로 둔다 — 저장은 눌러 보면 알 수 있다 */
      });

    doctorApi.guide(id).then(
      function (res) {
        if (mySeq !== loadSeq) return; // 그 사이 다른 진료로 갔다
        guide = res;
        renderAll();
      },
      function (error) {
        if (mySeq !== loadSeq) return;
        guide = null;
        renderAll();
        var say = guideMissingSaying(error);
        if (el("guide-say")) el("guide-say").textContent = say;
        if (el("final-say")) el("final-say").textContent = say;
      },
    );
  }

  /* 가로 탭 — 두 패널이 각자 고른 것을 기억한다.
     탭이 **본문 안에** 들어갔으므로(한 판으로 그린다) 본문에 붙인다.
     전에는 `#{prefix}-vtabs` 에 붙어 있었는데 그 칸이 이제 비어서, 거기
     그대로 두면 아무것도 안 눌린다. */
  ["guide", "final"].forEach(function (prefix) {
    var box = el(prefix + "-panel");
    if (!box) return;
    box.addEventListener("click", function (event) {
      var tab = event.target.closest ? event.target.closest("[data-section]") : null;
      if (!tab) return;
      section[prefix] = tab.getAttribute("data-section");
      renderOne(prefix, canEditNow(prefix));
    });
  });

  /* **승인 · 되돌리기.** 버튼은 그려지는데 누른 것을 받는 자리가 없었다 —
     의사 계정에서 승인이 안 눌리던 것이 이것이다.

     승인하면 발송이 예약된다(서버가 한 트랜잭션에서 한다). 그래서 성공 뒤에
     안내문을 다시 불러온다 — 상태가 「발송 대기」로 바뀌고 「현황」에 예약된
     문자가 선다. */
  document.addEventListener("click", function (event) {
    var t = event.target;
    if (!t || !t.closest) return;

    var go = t.closest("#final-approve");
    var back = t.closest("#final-return");
    if ((!go && !back) || !visitId) return;
    if ((go || back).disabled) return;

    var wantedId = visitId;

    if (back) {
      /* **사유 없이 되돌리지 않는다.** 그 문장이 스탭 알림에 그대로 뜨는데,
         비어 있으면 받는 사람은 무엇을 고쳐야 하는지 알 수 없다. */
      var why = window.prompt("무엇을 고쳐야 하는지 적어 주세요 — 스탭에게 그대로 전달됩니다");
      if (why === null) return;
      if (!String(why).trim()) {
        say("무엇을 고쳐야 하는지 적어 주세요");
        return;
      }
      back.disabled = true;
      doctorApi
        .returnToStaff(wantedId, String(why).trim())
        .then(function () {
          if (visitId !== wantedId) return;
          say("스탭에게 되돌렸습니다");
          loadGuide(wantedId);
          loadTimeline(wantedId);
          document.dispatchEvent(new CustomEvent("visit:changed"));
        })
        .catch(function (error) {
          if (visitId !== wantedId) return;
          back.disabled = false;
          say((error && error.message) || "되돌리지 못했습니다. 다시 시도해 주세요.");
        });
      return;
    }

    /* 두 번 눌리지 않게 잠근다 — 승인이 두 번 가면 발송이 두 번 예약될 수 있다.
       표의 유니크가 막지만, 그 전에 사람이 「안 됐나」로 읽는다. */
    go.disabled = true;
    doctorApi
      .approve(wantedId)
      .then(function (result) {
        if (visitId !== wantedId) return;
        say("승인했습니다 — 발송이 예약되었습니다");
        /* 와이어프레임 D1-5 — 무엇이 언제 누구에게 나가는지 그 자리에서 말한다.
           화면을 갈아끼우지 않아, 뒤에 최종 확인 탭이 그대로 남는다. */
        openModal(
          approvedModalHtml({
            scheduledAt: (result && result.scheduled_at) || null,
            name: ((guide && guide.patient) || {}).name || "",
          }),
        );
        loadGuide(wantedId);
        loadTimeline(wantedId);
        /* 목록의 그 줄이 「승인 요청」에서 「발송 대기」로 옮겨 가야 한다.
           옮기는 것은 골격 몫이다 — 여기서는 바뀌었다고만 알린다. */
        document.dispatchEvent(new CustomEvent("visit:changed"));
      })
      .catch(function (error) {
        if (visitId !== wantedId) return;
        go.disabled = false;
        say((error && error.message) || "승인하지 못했습니다. 다시 시도해 주세요.");
      });
  });

  /* ── 모달 (와이어프레임 D1-5) ─────────────────────────────────────
     본문은 `guide-view.js` 가 그린다 — 의사 화면과 같은 창을 쓴다. */
  function openModal(html) {
    var body = el("modal-body");
    var box = el("modal");
    if (!body || !box) return;
    body.innerHTML = html;
    box.hidden = false;
  }

  function closeModal() {
    var box = el("modal");
    if (box) box.hidden = true;
  }

  document.addEventListener("click", function (event) {
    var t = event.target;
    if (!t || !t.closest) return;

    /* 「현황 보기」는 탭 단추를 대신 누른다 — 탭을 바꾸는 규칙은 `detail.js`
       것이고, 여기서 흉내내면 표시(✓ · ● · ○)가 갈린다. */
    if (t.closest("[data-go-status]")) {
      closeModal();
      var tab = document.querySelector('.tab[data-tab="status"]');
      if (tab) tab.click();
      return;
    }
    if (t.closest("[data-close]")) closeModal();

    /* 바깥을 눌러도 닫힌다. 창 안(`.modal__card`)을 누른 것은 아니어야 한다 —
       글을 끌어 고르다 손을 떼면 닫히면 안 된다. */
    if (t.id === "modal") closeModal();
  });

  /* 「의사 승인 요청」 — 확인이 끝났다는 뜻이다. 성공하면 최종 확인 탭으로
     옮겨 준다: 무엇이 넘어갔는지 그 자리에서 보인다. */
  document.addEventListener("click", function (event) {
    var t = event.target;
    if (!t || !t.closest) return;

    if (t.closest("#guide-reupload")) {
      if (visitId) location.href = "/patients.html?visit=" + encodeURIComponent(visitId) + "&tab=record";
      return;
    }

    var go = t.closest("#guide-submit");
    if (!go || !visitId) return;

    /* **누르는 사이 두 번 눌리지 않게 잠근다.** 두 번 넘기면 서버가 409 로
       막지만, 그 사이 눌린 것은 스탭에게 「안 됐나」로 읽힌다. */
    go.disabled = true;
    var wantedId = visitId;
    doctorApi
      .submit(wantedId)
      .then(function () {
        if (visitId !== wantedId) return;
        say("의사에게 넘겼습니다 — 승인을 기다립니다");
        document.dispatchEvent(new CustomEvent("visit:changed"));
        return loadGuide(wantedId);
      })
      .catch(function (error) {
        if (visitId !== wantedId) return;
        go.disabled = false;
        say((error && error.message) || "넘기지 못했습니다. 다시 시도해 주세요.");
      });
  });

  /* 고치기는 `js/guide-view.js` 가 배선한다 — 의사 화면과 같은 것을 쓴다.
     화면마다 다른 것은 어느 진료인지와 다시 그리는 법뿐이다. */
  /* 문자 설정도 같은 배선을 쓴다 — 두 벌이면 어느 화면에서 만졌느냐에 따라
     되고 안 되고가 갈린다. */
  /* 저장한 뒤 한 줄. 문자 설정 카드 안에 뜬다 — 눌렀는데 아무 말이 없으면
     「저장이 됐나」가 된다. */
  var smsSaying = "";

  wireSmsSettings({
    reRender: function (keepCaret) {
      renderOne("guide", canEditNow("guide"), keepCaret);
      renderOne("final", canEditNow("final"), keepCaret);
    },
    say: say,
    courseDays: function () {
      return 0;
    },
    save: function (plan) {
      var wantedId = visitId;
      if (!wantedId) return;
      smsSaying = "저장하는 중…";
      renderAll();

      doctorApi
        .saveMessagePlan(wantedId, plan)
        .then(function (data) {
          if (visitId !== wantedId) return;
          /* **서버가 돌려준 것을 화면 상태로 삼는다.** 보낸 것을 그대로 두면,
             서버가 고쳐 준 값(일주일 뒤는 켜짐으로 되돌림)이 화면에 안 보인다. */
          smsAdopt(data);
          smsSaying = "저장했습니다";
          renderAll();
        })
        .catch(function (err) {
          if (visitId !== wantedId) return;
          smsSaying =
            err && err.code === "GUIDE_NOT_PENDING"
              ? "승인된 뒤에는 고칠 수 없습니다 — 현황에서 승인을 거두고 고쳐 주세요"
              : "저장하지 못했습니다. 잠시 뒤 다시 시도해 주세요";
          renderAll();
        });
    },
  });

  wireGuideEditing({
    visitId: function () {
      return visitId;
    },
    reRender: function (reload) {
      if (reload && visitId) return loadGuide(visitId);
      renderAll();
    },
    say: say,
  });

  document.addEventListener("visit:selected", function (event) {
    /* 앞 환자에게 고친 문구가 남으면 남의 문자로 보낸 것이 된다 */
    smsForget();
    var id = event.detail && (event.detail.visit_id || event.detail);
    if (!id) return;
    loadGuide(id);
    loadTimeline(id);
  });

  requireSession().then(function (who) {
    me = who;
    renderFinalActions();
  });

  renderStatus();
})();
