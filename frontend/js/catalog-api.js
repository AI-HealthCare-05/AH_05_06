/* 약속처방 카탈로그 — KEY-234.
 *
 *   GET  /api/v1/prescription-sets                        목록 (고르는 칸이 쓴다)
 *   GET  /api/v1/prescription-sets/{id}                   한 세트 (설정 화면)
 *   PUT  /api/v1/prescription-sets/{id}                   저장 — 진단·약·일수 (이름은 못 바꾼다)
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
    /* **판을 훑는다, 씨앗이 아니라.** 씨앗 여덟만 훑으면 새로 만든 처방이
       레일에 안 나타난다 — 목업에서만 나는 차이라 CI 가 못 잡는다. */
    if (MOCK) return Promise.resolve(mockSetStore().map(mockSetListRow));
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

  saveSet: function (id, plan) {
    if (MOCK) return mockSaveSet(id, plan);
    return request("/prescription-sets/" + encodeURIComponent(id), {
      method: "PUT",
      body: plan,
    });
  },

  /* **지우는 길은 없다.** 의료 데이터라 삭제가 금지되고, 지난 진료기록이
     이름 문자열로 이 세트를 가리킨다. 숨기면 새로 고를 수만 없어진다. */
  hideSet: function (id, hidden) {
    if (MOCK) return mockHideSet(id, hidden);
    return request(
      "/prescription-sets/" + encodeURIComponent(id) + (hidden ? "/hide" : "/unhide"),
      { method: "POST" },
    );
  },

  createSet: function (name, disease) {
    if (MOCK) return mockCreateSet(name, disease);
    return request("/prescription-sets", {
      method: "POST",
      body: { name: name, disease: disease },
    });
  },

  /* 의원이 쓰는 약 목록. **판독 화면도 이것을 본다** — `ocr-api.js` 가
     `catalogApi` 를 그대로 부르므로, 여기 한 곳만 두면 둘이 같은 목록을 본다. */
  drugs: function () {
    if (MOCK) return mockDrugs();
    return request("/prescription-drugs");
  },

  addDrug: function (row) {
    if (MOCK) return mockAddDrug(row);
    return request("/prescription-drugs", {
      method: "POST",
      /* 저장 전에 감추기를 눌러 둔 줄도 그 뜻이 남아야 한다 — 안 보내면
         등록이 그냥 보이는 상태로 되고 사용자는 알 길이 없다 (`#197` 리뷰). */
      body: {
        name: row.name,
        frequency: row.frequency,
        note: row.note,
        hidden: !!row.hidden,
      },
    });
  },

  saveDrug: function (id, row) {
    if (MOCK) return mockSaveDrug(id, row);
    return request("/prescription-drugs/" + encodeURIComponent(id), {
      method: "PUT",
      body: {
        /* 줄 전체를 보낸다. 서버는 **이름이 바뀌는지**로 개명을 가리므로,
           같은 이름을 실어 보내도 감추기·용법 수정은 안 막힌다. 진짜 개명은
           잠긴 뒤 409 로 튕긴다 (`#197` 리뷰). */
        name: row.name,
        frequency: row.frequency,
        note: row.note,
        hidden: !!row.hidden,
      },
    });
  },

  reviewCopy: function (setId) {
    if (MOCK) return mockReviewCopy(setId);
    return request("/guide-copy/" + encodeURIComponent(setId) + "/review", {
      method: "POST",
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
    /* **감춘 것도 목록에 담는다.** 거르면 되살릴 화면이 없어지고, 감춘
       처방으로 저장된 진료를 다시 열 때 확인 항목이 이름으로 안 찾아진다.
       거르는 것은 판독 확인의 **고르는 칸** 하나뿐이다. */
    hidden: mine ? !!mine.hidden : false,
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

function mockHideSet(id, hidden) {
  return new Promise(function (resolve, reject) {
    var store = mockSetStore();
    for (var i = 0; i < store.length; i++) {
      if (store[i].prescription_set_id !== Number(id)) continue;
      store[i].hidden = !!hidden;
      return resolve(JSON.parse(JSON.stringify(store[i])));
    }
    return reject(new ApiError("PRESCRIPTION_SET_NOT_FOUND", 404, {}));
  });
}

function mockCreateSet(name, disease) {
  return new Promise(function (resolve, reject) {
    /* 서버와 같은 다듬기 — 앞뒤 공백은 `unique` 가 안 막는다 */
    var clean = String(name || "").split(/\s+/).filter(Boolean).join(" ");
    if (!clean) return reject(new ApiError("NAME_REQUIRED", 422, {}));

    var store = mockSetStore();
    for (var i = 0; i < store.length; i++) {
      /* **감춘 이름도 못 쓴다** — 그 이름을 든 진료기록이 이미 있다 */
      if (store[i].name === clean) {
        return reject(new ApiError("PRESCRIPTION_SET_EXISTS", 409, {}));
      }
    }

    var made = {
      prescription_set_id: Math.max.apply(
        null,
        store.map(function (s) {
          return s.prescription_set_id;
        }),
      ) + 1,
      name: clean,
      disease: disease,
      hidden: false,
      phase: "CONTINUE",
      days_mode: "DAYS",
      days_per_pack: null,
      emr_code: null,
      revisit_note: null,
      check_d15_on: true,
      check_d30_on: false,
      run_out_on: true,
      run_out_before_days: 3,
      drugs: [],
      check_items: [],
    };
    store.push(made);
    return resolve(JSON.parse(JSON.stringify(made)));
  });
}

/* 서버 씨앗과 같은 넷. 갈라지면 목에서 고른 이름과 실제 이름이 달라진다. */
var MOCK_DRUGS = [
  { drug_catalog_id: 1, name: "비잔정(디에노게스트) 2mg", frequency: "1일 1회", note: "매일 같은 시간", hidden: false },
  { drug_catalog_id: 2, name: "야즈정(드로스피레논/에티닐에스트라디올)", frequency: "1일 1회", note: "매일 같은 시간", hidden: false },
  { drug_catalog_id: 3, name: "메트포르민 500mg", frequency: "1일 2회", note: "식후", hidden: false },
  { drug_catalog_id: 4, name: "진통제", frequency: "필요시", note: null, hidden: false },
];

var mockDrugStore = null;

function drugStore() {
  if (!mockDrugStore) mockDrugStore = JSON.parse(JSON.stringify(MOCK_DRUGS));
  return mockDrugStore;
}

function mockDrugs() {
  /* 서버와 같은 봉투 — `{draft, items}`. 갈라지면 목에서만 되는 화면이 된다. */
  return Promise.resolve({
    draft: true,
    items: JSON.parse(JSON.stringify(drugStore())),
  });
}

function clean(raw) {
  return String(raw || "").split(/\s+/).filter(Boolean).join(" ");
}

function mockAddDrug(row) {
  return new Promise(function (resolve, reject) {
    var name = clean(row.name);
    if (!name) return reject(new ApiError("NAME_REQUIRED", 422, {}));
    /* **한 줄에 약 하나.** 판독이 「야즈정(…) + 메트포르민 500mg」처럼 묶어
       읽어 온다 — 그대로 등록하면 목록에 약이 아닌 것이 한 줄 생긴다.
       `/` 는 성분이 둘인 한 약이라 막지 않는다. */
    if (name.indexOf("+") !== -1) {
      return reject(new ApiError("ONE_DRUG_PER_ROW", 422, {}));
    }
    var store = drugStore();
    for (var i = 0; i < store.length; i++) {
      /* **감춘 이름도 못 쓴다** — 서버와 같은 규칙이다 */
      if (store[i].name === name) return reject(new ApiError("DRUG_EXISTS", 409, {}));
    }
    var made = {
      drug_catalog_id: Math.max.apply(null, store.map(function (d) { return d.drug_catalog_id; })) + 1,
      name: name,
      frequency: row.frequency || null,
      note: row.note || null,
      /* 저장 전에 감추기를 눌러 둔 줄 — 서버와 같은 규칙이다 (`#197` 리뷰) */
      hidden: !!row.hidden,
    };
    store.push(made);
    return resolve(JSON.parse(JSON.stringify(made)));
  });
}

function mockSaveDrug(id, row) {
  return new Promise(function (resolve, reject) {
    var store = drugStore();
    for (var i = 0; i < store.length; i++) {
      if (store[i].drug_catalog_id !== Number(id)) continue;
      /* **서버와 같은 판정.** 같은 이름은 개명이 아니고, 안 보낸 `hidden` 은
         안 건드린다. 목이 서버와 갈리면 목에서만 되는 화면이 된다 —
         실제로 이 갈래가 갈려 있어서 「잠긴 뒤 저장이 전부 막히는」 버그를
         CI 가 못 잡았다 (`#197` 리뷰, 2heej). */
      if (row.name !== undefined && row.name !== null) {
        var name = clean(row.name);
        if (!name) return reject(new ApiError("NAME_REQUIRED", 422, {}));
        if (name !== store[i].name) {
          for (var j = 0; j < store.length; j++) {
            if (j !== i && store[j].name === name) {
              return reject(new ApiError("DRUG_EXISTS", 409, {}));
            }
          }
          store[i].name = name;
        }
      }
      store[i].frequency = row.frequency || null;
      store[i].note = row.note || null;
      if (row.hidden !== undefined) store[i].hidden = !!row.hidden;
      return resolve(JSON.parse(JSON.stringify(store[i])));
    }
    return reject(new ApiError("DRUG_NOT_FOUND", 404, {}));
  });
}

function mockSaveSet(id, plan) {
  return new Promise(function (resolve, reject) {
    setTimeout(function () {
      /* 서버 규칙 그대로 — **스탭도 고친다.** 2026-09-02 회의에서 설정 수정을
         스탭에게 열었고 서버는 `require_patient_read` 로 바뀌었는데, 목만
         의사를 요구한 채 남아 있었다. 주석은 「서버 규칙 그대로」라 적혀
         있었지만 실제로는 갈려서, 목으로 보면 스탭이 403 을 맞았다
         (`#192` 리뷰 ④, 2heej).

         통으로 세는데 한 통이 며칠인지 없으면 422 인 것은 그대로다. */
      if (plan.days_mode === "PACK" && !plan.days_per_pack) {
        return reject(new ApiError("DAYS_PER_PACK_REQUIRED", 422, {}));
      }

      var store = mockSetStore();
      for (var i = 0; i < store.length; i++) {
        if (store[i].prescription_set_id !== Number(id)) continue;
        /* **이름을 지켜서 덮는다.** 서버가 이름을 안 받으므로 `plan` 에는
           `name` 이 없다. 그대로 덮으면 목에서 이름 키가 사라져 상세 머리와
           레일이 빈칸이 된다 — 목이라 CI 가 못 잡고 눌러 봐야 보인다. */
        var keptName = store[i].name;
        store[i] = JSON.parse(JSON.stringify(plan));
        store[i].prescription_set_id = Number(id);
        store[i].name = keptName;
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

/* **서버 `app/services/guide_defaults.py` 와 같은 글이어야 한다.**
   갈라지면 목에서 보던 글과 실제로 나가는 글이 달라진다 — 서버가 이 값을
   응답에 실어 주므로 화면은 베끼지 않지만, 목은 서버가 없어 여기 둔다. */
var MOCK_COPY_DEFAULT = {
  medication: "복약 지시에 따라 정해진 시간에 복용해 주세요.",
  caution:
    "복용 중 의사 또는 약사에게 미리 안내받지 않은 증상이나 " +
    "불편감이 나타나면 의료진에게 알려 주세요.\n미리 안내받은 증상이라도 심해지거나 " +
    "계속되면 알려 주세요.",
  emergency:
    "처방약 복용 중 두드러기, 호흡 곤란, 심한 복통이 생기면 즉시 복용을 중단하고 응급실을 방문하세요.",
  life: "처방 기간 중 음주는 피해 주세요. 충분한 수분 섭취와 규칙적인 수면을 유지해 주세요.",
};

/* 고칠 수 있는 갈래 — 응급만 빠진다(KEY-150). 서버 `EDITABLE_SECTIONS` 와 같다. */
var MOCK_COPY_SECTIONS = ["medication", "caution", "emergency", "life"];

var mockCopyEdits = null;
var mockCopyReviews = null;

function mockCopyPage() {
  if (!mockCopyEdits) mockCopyEdits = {};
  if (!mockCopyReviews) mockCopyReviews = {};
  return Promise.resolve({
    /* 비면 의원 공통 — 2026-09-02 회의 결정 */
    doctor_id: null,
    defaults: MOCK_COPY_SECTIONS.map(function (key) {
      return {
        section_key: key,
        body: MOCK_COPY_DEFAULT[key],
        editable: key !== "emergency",
      };
    }),
    /* **판을 훑는다, 씨앗이 아니라.** 씨앗 여덟만 훑으면 새로 만든 처방이
       문구 목록에 없어, 만든 직후 안내문 절이 통째로 안 보인다 — 목업에서만
       나는 차이라 CI 가 못 잡는다. `sets()` 에서도 같은 자리를 고쳤다. */
    items: mockSetStore().map(function (row) {
      return {
        prescription_set_id: row.prescription_set_id,
        name: row.name,
        disease: row.disease,
        reviewed: !!mockCopyReviews[row.prescription_set_id],
        sections: MOCK_COPY_SECTIONS.map(function (key) {
          return {
            section_key: key,
            /* 승인 문구가 있으면 그것, 없으면 기본 문구 — 서버와 같다 */
            origin: MOCK_COPY_ORIGIN[key] || MOCK_COPY_DEFAULT[key],
            body: (mockCopyEdits[row.prescription_set_id] || {})[key] || null,
            /* 🚨 는 열리지 않는다 — 원문이 못박는다 */
            editable: key !== "emergency",
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
