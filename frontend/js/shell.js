/* 의료진 화면 골격 — 상단바 · 왼쪽 목록 · 로그아웃
 *
 * KEY-53 은 오른쪽 칸(S1-5 업로드)을 만든다. 왼쪽 목록의 검색·등록·필터
 * 동작은 KEY-35 몫이라 여기서는 **자리와 모양만** 잡는다.
 * 목록 데이터도 임시다 — 환자 API 가 생기면 KEY-35 가 갈아 끼운다.
 */

/* 상태 탭 다섯. 두 역할이 같은 탭을 쓰고 기본 선택만 다르다 —
   스탭은 「작성 중 + 보완」(오늘 할 일과 고칠 일), 의사는 「승인 요청」. */
var STATUS_TABS = [
  { key: "draft", label: "작성 중" },
  { key: "fix", label: "보완", warn: true },
  { key: "review", label: "승인 요청" },
  { key: "queued", label: "발송 대기" },
  { key: "done", label: "완료" },
];

var DEFAULT_TABS = {
  staff: ["draft", "fix"],
  doctor: ["review"],
};

/* 임시 목록 — KEY-35 가 API 로 갈아 끼운다.
   합성 데이터(docs/data/synthetic-patients.csv)의 시나리오를 따른다.

   식별자 셋을 처음부터 갈라 둔다 (KEY-26 계약 v1).

     patient_id           환자 리소스 식별자. 사람을 가리킨다
     visit_id             그 환자의 **한 진료 건**. OCR · 안내 · 업로드가 여기에 붙는다
     hospital_patient_no  병원 내 차트번호. **화면에 보이는 값**이고 검색에 쓴다

   셋을 하나로 뭉쳐 두면 나중에 갈라내기 어렵다. 차트번호로 업로드를 걸어 두면
   같은 환자의 지난 진료에 이번 기록이 붙는 사고가 난다. */
var SAMPLE_ROWS = [
  {
    patient_id: 1001,
    visit_id: 8842,
    hospital_patient_no: "12345",
    name: "김서연",
    dx: "자궁내막증",
    age: 36,
    doctor: "박연 원장",
    state: "진료기록 없음",
    tab: "draft",
  },
  {
    patient_id: 1002,
    visit_id: 8843,
    hospital_patient_no: "11204",
    name: "이지우",
    dx: "다낭성",
    age: 31,
    doctor: "김연우 원장",
    state: "생성 중",
    tab: "draft",
  },
  {
    patient_id: 1003,
    visit_id: 8798,
    hospital_patient_no: "09871",
    name: "박수빈",
    dx: "자궁내막증",
    age: 34,
    doctor: "박연 원장",
    state: "번호 오류",
    tab: "fix",
  },
  /* 승인 대기 셋 — 의사 화면(D1)이 기본으로 여는 묶음이다.
     의사 기본 탭이 「승인 요청」인데 그 탭에 행이 하나도 없으면,
     화면이 비어 있는 것이 「할 일이 없어서」인지 「아직 안 붙어서」인지
     구분되지 않는다. KEY-35 가 API 로 갈아 끼울 때 함께 사라진다. */
  {
    patient_id: 1003,
    visit_id: 8801,
    hospital_patient_no: "12345",
    name: "김서연",
    dx: "자궁내막증",
    age: 36,
    doctor: "박연 원장",
    state: "승인 대기",
    tab: "review",
  },
  {
    patient_id: 1008,
    visit_id: 8802,
    hospital_patient_no: "10982",
    name: "최다인",
    dx: "다낭성",
    age: 29,
    doctor: "김연우 원장",
    state: "승인 대기",
    tab: "review",
  },
  {
    patient_id: 1009,
    visit_id: 8803,
    hospital_patient_no: "12008",
    name: "정민아",
    dx: "자궁내막증",
    age: 38,
    doctor: "박연 원장",
    state: "승인 대기",
    tab: "review",
  },
];

function roleLabel(roles) {
  var names = { staff: "스탭", doctor: "의사", admin: "관리자" };
  return (roles || [])
    .map(function (r) {
      return names[r] || r;
    })
    .join(" · ");
}

function stateClass(state) {
  if (state === "번호 오류" || state === "보완") return "row__state row__state--warn";
  if (state === "발송 완료" || state === "완료") return "row__state row__state--done";
  return "row__state";
}

function renderChips(roles) {
  var on = (roles || []).indexOf("staff") !== -1 ? DEFAULT_TABS.staff : DEFAULT_TABS.doctor;
  document.getElementById("chips").innerHTML = STATUS_TABS.map(function (t) {
    var count = SAMPLE_ROWS.filter(function (r) {
      return r.tab === t.key;
    }).length;
    return (
      '<button class="chip' +
      (t.warn ? " chip--warn" : "") +
      '" type="button" aria-pressed="' +
      (on.indexOf(t.key) !== -1) +
      '" data-tab="' +
      t.key +
      '">' +
      (t.warn && count ? "⚠ " : "") +
      t.label +
      (count ? " " + count : "") +
      "</button>"
    );
  }).join("");
}

function renderRows() {
  document.getElementById("rows").innerHTML = SAMPLE_ROWS.map(function (r, i) {
    return (
      /* 행이 들고 가는 것은 **visit_id** 다 — 업로드 · 판독 · 안내가 붙는 자리.
         화면에 보이는 것은 hospital_patient_no 이고 둘은 다르다. */
      '<button class="row" type="button" aria-current="' +
      (i === 0) +
      '" data-visit-id="' +
      r.visit_id +
      '" data-patient-id="' +
      r.patient_id +
      '" data-chart-no="' +
      r.hospital_patient_no +
      '">' +
      '<span class="row__top"><span class="row__name">' +
      r.name +
      '</span><span class="row__dx">' +
      r.dx +
      "</span></span>" +
      '<span class="row__meta">차트 ' +
      r.hospital_patient_no +
      " · " +
      r.age +
      "세 · " +
      r.doctor +
      "</span><br>" +
      '<span class="' +
      stateClass(r.state) +
      '">' +
      r.state +
      "</span></button>"
    );
  }).join("");
}

/* 오늘 날짜. 목록의 축이 하루 단위다. */
function renderDay() {
  var d = new Date();
  var week = ["일", "월", "화", "수", "목", "금", "토"];
  document.getElementById("day").textContent =
    d.getMonth() + 1 + "월 " + d.getDate() + "일 (" + week[d.getDay()] + ") · 오늘";
}

document.getElementById("logout").addEventListener("click", function () {
  session.logout();
});

/* 탭은 다중 선택 토글이다 — 켠 탭들의 행이 함께 보인다.
   거르기 자체는 KEY-35 가 붙인다. */
document.getElementById("chips").addEventListener("click", function (event) {
  var chip = event.target.closest("[data-tab]");
  if (!chip) return;
  chip.setAttribute("aria-pressed", String(chip.getAttribute("aria-pressed") !== "true"));
});

document.getElementById("rows").addEventListener("click", function (event) {
  var row = event.target.closest("[data-visit-id]");
  if (!row) return;
  this.querySelectorAll("[data-visit-id]").forEach(function (r) {
    r.setAttribute("aria-current", String(r === row));
  });
  document.dispatchEvent(new CustomEvent("visit:selected", { detail: readRow(row) }));
});

/* 화면 어디서든 「지금 고른 진료 건」을 같은 모양으로 읽는다. */
function readRow(row) {
  return {
    visit_id: Number(row.dataset.visitId),
    patient_id: Number(row.dataset.patientId),
    hospital_patient_no: row.dataset.chartNo,
    name: row.querySelector(".row__name").textContent,
    meta: row.querySelector(".row__meta").textContent,
  };
}

function selectedVisit() {
  var row = document.querySelector(".row[aria-current='true']");
  return row ? readRow(row) : null;
}

/* 세션이 없거나 첫 로그인이면 여기서 되돌린다.
   화면에서 막는 것은 편의일 뿐이고 실제 차단은 서버가 한다(KEY-9). */
requireSession()
  .then(function (me) {
    document.getElementById("who-name").textContent = me.name;
    document.getElementById("who-roles").textContent = roleLabel(me.roles);
    renderDay();
    renderChips(me.roles);
    renderRows();
    document.dispatchEvent(new CustomEvent("session:ready", { detail: me }));
  })
  .catch(function () {});
