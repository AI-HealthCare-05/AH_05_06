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


/* 좌측 목록 접기는 `js/list-fold.js` 가 갖는다 — 어드민 화면도 같은 골격을
   쓰는데 그 화면은 이 파일을 싣지 않는다(환자 목록이 없어 `bindShell` 이
   찾는 칸이 없다). 공통 템플릿이라 따로 뺐다. */

/* 목록에서 그 진료의 줄을 찾는다. 서버가 준 줄이라 이름·차트번호·상태가 다 있다.
   순수 함수로 두어 검사가 부를 수 있게 한다 (KEY-158). */
function rowByVisit(list, visitId) {
  for (var i = 0; i < (list || []).length; i++) {
    if (list[i] && list[i].visit_id === visitId) return list[i];
  }
  return null;
}

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
      esc(t.label) +
      '</span><span class="chip__count" data-count hidden></span></button>'
    );
  }).join("");
  renderChipCounts();
}

/* **숫자는 라벨에 섞지 않는다.** 「작성 중 2」처럼 한 문자열로 두면 320px 목록에
   다섯이 한 줄에 안 들어오고, 숫자가 바뀔 때마다 칩 폭이 흔들려 옆 칩이 밀린다.

   iOS 앱 아이콘의 알림 수처럼 오른쪽 위에 띄운다 — 절대 위치라 **칩 폭을
   차지하지 않는다.** 그래서 숫자가 붙어도 한 줄이 유지된다.

   화면낭독기에는 붙여서 읽힌다(`aria-label`) — 「작성 중, 2건」. 배지만 보고
   무슨 숫자인지 알 수 없으면 소리로 듣는 사람에게는 뜻이 없다. */
function chipCountLabel(label, count) {
  return count ? label + ", " + count + "건" : label;
}

function renderChipCounts() {
  document.querySelectorAll(".chip").forEach(function (chip) {
    var tab = STATUS_TABS.find(function (t) {
      return t.key === chip.dataset.tab;
    });
    var count = rows.filter(function (r) {
      return r.work_category === chip.dataset.tab;
    }).length;

    chip.querySelector("[data-label]").textContent = (tab.warn && count ? "⚠ " : "") + tab.label;

    var badge = chip.querySelector("[data-count]");
    badge.textContent = count ? String(count) : "";
    badge.hidden = !count;

    /* 배지는 눈으로만 읽힌다 — 소리로 듣는 사람에게 숫자를 붙여 준다. */
    chip.setAttribute("aria-label", chipCountLabel(tab.label, count));
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

function renderRows(keepVisitId) {
  if (keepVisitId) {
    var asked = rowByVisit(rows, keepVisitId);
    if (asked) picked = asked;
  }

  var shown = visibleRows();
  var box = document.getElementById("rows");

  if (!shown.length) {
    box.innerHTML = '<div class="rows-blank">' + blankHtml() + "</div>";
    return;
  }

  /* 아직 아무도 안 골랐을 때만 맨 위를 고른다. **이미 고른 것이 있으면 지금
     필터에 안 걸려도 놓지 않는다** — 검색어를 한 글자 칠 때마다, 또 상태 탭을
     켜고 끌 때마다 오른쪽이 다른 환자로 넘어가면, 누르지도 않은 환자에게
     진료기록이 붙는다. 줄에 표시(`aria-current`)가 안 될 뿐 고른 것은 그대로다. */
  picked = nextPicked(picked, shown);

  box.innerHTML = shown
    .map(function (r) {
      return rowHtml(r, r.visit_id === picked.visit_id);
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
    /* 와이어프레임 S1-4 의 줄은 두 줄이다 — 첫 줄 왼쪽에 이름·진단, 오른쪽 끝에
       지금 상태. 상태를 셋째 줄로 내리면 한 줄이 세 줄이 되어, 320px 목록에
       하루치 환자가 안 들어온다. 스탭이 훑는 것은 이름과 상태 둘뿐이라
       같은 줄에 있어야 눈이 한 번만 움직인다. */
    '<span class="row__top"><span class="row__name">' +
    esc(r.name) +
    '</span><span class="row__dx">' +
    esc(r.diagnosis_name || "") +
    '</span><span class="' +
    stateClass(r.work_category) +
    '">' +
    esc(statusLabel(r.detail_status)) +
    "</span></span>" +
    '<span class="row__meta">차트 ' +
    esc(r.hospital_patient_no) +
    (r.age == null ? "" : " · " + r.age + "세") +
    " · " +
    esc(r.doctor ? r.doctor.name : "") +
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

  /* **하루가 빈 것**과 **필터가 가린 것**은 다르다. 예전에는 보이는 줄이 없으면
     오른쪽을 「할 일 없음」으로 밀었는데, 그래서 상태 탭 하나를 끄는 것만으로
     보던 환자를 빼앗겼다. 그 날 아무도 없을 때만 민다. */
  var visit = selectedVisit();
  var move = paneMove(visit ? visit.visit_id : null, toldId);

  showView(move.view);
  if (!move.tell) {
    toldId = null;
    return;
  }

  /* 줄 값만 새로 왔다고 알린다 — 승인 뒤에 상태 배지가 「승인 요청」에
     머무르지 않게 하려면 머리는 다시 그려야 하기 때문이다. */
  if (move.tell === "refresh") {
    document.dispatchEvent(new CustomEvent("visit:refreshed", { detail: visit }));
    return;
  }
  tellPane(visit);
}

function loadDay() {
  return patientsApi
    .onDay(toIsoDate(listDay))
    .then(function (page) {
      rows = page.items;
      /* **날짜를 옮겨도 고른 것을 놓지 않는다.** 어제 목록을 보러 갔다고 보던
         환자를 빼앗으면, 돌아왔을 때 다시 찾아 눌러야 한다. 날짜는 목록의
         보기이지 무엇을 열어 뒀는지가 아니다 — 상태 탭과 같은 규칙이다.
         (그 진료의 날짜는 상세 머리에 「8월 31일 진료」로 적혀 있다.) */
      renderChipCounts();
      renderRows();
      syncPane();
    })
    .catch(function () {
      rows = [];
      renderChipCounts(); // 목록은 비었는데 배지만 옛 숫자로 남지 않게
      renderRows();
      syncPane();
    });
}

/* 목록의 축은 하루다. 「오늘」인지 아닌지가 붙어야 지난 날짜를 보고 있다는 것을 안다.
   순수 함수로 두어 검사가 부를 수 있게 한다 (KEY-158). */
var WEEKDAYS = ["일", "월", "화", "수", "목", "금", "토"];

function dayHeading(day, now) {
  return (
    day.getMonth() +
    1 +
    "월 " +
    day.getDate() +
    "일 (" +
    WEEKDAYS[day.getDay()] +
    ")" +
    (toIsoDate(now) === toIsoDate(day) ? ' <span class="day__today">오늘</span>' : "")
  );
}

/* 달력이 준 `YYYY-MM-DD` 를 그 날 00:00 으로 읽는다.
   `new Date("2026-08-31")` 은 **UTC 자정**이라 KST 에서는 전날 09:00 이 된다 —
   그대로 쓰면 고른 날의 하루 전 목록이 열린다. */
function dayFromInput(value) {
  var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(value || ""));
  if (!m) return null;
  return new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
}

function renderDay() {
  var label = document.getElementById("day");
  if (label) label.innerHTML = dayHeading(listDay, new Date());

  /* 달력을 열었을 때 지금 보고 있는 날에서 시작한다. */
  var input = document.getElementById("day-input");
  if (input) input.value = toIsoDate(listDay);
}

function moveDay(days) {
  listDay = new Date(listDay.getTime() + days * 86400000);
  renderDay();
  loadDay();
}

/* 달력에서 고른 날로 간다. 하루씩 넘기는 것과 같은 길을 쓴다. */
function goToDay(day) {
  if (!day) return;
  listDay = day;
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

/* **고른 진료는 DOM 밖에 둔다.**
 *
 * 예전에는 고른 사실이 줄의 `aria-current` 한 곳에만 있었다. 그래서 상태 탭
 * (작성 중 · 보완 · 승인 요청 · 발송 대기 · 완료)을 끄면 그 줄이 목록에서
 * 빠지면서 **고른 사실까지 함께 사라졌다** — 오른쪽 상세가 통째로 리셋되고,
 * 탭을 다시 켜도 돌아오지 않았다.
 *
 * 목록에 **안 보이는 것**과 **안 고른 것**은 다르다. 상태 탭도 날짜도 목록의
 * **보기**일 뿐, 무엇을 열어 뒀는지가 아니다. 오른쪽은 **누른 것만** 바꾼다.
 *
 * 그래서 `visit_id` 가 아니라 **줄 자체**를 들고 있는다. 다른 날짜를 보는 동안
 * 그 줄은 오늘 목록(`rows`)에 없기 때문이다 — 아이디만 들고 있으면 날짜를
 * 옮기는 순간 오른쪽이 빈다.
 */
var picked = null;

/* 상세에 「이 사람이다」라고 마지막으로 알린 진료. `visit:selected` 는 상세를
   처음부터 그리게 하므로, 같은 사람에게 두 번 쏘면 열어 둔 칸이 기본정보로
   되감기고 치던 문자 문구가 날아간다. */
var toldId = null;

/* 「지금 고른 것은 무엇인가」 — **화면 밖의 규칙**이라 검사가 부를 수 있다.
 *
 * 아직 아무도 안 골랐을 때만 맨 위를 고른다. 이미 고른 것이 있으면 지금 목록에
 * 안 보여도 놓지 않는다 — 상태 탭을 끄거나 검색어를 한 글자 치는 것으로 고른
 * 사실이 사라지면, 오른쪽이 누르지도 않은 환자로 넘어간다.
 */
function nextPicked(current, shown) {
  if (current) return current;
  return shown.length ? shown[0] : null;
}

/* 「오른쪽 판을 어떻게 할 것인가」 — 이것도 화면 밖의 규칙이다.
 *
 *   pickedId  고른 진료. 아무도 안 골랐으면 `null`
 *   told      상세에 마지막으로 「이 사람이다」라고 알린 진료
 *
 * **고른 것이 있으면 무조건 연다.** 그 진료가 지금 목록에 보이는지, 오늘 날짜인지
 * 는 묻지 않는다 — 날짜를 옮기거나 상태 탭을 끄는 것으로 보던 환자를 빼앗기지
 * 않아야 한다.
 *
 * 같은 사람이면 `refresh` 다. `select` 는 상세를 처음부터 그리게 해서 열어 둔
 * 칸이 기본정보로 되감기고, 치던 문자 문구가 날아가고, 열어 둔 창이 닫힌다.
 */
function paneMove(pickedId, told) {
  if (pickedId === null) return { view: "view-none", tell: null };
  return { view: "view-card", tell: pickedId === told ? "refresh" : "select" };
}

function selectedVisit() {
  if (!picked) return null;
  /* 지금 목록에 그 줄이 있으면 **새로 받은 값**을 준다 — 승인 뒤에 상태 배지가
     「승인 요청」에 머무르지 않게. 없으면(다른 날을 보는 중) 들고 있던 것을 준다.

     사본을 준다 — `readRow` 와 같은 이유다. 받는 쪽이 고쳐도 목록은
     `renderRows` 로만 바뀐다. */
  return Object.assign({}, rowByVisit(rows, picked.visit_id) || picked);
}

/* 상세에 사람이 바뀌었다고 알린다. 여기 한 곳에서만 `toldId` 를 적어,
   「알렸는가」와 「알린 것이 누구인가」가 갈리지 않게 한다. */
function tellPane(visit) {
  toldId = visit.visit_id;
  document.dispatchEvent(new CustomEvent("visit:selected", { detail: visit }));
}

/* 방금 만든 진료 건을 목록에 세우고 고른다. 등록이 끝났다는 것을 목록이 보여 준다. */
/* 방금 만든 진료를 목록에 세운다 — **서버에서 다시 받아서** 세운다.
 *
 * 예전에는 `POST /visits` 응답을 그대로 `rows` 에 밀어 넣었다. 그런데 두
 * 응답의 모양이 다르다.
 *
 *     오늘 목록  FrontDeskVisitItem   name · hospital_patient_no · age ·
 *                                     diagnosis_name · work_category · detail_status
 *     진료 생성  VisitResponse        doctor_id · department · status ·
 *                                     planned_stop · visit_summary …
 *
 * 그래서 등록 직후 목록 줄에 **이름이 비고** 머리말이 「차트 undefined」로
 * 떴다. 상태 칩도 `work_category` 가 없어 아무 데도 안 걸렸다.
 *
 * 화면이 그 칸들을 지어내면 안 된다 — `work_category` 는 서버가 OCR · 안내 ·
 * 승인 · 발송의 최신 이벤트를 읽어 파생해 주는 값이다(계약 §6). 화면이 파생하면
 * 화면마다 규칙이 갈리고, 규칙이 바뀔 때 어디를 고쳐야 하는지 알 수 없다.
 */
function addVisit(visit) {
  /* 검색어를 먼저 지운다. 남겨 두면 다시 받아 온 목록에서도 방금 만든 줄이
     가려진다 — 「이서윤」을 찾다가 못 찾아 김서연을 등록하면, 화면은 등록한
     직후에 「이서윤로 오늘 등록된 환자가 없습니다」라고 말한다. */
  listQuery = "";
  var search = document.getElementById("quick-search");
  if (search) search.value = "";

  return loadDay().then(function () {
    var made = rowByVisit(rows, visit.visit_id);

    /* 방금 등록한 줄이 꺼진 탭에 속하면 목록에서 걸러진다. 등록했는데 안 보이면
       「등록이 안 됐나」가 되고, 고를 줄이 없어 엉뚱한 환자가 대신 선다.
       그 탭을 켜서 반드시 보이게 한다 — 탭 값은 **서버가 준 것**을 쓴다. */
    if (made) {
      var chip = document.querySelector('.chip[data-tab="' + made.work_category + '"]');
      if (chip) chip.setAttribute("aria-pressed", "true");
    }

    renderChipCounts();
    renderRows(visit.visit_id);
    showView("view-card");

    /* 방금 등록한 사람은 기본정보를 다시 볼 이유가 없다 — 진료기록 올리러 간다.
       줄을 눌러 들어올 때(기본정보)와 다른 자리라 어느 탭을 열지 실어 보낸다.
       `tab` 은 목록의 상태 묶음(작성 중 · 보완 …)이 이미 쓰고 있어서 이름을 달리한다. */
    var picked = selectedVisit();
    if (!picked) return; // 그래도 못 고르면 빈 것을 실어 보내지 않는다
    picked.open_tab = "record";
    tellPane(picked);
  });
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

  /* 달력에서 고른 날짜. `change` 로 듣는다 — `input` 은 연·월·일을 하나씩 칠 때마다
     불려서, 아직 다 안 친 날짜로 목록을 세 번 다시 부른다. */
  var dayInput = document.getElementById("day-input");
  if (dayInput) {
    dayInput.addEventListener("change", function () {
      goToDay(dayFromInput(this.value));
    });
  }

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
    /* 이름을 `picked` 로 두면 **고른 진료를 담아 두는 전역**을 가린다 —
       여기서 정한 것이 밖으로 안 나가 오른쪽이 앞사람에 머문다. */
    var hit = readRow(row);
    if (!hit) return;

    /* 등록 도중에 목록을 눌러도 잃는 것이 없어야 한다.
       막을 수 있는 쪽(등록 화면)이 스스로 되묻고 preventDefault 로 세운다. */
    var asking = new CustomEvent("visit:selecting", { cancelable: true, detail: hit });
    if (!document.dispatchEvent(asking)) return;

    /* **카드를 누르면 늘 기본정보다.**

       `open_tab` 은 목록의 **줄에 그대로 붙는다**(`row.open_tab = ...`). 주소로
       찾아와 한 번 붙으면 그 뒤로 그 환자를 누를 때마다 그 칸이 열렸다 —
       「진료기록」이 붙어 있으면 카드를 눌렀는데 판독 화면으로 튀어 나간다.
       누르는 것은 「이 환자를 본다」이지 「그때 보던 칸으로 간다」가 아니다. */
    hit.open_tab = null;
    var kept = rowByVisit(rows, hit.visit_id);
    if (kept) kept.open_tab = null;

    /* **여기가 오른쪽을 바꾸는 유일한 자리다.** 날짜도 상태 탭도 목록의 보기일 뿐이다. */
    picked = hit;
    this.querySelectorAll("[data-visit-id]").forEach(function (r) {
      r.setAttribute("aria-current", String(r === row));
    });
    showView("view-card");
    tellPane(hit);
  });

  /* 판독 화면은 원문을 넓게 봐야 해서 목록이 저절로 접힌다 (와이어프레임 `S1-7`
     「좌측 48px 접힌 레일」). 그 접힘은 기억하지 않는다 — 다음에 환자 목록을
     열었을 때 까닭 없이 접혀 있으면 고장으로 읽힌다. */
  wireFold(document.body.classList.contains("shell--fold-list"));

  /* 세션이 없거나 첫 로그인이면 여기서 되돌린다.
     화면에서 막는 것은 편의일 뿐이고 실제 차단은 서버가 한다(KEY-9). */
  /* **진료 상태가 바뀌었다** — 목록을 다시 부른다.
   *
   * 승인하면 그 줄이 「승인 요청」에서 「발송 대기」로 옮겨 가야 한다. 그런데
   * 상태를 바꾸는 것은 안내문 화면이고 목록은 여기가 갖는다 — 화면이 목록을
   * 직접 만지면 어느 쪽이 정본인지 흐려진다. 「바뀌었다」만 듣고 **다시 묻는다.**
   *
   * 파생은 서버가 한다(`work_category.py`). 화면이 「승인했으니 발송 대기겠지」
   * 라고 옮겨 적으면 서버 규칙이 바뀔 때 두 곳이 갈라진다.
   */
  document.addEventListener("visit:changed", function () {
    loadDay();
  });

  /* **주소로 찾아온 진료를 연다 — 그 진료의 날짜로 옮겨서.**
   *
   * 목록은 하루 단위인데 처음 여는 날은 늘 오늘이다. 그래서 어제 진료의
   * 주소(`?visit=12&tab=guide`)로 들어오면 오늘 목록에서 그 진료를 못 찾고,
   * 화면은 「오늘은 환자가 없습니다」를 띄웠다 — 판독 화면에서 「안내문」을
   * 누르거나 환자 카드에서 「판독 결과 확인」을 누를 때마다 그랬다.
   *
   * 주소에 날짜를 실어 보내는 방법도 있지만, 그러면 **주소를 만드는 모든
   * 자리**가 날짜를 붙여야 한다 — 한 곳만 빠뜨려도 같은 증상이 돌아온다.
   * 받는 쪽에서 한 번 물어보는 편이 한 자리에서 끝난다. 오늘 목록에 있으면
   * 묻지 않는다.
   */
  function openAsked(asked) {
    var here = rowByVisit(rows, asked.visitId);
    if (here) return openRow(here, asked.tab);

    return patientsApi
      .getVisit(asked.visitId)
      .then(function (visit) {
        var day = visit && visit.visited_at ? dayFromInput(String(visit.visited_at).slice(0, 10)) : null;
        if (!day) return null;
        listDay = day;
        renderDay();
        return loadDay();
      })
      .then(function () {
        var found = rowByVisit(rows, asked.visitId);
        if (found) openRow(found, asked.tab);
      })
      .catch(function () {
        /* 못 찾으면 오늘 목록 그대로 둔다 — 빈 화면을 띄우느니 오늘을 보인다 */
      })
      .then(clearAsked);
  }

  function openRow(row, tab) {
    if (tab) row.open_tab = tab;
    showView("view-card");
    renderRows(row.visit_id);
    tellPane(row);
    clearAsked();
  }

  /* 주소는 한 번만 쓰고 지운다. 남겨 두면 새로고침할 때마다 고르던 것을
     버리고 그 진료로 되돌아간다. */
  function clearAsked() {
    history.replaceState(null, "", location.pathname);
  }

  requireSession()
    .then(function (me) {
      document.getElementById("who-name").textContent = me.name;
      document.getElementById("who-roles").textContent = roleLabel(me.roles);
      renderDay();
      renderChips(me.roles);
      document.dispatchEvent(new CustomEvent("session:ready", { detail: me }));
      return loadDay();
    })
    .then(function () {
      /* **판독 화면에서 돌아왔는가.** `?visit=12&tab=basic` 을 달고 오면 그
         진료를 고르고 그 칸을 연다 — 5단계 줄이 그 주소를 만든다
         (`js/step-nav.js`). 이게 없으면 「기본정보」를 눌러도 오늘 목록의 맨 위
         환자가 열려, 누른 사람이 다른 환자를 보게 된다.

         주소는 한 번만 쓰고 지운다. 남겨 두면 새로고침할 때마다 고르던 것을
         버리고 그 진료로 되돌아간다. */
      var asked = stepFromSearch(location.search);
      if (!asked.visitId) return;
      return openAsked(asked);
    })
    .catch(function () {});

  return true;
}

bindShell();
