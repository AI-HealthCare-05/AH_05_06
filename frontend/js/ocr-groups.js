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

/* **늘 세우는 처방 여섯.** 안내문이 이것으로 만들어진다 — 무슨 약을, 얼마씩,
   하루 몇 번, 며칠 치. 하나라도 빠지면 안내문이 성립하지 않으므로, 판독이
   못 읽었어도 자리를 비워 두고 사람이 채우게 한다.

   구버전 이름은 여기 넣지 않는다 — 넣으면 새 이름과 옛 이름 두 줄이 나란히
   선다. 옛 행이 있으면 `splitFields` 가 이미 처방 묶음에 넣어 준다. */
var PRESCRIPTION_CORE = [
  "DIAGNOSIS",
  "MEDICATION_NAME",
  "DOSAGE",
  "FREQUENCY",
  "DURATION_DAYS",
  "PRESCRIPTION_DATE",
];

/* 검사일은 값 줄이 아니라 **묶음 머리**에 붙는다 (「이번 판독 값 · 검사일 08-05」).
   ②의 줄로도 세우면 같은 것이 두 번 보인다. */
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

var GROUPS_WITHOUT_SERVER = [
  {
    key: "carried",
    title: "이전 값 유지",
    note: "이번 미시행",
    /* 무엇이 있어야 이 묶음이 사는지 — 다음 사람이 읽을 자리다 */
    needs: "지난 진료의 확정 판독 값을 주는 자리 (GET /visits/{id}/ocr/previous 같은 것)",
    saying: "이번에 안 한 검사의 지난 값을 여기 흐리게 세웁니다 — 서버에 아직 자리가 없습니다",
  },
  {
    key: "checks",
    title: "확인 항목",
    note: "처방별",
    needs: "처방 세트별 확인 항목 목록 (DrugCautionContent 는 있으나 체크리스트를 주는 자리가 없다)",
    saying: "처방에 따라 여쭐 항목을 여기 세웁니다 — 서버에 아직 자리가 없습니다",
  },
];

/* ④ 확인 항목에 세울 것 — 와이어프레임 S1-6 이 그린 그대로.
 *
 * 처방에 따라 달라지는 것이 맞고(비잔이면 우울증 병력을 여쭙는다), 그것을
 * 주는 자리가 붙으면 이 목록은 서버에서 온다. 그때까지는 **무엇이 올 자리인지**
 * 를 보이기 위한 모양이다 — 화면은 이것을 꺼진 채로 세운다. */
var CHECK_ITEMS = ["우울증 병력", "고혈압", "골다공증", "당뇨", "임신 계획"];

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
