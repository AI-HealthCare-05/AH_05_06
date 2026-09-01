/* **판독 확인 화면의 오른쪽 네 묶음** — 와이어프레임 S1-6 · S1-7.
 *
 * 서버는 값을 **한 줄로 죽 준다** (`OcrResultResponse.fields`). 와이어프레임은
 * 그것을 네 묶음으로 세운다:
 *
 *   ① 진단 · 처방      진단 · 약품명 · 1회량 · 일일횟수 · 처방일수 · 처방일
 *   ② 이번 판독 값     이번에 읽은 검사값 (검사일이 묶음 머리에 붙는다)
 *   ③ 이전 값 유지     이번에 안 한 검사 — 지난 값을 흐리게 둔다
 *   ④ 확인 항목        처방별 체크리스트 · 추가 메모
 *
 * 나누는 이유는 보기 좋으라고가 아니다. **①은 안내문의 뼈대**고(무슨 약을
 * 며칠), **②는 참고값**이다. 한 줄로 두면 스탭이 「처방일수 84」와 「혈색소
 * 10.2」를 같은 무게로 훑는다. 84가 틀리면 환자가 약을 잘못 먹는다.
 *
 * **③④는 아직 서버에 자리가 없다.** 지난 판독 값을 주는 API 도, 처방별
 * 체크리스트를 주는 API 도 없다. 그래서 이 파일은 그 둘을 **비어 있다고
 * 정직하게** 말한다 — 목업 값을 넣어 두면 되는 것처럼 보이고, 그게 1차 시연이
 * 멈춘 방식이다. 껍데기 화면과 「아직 없다」는 다르다.
 */

/* ① 처방 묶음에 드는 항목 — **순서가 화면 순서다.** 와이어프레임의 줄 차례. */
var PRESCRIPTION_TYPES = [
  "DIAGNOSIS",
  "MEDICATION_NAME",
  "DOSAGE",
  "FREQUENCY",
  "DURATION_DAYS",
  "PRESCRIPTION_DATE",

  /* 구버전 이름 (KEY-187 개명 이전). 이 행들이 DB 에 남아 있어서, 여기
     없으면 약품명이 「이번 판독 값」(검사) 묶음으로 새어 들어간다. */
  "PRESCRIPTION_NAME",
  "PRESCRIPTION_DURATION",
];

/* **늘 세우는 처방 셋.** 무슨 병에 무슨 약을 며칠 치 — 안내문이 이것으로
   만들어진다. 서버가 필수로 보는 셋과 같고(`ocr_task.py` 의
   `_REQUIRED_OCR_FIELDS`), 맨 위 가로줄에 서는 셋과도 같다.

   1회량 · 일일횟수 · 처방일은 여기 없다. 와이어프레임 S1-6 의 진단·처방
   칸에도 없고(처방일은 아래 곁말 줄에 있다), 못 읽었을 때 물음표로 세우면
   맨 위 셋과 무게가 같아 보여 **무엇을 먼저 채워야 하는지가 흐려진다.**
   판독이 읽었으면 아래 줄로 그대로 보인다.

   구버전 이름은 여기 넣지 않는다 — 넣으면 새 이름과 옛 이름 두 줄이 나란히
   선다. 옛 행이 있으면 `splitFields` 가 이미 처방 묶음에 넣어 준다. */
var PRESCRIPTION_CORE = ["DIAGNOSIS", "MEDICATION_NAME", "DURATION_DAYS"];

/* **「이번 판독 값」에 늘 세우는 것 — 세 묶음.**
 *
 * 판독이 못 읽었어도 자리를 세운다. 안 세우면 스탭 눈에는 「그 검사가 없는
 * 진료」로 보이고, 못 읽은 것과 안 한 것을 구별할 수 없다. 자리가 있어야
 * 「이번엔 안 했다」고 말할 수도 있다.
 *
 * **묶어서 세운다.** 스물한 줄을 한 덩이로 두면 훑을 수가 없다 — 증상은 사람이
 * 물어 적는 것이고, 초음파는 본 것이고, 혈액은 뽑아 잰 것이다. 나온 곳이
 * 다르면 못 읽었을 때 어디를 다시 봐야 하는지도 다르다.
 *
 * 차례가 곧 화면 차례다.
 */
var LAB_GROUPS = [
  {
    key: "symptom",
    title: "증상",
    /* 사람이 물어 적는 값이다 — 판독이 못 읽으면 진료기록을 다시 보는 것이
       아니라 스탭이 직접 적는다. */
    types: ["PAIN_SCORE", "HEAVY_BLEEDING", "IRREGULAR_CYCLE"],
  },
  {
    key: "ultrasound",
    title: "초음파 검사",
    types: [
      "ADENOMYOSIS_SIZE",
      /* 개수가 크기보다 먼저다 — 몇 개인지 세고 나서 그 크기를 적는다.
         없으면 크기를 물을 일도 없다. */
      "MYOMA_COUNT",
      "MYOMA_SIZE",
      "ENDOMETRIAL_THICKNESS",
      "ADNEXAL_CYST_LEFT",
      "ADNEXAL_CYST_RIGHT",
    ],
  },
  {
    key: "blood",
    title: "혈액검사",
    types: [
      "HEMOGLOBIN",
      "AST",
      "ALT",
      "LH_FSH_RATIO",
      "DHEA_S",
      "TESTOSTERONE",
      "PROLACTIN",
      "TSH",
      "T3",
      "T4",
      "E2",
      "PROGESTERONE",
    ],
  },
];

/* 묶음에 든 것 전부를 한 줄로. `withMissingRows` 가 이 차례로 자리를 세운다. */
var LAB_CORE = (function () {
  var out = [];
  for (var i = 0; i < LAB_GROUPS.length; i++) {
    for (var j = 0; j < LAB_GROUPS[i].types.length; j++) out.push(LAB_GROUPS[i].types[j]);
  }
  return out;
})();

/* 묶음에 없는데 판독이 읽어 온 값 — 옛 이름(CA-125 · AMH · 간수치 AST/ALT)이
   그렇다. **버리지 않는다.** DB 에 남아 있는 값을 화면에서 지우면 읽은 것이
   없어진 것처럼 보인다. 맨 뒤에 따로 세운다. */
var LAB_OTHERS_TITLE = "그 밖에 읽은 값";

/* **어느 묶음이 어느 칸에 서는가.**
 *
 * 왼쪽은 사람이 보고 적는 것(증상 · 초음파), 오른쪽은 뽑아 잰 것(혈액)이다.
 * 혈액이 열두 줄로 가장 길어 혼자 한 칸을 쓴다 — 셋을 위아래로 쌓으면 스물한
 * 줄이 한 줄기로 늘어져 아래가 화면 밖으로 나간다.
 *
 * 묶음에 없던 값(「그 밖에 읽은 값」)은 왼쪽에 붙인다. 드물게 서는 것이라
 * 오른쪽 긴 칸을 더 늘리지 않는다.
 */
var LAB_COLUMNS = [
  { key: "left", groups: ["symptom", "ultrasound", "others"] },
  { key: "right", groups: ["blood"] },
];

/** 묶음들을 두 칸으로 나눈다. **빈 칸은 내지 않는다** — 한쪽만 있으면
    빈 칸이 옆에 서서 화면이 반쯤 무너진 것처럼 보인다. */
function labColumnsOf(groups) {
  var all = groups || [];
  var out = [];

  for (var i = 0; i < LAB_COLUMNS.length; i++) {
    var want = LAB_COLUMNS[i].groups;
    var mine = [];
    for (var w = 0; w < want.length; w++) {
      for (var j = 0; j < all.length; j++) {
        if (all[j].key === want[w]) mine.push(all[j]);
      }
    }
    if (mine.length) out.push({ key: LAB_COLUMNS[i].key, groups: mine });
  }
  return out;
}

/** 줄들을 화면 묶음으로 가른다. **빈 묶음은 내지 않는다** — 「그 밖에」가
    늘 서 있으면 무엇이 예외인지가 안 보인다. */
function labGroupsOf(rows) {
  var all = rows || [];
  var taken = {};
  var out = [];

  for (var i = 0; i < LAB_GROUPS.length; i++) {
    var group = LAB_GROUPS[i];
    var mine = [];
    for (var t = 0; t < group.types.length; t++) {
      for (var j = 0; j < all.length; j++) {
        if (all[j].field_type !== group.types[t]) continue;
        mine.push(all[j]);
        taken[j] = true;
      }
    }
    if (mine.length) out.push({ key: group.key, title: group.title, rows: mine });
  }

  var rest = [];
  for (var k = 0; k < all.length; k++) {
    if (!taken[k]) rest.push(all[k]);
  }
  if (rest.length) out.push({ key: "others", title: LAB_OTHERS_TITLE, rows: rest });

  return out;
}

var LAB_HEAD_TYPE = "LAB_DATE";

/** 서버가 준 한 줄짜리 목록을 화면의 묶음으로 가른다. */
function splitFields(fields) {
  var all = fields || [];
  var prescription = [];
  var labs = [];

  /* 처방 항목은 **와이어프레임 차례대로** 세운다. 서버가 준 차례는 추출기가
     정규식을 훑은 차례라 화면에서 뜻이 없다. */
  for (var i = 0; i < PRESCRIPTION_TYPES.length; i++) {
    for (var j = 0; j < all.length; j++) {
      if (all[j].field_type === PRESCRIPTION_TYPES[i]) prescription.push(all[j]);
    }
  }

  for (var k = 0; k < all.length; k++) {
    var type = all[k].field_type;
    if (type === LAB_HEAD_TYPE) continue;
    if (PRESCRIPTION_TYPES.indexOf(type) !== -1) continue;
    labs.push(all[k]);
  }

  return { prescription: prescription, labs: labs };
}

/** ②의 머리에 붙는 검사일. 없으면 빈 문자열 — 「검사일 —」로 두지 않는다. */
function labDateOf(fields) {
  var all = fields || [];
  for (var i = 0; i < all.length; i++) {
    if (all[i].field_type === LAB_HEAD_TYPE) return all[i].value || "";
  }
  return "";
}

/** 값 하나를 코드로 꺼낸다 — ① 머리줄이 진단·약·일수를 따로 쓴다. */
function fieldValueOf(fields, type) {
  var all = fields || [];
  for (var i = 0; i < all.length; i++) {
    if (all[i].field_type === type) return all[i].value || "";
  }
  return "";
}

/* ── 소진 예정일 ────────────────────────────────────────────────────────
 *
 * 와이어프레임이 「처방일 08-13 · 소진 예정일 11-05」를 나란히 둔다. 이건
 * 서버가 주는 값이 아니라 **처방일 + 처방일수**다. 이 프로그램이 하는 일
 * 자체가 「소진 임박에 안내를 보낸다」라, 이 날짜가 화면에 없으면 스탭이
 * 무엇을 확인해야 하는지 모른다.
 *
 * 날짜를 `new Date("2026-08-13")` 로 읽지 않는다 — 그건 UTC 자정으로 읽혀서
 * 한국 시간으로는 **전날**이 된다. 이 함정에 이미 한 번 걸렸다. 숫자로 뜯어
 * 숫자로 만든다. */
function runOutDate(startIso, days) {
  var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(startIso || ""));
  var n = parseInt(String(days || ""), 10);
  if (!m || !n || n <= 0) return "";

  var d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  d.setDate(d.getDate() + n);

  var mm = String(d.getMonth() + 1);
  var dd = String(d.getDate());
  return d.getFullYear() + "-" + (mm.length < 2 ? "0" + mm : mm) + "-" + (dd.length < 2 ? "0" + dd : dd);
}

/* 「ⓘ 총투는 **일수** 입니다 · 28 미만이면 확인을 여쭙습니다」 — 와이어프레임.
 *
 * EMR 의 「총투」 칸에 일수 대신 **총 알 수**가 찍혀 오는 일이 있다. 하루 두 알
 * 84일이면 168 이 들어오고, 반대로 일수 자리에 28 미만이 오면 처방을 짧게 낸
 * 것인지 잘못 읽은 것인지 사람이 봐야 한다. 막지는 않는다 — 짧은 처방도 있다. */
function courseWarn(days) {
  var n = parseInt(String(days || ""), 10);
  if (!n || n <= 0) return "";
  if (n < 28) return "처방일수가 28일 미만입니다 — 총투가 일수인지 확인해 주세요";
  return "";
}

/* ── ③ 이전 값 유지 · ④ 확인 항목 ──────────────────────────────────────
 *
 * 둘 다 **서버에 자리가 없다.** 여기서 지어내지 않는다. */

/* 둘 다 아직 못 채우는데, **막힌 곳이 서로 다르다.** 화면 문구를 뭉뚱그려
   「서버에 자리가 없습니다」로 두면, 판독 API 를 맡는 사람이 둘 다 표부터
   만들어야 하는 줄 안다. 하나는 표가 이미 있다.

     ③ 이전 값 유지 — 값은 `ocr_field` 에 **이미 쌓여 있다.** 지난 진료의
        확정 값이 그대로 들어 있고, 없는 것은 그것을 꺼내 주는 **길**이다.
        판독 API 는 전부 `ocr_job_id` 나 이번 진료로만 열려 있다.

     ④ 확인 항목 — 여기는 **담을 표부터 없다.** `prescription_set`(8종)과
        `drug_caution_content`(문구)는 있지만, 처방별로 무엇을 여쭐지의
        목록도, 스탭이 체크한 답을 진료에 붙여 둘 자리도 없다.
        (`visit.doctor_note` 는 의사 소견 칸이라 이것과 다르다.) */
var GROUPS_WITHOUT_SERVER = [
  {
    key: "carried",
    title: "이전 값 유지",
    note: "이번 미시행",
    /* 무엇이 있어야 이 묶음이 사는지 — 다음 사람이 읽을 자리다 */
    needs: "지난 진료의 확정 판독 값을 꺼내 주는 길. 표(ocr_field)에 값은 이미 있다",
    saying: "이번에 안 한 검사의 지난 값을 여기 흐리게 세웁니다 — 값은 이미 저장돼 있고, 꺼내 오는 길이 아직 없습니다",
  },
  {
    key: "checks",
    title: "확인 항목",
    /* 답은 이제 `visit_check_answer` 에 담긴다. 남은 것은 **무엇을 여쭐지가
       처방에 따라 달라지는 것**뿐이다 — 그 자리(D2-3 처방 세트)가 아직 없어
       지금은 다섯을 다 여쭙는다. */
    note: "처방별 — 지금은 다섯 모두",
    needs: "처방 세트별 확인 항목 목록 (D2-3). 답을 담을 자리는 생겼다",
    saying: "",
  },
];

/* ④ 확인 항목에 세울 것 — 와이어프레임 S1-6 이 그린 그대로.
 *
 * 처방에 따라 달라지는 것이 맞고(비잔이면 우울증 병력을 여쭙는다), 그것을
 * 주는 자리가 붙으면 이 목록은 서버에서 온다. 그때까지는 **무엇이 올 자리인지**
 * 를 보이기 위한 모양이다 — 화면은 이것을 꺼진 채로 세운다. */
/* 서버는 코드로 주고 화면이 사람 말로 옮긴다 — 판독 항목 이름표와 같은 규칙
   (`js/field-labels.js`). 서버가 한국어를 주면 문구를 바꿀 때 두 곳을 고쳐야
   하고, 지난 진료의 답이 어느 질문의 답이었는지도 흐려진다.

   **차례가 화면 차례다.** 서버가 준 차례를 그대로 쓰면 열거 정의 순서에 끌려간다. */
var CHECK_ITEM_LABELS = {
  DEPRESSION: "우울증 병력",
  HYPERTENSION: "고혈압",
  OSTEOPOROSIS: "골다공증",
  DIABETES: "당뇨",
  PREGNANCY_PLAN: "임신 계획",
};

var CHECK_ITEMS = ["DEPRESSION", "HYPERTENSION", "OSTEOPOROSIS", "DIABETES", "PREGNANCY_PLAN"];

function checkItemLabel(key) {
  return CHECK_ITEM_LABELS[String(key || "")] || String(key || "");
}

/** 이 묶음을 지금 채울 수 있는가. 채울 수 없으면 화면이 그렇게 말해야 한다. */
function groupIsReady(key, data) {
  var rows = (data || {})[key];
  return !!(rows && rows.length);
}


/* ── 문서 이름 ─────────────────────────────────────────────────────────
 *
 * **올린 이미지가 EMR 인지 검사 결과지인지는 중요하지 않다.** 중요한 것은
 * 그 이미지에서 어떤 값을 찾았느냐다. 종류를 이름으로 붙이면 두 가지가
 * 나빠진다:
 *
 *   ① 틀린다. 종류는 프로그램이 짐작한 것이고, 짐작이 틀리면 스탭은 「검사지1」
 *      이라 적힌 EMR 화면을 보게 된다 — 값보다 이름을 먼저 의심하게 된다.
 *   ② 쓸모가 없다. 출처 배지를 누르는 이유는 「이 값이 어느 사진에서 나왔나」를
 *      보려는 것이지 그 사진의 갈래를 알려는 것이 아니다.
 *
 * 업로드에서 「과거기록 · 소견 · 검사지」 고르기를 없앤 것과 같은 판단이다
 * (스탭이 매번 어느 칸인지 고민하게 만들지 않는다 — 와이어프레임 S1-3).
 *
 * 그래서 **올린 차례로 번호를 매긴다.** 순서는 서버가 준 차례를 그대로 쓴다 —
 * 스탭이 올린 차례이고, 화면을 다시 열어도 같은 번호가 나온다.
 */
function documentName(documents, documentId) {
  var list = documents || [];
  for (var i = 0; i < list.length; i++) {
    if (list[i].document_id === documentId) return "이미지" + (i + 1);
  }
  return "";
}

/** 탭에 세울 이름들. 서버가 준 차례가 곧 올린 차례다. */
function documentNames(documents) {
  return (documents || []).map(function (doc, i) {
    return { document_id: doc.document_id, name: "이미지" + (i + 1) };
  });
}


/* ── 없는 줄도 세운다 ─────────────────────────────────────────────────
 *
 * 화면이 **서버가 준 값만** 그리면, 판독이 못 읽은 항목은 화면에서 아예
 * 사라진다. 스탭 눈에는 「그 항목이 없는 진료」로 보이고, 빠진 채로 안내문이
 * 만들어진다.
 *
 * 와이어프레임 S1-7 이 그린 것이 바로 그 반대다 — 못 읽은 줄도 자리에 서
 * 있고, 점선 네모에 `?` 가 들어가고, 옆에 「직접 입력」이 붙는다.
 * 「그 줄만 점선 · 다른 줄과 확인 항목은 그대로다 — 추측해서 채우지 않는다」.
 *
 * **처방 여섯은 늘 세운다.** 안내문이 그것으로 만들어지기 때문이다 — 약 이름과
 * 며칠 치인지가 빠지면 안내문이 성립하지 않는다. 검사값은 진료마다 한 것이
 * 달라서 늘 세우지 않는다. 안 한 검사를 열 줄씩 `?` 로 세우면 진짜 못 읽은
 * 줄이 그 안에 묻힌다 — 이번에 안 한 검사는 ③ 「이전 값 유지」의 몫이다.
 */
function withMissingRows(fields, types) {
  var have = fields || [];
  var want = types || [];
  var out = [];

  for (var i = 0; i < want.length; i++) {
    var found = null;
    for (var j = 0; j < have.length; j++) {
      if (have[j].field_type === want[i]) {
        found = have[j];
        break;
      }
    }
    /* 못 읽은 줄에는 **가짜 번호를 주지 않는다.** `ocr_field_id` 가 없으면
       고칠 대상도 없다는 뜻이고, 화면이 그것을 보고 「직접 입력」을 그린다.
       0 이나 -1 을 넣으면 저장하려 들다가 서버에서 404 를 받는다. */
    out.push(found || { field_type: want[i], value: null, is_absent: true });
  }
  return out;
}


/* 원문 칸 머리에 붙는 곁말 — 「이미지1 에서 판독한 원문」.
 *
 * 전에는 「현재 화면에서 판독한 원문」이라는 붙박이 문구였다. 그런데 이미지가
 * 여럿이면 **지금 보고 있는 것이 몇 번째인지**가 이 칸의 전부다 — 값 옆
 * 출처 배지가 「이미지2」라고 적혀 있는데 원문 칸이 어느 것인지 안 말하면,
 * 눌러서 옮겨 온 뒤에도 제대로 왔는지 알 수 없다.
 *
 * 이름을 못 찾으면 붙박이 문구로 돌아간다 — 「 에서 판독한 원문」처럼
 * 앞이 빈 말을 내보내지 않는다. */
function rawTextNote(documents, documentId) {
  var name = documentName(documents, documentId);
  return name ? name + " 에서 판독한 원문" : "현재 화면에서 판독한 원문";
}


/* ── 화면에서 직접 채운 값 ─────────────────────────────────────────────
 *
 * 판독이 못 찾은 항목은 서버에 줄이 안 남는다 (`ocr_task.py` 의 Phase 2 게이트가
 * 필수 필드가 없으면 Phase 3 저장 앞에서 돌아선다). 그래서 고칠 대상도, 값을
 * 새로 만드는 자리(POST)도 없다 — 지금 서버로는 이 값을 보낼 수 없다.
 *
 * 그래도 **화면에서는 채울 수 있어야 한다.** 처방 여섯은 안내문의 뼈대라,
 * 스탭이 눈으로 읽은 값을 적을 자리가 없으면 화면이 거기서 끝난다.
 *
 * 채운 값은 **화면 안에만** 있다. 저장된 척하지 않는다 — 적어 넣고 안내문을
 * 만들면 그 값은 실리지 않는데, 그것을 말 안 하면 스탭은 실린 줄 안다.
 * 판독 API 가 새 값을 받게 되면 이 자리는 통째로 사라진다.
 */
function localFilled(local) {
  var keys = Object.keys(local || {});
  var out = [];
  for (var i = 0; i < keys.length; i++) {
    if (String(local[keys[i]] || "").trim()) out.push(keys[i]);
  }
  return out;
}

/** 적어 넣은 값이 안내문에 안 실린다는 것을 말한다. 막지는 않는다. */
function localSaying(local) {
  var filled = localFilled(local);
  if (!filled.length) return "";
  return (
    "직접 적은 " +
    filled.length +
    "개는 아직 저장되지 않아 안내문에 실리지 않습니다 — 판독 API 가 새 값을 받게 되면 반영됩니다"
  );
}


/* 판독 값이 **하나도 없을 때** 안내문을 만들 수 있는가.
 *
 * 없다. 서버는 확정된 항목이 하나는 있어야 안내문을 만든다
 * (`guides.py` 의 `OCR_NOT_CONFIRMED` 422). 그런데 필수 필드 게이트가
 * 돌아서면 항목이 아예 안 생기므로, 확정할 것도 없다.
 *
 * 그대로 두면 눌렀을 때 서버 오류로 떨어진다 — 「내가 뭘 잘못했나」로 읽힌다.
 * 미리 잠그고 **왜 지금 안 되는지**를 적는다. 화면에서 적은 값으로는 아직
 * 안 된다는 것도 같은 이야기다 (그 값은 서버에 없다). */
function noFieldsSaying(fields) {
  if ((fields || []).length) return "";
  return "판독한 값이 없어 안내문을 만들 수 없습니다 — 진료기록을 다시 올리거나, 값을 저장하는 자리가 붙으면 됩니다";
}


/* ── 약속처방 고르기 ──────────────────────────────────────────────────
 *
 * 「처방」은 판독이 읽은 약 이름이 아니라 **의사가 설정(D2-3)에서 정해 둔
 * 세트**에서 고른다. 세트에는 약 목록 · 처방일수 표기 방식 · 확인 항목 ·
 * 자동 발송 기본값이 함께 묶여 있고, 고르는 순간 그것들이 따라온다.
 *
 * 자유 입력이면 안 되는 이유가 그것이다 — 「비잔」과 「비잔정」이 다른 값으로
 * 들어오면 붙일 주의 문구를 못 찾는다.
 *
 * 판독이 읽은 약 이름은 버리지 않는다. **어느 세트에 가까운지 고르는 실마리**
 * 로 쓴다 (와이어프레임 D2-3 의 흐름 줄: 「저장 → S1-6의 가장 유사한 처방
 * 세트」). 자동으로 정하지는 않는다 — 틀리면 다른 약의 주의 문구가 붙는다.
 */
function guessPrescriptionSet(sets, readName) {
  var name = String(readName || "").trim();
  if (!name || !(sets || []).length) return null;

  /* 이름이 통째로 들어 있는 것만 본다. 글자 몇 개가 겹친다고 고르면
     「비잔」이 「비잔 불가」 세트를 집는다. */
  var hits = sets.filter(function (set) {
    return String(set.name || "").indexOf(name) !== -1;
  });

  /* **하나일 때만 고른다.** 둘 이상이면 사람이 골라야 한다 — 「비잔 (처음)」과
     「비잔 (계속)」은 안내문이 다르고, 기계가 고를 근거가 없다. */
  return hits.length === 1 ? hits[0] : null;
}

/** 목록을 못 불러왔을 때 화면이 할 말. 빈 채로 두면 「고장」으로 읽는다. */
function setsMissingSaying(sets, failed) {
  if (failed) return "약속처방 목록을 불러오지 못했습니다 — 판독 결과 확인을 다시 눌러 주세요";
  if (!(sets || []).length) return "약속처방이 아직 없습니다 — 설정 · 처방에서 추가해 주세요";
  return "";
}


/* 안내문을 만든 뒤 갈 곳.
 *
 * 전에는 「의사 승인 화면에서 이어서 보실 수 있습니다」라고만 적고 그 자리에
 * 머물렀다. 그런데 **안내문이 제대로 만들어졌는지 보는 것은 스탭 몫이다** —
 * 스탭이 먼저 확인하고 고친 뒤에 의사에게 넘긴다 (와이어프레임 S1-11~13).
 * 말만 하고 안 데려다주면 스탭은 단계 줄에서 「안내문」을 다시 찾아 눌러야 한다.
 *
 * **이미 있을 때(409)도 같은 곳으로 간다.** 새로고침 뒤 다시 눌렀거나 두
 * 사람이 같이 누른 것이고, 원하던 것은 이미 거기 있다. */
function guideScreenHref(visitId) {
  if (!visitId) return "";
  return "/patients.html?visit=" + encodeURIComponent(visitId) + "&tab=guide";
}
