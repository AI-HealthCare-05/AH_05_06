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
    /* 안내문 탭 — 넘기기 전이면 스탭도 고친다 */
    return isDoctor || (guide && guide.status === "STAFF_REVIEW");
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

    /* **한 판으로 그린다** — 제목 · 가로 탭 · 원문 · 미리보기가 한 덩어리다
       (와이어프레임 S1-11 · D1-1). 전에는 세로 탭과 본문이 따로 떠 있었다. */
    vtabs.innerHTML = "";
    panel.innerHTML = guideScreenHtml(guide.sections, now.key, prefix, canEdit);

    if (warn) {
      var line = guideWarnLine(guide.sections);
      warn.className = line.className;
      warn.textContent = line.text;
    }
  }

  /* 누른 뒤에 무슨 일이 일어났는지 한 줄. 작아서 화면낭독기가 읽어도
     시끄럽지 않다 — 다른 화면들과 같은 자리다. */
  function say(text) {
    var box = el("guide-say");
    if (box) box.textContent = text;
  }

  /* S1-11 하단 — 스탭이 확인을 마치고 의사에게 넘긴다. */
  function renderGuideActions() {
    var box = el("guide-actions");
    if (!box) return;
    if (!guide) {
      box.innerHTML = "";
      return;
    }

    var can = guideActionsFor(guide.status, me && me.roles);
    box.innerHTML =
      '<button class="button-ghost button-ghost--sm" type="button" id="guide-reupload">진료기록 재업로드</button>' +
      '<span class="grow"></span>' +
      '<span class="note">' +
      esc(can.say) +
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
        return loadGuide(wantedId);
      })
      .catch(function (error) {
        if (visitId !== wantedId) return;
        go.disabled = false;
        say((error && error.message) || "넘기지 못했습니다. 다시 시도해 주세요.");
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
