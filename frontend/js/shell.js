/* 의료진 화면 골격 — 상단바 · 왼쪽 목록 · 오른쪽 칸 전환
 *
 * KEY-53 이 오른쪽 칸(S1-5 업로드)을 만들고,
 * KEY-35 가 왼쪽 목록의 검색 · 등록 · 필터와 오른쪽 칸의 등록 화면을 붙였다.
 *
 * 목록은 환자 API 로 그린다(KEY-26 계약). 등록 화면은 patients.js 가 갖는다.
 */

/* 상태 탭 다섯. 두 역할이 같은 탭을 쓰고 기본 선택만 다르다 —
   스탭은 「작성 중 + 보완」(오늘 할 일과 고칠 일), 의사는 「승인 요청」.

   탭 값은 계약(KEY-26 §6)의 `work_category` 다. 서버가 OCR · 안내 · 승인 · 발송의
   최신 이벤트를 읽어 파생해 준다 — **화면은 파생하지 않는다.** 화면이 파생하면
   화면마다 규칙이 갈리고, 규칙이 바뀔 때 어디를 고쳐야 하는지 알 수 없다. */
var STATUS_TABS = WORK_CATEGORIES;

var DEFAULT_TABS = {
  staff: ["IN_PROGRESS", "NEEDS_ATTENTION"],
  doctor: ["APPROVAL_REQUESTED"],
};

/* 목록이 들고 있는 것.
   식별자 셋을 처음부터 갈라 둔다 (KEY-26 계약 v1).

     patient_id           환자 리소스 식별자. 사람을 가리킨다
     visit_id             그 환자의 **한 진료 건**. OCR · 안내 · 업로드가 여기에 붙는다
     hospital_patient_no  병원 내 차트번호. **화면에 보이는 값**이고 검색에 쓴다

   셋을 하나로 뭉쳐 두면 나중에 갈라내기 어렵다. 차트번호로 업로드를 걸어 두면
   같은 환자의 지난 진료에 이번 기록이 붙는 사고가 난다. */
var rows = [];
var listDay = new Date();
var listQuery = "";

/* 다른 화면에서 「이 진료의 이 탭을 열어라」로 들어온 것 (의사 화면의 진행 단계).
   **한 번만 쓰고 버린다** — 새로고침하거나 다른 줄을 눌렀는데도 계속 이 사람으로
   끌려가면 목록을 못 쓰게 된다. 주소에서도 지운다: 진료 번호가 주소창에 남으면
   화면을 공유하거나 복사할 때 따라간다. */
var entry = (function () {
  var q = new URLSearchParams(location.search);
  var visitId = q.get("visit");
  if (!visitId) return null;

  q.delete("visit");
  var tab = q.get("open");
  q.delete("open");
  if (typeof history !== "undefined" && typeof history.replaceState === "function") {
    var rest = q.toString();
    history.replaceState(null, "", location.pathname + (rest ? "?" + rest : ""));
  }
  return { visit_id: Number(visitId), open_tab: tab || null };
})();


function roleLabel(roles) {
  var names = { staff: "스탭", doctor: "의사", admin: "관리자" };
  return (roles || [])
    .map(function (r) {
      return names[r] || r;
    })
    .join(" · ");
}

function stateClass(workCategory) {
  /* 색을 한글 문자열로 정하면 문구가 바뀔 때마다 색이 조용히 빠진다.
     계약이 준 카테고리로 정한다. */
  if (workCategory === "NEEDS_ATTENTION") return "row__state row__state--warn";
  if (workCategory === "COMPLETED") return "row__state row__state--done";
  return "row__state";
}

/* ── 오른쪽 칸 ─────────────────────────────────────────
   화면 셋이 같은 자리에 번갈아 선다. 어느 것이 서 있는지 한 곳에서만 정한다 —
   두 곳에서 정하면 등록 도중에 목록을 눌렀을 때 둘 다 뜨거나 둘 다 사라진다. */
var VIEWS = ["view-none", "view-register", "view-card"];

function showView(id) {
  VIEWS.forEach(function (name) {
    document.getElementById(name).hidden = name !== id;
  });
}

/* ── 목록 ─────────────────────────────────────────────── */

function activeTabs() {
  return Array.prototype.slice.call(document.querySelectorAll(".chip[aria-pressed='true']")).map(function (chip) {
    return chip.dataset.tab;
  });
}

/* 목록 검색은 오늘 서 있는 줄만 좁힌다 — 등록된 환자 전체를 뒤지는 것은
   등록 화면의 ① 환자 찾기다. 둘을 한 칸으로 합치면 「지금 목록에 없는 사람」과
   「아직 등록 안 된 사람」이 같은 결과로 보인다. */
function visibleRows() {
  var on = activeTabs();
  var q = listQuery.trim();
  return rows.filter(function (r) {
    if (on.length && on.indexOf(r.work_category) === -1) return false;
    if (!q) return true;
    return r.name.indexOf(q) !== -1 || r.hospital_patient_no.indexOf(q) !== -1;
  });
}

function renderChips(roles) {
  var on = (roles || []).indexOf("staff") !== -1 ? DEFAULT_TABS.staff : DEFAULT_TABS.doctor;
  document.getElementById("chips").innerHTML = STATUS_TABS.map(function (t) {
    return (
      '<button class="chip' +
      (t.warn ? " chip--warn" : "") +
      '" type="button" aria-pressed="' +
      (on.indexOf(t.key) !== -1) +
      '" data-tab="' +
      t.key +
      '"><span data-label>' +
      t.label +
      "</span></button>"
    );
  }).join("");
  renderChipCounts();
}

/* 개수는 행이 바뀔 때마다 다시 센다. 등록하면 「작성 중」이 하나 늘어야 한다.
   탭 이름만 다시 그리면 켜고 끈 상태가 지워지므로 안쪽 라벨만 갈아 끼운다. */
function renderChipCounts() {
  document.querySelectorAll(".chip").forEach(function (chip) {
    var tab = STATUS_TABS.find(function (t) {
      return t.key === chip.dataset.tab;
    });
    var count = rows.filter(function (r) {
      return r.work_category === chip.dataset.tab;
    }).length;
    chip.querySelector("[data-label]").textContent =
      (tab.warn && count ? "⚠ " : "") + tab.label + (count ? " " + count : "");
  });
}

/* 0명에는 세 가지가 있고, 사람이 해야 할 일이 저마다 다르다.
   ① 찾는 이름이 오늘 목록에 없다 → 그 이름으로 바로 등록하러 간다
   ② 탭을 다 꺼서 안 보인다      → 탭을 켠다
   ③ 오늘 아무도 등록되지 않았다  → 등록하거나 지난 날짜로 간다
   「환자가 없습니다」 하나로 뭉치면 무엇을 해야 하는지가 사라진다. */
function blankHtml() {
  var q = listQuery.trim();
  if (q) {
    return (
      '<p class="rows-blank__title">「' +
      esc(q) +
      "」로<br>오늘 등록된 환자가 없습니다</p>" +
      '<button class="rows-blank__act" type="button" data-register-with="' +
      esc(q) +
      '">+ 「' +
      esc(q) +
      "」 등록하기</button>"
    );
  }
  if (rows.length) {
    return (
      '<p class="rows-blank__title">선택한 상태에 해당하는<br>환자가 없습니다</p>' +
      '<p class="rows-blank__lead">위 상태 탭을 켜 보세요</p>'
    );
  }
  return (
    '<p class="rows-blank__title">오늘 등록된<br>환자가 없습니다</p>' +
    '<p class="rows-blank__lead">지난 날짜는 ‹ 로 이동합니다</p>'
  );
}

/* 이 진료가 걸린 상태 탭을 켠다. 목록에 그 줄이 없으면(어제 진료 등) 아무것도
   안 한다 — 없는 것을 보이게 만들 수는 없고, 켜 봐야 엉뚱한 탭만 열린다. */
function showTabOf(visitId) {
  var found = rows.find(function (r) {
    return r.visit_id === visitId;
  });
  if (!found) return;

  var chip = document.querySelector('.chip[data-tab="' + found.work_category + '"]');
  if (chip) chip.setAttribute("aria-pressed", "true");
}

function renderRows(keepVisitId) {
  var shown = visibleRows();
  var box = document.getElementById("rows");

  if (!shown.length) {
    box.innerHTML = '<div class="rows-blank">' + blankHtml() + "</div>";
    return;
  }

  var chosen = selectedVisit();
  var current = keepVisitId || (chosen ? chosen.visit_id : null);

  if (
    !shown.some(function (r) {
      return r.visit_id === current;
    })
  ) {
    /* 고른 줄이 지금 필터에 안 걸린다.
       아직 아무도 안 골랐을 때만 맨 위를 고르고, 이미 고른 것이 있으면 놓지 않는다 —
       검색어를 한 글자 칠 때마다 오른쪽이 다른 환자로 넘어가면, 누르지도 않은
       환자에게 진료기록이 붙는다. 안 보이는 것과 안 고른 것은 다르다. */
    current = chosen ? null : shown[0].visit_id;
  }

  box.innerHTML = shown
    .map(function (r) {
      return rowHtml(r, r.visit_id === current);
    })
    .join("");
}

/* 줄 하나의 markup. 목록 전체와 한 줄 갱신이 **같은 함수**를 쓴다 —
   갈라 두면 한쪽만 고쳐져서 수정한 줄만 옛 모양으로 남는다. */
function rowHtml(r, current) {
  /* 행이 들고 가는 것은 **visit_id** 다 — 업로드 · 판독 · 안내가 붙는 자리.
     화면에 보이는 것은 hospital_patient_no 이고 둘은 다르다. */
  return (
    '<button class="row" type="button" aria-current="' +
    current +
    '" data-visit-id="' +
    r.visit_id +
    '" data-patient-id="' +
    r.patient_id +
    '" data-chart-no="' +
    esc(r.hospital_patient_no) +
    '">' +
    '<span class="row__top"><span class="row__name">' +
    esc(r.name) +
    '</span><span class="row__dx">' +
    esc(r.diagnosis_name || "") +
    "</span></span>" +
    '<span class="row__meta">차트 ' +
    esc(r.hospital_patient_no) +
    (r.age == null ? "" : " · " + r.age + "세") +
    " · " +
    esc(r.doctor ? r.doctor.name : "") +
    "</span><br>" +
    '<span class="' +
    stateClass(r.work_category) +
    '">' +
    esc(statusLabel(r.detail_status)) +
    "</span></button>"
  );
}

/* 목록의 한 줄만 고친다.
   전체를 다시 그리면 바쁜 날 50~100줄을 이름 한 글자 바꿀 때마다 다시 만든다.
   `rows` 를 밖에서 직접 뒤지지 않게 하는 자리이기도 하다 — 목록의 원본은
   이 파일이 갖고, 고치는 길도 여기 하나로 둔다. */
function updateRow(visitId, patch) {
  var found = rows.find(function (r) {
    return r.visit_id === visitId;
  });
  if (!found) return false;
  Object.assign(found, patch);

  var node = document.querySelector('.row[data-visit-id="' + visitId + '"]');
  if (node) node.outerHTML = rowHtml(found, node.getAttribute("aria-current") === "true");
  return true;
}

/* 목록이 비면 오른쪽도 「할 일 없음」이어야 한다.
   등록 화면을 열어 둔 채로는 밀어내지 않는다 — 쓰던 것을 빼앗기 때문이다. */
function syncPane(force) {
  /* 등록 화면은 스스로 닫을 때(force)만 밀어낸다. 탭을 켜고 끄거나 목록을
     다시 그릴 때 빼앗으면 쓰던 것이 날아간다. */
  if (!force && !document.getElementById("view-register").hidden) return;
  if (!visibleRows().length) return showView("view-none");
  showView("view-card");
  var visit = selectedVisit();
  if (!visit) return;

  /* 어느 탭을 열지는 **한 번만** 실어 보낸다. 그 뒤로는 평소대로 기본정보로
     열린다 — 다른 줄을 눌렀는데 앞 사람이 보던 탭이 따라오면 안 된다. */
  if (entry && entry.open_tab && visit.visit_id === entry.visit_id) visit.open_tab = entry.open_tab;
  document.dispatchEvent(new CustomEvent("visit:selected", { detail: visit }));
}

function loadDay() {
  return patientsApi
    .onDay(toIsoDate(listDay))
    .then(function (page) {
      rows = page.items;
      /* 지목받은 줄이 꺼진 탭에 속하면 목록에서 걸러진다 — 의사 화면은 「승인
         요청」만 켜 두는데 그 환자는 「보완」일 수 있다. 등록 직후와 같은 이유로
         (`addVisit`) 그 탭을 켜서 반드시 보이게 한다. 안 켜면 눌러서 왔는데
         빈 목록이 나오고, 엉뚱한 환자가 대신 선다. */
      if (entry) showTabOf(entry.visit_id);
      renderChipCounts();
      /* 지목한 진료가 오늘 목록에 있으면 그 줄을 골라 둔다. 없으면(어제 진료 등)
         평소대로 맨 위가 골라진다 — 빈 화면을 주지 않는다.

         **한 번 쓰면 반드시 버린다.** 못 찾았을 때도 버린다 — 안 그러면 날짜를
         옮기거나 목록을 다시 그릴 때마다 그 사람으로 끌려가 목록을 못 쓴다. */
      renderRows(entry ? entry.visit_id : undefined);
      syncPane();
      entry = null;
    })
    .catch(function () {
      rows = [];
      renderChipCounts(); // 목록은 비었는데 배지만 옛 숫자로 남지 않게
      renderRows();
      syncPane();
    });
}

/* 목록의 축은 하루다. 「오늘」인지 아닌지가 붙어야 지난 날짜를 보고 있다는 것을 안다. */
function renderDay() {
  var week = ["일", "월", "화", "수", "목", "금", "토"];
  var today = toIsoDate(new Date()) === toIsoDate(listDay);
  document.getElementById("day").textContent =
    listDay.getMonth() +
    1 +
    "월 " +
    listDay.getDate() +
    "일 (" +
    week[listDay.getDay()] +
    ")" +
    (today ? " · 오늘" : "");
}

function moveDay(days) {
  listDay = new Date(listDay.getTime() + days * 86400000);
  renderDay();
  loadDay();
}

/* 화면 어디서든 「지금 고른 진료 건」을 같은 모양으로 읽는다.

   DOM 에서 되읽지 않고 목록이 들고 있는 원본을 준다. 줄에 띄우는 것은 이름 ·
   차트 · 나이 · 담당뿐이라, DOM 에서 꺼내면 진료과 · 진료 시각 · 계획 중단이
   사라지고 남은 것도 「 · 」로 잘라야 한다. 상병에 ` · ` 가 하나 들어가면 그날
   담당의사가 어긋난다.

   사본을 주는 이유는, 받는 쪽이 고쳐도 목록이 저절로 바뀌지 않게 하려는 것이다 —
   목록은 renderRows 로만 바뀐다. */
function readRow(row) {
  var id = Number(row.dataset.visitId);
  var found = rows.find(function (r) {
    return r.visit_id === id;
  });
  /* 못 찾으면 **없는 것으로 답한다.**
     예전에는 DOM 에서 긁어 얇은 객체를 만들어 돌려줬는데, 진료과 · 진료 시각 ·
     계획 중단이 빠진 채로 상세 화면까지 흘러가 「· 진료」 같은 조각이 남았다.
     목록과 DOM 이 어긋난 상태를 **정상인 척** 넘기면 무엇이 틀렸는지 안 보인다. */
  return found ? Object.assign({}, found) : null;
}

function selectedVisit() {
  var row = document.querySelector(".row[aria-current='true']");
  return row ? readRow(row) : null;
}

/* 방금 만든 진료 건을 목록에 세우고 고른다. 등록이 끝났다는 것을 목록이 보여 준다. */
function addVisit(visit) {
  rows.unshift(visit);

  /* 방금 등록한 줄이 꺼진 탭에 속하면 목록에서 걸러진다. 등록했는데 안 보이면
     「등록이 안 됐나」가 되고, 고를 줄이 없어 엉뚱한 환자가 대신 서기도 한다.
     그 탭을 켜서 방금 만든 것이 반드시 보이게 한다. */
  var chip = document.querySelector('.chip[data-tab="' + visit.work_category + '"]');
  if (chip) chip.setAttribute("aria-pressed", "true");

  /* 검색어도 같은 이유로 지운다. 탭만 켜서는 부족하다 — 「이서윤」을 찾다가
     못 찾아 김서연을 등록하면, 남아 있는 검색어가 방금 만든 줄을 그대로
     가린다. 그때 화면은 **「이서윤」로 오늘 등록된 환자가 없습니다** 라고
     말한다. 등록한 직후에 등록된 사람이 없다고 하는 셈이다.

     찾던 이름을 지우는 것이 아깝지 않은 이유는, 등록을 마친 순간 그 검색의
     용무가 끝났기 때문이다 — 이제 봐야 할 것은 방금 만든 줄이다. */
  listQuery = "";
  var search = document.getElementById("quick-search");
  if (search) search.value = "";

  renderChipCounts();
  renderRows(visit.visit_id);
  showView("view-card");

  /* 방금 등록한 사람은 기본정보를 다시 볼 이유가 없다 — 진료기록 올리러 간다.
     줄을 눌러 들어올 때(기본정보)와 다른 자리라 어느 탭을 열지 실어 보낸다.
     `tab` 은 목록의 상태 묶음(작성 중 · 보완 …)이 이미 쓰고 있어서 이름을 달리한다. */
  var picked = selectedVisit();
  if (!picked) return; // 그래도 못 고르면 빈 것을 실어 보내지 않는다
  picked.open_tab = "record";
  document.dispatchEvent(new CustomEvent("visit:selected", { detail: picked }));
}

/* 오늘 목록에 이 환자의 진료가 이미 서 있는가.
   등록 화면이 rows 를 직접 뒤지지 않게 여기서 내준다 — 목록의 모양은 이 파일 것이다. */
function visitToday(patientId) {
  return (
    rows.find(function (r) {
      return r.patient_id === patientId;
    }) || null
  );
}

/* ── 손짓 ─────────────────────────────────────────────── */

/* **자기 칸이 없는 페이지에서는 아무것도 하지 않는다.**

   이 파일은 의료진 골격(상단바 · 왼쪽 목록 · 오른쪽 칸)을 가진 쪽에만 실린다.
   그런데 예전에는 최상위에서 곧장 `getElementById("logout").addEventListener`
   를 불렀다 — 그 칸이 없는 페이지에 실리면 **파일 전체가 그 줄에서 죽고**,
   위에 있는 순수 규칙(`roleLabel` · `readRow` 같은)도 함께 사라졌다.

   그래서 걸기 전에 뿌리를 한 번 본다. 없으면 조용히 돌아간다 — 규칙은 그대로
   남아서 다른 파일도, 검사도 부를 수 있다 (KEY-158). */
function bindShell() {
  if (!document.getElementById("logout")) return false;


  document.getElementById("logout").addEventListener("click", function () {
    session.logout();
  });

  /* 치는 대로 좁힌다 — [찾기]를 눌러야 움직이면 오늘 목록에서 한 명 고르는 데
     손이 두 번 간다. 등록 화면의 ① 은 서버에 묻기 때문에 그쪽만 버튼을 둔다. */
  document.getElementById("quick-search").addEventListener("input", function () {
    listQuery = this.value;
    renderRows();
    /* syncPane 을 부르지 않는다 — 검색은 **목록만** 좁힌다.
       오른쪽 칸을 따라 바꾸면, 찾는 이름을 치는 동안 클릭 한 번 없이 다른 환자의
       화면이 열린다. 화면을 바꾸는 것은 줄을 누를 때뿐이다. */
  });

  document.getElementById("day-prev").addEventListener("click", function () {
    moveDay(-1);
  });
  document.getElementById("day-next").addEventListener("click", function () {
    moveDay(1);
  });

  /* 탭은 다중 선택 토글이다 — 켠 탭들의 행이 함께 보인다 */
  document.getElementById("chips").addEventListener("click", function (event) {
    var chip = event.target.closest("[data-tab]");
    if (!chip) return;
    chip.setAttribute("aria-pressed", String(chip.getAttribute("aria-pressed") !== "true"));
    renderRows();
    syncPane();
  });

  document.getElementById("rows").addEventListener("click", function (event) {
    var row = event.target.closest("[data-visit-id]");
    if (!row) return;

    /* 목록에 없는 줄은 누른 것으로 치지 않는다. 목록과 DOM 이 어긋난 상태인데,
       반쪽짜리 값으로 상세를 열면 다른 환자의 화면처럼 보인다. */
    var picked = readRow(row);
    if (!picked) return;

    /* 등록 도중에 목록을 눌러도 잃는 것이 없어야 한다.
       막을 수 있는 쪽(등록 화면)이 스스로 되묻고 preventDefault 로 세운다. */
    var asking = new CustomEvent("visit:selecting", { cancelable: true, detail: picked });
    if (!document.dispatchEvent(asking)) return;

    this.querySelectorAll("[data-visit-id]").forEach(function (r) {
      r.setAttribute("aria-current", String(r === row));
    });
    showView("view-card");
    document.dispatchEvent(new CustomEvent("visit:selected", { detail: picked }));
  });

  /* 세션이 없거나 첫 로그인이면 여기서 되돌린다.
     화면에서 막는 것은 편의일 뿐이고 실제 차단은 서버가 한다(KEY-9). */
  requireSession()
    .then(function (me) {
      document.getElementById("who-name").textContent = me.name;
      document.getElementById("who-roles").textContent = roleLabel(me.roles);
      renderDay();
      renderChips(me.roles);
      document.dispatchEvent(new CustomEvent("session:ready", { detail: me }));
      return loadDay();
    })
    .catch(function () {});

  return true;
}

bindShell();
