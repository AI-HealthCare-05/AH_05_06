/* D1 의사 검토·수정·승인·반려 — KEY-86
 *
 * 원장님이 이 화면에서 하는 일은 하나다. **환자에게 나갈 글을 읽고 승인한다.**
 *
 * 그래서 지키는 원칙 넷 —
 *   ① 고칠 것이 없으면 승인 한 번. ⚠ 만 보면 되고, 없으면 읽지 않고 승인해도 된다.
 *   ② 🚨 응급 문장은 고칠 수 없다. 식약처 정보를 근거로 미리 써 둔 문장이라
 *      약이 바뀌면 문장도 함께 바뀐다 — 사람이 손댈 자리가 아니다.
 *   ③ 되돌릴 때는 **사유를 받는다.** 그 문장이 스탭의 알림에 그대로 뜬다.
 *      「승인 반려」만 뜨면 받는 사람은 무엇을 고쳐야 하는지 알 수 없다.
 *   ④ 승인은 화면을 갈아끼우지 않는다 — 모달로 덮고 뒤는 그대로 남긴다.
 *      방금 무엇을 승인했는지가 눈앞에서 사라지면 확인할 방법이 없다.
 *
 * 권한은 **서버가 판단한다**(`docs/models-layout.md`). 여기서 버튼을 잠그는 것은
 * 편의일 뿐이고, 스탭 계정으로 요청이 가면 서버가 403 으로 막는다.
 */

(function () {
  var el = function (id) {
    return document.getElementById(id);
  };

  var guide = null;
  var visit = null;
  var me = null;
  var section = "medication";
  var loadSeq = 0;

  function isDoctor() {
    return !!(me && (me.roles || []).indexOf("doctor") !== -1);
  }

  function esc(text) {
    return String(text == null ? "" : text).replace(/[&<>"]/g, function (ch) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[ch];
    });
  }

  /* ── 안내문 ──────────────────────────────────────────── */

  function currentSection() {
    for (var i = 0; i < guide.sections.length; i++) {
      if (guide.sections[i].key === section) return guide.sections[i];
    }
    return guide.sections[0];
  }

  function renderTabs() {
    var tabs = guide.sections
      .map(function (s) {
        var warn = s.blocks.filter(function (b) {
          return b.warn;
        }).length;
        return (
          '<button class="vtab' +
          (s.key === section ? " is-on" : "") +
          '" type="button" data-section="' +
          s.key +
          '">' +
          esc(s.label) +
          (warn ? ' <span class="vtab__warn">⚠ ' + warn + "</span>" : "") +
          "</button>"
        );
      })
      .join("");
    tabs +=
      '<button class="vtab' +
      (section === "messages" ? " is-on" : "") +
      '" type="button" data-section="messages">문자 설정</button>';
    el("vtabs").innerHTML = tabs;
  }

  function blockHtml(block) {
    var body = "";
    if (block.body) body += '<p class="block__body">' + esc(block.body) + "</p>";
    if (block.list) {
      body +=
        '<ul class="block__list">' +
        block.list
          .map(function (item) {
            return "<li>" + esc(item) + "</li>";
          })
          .join("") +
        "</ul>";
    }
    if (block.table) {
      body +=
        '<table class="block__table"><thead><tr>' +
        block.table.head
          .map(function (h) {
            return "<th>" + esc(h) + "</th>";
          })
          .join("") +
        "</tr></thead><tbody>" +
        block.table.rows
          .map(function (row) {
            return (
              "<tr>" +
              row
                .map(function (cell, i) {
                  return (i === 0 ? "<th>" : "<td>") + esc(cell) + (i === 0 ? "</th>" : "</td>");
                })
                .join("") +
              "</tr>"
            );
          })
          .join("") +
        "</tbody></table>";
    }

    /* 잠긴 블록은 왜 잠겼는지를 함께 적는다. 이유 없이 안 눌리는 버튼은
       「고장났다」로 읽히고, 원장님은 그것을 확인하느라 시간을 쓴다. */
    var tail = block.locked
      ? '<p class="block__locked">🔒 ' + esc(block.locked) + "</p>"
      : '<button class="block__edit" type="button" data-edit="' + esc(block.title) + '">수정</button>';

    return (
      '<section class="block' +
      (block.warn ? " block--warn" : "") +
      (block.locked ? " block--locked" : "") +
      '">' +
      '<h3 class="block__title">' +
      esc(block.title) +
      "</h3>" +
      (block.warn ? '<p class="block__warnline">⚠ ' + esc(block.warn) + "</p>" : "") +
      body +
      tail +
      "</section>"
    );
  }

  function renderMessages() {
    var m = guide.messages;
    var rows = m.schedule
      .map(function (s) {
        return (
          '<label class="sched' +
          (s.fixed ? " sched--fixed" : "") +
          '"><input type="checkbox"' +
          (s.on ? " checked" : "") +
          (s.fixed || !isDoctor() ? " disabled" : "") +
          ' data-sched="' +
          s.key +
          '" /><span class="sched__label">' +
          esc(s.label) +
          (s.fixed ? ' <span class="sched__fixed">고정</span>' : "") +
          '</span><span class="sched__when">' +
          esc(s.when) +
          "</span></label>"
        );
      })
      .join("");

    el("panel").innerHTML =
      '<section class="block"><h3 class="block__title">확인 문자</h3>' +
      '<p class="block__hint">처방 세트 기본값 · 이 환자만 바꿉니다</p>' +
      rows +
      '<p class="block__hint">ⓘ 일주일 뒤는 어느 쪽에서도 끌 수 없습니다 · 발송 시각 ' +
      esc(m.send_at) +
      "</p></section>" +
      '<section class="block"><h3 class="block__title">문구 · ' +
      esc(m.template_name) +
      "</h3>" +
      '<pre class="block__tpl">' +
      esc(m.body) +
      "</pre>" +
      '<p class="block__hint">ⓘ {링크}는 지울 수 없습니다</p>' +
      '<button class="block__edit" type="button" data-edit="문자 문구">수정</button></section>' +
      '<section class="block"><h3 class="block__title">미리보기</h3>' +
      '<p class="block__preview">' +
      esc(m.preview) +
      "</p>" +
      '<p class="block__hint">' +
      esc(m.preview_meta) +
      "</p></section>";
  }

  function renderPanel() {
    if (section === "messages") return renderMessages();
    el("panel").innerHTML = currentSection().blocks.map(blockHtml).join("");
  }

  function warnCount() {
    return guide.sections.reduce(function (n, s) {
      return (
        n +
        s.blocks.filter(function (b) {
          return b.warn;
        }).length
      );
    }, 0);
  }

  /* 위에 몇 개를 봐야 하는지 먼저 말한다. 없으면 「없다」고 분명히 말한다 —
     그래야 읽지 않고 승인해도 된다는 것이 전해진다. */
  function renderSummary() {
    var n = warnCount();
    el("warn-line").className = "warnline" + (n ? " warnline--warn" : " warnline--ok");
    el("warn-line").textContent = n
      ? "확인 부탁드리는 곳 " + n + "군데 — ⚠ 표시만 보시면 됩니다"
      : "확인 부탁드릴 곳이 없습니다 — 그대로 승인하셔도 됩니다";
  }

  /* 안내문이 없으면 **앞 환자의 이름을 지운다.** 안내문을 불러오는 동안 이름만
     남아 있으면, 화면은 앞 사람을 말하는데 `visit` 은 뒷사람이라 원장님이 읽는
     대상과 누를 대상이 어긋난다. 환자 식별이 걸린 자리라 비워 두는 편이 낫다. */
  function renderHead() {
    if (guide === null) {
      el("p-name").textContent = "—";
      el("p-id").textContent = "";
      el("p-visit").textContent = "";
      return;
    }

    var p = guide.patient;
    el("p-name").textContent = p.name;
    el("p-id").textContent = p.gender + " " + p.age + "세 · 차트 " + p.hospital_patient_no;
    el("p-visit").textContent = guide.summary;
  }

  /* ── 권한 ───────────────────────────────────────────── */

  /* 이미 승인한 진료는 다시 승인하지 않는다.

     예전에는 승인 직후에만 버튼을 잠갔는데(`target.disabled = true`), 다른 줄에
     갔다 돌아오면 `renderRole()` 이 되살려서 **같은 진료를 두 번 승인할 수
     있었다.** 환자에게 문자가 나가는 자리라 두 번 승인은 두 번 발송이 된다.

     화면 상태가 아니라 **그 진료의 상태**를 본다 — 목록 줄이 곧 사실이다. */
  function alreadyDone() {
    return !!(visit && visit.work_category && visit.work_category !== "APPROVAL_REQUESTED");
  }

  /* `guide` 가 조건에 들어간 이유.

     `load()` 는 `visit` 을 **즉시** 새 환자로 바꾸는데 안내문은 응답이 와야
     온다. 그 사이 버튼이 살아 있으면 이렇게 된다.

         화면에 보이는 것   앞 환자의 안내문
         approve() 가 보내는 것   뒷 환자의 visit_id

     원장님은 **읽지 않은 안내문을 승인**하게 되고, 승인은 곧 환자에게 발송이다.
     그래서 「안내문이 화면에 있는가」를 최상위 조건으로 둔다 — 없으면 승인할
     대상도 없다. 실패했을 때도 `guide` 가 `null` 이라 그대로 잠긴다. */
  function renderRole() {
    var can = isDoctor() && !alreadyDone() && guide !== null;
    el("approve").disabled = !can;
    el("return").disabled = !can;
    el("role-note").hidden = isDoctor();
  }

  /* 승인·되돌리기가 끝나면 왼쪽 줄도 그 사실을 말해야 한다. 목록이 「승인
     대기」인 채로 남으면 원장님은 안 나간 것으로 읽고 한 번 더 누른다. */
  /* 응답이 오는 사이에 의사가 다른 환자를 고를 수 있다. 그때 전역 `visit` 은
     이미 다른 사람이라, 그걸 고치면 **승인한 적 없는 환자가 발송 대기로
     바뀌고** 정작 승인한 환자는 목록에 남아 다시 승인된다.

     그래서 줄은 언제나 **요청을 보낼 때 잡아 둔 id** 로 찾는다. 전역은 그것이
     아직 같은 사람일 때만 손댄다. `load()` 가 `loadSeq` 로 하는 것과 같은 이유다. */
  function markDone(visitId, patch) {
    if (typeof updateRow === "function") updateRow(visitId, patch);
    if (visit && visit.visit_id === visitId) Object.assign(visit, patch);
    if (typeof renderChipCounts === "function") renderChipCounts();
    renderRole();
  }

  /* ── 모달 ───────────────────────────────────────────── */

  function openModal(html) {
    el("modal-body").innerHTML = html;
    el("modal").hidden = false;
  }

  function closeModal() {
    el("modal").hidden = true;
  }

  /* 권한 문제와 그 밖을 가른다.

     예전에는 `catch` 가 모든 오류를 받아 늘 「의사 계정으로 로그인했는지
     확인해 주세요」라고 했다. 서버가 500 을 줘도 그렇게 말하니, 원장님은 멀쩡한
     계정을 의심해 로그아웃했다 들어오고 그래도 안 되면 사람을 부른다 —
     **고칠 수 없는 것을 고치려 시간을 쓴다.** */
  function failedModal(title, error) {
    var lead =
      error && error.status === 403 ? "의사 계정으로 로그인했는지 확인해 주세요." : "잠시 뒤 다시 시도해 주세요.";
    return (
      '<h2 class="modal__title">' +
      esc(title) +
      "</h2>" +
      '<p class="modal__lead">' +
      lead +
      "</p>" +
      '<div class="modal__acts"><button class="button-ghost" type="button" data-close>닫기</button></div>'
    );
  }

  function approvedModal(result) {
    return (
      '<p class="modal__mark">✓</p>' +
      '<h2 class="modal__title">승인 완료</h2>' +
      '<p class="modal__lead">' +
      esc(result.send_at) +
      " · " +
      esc(result.to) +
      "께 발송 예정</p>" +
      '<p class="modal__note">확인 문자(일주일 뒤 · 보름 뒤)와 소진 임박 안내는 자동 발송됩니다.<br />' +
      "발송 실패 시 알림 창에서 확인할 수 있습니다.</p>" +
      '<div class="modal__acts"><button class="button-ghost" type="button" data-close>닫기</button></div>'
    );
  }

  function returnModal() {
    return (
      '<h2 class="modal__title">스탭에 되돌리기</h2>' +
      /* 사유가 스탭 알림에 그대로 뜬다는 것을 여기서 말한다.
         어디로 가는지 모르는 입력은 대충 적히고, 대충 적힌 사유는 왕복을 늘린다. */
      '<p class="modal__lead">고쳐야 할 것을 적어 주세요 — 이 문장이 스탭 알림에 그대로 뜹니다.</p>' +
      '<div class="reasons">' +
      RETURN_REASONS.map(function (r) {
        return '<button class="reason" type="button" data-reason="' + esc(r) + '">' + esc(r) + "</button>";
      }).join("") +
      "</div>" +
      '<textarea class="modal__input" id="reason-text" rows="3" placeholder="필요하면 덧붙여 주세요"></textarea>' +
      '<p class="modal__error" id="reason-error" hidden></p>' +
      '<div class="modal__acts"><button class="button-ghost" type="button" data-close>취소</button>' +
      '<span class="grow"></span><button class="button-primary" type="button" id="return-go">되돌리기</button></div>'
    );
  }

  /* ── 불러오기 ───────────────────────────────────────── */

  function load(next) {
    visit = next;
    var mine = ++loadSeq;

    /* 앞 환자의 것을 먼저 거둔다. `visit` 만 바뀌고 나머지가 남아 있는 순간이
       생기면 안 된다 — 그 틈이 곧 「읽은 것과 누른 것이 다른」 구간이다.

       창도 함께 닫는다. 반려 사유 창이 열린 채로 환자를 바꾸면, 앞 환자에게
       쓰던 사유가 뒷 환자의 이름 아래 남는다. 이름·버튼을 거두는 것과 같은
       이유다 — 화면이 말하는 사람과 눌렀을 때 가는 사람이 달라진다. */
    guide = null;
    closeModal();
    renderHead();
    renderRole();

    el("panel").innerHTML = '<p class="block__hint">불러오는 중…</p>';
    el("warn-line").textContent = "";

    doctorApi
      .guide(visit.visit_id)
      .then(function (data) {
        if (mine !== loadSeq) return;
        guide = data;
        section = "medication";
        renderHead();
        renderTabs();
        renderPanel();
        renderSummary();
        renderRole();
      })
      .catch(function () {
        if (mine !== loadSeq) return;
        el("panel").innerHTML = '<p class="block__hint">안내문을 불러오지 못했습니다. 잠시 뒤 다시 시도해 주세요.</p>';
        renderRole(); // guide 가 null 이라 잠긴 채로 남는다
      });
  }

  /* ── 이벤트 ─────────────────────────────────────────── */

  document.addEventListener("click", function (event) {
    var target = event.target;

    var tab = target.closest("[data-section]");
    if (tab) {
      section = tab.getAttribute("data-section");
      renderTabs();
      renderPanel();
      return;
    }

    if (target.closest("[data-close]")) return closeModal();

    var reason = target.closest("[data-reason]");
    if (reason) {
      var box = el("reason-text");
      box.value = reason.getAttribute("data-reason");
      box.focus();
      return;
    }

    if (target.id === "approve" && guide) {
      target.disabled = true;
      var approvingId = visit.visit_id; // 지금 누른 그 환자. 전역은 곧 바뀔 수 있다
      doctorApi
        .approve(approvingId)
        .then(function (result) {
          /* 승인했으면 그 진료는 발송 대기다. 줄을 먼저 고치고 모달을 연다 —
             모달을 닫았을 때 목록이 이미 사실을 말하고 있어야 한다. */
          markDone(approvingId, { work_category: "SEND_PENDING", detail_status: "SCHEDULED_TO_SEND" });
          openModal(approvedModal(result));
        })
        .catch(function (error) {
          /* target.disabled = false 로 그냥 되살리면 안 된다. 요청이 실패로
             돌아오는 사이 다른(이미 처리된) 진료로 넘어가 있을 수 있는데, 그 경우
             무조건 풀어 버리면 재승인 경합이 그대로 재현된다(위 markDone 과 같은
             이유). 항상 지금 화면의 상태를 다시 물어야 한다. */
          renderRole();
          openModal(failedModal("승인하지 못했습니다", error));
        });
      return;
    }

    if (target.id === "return" && guide) {
      openModal(returnModal());
      return;
    }

    if (target.id === "return-go") {
      var text = el("reason-text").value.trim();
      if (!text) {
        el("reason-error").textContent = "무엇을 고쳐야 하는지 적어 주세요.";
        el("reason-error").hidden = false;
        return;
      }
      target.disabled = true;
      var returningId = visit.visit_id; // 승인과 같은 이유로 지금 잡아 둔다
      doctorApi
        .returnToStaff(returningId, text)
        .then(function () {
          markDone(returningId, { work_category: "NEEDS_ATTENTION", detail_status: "APPROVAL_RETURNED" });
          openModal(
            '<h2 class="modal__title">스탭에 되돌렸습니다</h2>' +
              '<p class="modal__lead">「' +
              esc(text) +
              "」로 알렸습니다.</p>" +
              '<p class="modal__note">스탭이 고쳐 다시 승인 요청하면 목록에 돌아옵니다.</p>' +
              '<div class="modal__acts"><button class="button-ghost" type="button" data-close>닫기</button></div>',
          );
        })
        .catch(function () {
          /* 승인 쪽과 같은 이유다(이희진 님 `f184e4f`) — 응답이 실패로 돌아오는
             사이 다른 진료로 넘어가 있을 수 있다.

             다만 여기 `target` 은 **사유 창 안의 버튼**이라 `renderRole()` 이
             닿지 않는다. 그래서 「되돌리려던 그 진료가 아직 화면에 있을 때만」
             되살린다. 넘어갔으면 잠긴 채로 두고, `load()` 가 창을 닫는다. */
          if (visit && returningId === visit.visit_id) {
            target.disabled = false;
          }
          el("reason-error").textContent = "되돌리지 못했습니다. 잠시 뒤 다시 시도해 주세요.";
          el("reason-error").hidden = false;
        });
      return;
    }

    /* 항목 수정은 서버가 붙은 뒤다(KEY-111) — 지금은 어디까지 됐는지 말한다. */
    var edit = target.closest("[data-edit]");
    if (edit) {
      openModal(
        '<h2 class="modal__title">' +
          esc(edit.getAttribute("data-edit")) +
          " 수정</h2>" +
          '<p class="modal__lead">항목 편집은 승인 API 가 붙은 뒤입니다 (KEY-111).</p>' +
          '<p class="modal__note">지금은 읽고 승인하거나 되돌리는 것까지 됩니다.</p>' +
          '<div class="modal__acts"><button class="button-ghost" type="button" data-close>닫기</button></div>',
      );
    }
  });

  document.addEventListener("session:ready", function (event) {
    me = event.detail;
    if (guide) return renderRole();
    /* 목록이 그려지면 맨 위 줄이 이미 골라져 있다(shell.js). 그런데 「고름」은
       클릭으로만 알려지므로, 처음 들어왔을 때는 오른쪽이 빈 채로 남는다 —
       원장님이 한 번 더 눌러야 한다. 골라져 있는 것을 그대로 연다. */
    var first = selectedVisit();
    if (first) load(first);
  });

  document.addEventListener("visit:selected", function (event) {
    load(event.detail);
  });
})();
