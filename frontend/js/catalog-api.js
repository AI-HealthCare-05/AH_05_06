/* 약속처방 카탈로그 — KEY-234.
 *
 *   GET  /api/v1/prescription-sets                        목록 (고르는 칸이 쓴다)
 *   GET  /api/v1/prescription-sets/{id}                   한 세트 (설정 화면)
 *   PUT  /api/v1/prescription-sets/{id}                   저장 — 의사만
 *
 * **목록과 상세를 가른다.** 목록에 상세를 다 실으면 고르는 칸 하나 그리려고
 * 여덟 세트의 약·문구를 전부 받아 온다.
 */
/* 확인 항목은 **처방이 정한다**(와이어프레임 S1-6 「처방별」). 지금은 여덟
   세트 모두 다섯을 여쭙는다 — 서버 씨앗과 같은 값이다. 어느 처방에 무엇을
   여쭐지는 의사가 설정(D2-3)에서 정하고, 그때 이 목업도 따라가야 한다. */
var MOCK_CHECK_ITEMS = [
  "DEPRESSION",
  "HYPERTENSION",
  "OSTEOPOROSIS",
  "DIABETES",
  "PREGNANCY_PLAN",
];

var MOCK_PRESCRIPTION_SETS = [
  {
    prescription_set_id: 1,
    name: "자궁내막증 · 비잔 (처음)",
    check_items: MOCK_CHECK_ITEMS,
    drugs: [{ name: "비잔정(디에노게스트) 2mg", frequency: "1일 1회", note: "매일 같은 시간" }],
  },
  {
    prescription_set_id: 2,
    name: "자궁내막증 · 비잔 (계속)",
    check_items: MOCK_CHECK_ITEMS,
    drugs: [{ name: "비잔정(디에노게스트) 2mg", frequency: "1일 1회", note: "매일 같은 시간" }],
  },
  {
    prescription_set_id: 3,
    name: "자궁내막증 · 통증관리",
    check_items: MOCK_CHECK_ITEMS,
    drugs: [{ name: "진통제", frequency: "필요시", note: "통증이 있을 때만" }],
  },
  {
    prescription_set_id: 4,
    name: "PCOS · 초진",
    check_items: MOCK_CHECK_ITEMS,
    days_mode: "PACK",
    days_per_pack: 28,
    drugs: [{ name: "야즈정(드로스피레논/에티닐에스트라디올)", frequency: "1일 1회", note: "매일 같은 시간" },
      { name: "진통제", frequency: "필요시" }],
  },
  {
    prescription_set_id: 5,
    name: "PCOS · 초진 (야즈 불가)",
    check_items: MOCK_CHECK_ITEMS,
    drugs: [{ name: "메트포르민 500mg", frequency: "1일 2회", note: "아침 · 저녁 식후" }],
  },
  {
    prescription_set_id: 6,
    name: "PCOS · 야즈 (계속)",
    check_items: MOCK_CHECK_ITEMS,
    drugs: [{ name: "야즈정(드로스피레논/에티닐에스트라디올)", frequency: "1일 1회", note: "매일 같은 시간" }],
  },
  {
    prescription_set_id: 7,
    name: "PCOS · 야즈 + 메트포르민",
    check_items: MOCK_CHECK_ITEMS,
    drugs: [{ name: "야즈정(드로스피레논/에티닐에스트라디올)", frequency: "1일 1회", note: "매일 같은 시간" },
      { name: "메트포르민 500mg", frequency: "1일 2회", note: "아침 · 저녁 식후" }],
  },
  {
    prescription_set_id: 8,
    name: "PCOS · 대사관리",
    check_items: MOCK_CHECK_ITEMS,
    drugs: [{ name: "메트포르민 500mg", frequency: "1일 2회", note: "아침 · 저녁 식후" }],
  },
];

var catalogApi = {
  sets: function () {
    if (MOCK)
      return Promise.resolve(MOCK_PRESCRIPTION_SETS.map(mockSetListRow));
    return request("/prescription-sets");
  },

  set: function (id) {
    if (MOCK) return mockSetDetail(id);
    return request("/prescription-sets/" + encodeURIComponent(id));
  },

  /* 문자 문구(D2-5). **안내문과 층이 다르다** — 이쪽은 링크를 실어 나르는
     문자 본문이다. 저장·되돌리기 모두 판 전체를 돌려받는다: 한 칸을 고치면
     「지금 기본값인가」가 그 칸만 바뀌므로 굳이 따로 물을 이유가 없다. */
  templates: function () {
    if (MOCK) return mockTemplates();
    return request("/message-templates");
  },

  saveTemplate: function (kind, body) {
    if (MOCK) return mockSaveTemplate(kind, body);
    return request("/message-templates/" + encodeURIComponent(kind), {
      method: "PUT",
      body: { body: body },
    });
  },

  resetTemplate: function (kind) {
    if (MOCK) return mockSaveTemplate(kind, null);
    return request("/message-templates/" + encodeURIComponent(kind), {
      method: "DELETE",
    });
  },

  /* 검사 기준선(D2-4). `doctor_id` 가 없으면 의원 공통이다 — 원문의
     「누구 기준」. 저장은 **한 판 통째로**: 줄마다 번호를 주고받으면 지운 줄을
     놓쳐 유령이 남는다. */
  baselines: function (doctorId) {
    if (MOCK) return mockBaselines(doctorId);
    return request(
      "/lab-baselines" +
        (doctorId ? "?doctor_id=" + encodeURIComponent(doctorId) : ""),
    );
  },

  saveBaselines: function (doctorId, items) {
    if (MOCK) return mockSaveBaselines(doctorId, items);
    return request(
      "/lab-baselines" +
        (doctorId ? "?doctor_id=" + encodeURIComponent(doctorId) : ""),
      {
        method: "PUT",
        body: { items: items },
      },
    );
  },

  /* 안내문 문구(D2-1 · D2-2). **원본은 손대지 않는다** — 이 API 가 다루는
     것은 그 위에 덧씌우는 표현뿐이다. */
  guideCopy: function (doctorId) {
    if (MOCK) return mockGuideCopy();
    return request(
      "/guide-copy" +
        (doctorId ? "?doctor_id=" + encodeURIComponent(doctorId) : ""),
    );
  },

  saveCopy: function (setId, section, body) {
    if (MOCK) return mockSaveCopy(setId, section, body);
    return request(
      "/guide-copy/" +
        encodeURIComponent(setId) +
        "/" +
        encodeURIComponent(section),
      {
        method: "PUT",
        body: { body: body },
      },
    );
  },

  revertCopy: function (setId, section) {
    if (MOCK) return mockSaveCopy(setId, section, null);
    return request(
      "/guide-copy/" +
        encodeURIComponent(setId) +
        "/" +
        encodeURIComponent(section),
      {
        method: "DELETE",
      },
    );
  },

  reviewCopy: function (setId) {
    if (MOCK) return mockReviewCopy(setId);
    return request("/guide-copy/" + encodeURIComponent(setId) + "/review", {
      method: "POST",
    });
  },

  saveSet: function (id, plan) {
    if (MOCK) return mockSaveSet(id, plan);
    return request("/prescription-sets/" + encodeURIComponent(id), {
      method: "PUT",
      body: plan,
    });
  },
};

/* ── 목업 ──────────────────────────────────────────────────────────────
 *
 * 서버와 **같은 모양**이어야 한다. 다르면 목업에서만 되는 화면이 생긴다 —
 * `MOCK_PATIENTS` 가 서로를 덮던 것을 이 저장소에서 이미 겪었다.
 */
var mockSetDetails = null;

function mockSetSeed() {
  /* 씨앗은 서버 마이그레이션과 같은 규칙이다 — 이름에서 질환·시점을 읽는다 */
  return MOCK_PRESCRIPTION_SETS.map(function (row) {
    return {
      prescription_set_id: row.prescription_set_id,
      name: row.name,
      disease: row.name.indexOf("PCOS") === 0 ? "PCOS" : "ENDOMETRIOSIS",
      phase:
        row.name.indexOf("(처음)") !== -1 || row.name.indexOf("초진") !== -1
          ? "FIRST"
          : "CONTINUE",
      /* **기본 목록이 정한 것을 덮지 않는다.** 여기서 `"DAYS"` 로 못박아
         두었더니 목록에 적어 둔 「통으로 센다」가 사라져, 화면에서 통 환산을
         한 번도 못 봤다. */
      days_mode: row.days_mode || "DAYS",
      days_per_pack: row.days_per_pack == null ? null : row.days_per_pack,
      emr_code: null,
      revisit_note: null,
      check_d15_on: true,
      check_d30_on: false,
      run_out_on: true,
      run_out_before_days: 3,
      drugs: (row.drugs || []).slice(),
      check_items: (row.check_items || []).slice(),
    };
  });
}

function mockSetStore() {
  if (!mockSetDetails) mockSetDetails = mockSetSeed();
  return mockSetDetails;
}

function mockSetListRow(row) {
  /* 서버가 목록에 담아 주는 것과 **같은 칸만** 준다. 목업이 더 주면 화면이
     목업에서만 되는 것을 쓰게 되고, 서버에 붙이는 날 조용히 빈다. */
  var mine = mockSetStore().filter(function (s) {
    return s.prescription_set_id === row.prescription_set_id;
  })[0];
  return {
    prescription_set_id: row.prescription_set_id,
    name: mine ? mine.name : row.name,
    /* 레일이 질환으로 묶는다 — 상세를 받아야 알 수 있게 두면 여덟 번 다녀온다 */
    disease: mine ? mine.disease : "ENDOMETRIOSIS",
    check_items: mine ? mine.check_items.slice() : [],
    /* 판독 화면이 처방을 고르는 순간 약 목록을 세운다 — 확인 항목과 같은
       이유로 목록과 함께 준다 (2heej 님 `#176` 리뷰) */
    drugs: mine ? mine.drugs.slice() : [],
    days_mode: mine ? mine.days_mode : "DAYS",
    days_per_pack: mine ? mine.days_per_pack : null,
  };
}

function mockSetDetail(id) {
  return new Promise(function (resolve, reject) {
    setTimeout(function () {
      var mine = mockSetStore().filter(function (s) {
        return s.prescription_set_id === Number(id);
      })[0];
      if (!mine)
        return reject(new ApiError("PRESCRIPTION_SET_NOT_FOUND", 404, {}));
      return resolve(JSON.parse(JSON.stringify(mine)));
    }, 80);
  });
}

function mockSaveSet(id, plan) {
  return new Promise(function (resolve, reject) {
    setTimeout(function () {
      /* 서버 규칙 그대로 — 의사만, 통으로 세는데 한 통이 며칠인지 없으면 422 */
      var who = MOCK_STAFF[sessionStorage.getItem("mockUser")];
      if (!who || (who.roles || []).indexOf("doctor") === -1) {
        return reject(new ApiError("FORBIDDEN", 403, {}));
      }
      if (plan.days_mode === "PACK" && !plan.days_per_pack) {
        return reject(new ApiError("DAYS_PER_PACK_REQUIRED", 422, {}));
      }

      var store = mockSetStore();
      for (var i = 0; i < store.length; i++) {
        if (store[i].prescription_set_id !== Number(id)) continue;
        store[i] = JSON.parse(JSON.stringify(plan));
        store[i].prescription_set_id = Number(id);
        /* 일수로 세면 통 크기를 비운다 — 서버와 같다 */
        if (store[i].days_mode !== "PACK") store[i].days_per_pack = null;
        return resolve(JSON.parse(JSON.stringify(store[i])));
      }
      return reject(new ApiError("PRESCRIPTION_SET_NOT_FOUND", 404, {}));
    }, 120);
  });
}

/* ── 문자 문구 목업 (D2-5) ─────────────────────────────────────────────
 *
 * 기본 문구는 **서버와 같은 글**이어야 한다. 다르면 목업에서 센 바이트 수와
 * 실제로 나가는 문자가 갈린다.
 */
var MOCK_TEMPLATE_DEFAULT = {
  GUIDE:
    "[{의원명}] {환자명}님, 오늘 진료 안내입니다. {만료일}까지 보실 수 있어요: {링크}",
  CHECK_D7:
    "{환자명}님, 복약 {일차}일째 확인입니다. 잘 드시고 계신가요? {링크}",
  CHECK_D15:
    "{환자명}님, 복약 {일차}일째 확인입니다. 불편한 점은 없으세요? {링크}",
  CHECK_D30:
    "{환자명}님, 복약 한 달째 확인입니다. 계속 드시고 계신가요? {링크}",
  RUN_OUT:
    "[{의원명}] 처방약이 {D}일 뒤 소진됩니다. 재진 예약을 잡아주세요: {예약링크}",
  REVISIT:
    "[{의원명}] {환자명}님, 처방받으신 약({일수}일분)이 소진되었습니다. 재진 예약을 잡아주세요 · 예약: {예약링크}",
};

var MOCK_TEMPLATE_REQUIRED = {
  GUIDE: ["링크"],
  CHECK_D7: ["링크"],
  CHECK_D15: ["링크"],
  CHECK_D30: ["링크"],
  RUN_OUT: ["예약링크"],
  REVISIT: ["예약링크"],
};

var MOCK_TEMPLATE_KNOWN = [
  "D",
  "링크",
  "만료일",
  "번호",
  "예약링크",
  "의원명",
  "일수",
  "일차",
  "환자명",
];
var MOCK_TEMPLATE_SYSTEM =
  "[{의원명}] 인증번호 {번호} — 3분 안에 입력해 주세요";

/* 고친 것만 담는다 — 서버와 같은 규칙이다. */
var mockTemplateEdits = {};

function mockTemplatePage() {
  return Promise.resolve({
    items: Object.keys(MOCK_TEMPLATE_DEFAULT).map(function (kind) {
      var edited = mockTemplateEdits[kind];
      return {
        kind: kind,
        body: edited == null ? MOCK_TEMPLATE_DEFAULT[kind] : edited,
        default_body: MOCK_TEMPLATE_DEFAULT[kind],
        is_default: edited == null,
        required_variables: MOCK_TEMPLATE_REQUIRED[kind],
      };
    }),
    known_variables: MOCK_TEMPLATE_KNOWN,
    sms_limit: 90,
    system_body: MOCK_TEMPLATE_SYSTEM,
  });
}

function mockTemplates() {
  return mockTemplatePage();
}

function mockSaveTemplate(kind, body) {
  if (body == null) delete mockTemplateEdits[kind];
  else mockTemplateEdits[kind] = body;
  return mockTemplatePage();
}

/* ── 검사 기준선 목업 (D2-4) ───────────────────────────────────────────
 *
 * 원문의 열세 줄. **서버 기본값과 같은 글이어야 한다** — 다르면 목업에서
 * 본 기준으로 「목표까지 얼마」를 말하게 된다.
 */
function mockBaselineSeed() {
  return [
    {
      disease: "PCOS",
      name: "월경 주기",
      direction: "KEEP",
      low: "21.00",
      high: "35.00",
      by_age: false,
      keywords: "LMP, 월경, 주기",
      unit: "일",
      always_shown: true,
    },
    {
      disease: "PCOS",
      name: "총 테스토스테론",
      direction: "LOWER",
      low: null,
      high: null,
      by_age: false,
      keywords: "Testosterone, 테스토스테론",
      unit: "ng/dL",
      always_shown: true,
    },
    {
      disease: "PCOS",
      name: "DHEA-S",
      direction: "LOWER",
      low: null,
      high: null,
      by_age: false,
      keywords: "DHEA-S, DHEAS",
      unit: "µg/dL",
      always_shown: true,
    },
    {
      disease: "PCOS",
      name: "AMH",
      direction: "KEEP",
      low: null,
      high: null,
      by_age: true,
      keywords: "AMH, 항뮬러관",
      unit: "ng/mL",
      always_shown: true,
    },
    {
      disease: "PCOS",
      name: "LH / FSH",
      direction: "REFERENCE",
      low: null,
      high: null,
      by_age: false,
      keywords: "LH, FSH",
      unit: "비율",
      always_shown: true,
    },
    {
      disease: "PCOS",
      name: "HbA1c",
      direction: "LOWER",
      low: null,
      high: null,
      by_age: false,
      keywords: "HbA1c, 당화혈색소",
      unit: "%",
      always_shown: false,
    },
    {
      disease: "PCOS",
      name: "BMI",
      direction: "LOWER",
      low: null,
      high: null,
      by_age: false,
      keywords: "BMI, 체질량",
      unit: "",
      always_shown: false,
    },
    {
      disease: "ENDOMETRIOSIS",
      name: "혈색소 Hb",
      direction: "KEEP",
      low: "12.00",
      high: null,
      by_age: false,
      keywords: "Hb, 혈색소, Hemoglobin",
      unit: "g/dL",
      always_shown: true,
    },
    {
      disease: "ENDOMETRIOSIS",
      name: "자궁내막종 크기",
      direction: "LOWER",
      low: null,
      high: null,
      by_age: false,
      keywords: "LO, RO, cyst, 내막종",
      unit: "cm",
      always_shown: true,
    },
    {
      disease: "ENDOMETRIOSIS",
      name: "내막 두께 EM",
      direction: "KEEP",
      low: null,
      high: null,
      by_age: false,
      keywords: "EM, 내막두께",
      unit: "cm",
      always_shown: true,
    },
    {
      disease: "ENDOMETRIOSIS",
      name: "AMH",
      direction: "KEEP",
      low: null,
      high: null,
      by_age: true,
      keywords: "AMH, 항뮬러관",
      unit: "ng/mL",
      always_shown: true,
    },
    {
      disease: "ENDOMETRIOSIS",
      name: "간수치 AST/ALT",
      direction: "KEEP",
      low: null,
      high: "40.00",
      by_age: false,
      keywords: "AST, ALT, SGOT",
      unit: "U/L",
      always_shown: true,
    },
    {
      disease: "ENDOMETRIOSIS",
      name: "CA-125",
      direction: "LOWER",
      low: null,
      high: "35.00",
      by_age: false,
      keywords: "CA-125, CA125",
      unit: "U/mL",
      always_shown: false,
    },
  ];
}

/* 의사 둘 — 원문의 「누구 기준」이 뜨는 자리를 눈으로 보려면 둘이어야 한다. */
var MOCK_BASELINE_DOCTORS = [
  { doctor_id: 1, name: "박연" },
  { doctor_id: 2, name: "김연우" },
];

var mockBaselineBoards = null;

function mockBaselineBoard(doctorId) {
  if (!mockBaselineBoards) mockBaselineBoards = { common: mockBaselineSeed() };
  var key = doctorId ? "d" + doctorId : "common";
  /* 그 의사만의 기준을 아직 안 만들었으면 **의원 공통을 보인다** — 빈 화면은
     「이 의사에게는 기준이 없다」로 읽히는데 실제로는 공통이 쓰인다. */
  return mockBaselineBoards[key] || mockBaselineBoards.common;
}

function mockBaselines(doctorId) {
  return Promise.resolve({
    doctor_id: doctorId || null,
    items: mockBaselineBoard(doctorId),
    doctors: MOCK_BASELINE_DOCTORS,
  });
}

function mockSaveBaselines(doctorId, items) {
  if (!mockBaselineBoards) mockBaselineBoards = { common: mockBaselineSeed() };
  mockBaselineBoards[doctorId ? "d" + doctorId : "common"] = items.map(
    function (row) {
      return Object.assign({}, row, {
        low: row.by_age ? null : row.low,
        high: row.by_age ? null : row.high,
      });
    },
  );
  return mockBaselines(doctorId);
}

/* ── 안내문 문구 목업 (D2-1 · D2-2) ────────────────────────────────────
 *
 * 원본은 **씨앗의 합성 문구**를 옮긴다 — `[합성]` 이 붙은 그대로다. 지어낸
 * 의학 문장을 목업에 넣으면 그것이 진짜처럼 읽힌다.
 */
var MOCK_COPY_ORIGIN = {
  caution:
    "[합성] 복용 초기에 두통, 구역, 유방압통, 불규칙한 질출혈이 나타날 수 있으며 대개 2~3개월 내 호전됩니다.",
  emergency:
    "[합성] 한쪽 다리에 심한 통증·부기·발적이 생기거나, 갑작스러운 흉통·호흡 곤란·시야 이상이 나타나면 즉시 복용을 중단하고 응급실을 방문하세요.",
};

var mockCopyEdits = null;
var mockCopyReviews = null;

function mockCopyPage() {
  if (!mockCopyEdits) mockCopyEdits = {};
  if (!mockCopyReviews) mockCopyReviews = {};
  return Promise.resolve({
    doctor_id: 1,
    items: MOCK_PRESCRIPTION_SETS.map(function (row) {
      return {
        prescription_set_id: row.prescription_set_id,
        name: row.name,
        disease: row.name.indexOf("PCOS") === 0 ? "PCOS" : "ENDOMETRIOSIS",
        reviewed: !!mockCopyReviews[row.prescription_set_id],
        sections: ["caution", "emergency"].map(function (key) {
          return {
            section_key: key,
            origin: MOCK_COPY_ORIGIN[key],
            body: (mockCopyEdits[row.prescription_set_id] || {})[key] || null,
            /* 🚨 는 열리지 않는다 — 원문이 못박는다 */
            editable: key === "caution",
          };
        }),
      };
    }),
  });
}

function mockGuideCopy() {
  return mockCopyPage();
}

function mockSaveCopy(setId, section, body) {
  if (!mockCopyEdits) mockCopyEdits = {};
  if (!mockCopyReviews) mockCopyReviews = {};
  if (!mockCopyEdits[setId]) mockCopyEdits[setId] = {};
  if (body == null) delete mockCopyEdits[setId][section];
  else mockCopyEdits[setId][section] = body;
  /* **고치면 확인이 풀린다** — 서버와 같은 규칙이다. */
  delete mockCopyReviews[setId];
  return mockCopyPage();
}

function mockReviewCopy(setId) {
  if (!mockCopyReviews) mockCopyReviews = {};
  mockCopyReviews[setId] = true;
  return mockCopyPage();
}
