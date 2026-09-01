/* 환자·진료 API — KEY-35 · KEY-50
 *
 * 계약은 `docs/api/hospital.md` (KEY-26) 를 따른다.
 *
 *   GET   /api/v1/patients?keyword=&category=&cursor=&limit=
 *   POST  /api/v1/patients
 *   GET   /api/v1/patients/{patient_id}
 *   PATCH /api/v1/patients/{patient_id}
 *   POST  /api/v1/patients/{patient_id}/visits
 *   GET   /api/v1/patients/{patient_id}/visits
 *   PATCH /api/v1/visits/{visit_id}
 *   GET   /api/v1/front-desk/visits?date=&categories=&cursor=&limit=
 *
 * 식별자 셋을 섞지 않는다.
 *   patient_id           사람
 *   visit_id             그 사람의 한 진료 건 — 업로드 · 판독 · 안내가 붙는다
 *   hospital_patient_no  화면에 보이는 차트번호. 검색에 쓴다
 *
 * **오늘 목록은 `/patients` 가 아니라 `/front-desk/visits` 다.** 앞은 사람을
 * 찾는 곳이고 뒤는 「오늘 무엇을 해야 하는가」를 읽는 곳이다. 뒤쪽만이 업무
 * 상태(`work_category`)를 이벤트에서 파생해 준다.
 *
 * 서버가 아직 없다(KEY-34 진행 중). 계약대로 짜 두고 ?mock=1 로 화면을 확인한다.
 * 서버가 붙으면 아래 「목업」 아래를 통째로 지우면 된다 — api.js 의 request() 를
 * 그대로 쓰므로 이 파일 위쪽은 손댈 것이 없다.
 */

function patientsRequest(path, options) {
  options = options || {};
  if (MOCK) return mockPatientsRequest(path, options);
  return request(path, options);
}

function query(params) {
  return Object.keys(params)
    .filter(function (k) {
      return params[k] !== undefined && params[k] !== null && params[k] !== "";
    })
    .map(function (k) {
      return k + "=" + encodeURIComponent(params[k]);
    })
    .join("&");
}

var patientsApi = {
  /* 등록 화면의 ① 환자 찾기. 이름 한 글자 · 차트번호 · 정규화한 휴대폰을 서버가 본다.
     `category` 는 기본 ALL 이라 보내지 않는다 — 등록은 「모든 환자」에서 찾는다. */
  search: function (keyword, cursor) {
    return patientsRequest("/patients?" + query({ keyword: keyword, cursor: cursor }));
  },

  /* 오늘 목록(S1-1). 날짜는 **병원 표시 시간대(Asia/Seoul)의 현지 날짜**다.
     보완(NEEDS_ATTENTION)은 해결될 때까지 날짜와 무관하게 딸려 온다 —
     박수빈(08-11 건)이 오늘 목록에 서 있는 이유가 그것이다. */
  onDay: function (isoDate, categories, cursor) {
    return patientsRequest(
      "/front-desk/visits?" +
        query({
          date: isoDate,
          categories: (categories || []).join(","),
          cursor: cursor,
        }),
    );
  },

  /* 환자 관리 표(S2-1). 검색과 같은 자리를 부르되 **분류와 쪽 크기를 함께
     보낸다** — 등록 화면의 찾기는 「모든 환자」에서 이름으로 좁히는 일이고,
     이쪽은 의원 전체를 훑으며 챙길 환자를 고르는 일이라 묻는 것이 다르다. */
  roster: function (keyword, category, cursor, limit) {
    return patientsRequest(
      "/patients?" +
        query({ keyword: keyword, category: category, cursor: cursor, limit: limit }),
    );
  },

  /* 환자 이력 모달(S2-2). **환자 단위다** — 진료 타임라인(D1-6)은 진료
     하나짜리라 「이 환자가 지난 세 번 어떻게 했나」를 물을 수 없다. */
  history: function (patientId, limit) {
    if (MOCK) return mockPatientHistory(patientId, limit);
    return patientsRequest(
      "/patients/" + encodeURIComponent(patientId) + "/history?" + query({ limit: limit }),
    );
  },

  create: function (patient) {
    return patientsRequest("/patients", { method: "POST", body: patient });
  },
  createVisit: function (patientId, visit) {
    return patientsRequest("/patients/" + patientId + "/visits", {
      method: "POST",
      body: visit,
    });
  },

  /* ── 환자 카드 (KEY-50) ─────────────────────────────
     계약 §5 의 네 리소스. 수정 가능한 것과 아닌 것이 갈려 있고,
     그 경계가 화면의 잠금과 그대로 같다. */
  get: function (patientId) {
    return patientsRequest("/patients/" + patientId);
  },
  /* 차트번호는 못 고친다 — 생성 후 변경 불가(계약 §4·§6).
     보낼 수 있는 것은 name · birth_date · gender · phone · sms_consent 뿐이다. */
  update: function (patientId, patch) {
    return patientsRequest("/patients/" + patientId, { method: "PATCH", body: patch });
  },
  visits: function (patientId) {
    return patientsRequest("/patients/" + patientId + "/visits");
  },
  /* 오늘 목록은 진료 상세 칸을 주지 않는다 — `department` 스냅샷 · `status` ·
     `planned_stop` 은 이 리소스에만 있다(계약 §4). 목록 줄로 상세를 그리면
     목업에서는 돌고 서버에서는 빈다. */
  getVisit: function (visitId) {
    return patientsRequest("/visits/" + visitId);
  },
  updateVisit: function (visitId, patch) {
    return patientsRequest("/visits/" + visitId, { method: "PATCH", body: patch });
  },
};

/* 계약 §6 이 정한 수정 가능 필드. 화면이 이 목록 밖을 보내면 400 이다.
   목록을 코드에 두는 이유는, 폼에 칸을 하나 늘렸을 때 여기도 같이 늘려야
   한다는 것이 눈에 보이게 하려는 것이다. */
var PATIENT_EDITABLE = ["name", "birth_date", "gender", "phone", "sms_consent"];
var VISIT_EDITABLE = [
  "doctor_id",
  "department_id",
  "visited_at",
  "visit_summary",
  "doctor_note",
  "status",
  "planned_stop",
];

/* 등록 화면에서 고르는 진료과 · 담당의사.
   계약은 `department_id` · `doctor_id` 를 받는다 — 화면이 이름을 보내면 진료과가
   폐지됐는지, 그 의사가 거기 소속인지 서버가 볼 수 없다.
   TODO(KEY-33) 직원·진료과 API 가 생기면 여기를 그걸로 갈아 끼운다.
   지금 값은 docs/data/synthetic-staff.csv 의 의사 계정을 따른다. */
var DEPARTMENTS = [{ department_id: 7, name: "산부인과" }];
var DOCTORS = [
  { doctor_id: 2, name: "박연 원장", department_id: 7 },
  { doctor_id: 3, name: "김연우 원장", department_id: 7 },
];

/* 업무 카테고리 — 계약 §6 「S1-1 날짜별 업무 목록」.
   **서버가 OCR · 안내 · 승인 · 발송의 최신 이벤트를 읽어 파생해 준다.**
   화면이 파생하면 화면마다 규칙이 갈리고, 규칙이 바뀔 때 어디를 고쳐야 하는지
   알 수 없다. 화면은 받은 값을 한국어로 옮기기만 한다. */
var WORK_CATEGORIES = [
  { key: "IN_PROGRESS", label: "작성 중" },
  { key: "NEEDS_ATTENTION", label: "보완", warn: true },
  { key: "APPROVAL_REQUESTED", label: "승인 요청" },
  { key: "SEND_PENDING", label: "발송 대기" },
  { key: "COMPLETED", label: "완료" },
];

/* 줄에 뜨는 세부 상태. 계약의 detail_status 12값을 그대로 옮긴다. */
var DETAIL_STATUS_LABEL = {
  NO_DOCUMENT: "진료기록 없음",
  OCR_REVIEW: "판독 확인",
  GUIDE_GENERATING: "생성 중",
  STAFF_REVIEW: "스탭 확인 중",
  GENERATION_FAILED: "생성 실패",
  INVALID_PHONE: "번호 오류",
  SMS_OPT_OUT: "수신 거부",
  APPROVAL_RETURNED: "승인 반려",
  APPROVAL_PENDING: "승인 대기",
  SCHEDULED_TO_SEND: "발송 예정",
  SENT: "발송 완료",
  VIEWED: "열람",
};

function statusLabel(detailStatus) {
  return DETAIL_STATUS_LABEL[detailStatus] || detailStatus || "";
}

/* 기본 상태를 사람 말로. 목록(S1)은 탭 이름으로 쓰고 환자 관리 표(S2-1)는
   열로 쓰는데, **같은 값이라 이름도 같아야 한다.** */
function categoryLabel(workCategory) {
  for (var i = 0; i < WORK_CATEGORIES.length; i++) {
    if (WORK_CATEGORIES[i].key === workCategory) return WORK_CATEGORIES[i].label;
  }
  return workCategory || "—";
}

/* ── 목업 ──────────────────────────────────────────────────────
 * 합성 데이터(docs/data/synthetic-patients.csv)의 동명이인 무리를 그대로 옮겼다.
 * 「김」 한 글자로 찾으면 김서연 셋이 뜨고 생년월일로 갈라야 고를 수 있다.
 * 이서윤 둘은 생년월일까지 같아서 폰 뒷자리(4153 / 4156)로만 갈린다 —
 * S1-2 의 결과 줄이 실제로 갈라 주는지 보려면 이 둘이 필요하다.
 */
var MOCK_PATIENTS = [
  {
    patient_id: 1001,
    hospital_patient_no: "10737",
    name: "김서연",
    birth_date: "1975-03-09",
    phone: "01044342271",
    last_visited_on: "2026-08-07",
    last_dx: "자궁내막증",
    last_drug: "비잔",
  },
  {
    patient_id: 1002,
    hospital_patient_no: "08157",
    name: "김서연",
    birth_date: "1988-07-14",
    phone: "01083245439",
    last_visited_on: "2026-02-14",
    last_dx: "다낭성",
    last_drug: "메트포르민",
  },
  {
    patient_id: 1003,
    hospital_patient_no: "12345",
    name: "김서연",
    birth_date: "1990-01-01",
    phone: "01044524085",
    last_visited_on: "2026-05-20",
    last_dx: "자궁내막증",
    last_drug: "비잔",
  },
  {
    patient_id: 1004,
    hospital_patient_no: "09817",
    name: "이서윤",
    birth_date: "1994-05-21",
    phone: "01088214153",
    last_visited_on: "2026-02-14",
    last_dx: "다낭성",
    last_drug: "야스민",
  },
  {
    patient_id: 1005,
    hospital_patient_no: "10878",
    name: "이서윤",
    birth_date: "1994-05-21",
    phone: "01038944156",
    last_visited_on: "2026-07-29",
    last_dx: "자궁내막증",
    last_drug: "비잔",
  },
  {
    patient_id: 1006,
    hospital_patient_no: "11204",
    name: "이지우",
    birth_date: "1995-04-02",
    phone: "01022331204",
    last_visited_on: "2026-08-01",
    last_dx: "다낭성",
    last_drug: "메트포르민",
  },
  {
    patient_id: 1007,
    hospital_patient_no: "09871",
    name: "박수빈",
    birth_date: "1992-09-18",
    phone: "01077129871",
    last_visited_on: "2026-08-11",
    last_dx: "자궁내막증",
    last_drug: "비잔",
  },
  {
    /* D1 의사 화면이 「남의 환자」로 여는 사람(KEY-86). 오늘 목록에만 넣고
       여기 빠뜨려서, 그 줄을 누르면 환자 카드가 「찾을 수 없습니다 — 목록을
       새로 고쳐 주세요」로 떴다. 새로 고쳐도 없으니 안내까지 틀렸다. */
    patient_id: 1008,
    hospital_patient_no: "10982",
    name: "최다인",
    birth_date: "1997-03-11",
    phone: "01033910982",
    last_visited_on: "2026-05-14",
    last_dx: "다낭성",
    last_drug: "메트포르민",
  },
];

/* 성별과 동의는 합성 CSV 에 칸이 없다 — KEY-30 매핑표의 `CSV_CANNOT_SUPPLY` 와 같은 자리다.
   부인과라 성별은 상수로 채우고, 동의 시각은 마지막 방문일로 둔다. */
MOCK_PATIENTS.forEach(function (p) {
  p.gender = "FEMALE";
  p.sms_consent = true;
  p.sms_consented_at = p.last_visited_on;
});

var MOCK_NEXT_ID = { patient: 2000, visit: 9000 };

/* 오늘 목록. 등록하면 여기에 쌓인다 — 화면이 실제로 늘어나는지 봐야 한다.
   ?today=empty 로 비우면 S1-1(도입 첫날)을 그대로 볼 수 있다. */
var MOCK_TODAY = (function () {
  var q = new URLSearchParams(location.search).get("today");
  if (q !== null) sessionStorage.setItem("mockToday", q);
  if (sessionStorage.getItem("mockToday") === "empty") return [];
  /* 계약 §6 의 응답 항목 모양 그대로다 — 서버가 붙어도 화면이 안 바뀐다.
     `doctor` 는 객체, `diagnosis_name` 은 미확정이면 null, 상태는 두 층
     (work_category = 탭, detail_status = 줄에 뜨는 글자)이다. */
  return [
    {
      visit_id: 8842,
      patient_id: 1003,
      name: "김서연",
      hospital_patient_no: "12345",
      birth_date: "1990-01-01",
      age: 36,
      diagnosis_name: "자궁내막증",
      doctor: { doctor_id: 12, name: "박연 원장" },
      visited_at: "2026-08-20T10:32:00+09:00",
      work_category: "IN_PROGRESS",
      detail_status: "NO_DOCUMENT",
    },
    {
      visit_id: 8843,
      patient_id: 1006,
      name: "이지우",
      hospital_patient_no: "11204",
      birth_date: "1995-04-02",
      age: 31,
      diagnosis_name: "다낭성",
      doctor: { doctor_id: 13, name: "김연우 원장" },
      visited_at: "2026-08-20T09:14:00+09:00",
      work_category: "IN_PROGRESS",
      detail_status: "GUIDE_GENERATING",
    },
    {
      /* 08-11 건인데 오늘 목록에 있다 — NEEDS_ATTENTION 은 해결될 때까지
         날짜와 무관하게 딸려 온다(계약 §6). 이 줄이 그 규칙의 증거다. */
      visit_id: 8798,
      patient_id: 1007,
      name: "박수빈",
      hospital_patient_no: "09871",
      birth_date: "1992-09-18",
      age: 34,
      diagnosis_name: "자궁내막증",
      doctor: { doctor_id: 12, name: "박연 원장" },
      visited_at: "2026-08-11T16:05:00+09:00",
      work_category: "NEEDS_ATTENTION",
      detail_status: "INVALID_PHONE",
    },
    /* 승인 대기 둘 — 의사 화면(D1)이 기본으로 여는 묶음이다.
       의사 기본 탭이 「승인 요청」인데(shell.js DEFAULT_TABS) 그 탭에 행이
       하나도 없으면, 화면이 빈 것이 **할 일이 없어서인지 아직 안 붙어서인지**
       구분되지 않는다. 담당의를 둘로 나눈 것은 D1-1 이 「내 환자」와 「남의
       환자」를 함께 보여 주기 때문이다 — 원장님은 남의 것도 볼 수 있다. */
    {
      visit_id: 8801,
      patient_id: 1003,
      name: "김서연",
      hospital_patient_no: "12345",
      birth_date: "1990-01-01",
      age: 36,
      diagnosis_name: "자궁내막증",
      doctor: { doctor_id: 12, name: "박연 원장" },
      visited_at: "2026-08-20T10:32:00+09:00",
      work_category: "APPROVAL_REQUESTED",
      detail_status: "APPROVAL_PENDING",
    },
    {
      visit_id: 8802,
      patient_id: 1008,
      name: "최다인",
      hospital_patient_no: "10982",
      birth_date: "1997-03-11",
      age: 29,
      diagnosis_name: "다낭성",
      doctor: { doctor_id: 13, name: "김연우 원장" },
      visited_at: "2026-08-20T11:05:00+09:00",
      work_category: "APPROVAL_REQUESTED",
      detail_status: "APPROVAL_PENDING",
    },
  ];
})();

/* **고정 데이터의 날짜를 오늘에 맞춘다.**
 *
 * 고정 값은 「2026-08-20 이 오늘」이라 치고 적혔다. 달력이 지나면 그 날은
 * 지난 날짜가 되고, 목록은 「오늘 등록된 환자가 없습니다」만 띄운다 — 목업이
 * 하루가 지날 때마다 조용히 쓸모없어진다.
 *
 * 날짜를 지우지 않고 **통째로 민다.** 사이 간격은 뜻이 있기 때문이다 —
 * 박수빈의 08-11 은 「아홉 날 전에 걸린 채로 남은 보완」이고, 그 간격이
 * 사라지면 오늘 것과 구분이 안 된다.
 */
var MOCK_TODAY_BASE = "2026-08-20";

(function shiftToToday() {
  var base = new Date(MOCK_TODAY_BASE + "T00:00:00");
  var now = new Date();
  var today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  var days = Math.round((today - base) / 86400000);
  if (!days) return;

  MOCK_TODAY.forEach(function (v) {
    var m = /^(\d{4})-(\d{2})-(\d{2})(.*)$/.exec(String(v.visited_at));
    if (!m) return;
    var at = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]) + days);
    v.visited_at = toIsoDate(at) + m[4];
  });
})();

/* 진료 상세에만 있는 칸. 오늘 목록(§6 S1-1)은 이것들을 주지 않는다 —
   목업 저장소는 하나지만, 아래 두 투영이 각각 자기 계약의 칸만 내보낸다. */
MOCK_TODAY.forEach(function (v) {
  v.department = "산부인과";
  v.status = "COMPLETED";
  v.planned_stop = false;
  v.visit_summary = null;
  v.doctor_note = null;
});

/* ── 계약이 정한 응답 봉투 ──────────────────────────────────────
   화면이 `items` 만 꺼내 쓰더라도 목업이 봉투를 갖춰야, 서버가 붙는 날
   「그런 키가 없다」로 처음 알게 되는 일이 없다. */

/* 저장소 한 줄을 두 계약으로 갈라 내보낸다.

   오늘 목록은 「무엇을 해야 하는가」를 읽는 곳이고, 진료 상세는 「이 진료가
   무엇인가」를 읽는 곳이다. 둘은 칸이 다르다 — 목록에 `planned_stop` 이 없고,
   상세에 `work_category` 가 없다. 목업이 한 줄을 통째로 돌려주면 화면이 없는
   칸을 읽고도 목업에서는 잘 도는 상태가 되고, 서버가 붙는 날 처음 빈다.

   TODO(KEY-26 확인) 상세의 `doctor_id` 만으로는 이름을 못 띄운다. 목록은
   `doctor: {doctor_id, name}` 을 주는데 상세 계약에는 그 대응이 없다. */
function deskItem(row) {
  return {
    visit_id: row.visit_id,
    patient_id: row.patient_id,
    name: row.name,
    hospital_patient_no: row.hospital_patient_no,
    birth_date: row.birth_date,
    age: row.age,
    diagnosis_name: row.diagnosis_name,
    doctor: row.doctor,
    visited_at: row.visited_at,
    work_category: row.work_category,
    detail_status: row.detail_status,
  };
}

function visitResource(row) {
  return {
    visit_id: row.visit_id,
    patient_id: row.patient_id,
    doctor_id: row.doctor ? row.doctor.doctor_id : null,
    department: row.department,
    visited_at: row.visited_at,
    visit_summary: row.visit_summary,
    doctor_note: row.doctor_note,
    status: row.status,
    planned_stop: row.planned_stop,
  };
}

/* 진료과 이름은 서버가 붙인다 — 화면은 id 만 보낸다(계약 §4). */
function departmentOf(departmentId) {
  var found = DEPARTMENTS.find(function (d) {
    return d.department_id === Number(departmentId);
  });
  return found ? found.name : null;
}

function patientPage(items) {
  return {
    counts: { ALL: MOCK_PATIENTS.length },
    selected_category: "ALL",
    items: items,
    page: { next_cursor: null, has_next: false },
  };
}

/* ── 환자 관리 표 목업 (S2-4 · 와이어프레임 S2-1) ────────────────────────
 *
 * 원문의 열 줄을 그대로 옮긴다. `MOCK_PATIENTS` 를 다시 쓰지 않는 이유는
 * 저쪽이 **동명이인 찾기**를 보이려고 만든 자료라(김서연 셋) 상태·담당·이탈이
 * 하나도 없기 때문이다. 표가 보여야 할 것이 다르다.
 */
var MOCK_ROSTER = [
  { patient_id: 2001, hospital_patient_no: "10118", name: "유지수", birth_date: "1996-04-10", gender: "FEMALE", age: 30, phone: "01031414410", sms_consent: true, sms_consented_at: "2026-05-20T10:00:00+09:00", sms_opted_out_at: null, diagnosis_name: "자궁내막증", doctor: { doctor_id: 2, name: "김연우" }, latest_visit: { visit_id: 9101, visited_at: "2026-05-20T10:00:00+09:00", status: "COMPLETED" }, work_category: "COMPLETED", detail_status: "VIEWED", flags: ["UNREAD_STREAK"] },
  { patient_id: 2002, hospital_patient_no: "09660", name: "백소라", birth_date: "1990-11-02", gender: "FEMALE", age: 35, phone: "01026487203", sms_consent: true, sms_consented_at: "2026-06-02T10:00:00+09:00", sms_opted_out_at: null, diagnosis_name: "다낭성", doctor: { doctor_id: 1, name: "박연" }, latest_visit: { visit_id: 9102, visited_at: "2026-06-02T10:00:00+09:00", status: "COMPLETED" }, work_category: "COMPLETED", detail_status: "VIEWED", flags: ["STOPPED_DOSING"] },
  { patient_id: 2003, hospital_patient_no: "08455", name: "문지원", birth_date: "1993-02-18", gender: "FEMALE", age: 33, phone: "01081159034", sms_consent: true, sms_consented_at: "2026-05-12T10:00:00+09:00", sms_opted_out_at: null, diagnosis_name: "자궁내막증", doctor: { doctor_id: 1, name: "박연" }, latest_visit: { visit_id: 9103, visited_at: "2026-05-12T10:00:00+09:00", status: "COMPLETED" }, work_category: "COMPLETED", detail_status: "VIEWED", flags: ["RUN_OUT_OVERDUE"] },
  { patient_id: 2004, hospital_patient_no: "09871", name: "박수빈", birth_date: "1992-05-20", gender: "FEMALE", age: 34, phone: "01062908901", sms_consent: true, sms_consented_at: "2026-08-11T10:00:00+09:00", sms_opted_out_at: null, diagnosis_name: "자궁내막증", doctor: { doctor_id: 1, name: "박연" }, latest_visit: { visit_id: 8801, visited_at: "2026-08-11T10:00:00+09:00", status: "COMPLETED" }, work_category: "NEEDS_ATTENTION", detail_status: "INVALID_PHONE", flags: [] },
  { patient_id: 2005, hospital_patient_no: "11550", name: "한소영", birth_date: "1999-06-25", gender: "FEMALE", age: 27, phone: "01029055678", sms_consent: false, sms_consented_at: null, sms_opted_out_at: "2026-07-28T10:00:00+09:00", diagnosis_name: "자궁내막증", doctor: { doctor_id: 2, name: "김연우" }, latest_visit: { visit_id: 9105, visited_at: "2026-07-28T10:00:00+09:00", status: "COMPLETED" }, work_category: "NEEDS_ATTENTION", detail_status: "SMS_OPT_OUT", flags: [] },
  { patient_id: 2006, hospital_patient_no: "12345", name: "김서연", birth_date: "1990-01-01", gender: "FEMALE", age: 36, phone: "01056781234", sms_consent: true, sms_consented_at: "2026-05-20T10:00:00+09:00", sms_opted_out_at: null, diagnosis_name: "자궁내막증", doctor: { doctor_id: 1, name: "박연" }, latest_visit: { visit_id: 9106, visited_at: "2026-08-13T10:00:00+09:00", status: "COMPLETED" }, work_category: "IN_PROGRESS", detail_status: "NO_DOCUMENT", flags: [] },
  { patient_id: 2007, hospital_patient_no: "11204", name: "이지우", birth_date: "1995-03-08", gender: "FEMALE", age: 31, phone: "01077421234", sms_consent: true, sms_consented_at: "2026-08-13T10:00:00+09:00", sms_opted_out_at: null, diagnosis_name: "다낭성", doctor: { doctor_id: 2, name: "김연우" }, latest_visit: { visit_id: 9107, visited_at: "2026-08-13T10:00:00+09:00", status: "COMPLETED" }, work_category: "IN_PROGRESS", detail_status: "GUIDE_GENERATING", flags: [] },
  { patient_id: 2008, hospital_patient_no: "12008", name: "정민아", birth_date: "1988-03-14", gender: "FEMALE", age: 38, phone: "01044373456", sms_consent: true, sms_consented_at: "2026-08-13T10:00:00+09:00", sms_opted_out_at: null, diagnosis_name: "자궁내막증", doctor: { doctor_id: 1, name: "박연" }, latest_visit: { visit_id: 9108, visited_at: "2026-08-13T10:00:00+09:00", status: "COMPLETED" }, work_category: "APPROVAL_REQUESTED", detail_status: "APPROVAL_PENDING", flags: [] },
  { patient_id: 2009, hospital_patient_no: "11732", name: "이서아", birth_date: "1998-12-01", gender: "FEMALE", age: 27, phone: "01055219210", sms_consent: true, sms_consented_at: "2026-08-13T10:00:00+09:00", sms_opted_out_at: null, diagnosis_name: "다낭성", doctor: { doctor_id: 2, name: "김연우" }, latest_visit: { visit_id: 9109, visited_at: "2026-08-13T10:00:00+09:00", status: "COMPLETED" }, work_category: "SEND_PENDING", detail_status: "SCHEDULED_TO_SEND", flags: [] },
  { patient_id: 2010, hospital_patient_no: "09102", name: "서다은", birth_date: "1995-07-19", gender: "FEMALE", age: 31, phone: "01091866120", sms_consent: true, sms_consented_at: "2026-02-02T10:00:00+09:00", sms_opted_out_at: null, diagnosis_name: "다낭성", doctor: { doctor_id: 1, name: "박연" }, latest_visit: { visit_id: 9110, visited_at: "2026-02-02T10:00:00+09:00", status: "COMPLETED" }, work_category: "COMPLETED", detail_status: "VIEWED", flags: [] },
];

/* 서버와 **같은 규칙**으로 거른다. 다르면 목업에서만 되는 화면이 생긴다. */
function rosterHits(row, category) {
  if (category === "IN_TREATMENT") return row.work_category && row.work_category !== "COMPLETED";
  if (category === "NEEDS_ATTENTION") {
    return row.work_category === "NEEDS_ATTENTION" || (row.flags || []).length > 0;
  }
  if (category === "SMS_OPT_OUT") return !!row.sms_opted_out_at;
  if (category === "INACTIVE_6_MONTHS") {
    var when = new Date(row.latest_visit && row.latest_visit.visited_at);
    var edge = new Date();
    edge.setMonth(edge.getMonth() - 6);
    return !isNaN(when.getTime()) && when < edge;
  }
  return true;
}

function rosterPage(keyword, params) {
  var category = params.get("category") || "ALL";
  var limit = Number(params.get("limit")) || 20;
  var digits = keyword.replace(/\D/g, "");
  var searched = MOCK_ROSTER.filter(function (row) {
    if (!keyword) return true;
    if (row.name.indexOf(keyword) === 0) return true;
    if (!digits) return false;
    return row.hospital_patient_no.indexOf(digits) !== -1 || row.phone.indexOf(digits) !== -1;
  });
  var shown = searched.filter(function (row) {
    return rosterHits(row, category);
  });
  var counted = function (name) {
    return searched.filter(function (row) {
      return rosterHits(row, name);
    }).length;
  };
  return {
    counts: {
      ALL: searched.length,
      IN_TREATMENT: counted("IN_TREATMENT"),
      NEEDS_ATTENTION: counted("NEEDS_ATTENTION"),
      SMS_OPT_OUT: counted("SMS_OPT_OUT"),
      INACTIVE_6_MONTHS: counted("INACTIVE_6_MONTHS"),
    },
    selected_category: category,
    items: shown.slice(0, limit),
    page: { next_cursor: null, has_next: shown.length > limit },
  };
}

/* ── 환자 이력 모달 목업 (S2-2) ─────────────────────────────────────────
 *
 * 원문의 세 블록을 그대로 옮긴다 — 「3회 연속 미열람」인 최근 코스, 응답이
 * 있는 지난 코스, 「먹고 있는데 불편해요」로 답한 첫 코스.
 */
var MOCK_PATIENT_HISTORY = {
  2001: {
    patient_id: 2001,
    name: "유지수",
    hospital_patient_no: "10118",
    phone: "01031414410",
    diagnosis_name: "자궁내막증",
    doctor: { doctor_id: 2, name: "김연우" },
    total: 4,
    visits: [
      {
        visit_id: 9101,
        visited_at: "2026-05-20T10:00:00+09:00",
        prescription_set: "비잔 (계속)",
        course_days: 84,
        guide_sent_at: "2026-05-20T18:00:00+09:00",
        guide_viewed_at: "2026-05-27T09:00:00+09:00",
        checks: [
          { kind: "CHECK_D7", at: "2026-05-27T10:00:00+09:00", sent: true, viewed_at: null, answer: null },
          { kind: "CHECK_D15", at: "2026-06-04T10:00:00+09:00", sent: true, viewed_at: null, answer: null },
          { kind: "CHECK_D30", at: "2026-06-19T10:00:00+09:00", sent: true, viewed_at: null, answer: null },
        ],
        runs_out_on: "2026-08-12",
        revisited: false,
      },
      {
        visit_id: 9111,
        visited_at: "2026-02-14T10:00:00+09:00",
        prescription_set: "비잔 (계속)",
        course_days: 90,
        guide_sent_at: "2026-02-14T18:00:00+09:00",
        guide_viewed_at: "2026-02-15T09:00:00+09:00",
        checks: [
          { kind: "CHECK_D7", at: "2026-02-21T10:00:00+09:00", sent: true, viewed_at: "2026-02-21T20:00:00+09:00", answer: "taking" },
        ],
        runs_out_on: "2026-05-15",
        revisited: true,
      },
      {
        visit_id: 9112,
        visited_at: "2025-11-07T10:00:00+09:00",
        prescription_set: "비잔 (초회)",
        course_days: 84,
        guide_sent_at: "2025-11-07T18:00:00+09:00",
        guide_viewed_at: "2025-11-07T20:00:00+09:00",
        checks: [
          { kind: "CHECK_D7", at: "2025-11-14T10:00:00+09:00", sent: true, viewed_at: "2025-11-14T21:00:00+09:00", answer: "uncomfortable" },
        ],
        runs_out_on: "2026-01-30",
        revisited: true,
      },
    ],
  },
};

function mockPatientHistory(patientId, limit) {
  var found = MOCK_PATIENT_HISTORY[patientId];
  if (!found) {
    /* 목업에 없는 환자도 모달이 열려야 한다 — 이력이 없는 것도 답이다. */
    var row = MOCK_ROSTER.filter(function (item) {
      return item.patient_id === Number(patientId);
    })[0];
    if (!row) return Promise.reject(new ApiError("PATIENT_NOT_FOUND", 404, {}));
    return Promise.resolve({
      patient_id: row.patient_id,
      name: row.name,
      hospital_patient_no: row.hospital_patient_no,
      phone: row.phone,
      diagnosis_name: row.diagnosis_name,
      doctor: row.doctor,
      visits: [],
      total: 0,
    });
  }
  var shown = found.visits.slice(0, limit || 3);
  return Promise.resolve(Object.assign({}, found, { visits: shown }));
}

function deskPage(isoDate, categories) {
  var wanted = (categories || "").split(",").filter(Boolean);

  var rows = MOCK_TODAY.filter(function (v) {
    /* 보완은 해결될 때까지 날짜를 무시한다. 나머지는 visited_at 을
       Asia/Seoul 로 옮긴 날짜가 요청한 날과 같아야 한다(계약 §6). */
    if (v.work_category === "NEEDS_ATTENTION") return true;
    return v.visited_at.slice(0, 10) === isoDate;
  });

  var counts = {};
  WORK_CATEGORIES.forEach(function (c) {
    counts[c.key] = rows.filter(function (v) {
      return v.work_category === c.key;
    }).length;
  });

  return {
    date: isoDate,
    timezone: "Asia/Seoul",
    counts: counts,
    selected_categories: wanted.length
      ? wanted
      : WORK_CATEGORIES.map(function (c) {
          return c.key;
        }),
    items: (wanted.length
      ? rows.filter(function (v) {
          return wanted.indexOf(v.work_category) !== -1;
        })
      : rows
    ).map(deskItem),
    page: { next_cursor: null, has_next: false },
  };
}

/* 지난 방문. 「전에 뭐라고 안내했지?」를 관리 화면에서 찾지 않게 하려고
   환자 카드 안에 둔다(S1-4).

   약과 처방일수는 PRESCRIPTION 도메인 소유다 — KEY-26 §9 「처방 계약 경계」가
   `PRESCRIPTION_ITEM.duration_days` 로 정했고 아직 구현이 없다.
   TODO(KEY-41 이후) 그 API 가 생기면 여기 두 칸을 거기서 받는다. */
var MOCK_HISTORY = {
  1003: [
    {
      visit_id: 8201,
      visited_at: "2026-05-20",
      diagnosis_name: "자궁내막증",
      drug: "비잔 2mg",
      days: 90,
      has_guide: true,
    },
    {
      visit_id: 7714,
      visited_at: "2025-11-02",
      diagnosis_name: "자궁내막증",
      drug: "비잔 2mg",
      days: 90,
      has_guide: true,
    },
    {
      visit_id: 7302,
      visited_at: "2025-08-11",
      diagnosis_name: "자궁내막증 (초진)",
      drug: "비잔 2mg",
      days: 30,
      has_guide: true,
    },
  ],
  1006: [
    {
      visit_id: 8155,
      visited_at: "2026-08-01",
      diagnosis_name: "다낭성",
      drug: "메트포르민 500mg",
      days: 60,
      has_guide: true,
    },
  ],
  1007: [
    {
      visit_id: 8102,
      visited_at: "2026-08-11",
      diagnosis_name: "자궁내막증",
      drug: "비잔 2mg",
      days: 84,
      has_guide: false,
    },
  ],
  1008: [
    {
      visit_id: 8090,
      visited_at: "2026-05-14",
      diagnosis_name: "다낭성",
      drug: "메트포르민 500mg",
      days: 90,
      has_guide: true,
    },
  ],
};

function mockPatientsRequest(path, options) {
  var body = options.body || {};

  return new Promise(function (resolve, reject) {
    setTimeout(function () {
      /* 검색 — 이름은 **앞부분 일치**(계약 「한 글자부터 허용」) · 차트번호 · 정규화한 전화번호.
         서버가 `name__startswith` 로 도는데(#39) 화면이 「포함」으로 흉내내면
         목업에서만 찾히고 실서버에서 0건이 된다. */
      if (path.indexOf("/patients?") === 0) {
        var params = new URLSearchParams(path.slice("/patients?".length));
        var keyword = (params.get("keyword") || "").trim();
        /* **환자 관리 표(S2-1)는 빈 검색어에도 답한다.** 등록 화면의 찾기는
           아무 말 없이 온 세상을 돌려주면 안 되지만, 이쪽은 「의원 전체를
           훑는 자리」라 빈 목록이 답이 아니다 — `category` 가 그 갈림이다. */
        if (params.get("category")) return resolve(rosterPage(keyword, params));
        if (!keyword) return resolve(patientPage([]));
        var digits = keyword.replace(/\D/g, "");
        var hits = MOCK_PATIENTS.filter(function (p) {
          if (p.name.indexOf(keyword) === 0) return true;
          if (!digits) return false;
          return p.hospital_patient_no.indexOf(digits) !== -1 || p.phone.indexOf(digits) !== -1;
        });
        return resolve(patientPage(hits));
      }

      /* 오늘 목록(S1-1). NEEDS_ATTENTION 은 날짜와 무관하게 딸려 온다. */
      if (path.indexOf("/front-desk/visits?") === 0) {
        var deskParams = new URLSearchParams(path.slice("/front-desk/visits?".length));
        return resolve(deskPage(deskParams.get("date"), deskParams.get("categories")));
      }

      if (path === "/patients" && options.method === "POST") {
        /* 차트번호는 병원 내 유일하다. 화면에서도 막지만 판정은 서버가 한다. */
        var taken = MOCK_PATIENTS.some(function (p) {
          return p.hospital_patient_no === body.hospital_patient_no;
        });
        if (taken) return reject(new ApiError("DUPLICATE_HOSPITAL_PATIENT_NO", 409, {}));

        var created = {
          patient_id: ++MOCK_NEXT_ID.patient,
          hospital_patient_no: body.hospital_patient_no,
          name: body.name,
          birth_date: body.birth_date,
          phone: (body.phone || "").replace(/\D/g, ""),
          gender: body.gender || "FEMALE",
          sms_consent: !!body.sms_consent,
          sms_consented_at: body.sms_consent ? toIsoDate(new Date()) : null,
          last_visited_on: null,
        };
        MOCK_PATIENTS.push(created);
        return resolve(created);
      }

      /* 환자 한 명 (S1-4 ① 환자 정보) */
      var onePatient = path.match(/^\/patients\/(\d+)$/);
      if (onePatient && !options.method) {
        var found = MOCK_PATIENTS.find(function (p) {
          return p.patient_id === Number(onePatient[1]);
        });
        if (!found) return reject(new ApiError("PATIENT_NOT_FOUND", 404, {}));
        return resolve(found);
      }

      if (onePatient && options.method === "PATCH") {
        var target = MOCK_PATIENTS.find(function (p) {
          return p.patient_id === Number(onePatient[1]);
        });
        if (!target) return reject(new ApiError("PATIENT_NOT_FOUND", 404, {}));
        if (!Object.keys(body).length) return reject(new ApiError("EMPTY_UPDATE_FIELDS", 400, {}));
        /* 서버가 거부하는 것을 목업도 거부한다 — 화면이 못 보낼 것을 보내고 있으면
           목업에서 통과해 버리면 서버에 붙는 날 처음 알게 된다. */
        var illegal = Object.keys(body).filter(function (k) {
          return PATIENT_EDITABLE.indexOf(k) === -1;
        });
        if (illegal.length) {
          return reject(new ApiError("INVALID_REQUEST", 400, { field_errors: illegal }));
        }
        Object.keys(body).forEach(function (k) {
          target[k] = k === "phone" ? String(body[k]).replace(/\D/g, "") : body[k];
        });
        return resolve(target);
      }

      /* 지난 방문 — visited_at DESC, visit_id DESC 안정 정렬(계약 §6) */
      var visitList = path.match(/^\/patients\/(\d+)\/visits$/);
      if (visitList && !options.method) {
        var history = (MOCK_HISTORY[Number(visitList[1])] || []).slice().sort(function (a, b) {
          if (a.visited_at === b.visited_at) return b.visit_id - a.visit_id;
          return a.visited_at < b.visited_at ? 1 : -1;
        });
        return resolve({ items: history, page: { next_cursor: null, has_next: false } });
      }

      var oneVisit = path.match(/^\/visits\/(\d+)$/);
      var visitRow = oneVisit
        ? MOCK_TODAY.find(function (v) {
            return v.visit_id === Number(oneVisit[1]);
          })
        : null;

      if (oneVisit && !options.method) {
        if (!visitRow) return reject(new ApiError("VISIT_NOT_FOUND", 404, {}));
        return resolve(visitResource(visitRow));
      }

      if (oneVisit && options.method === "PATCH") {
        if (!visitRow) return reject(new ApiError("VISIT_NOT_FOUND", 404, {}));
        if (!Object.keys(body).length) return reject(new ApiError("EMPTY_UPDATE_FIELDS", 400, {}));

        var offLimits = Object.keys(body).filter(function (k) {
          return VISIT_EDITABLE.indexOf(k) === -1;
        });
        if (offLimits.length) {
          return reject(new ApiError("INVALID_REQUEST", 400, { field_errors: offLimits }));
        }

        /* 서버가 진료과·의사를 검증한 뒤 이름을 스냅샷으로 저장한다(계약 §6).
           그 두 갈래를 목업도 갈라 놓는다 — 화면이 오류 문구를 코드마다
           다르게 띄우는지 여기서 밖에 볼 데가 없다. */
        if ("department_id" in body) {
          var deptName = departmentOf(body.department_id);
          if (!deptName) return reject(new ApiError("INVALID_DEPARTMENT", 400, {}));
          visitRow.department = deptName;
        }
        if ("doctor_id" in body) {
          var picked = DOCTORS.find(function (d) {
            return d.doctor_id === Number(body.doctor_id);
          });
          if (!picked) return reject(new ApiError("INVALID_REQUEST", 400, {}));
          var wantDept = "department_id" in body ? Number(body.department_id) : picked.department_id;
          if (picked.department_id !== wantDept) {
            return reject(new ApiError("DOCTOR_DEPARTMENT_MISMATCH", 400, {}));
          }
          visitRow.doctor = { doctor_id: picked.doctor_id, name: picked.name };
        }
        ["visited_at", "visit_summary", "doctor_note", "status", "planned_stop"].forEach(function (k) {
          if (k in body) visitRow[k] = body[k];
        });
        return resolve(visitResource(visitRow));
      }

      var visitPath = path.match(/^\/patients\/(\d+)\/visits$/);
      if (visitPath && options.method === "POST") {
        var patientId = Number(visitPath[1]);
        var who = MOCK_PATIENTS.find(function (p) {
          return p.patient_id === patientId;
        });
        if (!who) return reject(new ApiError("PATIENT_NOT_FOUND", 404, {}));

        var doctor = null;
        if ("doctor_id" in body && body.doctor_id !== null) {
          doctor = DOCTORS.find(function (d) {
            return d.doctor_id === Number(body.doctor_id);
          });
          if (!doctor) return reject(new ApiError("INVALID_REQUEST", 400, {}));
        }
        var visit = {
          visit_id: ++MOCK_NEXT_ID.visit,
          patient_id: patientId,
          name: who.name,
          hospital_patient_no: who.hospital_patient_no,
          birth_date: who.birth_date,
          age: ageOf(who.birth_date),
          diagnosis_name: who.last_dx || null,
          doctor: doctor ? { doctor_id: doctor.doctor_id, name: doctor.name } : null,
          /* 화면은 department_id 를 보내고 이름은 서버가 붙인다 — 계약 §4 「검증된
             진료과 명칭을 저장한 진료 당시 스냅샷」. 진료과 이름이 나중에 바뀌어도
             지난 진료는 그날의 이름으로 남아야 한다. */
          department: departmentOf(body.department_id),
          visited_at: body.visited_at || new Date().toISOString(),
          status: body.status || "COMPLETED",
          planned_stop: body.planned_stop || false,
          /* 새 진료는 아직 아무 이벤트도 없다 — 계약의 파생 규칙대로 IN_PROGRESS · NO_DOCUMENT */
          work_category: "IN_PROGRESS",
          detail_status: "NO_DOCUMENT",
        };
        MOCK_TODAY.unshift(visit);
        return resolve(visit);
      }

      return reject(new ApiError("NOT_FOUND", 404, {}));
    }, 180);
  });
}

/* 나이는 저장하지 않는다 — birth_date 에서 계산한다 */
function ageOf(birthDate) {
  var born = new Date(birthDate);
  if (isNaN(born.getTime())) return null;
  var now = new Date();
  var years = now.getFullYear() - born.getFullYear();
  var monthDiff = now.getMonth() - born.getMonth();
  if (monthDiff < 0 || (monthDiff === 0 && now.getDate() < born.getDate())) years -= 1;
  return years;
}

/* **화면에는 전체 번호를 보여 준다.**
 *
 * 전에는 가운데를 `****` 로 가렸다(와이어프레임도 그렇게 그렸다). 그런데 이
 * 번호를 보는 사람은 그 환자를 방금 접수한 그 의원의 스탭이고, 안내 문자가
 * 안 가면 **전화를 걸어야 하는 사람**이다. 가려 두면 번호를 확인하려고 EMR 을
 * 따로 열게 되고, 그 사이에 옮겨 적다 틀린다.
 *
 * **로그와 오류 응답의 마스킹은 그대로다** — 그쪽은 KEY-48 이 요구하는 보안
 * 사항이고 여기와 다른 문제다. 화면은 권한 있는 사람이 보고, 로그는 누가 볼지
 * 모른다.
 *
 * 끊어 쓰는 것은 읽기 위해서다 — `01056785687` 은 눈으로 옮겨 적기 어렵다.
 */
/* ── 숫자만 쳐도 하이픈이 붙는다 ─────────────────────────────────────
 *
 * 스탭은 EMR 을 보며 옮겨 적는다. 거기 적힌 것은 `19940722` · `01047851256`
 * 같은 숫자열이라, 하이픈을 손으로 넣게 하면 자리를 세어 가며 친다. 게다가
 * 안 넣으면 「생년월일은 1994-07-22 처럼 적어 주세요」로 막혀 다시 고친다.
 *
 * **화면 밖의 규칙이라 검사가 부른다.** 자리 셈은 눈으로 확인하기 어렵다.
 */

function onlyDigits(text) {
  return String(text === null || text === undefined ? "" : text).replace(/\D/g, "");
}

/** `19940722` → `1994-07-22`. **치는 도중에도 자연스럽게** — 5자면 `1994-0`.
    다 친 뒤에만 모양을 잡으면 마지막 글자에서 화면이 튄다. */
function birthMask(text) {
  var d = onlyDigits(text).slice(0, 8);
  if (d.length <= 4) return d;
  if (d.length <= 6) return d.slice(0, 4) + "-" + d.slice(4);
  return d.slice(0, 4) + "-" + d.slice(4, 6) + "-" + d.slice(6);
}

/** `01047851256` → `010-4785-1256`.

    가운데 자릿수는 **길이가 정한다** — 11자리는 4, 10자리는 3이다(`011-234-5678`).
    010 만 보고 4로 박으면 옛 번호가 `011-2345-678` 로 어긋난다. */
function phoneMask(text) {
  var d = onlyDigits(text).slice(0, 11);
  if (d.length <= 3) return d;
  var mid = d.length > 10 ? 4 : 3;
  if (d.length <= 3 + mid) return d.slice(0, 3) + "-" + d.slice(3);
  return d.slice(0, 3) + "-" + d.slice(3, 3 + mid) + "-" + d.slice(3 + mid);
}

/** 숫자 `n` 개를 지난 자리. 하이픈을 넣으면 글자 수가 늘어 커서가 밀린다 —
    **몇 번째 숫자 뒤였는지**로 되찾는다. */
function maskCaret(masked, digits) {
  if (digits <= 0) return 0;
  var seen = 0;
  for (var i = 0; i < masked.length; i++) {
    if (/\d/.test(masked[i])) {
      seen += 1;
      if (seen === digits) return i + 1;
    }
  }
  return masked.length;
}

/** 지운 것이 하이픈뿐이었나. 그러면 그 앞 숫자를 마저 지운다 — 안 그러면
    하이픈이 곧바로 다시 붙어 **지운 것이 없어 보이고**, 두 번 눌러야 한다. */
function maskAfterDelete(digits, at) {
  if (at <= 0) return { digits: digits, at: at };
  return { digits: digits.slice(0, at - 1) + digits.slice(at), at: at - 1 };
}

/** 담아 둔 번호를 읽기 좋게. **치는 중과 같은 규칙을 쓴다** — 두 벌로 두면
    손으로 친 것과 화면에 뜬 것이 달라 보인다. */
function formatPhone(digits) {
  return phoneMask(digits);
}
