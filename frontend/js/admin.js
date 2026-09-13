/* 어드민 화면 (A1-1 ~ A1-7) — KEY-234.
 *
 * 와이어프레임의 일곱 프레임은 별도 화면이 아니라 **좌측 목록 네 줄**로 묶인다.
 *
 *     직원        A1-1 목록 · A1-2 추가 · A1-3 수정
 *     의원 정보    A1-4
 *     문자        A1-5
 *     전체 로그    A1-6 목록 · A1-7 한 건 시간 흐름
 *
 * **본문은 아직 데이터가 없다.** `GET /staffs` 도 `GET /hospital` 도 서버에
 * 없다. 그래서 각 줄은 그 자리가 무엇을 할 곳이고 무엇이 있어야 되는지를
 * 말한다 — 없는 값을 화면이 지어내지 않는다.
 *
 * 화면에 쓰는 설명은 `js/frames.js` 하나에서 온다. 프레임이 구현되면 그 줄의
 * `level` 만 고치면 되고, 설명이 두 군데로 갈라지지 않는다.
 */

/* **좌측 목록 네 줄과 그 안에 묶이는 프레임** — 와이어프레임 A1-1 좌측 칸.
 *
 * IIFE 밖에 둔다. 화면을 그리는 코드는 `browser-shim` 아래서 안 돌아
 * 검사가 닿지 않지만, 이 표는 닿는다. 프레임 일곱이 다 어딘가에 묶여
 * 있는지를 검사가 잴 수 있어야 한다. */
var ADMIN_MENU = [
  { key: "staff", label: "직원", frames: ["A1-1", "A1-2", "A1-3"] },
  { key: "clinic", label: "의원 정보", frames: ["A1-4"] },
  { key: "sms", label: "문자", frames: ["A1-5"] },
  { key: "log", label: "전체 로그", frames: ["A1-6", "A1-7"] },
];

/* 메뉴 한 줄이 품은 프레임들을 표에서 찾아 온다. 없는 번호가 섞이면
   `null` 이 아니라 걸러 낸다 — 화면이 빈 카드를 그리지 않게. */
function adminFramesFor(menuKey) {
  var found = null;
  for (var i = 0; i < ADMIN_MENU.length; i++) {
    if (ADMIN_MENU[i].key === menuKey) found = ADMIN_MENU[i];
  }
  if (!found) return [];

  var out = [];
  for (var f = 0; f < found.frames.length; f++) {
    var frame = frameById(found.frames[f]);
    if (frame) out.push(frame);
  }
  return out;
}

/* 어드민 메뉴가 와이어프레임의 일곱 프레임을 하나도 안 빠뜨렸는가.
   검사가 부른다 — 프레임을 늘리고 메뉴에 안 넣으면 화면에서 사라진다. */
function adminMenuCovers(frames) {
  var listed = [];
  for (var i = 0; i < ADMIN_MENU.length; i++) {
    for (var f = 0; f < ADMIN_MENU[i].frames.length; f++)
      listed.push(ADMIN_MENU[i].frames[f]);
  }
  var missing = [];
  for (var n = 0; n < (frames || []).length; n++) {
    if (listed.indexOf(frames[n].id) === -1) missing.push(frames[n].id);
  }
  return missing;
}

(function () {
  "use strict";

  var menuBox = document.getElementById("admin-menu");
  var bodyBox = document.getElementById("admin-body");
  if (!menuBox || !bodyBox) return;

  var current = ADMIN_MENU[0].key;

  function escape(text) {
    return String(text == null ? "" : text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function renderMenu() {
    var html = "";
    for (var i = 0; i < ADMIN_MENU.length; i++) {
      var item = ADMIN_MENU[i];
      var on = item.key === current;
      html +=
        '<button class="row admin-row' +
        (on ? " admin-row--on" : "") +
        '"' +
        ' type="button" role="tab" aria-selected="' +
        (on ? "true" : "false") +
        '" data-menu="' +
        escape(item.key) +
        '">' +
        '<span class="row__name">' +
        escape(item.label) +
        "</span>" +
        '<span class="row__meta">' +
        item.frames.length +
        "화면</span>" +
        "</button>";
    }
    menuBox.innerHTML = html;
  }

  /* **「직원」 칸은 이제 셋 다 진짜다** — A1-1 목록 · A1-2 추가 (KEY-321) ·
     A1-3 수정 (KEY-330). 나머지 칸들은 여전히 줄 API 가 없어 프레임 카드다.

     같은 화면 안에서 어떤 칸은 살아 있고 어떤 칸은 아직인 것이 이상해 보이지만,
     반대(다 되는 척)가 이 저장소가 없애 온 모양이다. */
  function renderStaffBody() {
    bodyBox.innerHTML =
      '<h1 class="pane__title">직원</h1>' +
      '<div id="staff-list"><section class="staff-card">' +
      '<h2 class="staff-card__title">직원 목록</h2>' +
      '<p class="pane__lead">불러오는 중…</p></section></div>' +
      staffFormHtml();
    wireStaffForm();
    wireStaffEdit();
    loadStaffList();
  }

  /* 줄의 [수정] — A1-3 (KEY-330).
   *
   * **목록을 다시 그리는 것으로 연다.** 판을 따로 들고 있으면 목록이 새로
   * 올 때 그 판이 옛 사람을 가리킨 채 남는다.
   */
  function wireStaffEdit() {
    bodyBox.addEventListener("click", function (event) {
      var t = event.target;
      if (!t || !t.closest) return;

      var asked = t.closest("[data-edit-staff]");
      if (asked) {
        var id = Number(asked.getAttribute("data-edit-staff"));
        staffListOpen(staffOpenNow() === id ? null : id);
        return loadStaffList();
      }
      if (t.closest("[data-edit-staff-close]")) {
        staffListOpen(null);
        return loadStaffList();
      }
    });

    bodyBox.addEventListener("submit", function (event) {
      var form = event.target;
      if (!form || form.id !== "staff-edit") return;
      event.preventDefault();
      saveStaffEdit();
    });
  }

  function saveStaffEdit() {
    var id = staffOpenNow();
    var say = document.getElementById("staff-edit-say");
    var go = document.getElementById("staff-edit-go");
    if (!id || !say || !go) return;

    /* 모르는 조합으로 열린 판이다 — 고르기 전에는 안 보낸다. 빈 역할을 그대로
       보내면 서버가 422 로 막는데, 화면이 먼저 말하는 것이 맞다. */
    var chosen = document.getElementById("staff-edit-roles").value;
    if (!chosen) {
      say.textContent = "역할을 먼저 골라 주세요.";
      return;
    }

    var password = document.getElementById("staff-edit-password").value;
    var body = {
      roles: staffRolesFor(chosen),
      status: document.getElementById("staff-edit-status").value,
    };
    /* **비워 두면 안 보낸다.** 빈 글자를 보내면 서버가 형식 검사에서 막는데,
       관리자가 의도한 것은 「비밀번호는 그대로」다. */
    if (password) body.password = password;

    /* 두 번 눌리지 않게 잠근다 — 비밀번호 재설정이 두 번 가면 관리자가 방금
       적어 준 값이 아닌 것으로 또 덮인다. */
    go.disabled = true;
    say.textContent = "저장하는 중…";
    updateStaff(id, body)
      .then(function (saved) {
        staffListOpen(null);
        loadStaffList();
        var cut = saved.revoked_sessions
          ? " 쓰고 있던 로그인 " + saved.revoked_sessions + "건을 끊었습니다."
          : "";
        staffSay(saved.name + " 님을 저장했습니다." + cut);
      })
      .catch(function (error) {
        go.disabled = false;
        say.textContent = staffEditSaying(error);
      });
  }

  /* 저장 뒤의 말은 **목록 위 한 곳**에 둔다 — 판은 닫혀서 사라진다. */
  function staffSay(text) {
    var box = document.getElementById("staff-say");
    if (box) box.textContent = text;
  }

  function loadStaffList() {
    var box = document.getElementById("staff-list");
    if (!box) return;
    listStaffs()
      .then(function (data) {
        box.outerHTML = '<div id="staff-list">' + staffListHtml(data.staffs) + "</div>";
      })
      .catch(function (error) {
        /* **「비어 있다」로 그리지 않는다.** 못 불러온 것을 「직원이 없다」로
           보이면 관리자가 다시 만들려 든다. */
        box.textContent = errorMessage(
          error,
          [{ status: 403, say: "직원 목록을 볼 권한이 없습니다." }],
          "직원 목록을 불러오지 못했습니다.",
        );
      });
  }

  function wireStaffForm() {
    var form = document.getElementById("staff-add");
    if (!form) return;
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      var say = document.getElementById("staff-say");
      var go = document.getElementById("staff-add-go");
      /* 두 번 눌러 계정이 둘 생기는 자리를 막는다 — 아이디가 유일해서 둘째는
         409 로 끝나지만, 그 사이 화면은 아무 말도 안 한다. */
      go.disabled = true;
      say.textContent = "추가하는 중…";
      createStaff({
        name: document.getElementById("staff-name").value,
        login_id: document.getElementById("staff-login-id").value,
        password: document.getElementById("staff-password").value,
        roles: staffRolesFor(document.getElementById("staff-roles").value),
      })
        .then(function (made) {
          say.textContent = made.name + " 님을 추가했습니다. 첫 로그인에서 비밀번호를 바꾸게 됩니다.";
          form.reset();
          loadStaffList();
        })
        .catch(function (error) {
          say.textContent = staffCreateSaying(error);
        })
        .then(function () {
          go.disabled = false;
        });
    });
  }

  /* 아직 API 가 없는 프레임만 카드로 남긴다. */
  function remainingFrameCards(ids) {
    var html = "";
    for (var i = 0; i < ids.length; i++) {
      var frame = frameById(ids[i]);
      if (frame) html += frameCardHtml(frame);
    }
    return html;
  }

  /* ── 전체 로그 (A1-6 · A1-7) — KEY-322 ──────────────────────────────── */

  var auditCursor = null;
  var auditQuery = {};

  /* **몇 번째 검색의 응답인가.**
   *
   * 응답이 오는 순서는 요청한 순서가 아니다. 「안내문」으로 걸러 놓고 곧바로
   * 「문자」로 다시 거르면, 늦게 도착한 안내문 응답이 목록을 덮어 **거르개는
   * 문자인데 줄은 안내문**이 된다. 다음 쪽 커서도 그 응답 것으로 덮이므로,
   * 이어서 「더 보기」를 누르면 문자 조건에 안내문 커서를 얹어 보낸다.
   * 「더 보기」가 도는 중에 거르개를 바꾸면 옛 조건의 줄이 새 목록에
   * **붙는다** (한금준 님 `#287` 리뷰).
   *
   * 검색을 새로 낼 때마다 번호를 올리고, 요청은 떠날 때의 번호를 쥔다.
   * 돌아왔을 때 번호가 다르면 **화면에 손대지 않는다** — 목록도, 커서도,
   * 오류 문구도. 「더 보기」는 저를 부른 검색의 번호를 그대로 쓴다: 그
   * 검색이 밀려났으면 이어 붙일 목록도 이미 사라진 것이다.
   *
   * 요청을 취소하지는 않는다. 응답을 **안 쓸** 뿐이다 — 끊는 것은 `fetch` 를
   * 손봐야 하는 일이고, 여기서 고치려는 것은 「누가 화면을 차지하는가」다. */
  var auditRun = 0;

  function renderAuditBody() {
    auditRun += 1;
    bodyBox.innerHTML =
      '<h1 class="pane__title">전체 로그</h1>' +
      '<p class="pane__lead" id="audit-filter-slot">거르개를 준비하는 중…</p>' +
      '<div id="audit-list"><p class="pane__lead">불러오는 중…</p></div>' +
      '<div class="audit-more" id="audit-more"></div>';

    /* **행위자 목록은 A1-1 것을 그대로 쓴다.** 못 불러와도 나머지 거르개는
       서야 하므로 빈 목록으로 세운다 — 하나가 늦다고 화면이 통째로 멈추면
       안 된다. */
    listStaffs()
      .then(function (data) {
        return data.staffs;
      })
      .catch(function () {
        return [];
      })
      .then(function (staffs) {
        var slot = document.getElementById("audit-filter-slot");
        if (!slot) return;
        slot.outerHTML = auditFilterHtml(staffs);
        wireAuditFilter();
      });

    auditQuery = {};
    auditCursor = null;
    loadAudit(false);
  }

  function wireAuditFilter() {
    var form = document.getElementById("audit-filter");
    if (!form) return;
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      auditQuery = auditQueryFrom({
        source: document.getElementById("audit-source").value,
        actor: document.getElementById("audit-actor").value,
        visit: document.getElementById("audit-visit").value.trim(),
        from: document.getElementById("audit-from").value,
        to: document.getElementById("audit-to").value,
      });
      auditCursor = null;
      auditRun += 1;
      loadAudit(false);
    });
  }

  function loadAudit(append) {
    /* 떠날 때의 번호를 쥔다 — 돌아와서 견줄 것은 이것이다. */
    var run = auditRun;
    var box = document.getElementById("audit-list");
    var more = document.getElementById("audit-more");
    if (!box) return;
    if (!append) box.innerHTML = '<p class="pane__lead">불러오는 중…</p>';
    if (more) more.innerHTML = "";

    var asked = {};
    for (var key in auditQuery) {
      if (Object.prototype.hasOwnProperty.call(auditQuery, key)) asked[key] = auditQuery[key];
    }
    if (append && auditCursor) asked.cursor = auditCursor;

    listAuditLogs(asked)
      .then(function (page) {
        if (run !== auditRun) return;
        var html = auditListHtml(page.entries);
        if (append) {
          var body = box.querySelector("tbody");
          /* 앞 쪽이 비어 표가 없으면 이어 붙일 자리가 없다 — 통째로 그린다. */
          if (body && page.entries.length) {
            for (var i = 0; i < page.entries.length; i++) {
              body.insertAdjacentHTML("beforeend", auditRowHtml(page.entries[i]));
            }
          } else {
            box.innerHTML = html;
          }
        } else {
          box.innerHTML = html;
        }
        auditCursor = page.next_cursor;
        if (more) {
          more.innerHTML = page.has_more
            ? '<button class="button-ghost" type="button" id="audit-more-go">더 보기</button>'
            : "";
          var go = document.getElementById("audit-more-go");
          if (go) {
            go.addEventListener("click", function () {
              go.disabled = true;
              loadAudit(true);
            });
          }
        }
      })
      .catch(function (error) {
        /* **실패도 똑같이 늦게 온다.** 지난 검색이 실패한 것을 지금 목록 위에
           적으면, 멀쩡히 그려진 줄 위에 오류 문구가 앉거나 남의 「더 보기」가
           「다시 시도」로 바뀐다. */
        if (run !== auditRun) return;
        var saying = esc(auditLoadSaying(error));
        if (append) {
          /* **이미 그린 줄을 지우지 않는다.** 「더 보기」가 실패했다고 앞서 본
             쉰 줄이 오류 문구 하나로 바뀌면, 관리자는 보고 있던 것을 잃는다 —
             그리고 요청 전에 「더 보기」를 비웠으므로 **다시 눌러 볼 단추도
             없다.** 필터를 다시 내는 것 말고는 돌아올 길이 없었다
             (이희진 님 `#287` 리뷰 ①).

             실패는 목록이 아니라 목록 **아래**에 적고, 그 자리에 다시 누를
             단추를 돌려 놓는다. */
          if (more) {
            more.innerHTML =
              '<p class="pane__lead">' +
              saying +
              "</p>" +
              '<button class="button-ghost" type="button" id="audit-more-go">다시 시도</button>';
            var retry = document.getElementById("audit-more-go");
            if (retry) {
              retry.addEventListener("click", function () {
                retry.disabled = true;
                loadAudit(true);
              });
            }
          }
          return;
        }
        /* **「기록이 없다」로 그리지 않는다.** 못 불러온 것을 없는 것으로 보이면
           관리자는 그 시각에 아무 일도 없었다고 읽는다. */
        box.innerHTML = '<p class="pane__lead">' + saying + "</p>";
      });
  }

  function renderBody() {
    if (current === "staff") return renderStaffBody();
    if (current === "log") return renderAuditBody();
    var frames = adminFramesFor(current);
    if (!frames.length) {
      bodyBox.innerHTML =
        '<p class="pane__lead">고를 수 있는 화면이 없습니다.</p>';
      return;
    }

    var html = "";
    for (var i = 0; i < frames.length; i++) {
      html += frameCardHtml(frames[i]);
    }
    bodyBox.innerHTML =
      '<h1 class="pane__title">' + escape(menuLabel()) + "</h1>" + html;
  }

  function frameCardHtml(frame) {
    return (
      '<section class="admin-card">' +
        '<span class="frame__id">' +
        escape(frame.id) +
        "</span>" +
        '<h2 class="admin-card__name">' +
        escape(frame.name) +
        "</h2>" +
        '<p class="frame__role">' +
        escape(frame.role || "") +
        "</p>" +
        '<dl class="frame__facts">' +
        "<dt>지금 상태</dt>" +
        '<dd><span class="frames__badge frames__badge--' +
        frame.level +
        '">' +
        escape(FRAME_LEVELS[frame.level]) +
        "</span></dd>" +
        "<dt>이 화면이 되려면</dt>" +
        "<dd>" +
      escape(frame.blocker || "미정") +
      "</dd>" +
      "</dl>" +
      "</section>"
    );
  }

  function menuLabel() {
    for (var i = 0; i < ADMIN_MENU.length; i++) {
      if (ADMIN_MENU[i].key === current) return ADMIN_MENU[i].label;
    }
    return "어드민";
  }

  menuBox.addEventListener("click", function (event) {
    var row = event.target.closest ? event.target.closest("[data-menu]") : null;
    if (!row) return;
    current = row.getAttribute("data-menu");
    renderMenu();
    renderBody();
  });

  var logout = document.getElementById("logout");
  if (logout) {
    logout.addEventListener("click", function () {
      session.clear();
      location.replace("/login.html");
    });
  }

  /* 화면을 먼저 그리고 신원을 채운다 — 서버가 늦어도 골격은 서 있어야 한다. */
  renderMenu();
  renderBody();

  /* 좌측 접기는 의료진 화면과 같은 것을 쓴다 (js/list-fold.js) — 공통 골격이다. */
  wireFold(false);

  requireSession().then(function (me) {
    var name = document.getElementById("who-name");
    var roles = document.getElementById("who-roles");
    if (name) name.textContent = me.name || "—";
    if (roles) roles.textContent = roleLabel(me.roles);

    /* **갈 곳 없는 탭은 죽은 채로 두지 않는다.** 제자리로 도로 오는 링크와
       403 을 받는 링크가 가장 나쁘다 — 눌러 보고서야 아는 꼴이다. */
    function park(id, why) {
      var tab = document.getElementById(id);
      if (!tab) return;
      var off = document.createElement("button");
      off.className = "topbar__tab tab--later";
      off.type = "button";
      off.setAttribute("aria-disabled", "true");
      off.title = why;
      off.textContent = tab.textContent;
      tab.parentNode.replaceChild(off, tab);
    }

    /* 「현황」이 갈 곳은 역할이 정한다. 의사만 가진 계정을 환자 목록으로
       보내면 빈 화면을 만난다. admin 만 가진 계정에는 갈 곳이 없다 —
       `landingFor` 가 이 화면을 도로 돌려준다. */
    var goes = landingFor(me.roles);
    var work = document.getElementById("to-work");
    if (goes === "/admin.html") {
      park("to-work", "진료 화면은 스탭 또는 의사 역할이 있어야 열립니다");
    } else if (work) {
      work.setAttribute("href", goes);
    }

    /* **「관리」도 같은 자리다** — KEY-236.
     *
     * 「현황」과 「설정」은 잠그면서 이것만 빠져 있었다. 관리 화면은 환자 관리·
     * 발송이라 스탭 일인데, admin 만 가진 계정에도 눌리는 모양 그대로였다 —
     * 위 주석이 말한 「403 을 받는 링크가 가장 나쁘다」가 여기에도 걸린다. */
    if (goes === "/admin.html") {
      park("to-manage", "관리 화면은 스탭 또는 의사 역할이 있어야 열립니다");
    }

    if (!opensSettings(me.roles)) {
      park("to-settings", "처방 설정은 스탭 또는 의사 역할이 있어야 열립니다");
    }
  });
})();
