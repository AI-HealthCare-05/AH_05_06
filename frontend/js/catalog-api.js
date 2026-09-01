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
  },
  {
    prescription_set_id: 2,
    name: "자궁내막증 · 비잔 (계속)",
    check_items: MOCK_CHECK_ITEMS,
  },
  {
    prescription_set_id: 3,
    name: "자궁내막증 · 통증관리",
    check_items: MOCK_CHECK_ITEMS,
  },
  {
    prescription_set_id: 4,
    name: "PCOS · 초진",
    check_items: MOCK_CHECK_ITEMS,
  },
  {
    prescription_set_id: 5,
    name: "PCOS · 초진 (야즈 불가)",
    check_items: MOCK_CHECK_ITEMS,
  },
  {
    prescription_set_id: 6,
    name: "PCOS · 야즈 (계속)",
    check_items: MOCK_CHECK_ITEMS,
  },
  {
    prescription_set_id: 7,
    name: "PCOS · 야즈 + 메트포르민",
    check_items: MOCK_CHECK_ITEMS,
  },
  {
    prescription_set_id: 8,
    name: "PCOS · 대사관리",
    check_items: MOCK_CHECK_ITEMS,
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
      days_mode: "DAYS",
      days_per_pack: null,
      emr_code: null,
      revisit_note: null,
      check_d15_on: true,
      check_d30_on: false,
      run_out_on: true,
      run_out_before_days: 3,
      drugs: [],
      check_items: (row.check_items || []).slice(),
    };
  });
}

function mockSetStore() {
  if (!mockSetDetails) mockSetDetails = mockSetSeed();
  return mockSetDetails;
}

function mockSetListRow(row) {
  /* 목록은 **이름과 확인 항목**만 준다 — 서버와 같다 */
  var mine = mockSetStore().filter(function (s) {
    return s.prescription_set_id === row.prescription_set_id;
  })[0];
  return {
    prescription_set_id: row.prescription_set_id,
    name: mine ? mine.name : row.name,
    /* 레일이 질환으로 묶는다 — 상세를 받아야 알 수 있게 두면 여덟 번 다녀온다 */
    disease: mine ? mine.disease : "ENDOMETRIOSIS",
    check_items: mine ? mine.check_items.slice() : [],
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
