/* 환자·진료 API — KEY-35 · KEY-50
 *
 * 계약은 `docs/contracts/patient-visit-api-v1.md` (KEY-26) 를 따른다.
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

  create: function (patient) {
    return patientsRequest("/patients", { method: "POST", body: patient });
  },
  createVisit: function (patientId, visit) {
    return patientsRequest("/patients/" + patientId + "/visits", {
      method: "POST",
      body: visit,
    });
  },
};

/* 등록 화면에서 고르는 진료과 · 담당의사.
   계약은 `department_id` · `doctor_id` 를 받는다 — 화면이 이름을 보내면 진료과가
   폐지됐는지, 그 의사가 거기 소속인지 서버가 볼 수 없다.
   TODO(KEY-33) 직원·진료과 API 가 생기면 여기를 그걸로 갈아 끼운다.
   지금 값은 docs/data/synthetic-staff.csv 의 의사 계정을 따른다. */
var DEPARTMENTS = [{ department_id: 7, name: "산부인과" }];
var DOCTORS = [
  { doctor_id: 12, name: "박연 원장", department_id: 7 },
  { doctor_id: 13, name: "김연우 원장", department_id: 7 },
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
];

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
  ];
})();

/* ── 계약이 정한 응답 봉투 ──────────────────────────────────────
   화면이 `items` 만 꺼내 쓰더라도 목업이 봉투를 갖춰야, 서버가 붙는 날
   「그런 키가 없다」로 처음 알게 되는 일이 없다. */

function patientPage(items) {
  return {
    counts: { ALL: MOCK_PATIENTS.length },
    selected_category: "ALL",
    items: items,
    page: { next_cursor: null, has_next: false },
  };
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
    items: wanted.length
      ? rows.filter(function (v) {
          return wanted.indexOf(v.work_category) !== -1;
        })
      : rows,
    page: { next_cursor: null, has_next: false },
  };
}

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
          last_visited_on: null,
        };
        MOCK_PATIENTS.push(created);
        return resolve(created);
      }

      var visitPath = path.match(/^\/patients\/(\d+)\/visits$/);
      if (visitPath && options.method === "POST") {
        var patientId = Number(visitPath[1]);
        var who = MOCK_PATIENTS.find(function (p) {
          return p.patient_id === patientId;
        });
        if (!who) return reject(new ApiError("PATIENT_NOT_FOUND", 404, {}));

        var doctor = DOCTORS.find(function (d) {
          return d.doctor_id === body.doctor_id;
        });
        var visit = {
          visit_id: ++MOCK_NEXT_ID.visit,
          patient_id: patientId,
          name: who.name,
          hospital_patient_no: who.hospital_patient_no,
          birth_date: who.birth_date,
          age: ageOf(who.birth_date),
          diagnosis_name: who.last_dx || null,
          doctor: doctor ? { doctor_id: doctor.doctor_id, name: doctor.name } : null,
          visited_at: body.visited_at || new Date().toISOString(),
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

/* 화면에 전체 번호를 띄우지 않는다 — 같은 이름을 가를 만큼만 보여 준다 */
function maskPhone(digits) {
  var d = (digits || "").replace(/\D/g, "");
  if (d.length < 8) return d;
  return d.slice(0, 3) + "-****-" + d.slice(-4);
}
