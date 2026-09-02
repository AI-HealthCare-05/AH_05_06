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

  function renderBody() {
    var frames = adminFramesFor(current);
    if (!frames.length) {
      bodyBox.innerHTML =
        '<p class="pane__lead">고를 수 있는 화면이 없습니다.</p>';
      return;
    }

    var html = "";
    for (var i = 0; i < frames.length; i++) {
      var frame = frames[i];
      html +=
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
        "</section>";
    }
    bodyBox.innerHTML =
      '<h1 class="pane__title">' + escape(menuLabel()) + "</h1>" + html;
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

    if (!opensSettings(me.roles)) {
      park("to-settings", "처방 설정은 스탭 또는 의사 역할이 있어야 열립니다");
    }
  });
})();
