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
  updateVisit: function (visitId, patch) {
    return patientsRequest("/visits/" + visitId, { method: "PATCH", body: patch });
  },
};

/* 계약 §6 이 정한 수정 가능 필드. 화면이 이 목록 밖을 보내면 400 이다.
   목록을 코드에 두는 이유는, 폼에 칸을 하나 늘렸을 때 여기도 같이 늘려야
   한다는 것이 눈에 보이게 하려는 것이다. */
var PATIENT_EDITABLE = ["name", "birth_date", "gender", "phone", "sms_consent"];
var VISIT_EDITABLE = ["doctor_name", "department", "visited_at", "status", "planned_stop"];

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
  return [
    { patient_id: 1003, visit_id: 8842, hospital_patient_no: "12345", name: "김서연", dx: "자궁내막증", age: 36, department: "산부인과", doctor: "박연 원장", visited_at: "2026-08-19T10:32:00+09:00", status: "COMPLETED", planned_stop: false, state: "진료기록 없음", tab: "draft" },
    { patient_id: 1006, visit_id: 8843, hospital_patient_no: "11204", name: "이지우", dx: "다낭성", age: 31, department: "산부인과", doctor: "김연우 원장", visited_at: "2026-08-19T09:14:00+09:00", status: "COMPLETED", planned_stop: false, state: "생성 중", tab: "draft" },
    /* 08-11 건인데 오늘 목록에 있다 — 보완 탭만은 날짜와 무관하게 해결될 때까지 남는다 */
    { patient_id: 1007, visit_id: 8798, hospital_patient_no: "09871", name: "박수빈", dx: "자궁내막증", age: 34, department: "산부인과", doctor: "박연 원장", visited_at: "2026-08-11T16:05:00+09:00", status: "COMPLETED", planned_stop: false, state: "번호 오류", tab: "fix" },
  ];
})();

/* 지난 방문. 「전에 뭐라고 안내했지?」를 관리 화면에서 찾지 않게 하려고
   환자 카드 안에 둔다(S1-4).

   약과 처방일수는 PRESCRIPTION 도메인 소유다 — KEY-26 §9 「처방 계약 경계」가
   `PRESCRIPTION_ITEM.duration_days` 로 정했고 아직 구현이 없다.
   TODO(KEY-41 이후) 그 API 가 생기면 여기 두 칸을 거기서 받는다. */
var MOCK_HISTORY = {
  1003: [
    { visit_id: 8201, visited_at: "2026-05-20", dx: "자궁내막증", drug: "비잔 2mg", days: 90, has_guide: true },
    { visit_id: 7714, visited_at: "2025-11-02", dx: "자궁내막증", drug: "비잔 2mg", days: 90, has_guide: true },
    { visit_id: 7302, visited_at: "2025-08-11", dx: "자궁내막증 (초진)", drug: "비잔 2mg", days: 30, has_guide: true },
  ],
  1006: [{ visit_id: 8155, visited_at: "2026-08-01", dx: "다낭성", drug: "메트포르민 500mg", days: 60, has_guide: true }],
  1007: [{ visit_id: 8102, visited_at: "2026-08-11", dx: "자궁내막증", drug: "비잔 2mg", days: 84, has_guide: false }],
};

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
      if (oneVisit && options.method === "PATCH") {
        var row = MOCK_TODAY.find(function (v) {
          return v.visit_id === Number(oneVisit[1]);
        });
        if (!row) return reject(new ApiError("VISIT_NOT_FOUND", 404, {}));
        if (!Object.keys(body).length) return reject(new ApiError("EMPTY_UPDATE_FIELDS", 400, {}));
        Object.keys(body).forEach(function (k) {
          if (k === "doctor_name") row.doctor = body[k];
          else row[k] = body[k];
        });
        return resolve(row);
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
          department: body.department || "",
          doctor: body.doctor_name || "",
          visited_at: body.visited_at || new Date().toISOString(),
          status: "COMPLETED",
          planned_stop: false,
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
