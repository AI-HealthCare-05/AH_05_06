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
  var section = { guide: "medication", final: "medication" };

  function el(id) {
    return document.getElementById(id);
  }

  /* 두 탭이 같은 안내문을 그린다 — 다른 것은 편집 권한과 아래 버튼뿐이다. */
  function renderOne(prefix, canEdit) {
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

    vtabs.innerHTML = guideTabsHtml(guide.sections, now.key);
    panel.innerHTML = guidePanelHtml(guide.sections, now.key, canEdit);

    if (warn) {
      var line = guideWarnLine(guide.sections);
      warn.className = line.className;
      warn.textContent = line.text;
    }
  }

  function renderFinalActions() {
    var box = el("final-actions");
    if (!box) return;
    if (!guide) {
      box.innerHTML = "";
      return;
    }

    var can = finalActionsFor(me && me.roles);
    box.innerHTML = can.canApprove
      ? '<button class="button-ghost" type="button" id="final-return">스탭에게 되돌리기</button>' +
        '<span class="grow"></span>' +
        '<button class="button-primary" type="button" id="final-approve">승인</button>'
      : '<p class="note">' + esc(can.why) + "</p>";
  }

  /* 「현황」은 아직 줄 API 가 없다 — 발송 이력 테이블 자체가 서버에 없다.
     값을 지어내지 않고 무엇이 있어야 되는지를 말한다(KEY-234 안내 화면 규칙). */
  function renderStatus() {
    var body = el("status-body");
    if (!body) return;

    var html = "";
    var ids = ["D1-6", "D1-7"];
    for (var i = 0; i < ids.length; i++) {
      var frame = typeof frameById === "function" ? frameById(ids[i]) : null;
      if (!frame) continue;
      html +=
        '<section class="box">' +
        '<div class="box__head"><h2 class="box__title">' +
        esc(frame.name) +
        "</h2></div>" +
        '<p class="note">' + esc(frame.role || "") + "</p>" +
        '<p class="note">이 화면이 되려면 — ' + esc(frame.blocker || "미정") + "</p>" +
        "</section>";
    }
    body.innerHTML = html || '<p class="note">현황을 보여 줄 자리가 아직 없습니다.</p>';
  }

  function renderAll() {
    /* 스탭은 고칠 수 있고(GUIDE_DRAFT), 의사도 고칠 수 있다. 「최종 확인」은
       읽는 자리라 편집을 열지 않는다 — 고치려면 「안내문」 탭으로 간다. */
    renderOne("guide", true);
    renderOne("final", false);
    renderFinalActions();
    renderStatus();
  }

  function loadGuide(id) {
    visitId = id;
    var mySeq = ++loadSeq;
    guide = null;
    renderAll();
    if (!id) return;

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

  /* 세그먼트 탭 — 두 패널이 각자 고른 것을 기억한다. */
  ["guide", "final"].forEach(function (prefix) {
    var box = el(prefix + "-vtabs");
    if (!box) return;
    box.addEventListener("click", function (event) {
      var tab = event.target.closest ? event.target.closest("[data-section]") : null;
      if (!tab) return;
      section[prefix] = tab.getAttribute("data-section");
      renderOne(prefix, prefix === "guide");
    });
  });

  document.addEventListener("visit:selected", function (event) {
    if (event.detail) loadGuide(event.detail.visit_id || event.detail);
  });

  requireSession().then(function (who) {
    me = who;
    renderFinalActions();
  });

  renderStatus();
})();
