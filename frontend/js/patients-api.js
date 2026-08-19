/* 환자·진료 API — KEY-35
 *
 * 계약은 KEY-26 (환자·진료 v1) 을 따른다.
 *   GET  /api/v1/patients?q=&visited_on=&offset=&limit=   → { items, total, offset, limit }
 *   POST /api/v1/patients
 *   POST /api/v1/patients/{patient_id}/visits
 *
 * 식별자 셋을 섞지 않는다.
 *   patient_id           사람
 *   visit_id             그 사람의 한 진료 건 — 업로드 · 판독 · 안내가 붙는다
 *   hospital_patient_no  화면에 보이는 차트번호. 검색에 쓴다
 *
 * 서버에 아직 이 셋이 없다(KEY-31 진행 중). 계약대로 짜 두고 ?mock=1 로 화면을
 * 확인한다. 서버가 붙으면 아래 「목업」 아래를 통째로 지우면 된다 —
 * api.js 의 request() 를 그대로 쓰므로 이 파일 위쪽은 손댈 것이 없다.
 */

function patientsRequest(path, options) {
  options = options || {};
  if (MOCK) return mockPatientsRequest(path, options);
  return request(path, options);
}

var patientsApi = {
  search: function (query) {
    return patientsRequest("/patients?q=" + encodeURIComponent(query));
  },
  /* 목록의 축은 하루다. 계약의 visited_at 은 datetime 이라 날짜로 묶어 묻는다. */
  onDay: function (isoDate) {
    return patientsRequest("/patients?visited_on=" + encodeURIComponent(isoDate));
  },
  create: function (patient) {
    return patientsRequest("/patients", { method: "POST", body: patient });
  },
  createVisit: function (patientId, visit) {
    return patientsRequest("/patients/" + patientId + "/visits", { method: "POST", body: visit });
  },
};

/* 등록 화면에서 고르는 진료과 · 담당의사.
   TODO(KEY-33) 직원 API 가 생기면 GET /api/v1/staff?role=doctor 로 갈아 끼운다.
   지금 값은 docs/data/synthetic-staff.csv 의 의사 계정을 따른다. */
var DEPARTMENTS = ["산부인과"];
var DOCTORS = ["박연 원장", "김연우 원장"];

/* ── 목업 ──────────────────────────────────────────────────────
 * 합성 데이터(docs/data/synthetic-patients.csv)의 동명이인 무리를 그대로 옮겼다.
 * 「김」 한 글자로 찾으면 김서연 셋이 뜨고 생년월일로 갈라야 고를 수 있다.
 * 이서윤 둘은 생년월일까지 같아서 폰 뒷자리(4153 / 4156)로만 갈린다 —
 * S1-2 의 결과 줄이 실제로 갈라 주는지 보려면 이 둘이 필요하다.
 */
var MOCK_PATIENTS = [
  { patient_id: 1001, hospital_patient_no: "10737", name: "김서연", birth_date: "1975-03-09", phone: "01044342271", last_visited_on: "2026-08-07", last_dx: "자궁내막증", last_drug: "비잔" },
  { patient_id: 1002, hospital_patient_no: "08157", name: "김서연", birth_date: "1988-07-14", phone: "01083245439", last_visited_on: "2026-02-14", last_dx: "다낭성", last_drug: "메트포르민" },
  { patient_id: 1003, hospital_patient_no: "12345", name: "김서연", birth_date: "1990-01-01", phone: "01044524085", last_visited_on: "2026-05-20", last_dx: "자궁내막증", last_drug: "비잔" },
  { patient_id: 1004, hospital_patient_no: "09817", name: "이서윤", birth_date: "1994-05-21", phone: "01088214153", last_visited_on: "2026-02-14", last_dx: "다낭성", last_drug: "야스민" },
  { patient_id: 1005, hospital_patient_no: "10878", name: "이서윤", birth_date: "1994-05-21", phone: "01038944156", last_visited_on: "2026-07-29", last_dx: "자궁내막증", last_drug: "비잔" },
  { patient_id: 1006, hospital_patient_no: "11204", name: "이지우", birth_date: "1995-04-02", phone: "01022331204", last_visited_on: "2026-08-01", last_dx: "다낭성", last_drug: "메트포르민" },
  { patient_id: 1007, hospital_patient_no: "09871", name: "박수빈", birth_date: "1992-09-18", phone: "01077129871", last_visited_on: "2026-08-11", last_dx: "자궁내막증", last_drug: "비잔" },
];

var MOCK_NEXT_ID = { patient: 2000, visit: 9000 };

/* 오늘 목록. 등록하면 여기에 쌓인다 — 화면이 실제로 늘어나는지 봐야 한다.
   ?today=empty 로 비우면 S1-1(도입 첫날)을 그대로 볼 수 있다. */
var MOCK_TODAY = (function () {
  var q = new URLSearchParams(location.search).get("today");
  if (q !== null) sessionStorage.setItem("mockToday", q);
  if (sessionStorage.getItem("mockToday") === "empty") return [];
  return [
    { patient_id: 1003, visit_id: 8842, hospital_patient_no: "12345", name: "김서연", dx: "자궁내막증", age: 36, doctor: "박연 원장", state: "진료기록 없음", tab: "draft" },
    { patient_id: 1006, visit_id: 8843, hospital_patient_no: "11204", name: "이지우", dx: "다낭성", age: 31, doctor: "김연우 원장", state: "생성 중", tab: "draft" },
    /* 08-11 건인데 오늘 목록에 있다 — 보완 탭만은 날짜와 무관하게 해결될 때까지 남는다 */
    { patient_id: 1007, visit_id: 8798, hospital_patient_no: "09871", name: "박수빈", dx: "자궁내막증", age: 34, doctor: "박연 원장", state: "번호 오류", tab: "fix" },
  ];
})();

function mockPatientsRequest(path, options) {
  var body = options.body || {};

  return new Promise(function (resolve, reject) {
    setTimeout(function () {
      /* 검색 — 이름 한 글자부터 · 차트번호 · 정규화한 전화번호 */
      if (path.indexOf("/patients?q=") === 0) {
        var q = decodeURIComponent(path.slice("/patients?q=".length)).trim();
        if (!q) return resolve({ items: [], total: 0, offset: 0, limit: 20 });
        var digits = q.replace(/\D/g, "");
        var hits = MOCK_PATIENTS.filter(function (p) {
          if (p.name.indexOf(q) !== -1) return true;
          if (!digits) return false;
          return p.hospital_patient_no.indexOf(digits) !== -1 || p.phone.indexOf(digits) !== -1;
        });
        return resolve({ items: hits, total: hits.length, offset: 0, limit: 20 });
      }

      if (path.indexOf("/patients?visited_on=") === 0) {
        return resolve({ items: MOCK_TODAY.slice(), total: MOCK_TODAY.length, offset: 0, limit: 20 });
      }

      if (path === "/patients" && options.method === "POST") {
        /* 차트번호는 병원 내 유일하다. 화면에서도 막지만 판정은 서버가 한다. */
        var taken = MOCK_PATIENTS.some(function (p) {
          return p.hospital_patient_no === body.hospital_patient_no;
        });
        if (taken) return reject(new ApiError("duplicate_hospital_patient_no", 409, {}));

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
        if (!who) return reject(new ApiError("patient_not_found", 404, {}));

        var visit = {
          visit_id: ++MOCK_NEXT_ID.visit,
          patient_id: patientId,
          hospital_patient_no: who.hospital_patient_no,
          name: who.name,
          dx: who.last_dx || "",
          age: ageOf(who.birth_date),
          doctor: body.doctor_name || "",
          state: "진료기록 없음",
          tab: "draft",
        };
        MOCK_TODAY.unshift(visit);
        return resolve(visit);
      }

      return reject(new ApiError("unknown", 404, {}));
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
