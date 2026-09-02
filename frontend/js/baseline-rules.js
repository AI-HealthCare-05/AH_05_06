/* 검사 기준선 — 와이어프레임 D2-4 의 규칙들. KEY-234.
 *
 * 원문 주석: 「기준선 → D1 「나의 목표」의 남은 거리 계산에 쓰인다」.
 *
 * **기준선은 비워 둘 수 있다.** 원문: 「비워 두면 값과 추이만 표시하고 목표
 * 대비 수치는 계산하지 않습니다」. 검사기관과 나이에 따라 다르기 때문이고,
 * 모르는 채로 셈해 「목표까지 3 남았습니다」라고 말하는 것이 제일 나쁘다.
 */

/* 방향 — 원문 「유지 · ↓ 낮춤 · 참고」. 「참고」는 목표가 없다는 뜻이다:
   LH/FSH 비율처럼 보기는 하되 올리고 내릴 값이 아닌 것들이 있다. */
var BASELINE_DIRECTIONS = [
  { key: "KEEP", say: "유지" },
  { key: "LOWER", say: "↓ 낮춤" },
  { key: "REFERENCE", say: "참고" },
];

function directionSaying(key) {
  for (var i = 0; i < BASELINE_DIRECTIONS.length; i++) {
    if (BASELINE_DIRECTIONS[i].key === key) return BASELINE_DIRECTIONS[i].say;
  }
  return key || "";
}

/* 기준선 한 칸을 사람 말로 — 원문의 여섯 가지 모양.
 *
 *   21~35     둘 다 있음
 *   12.0 이상  아래만
 *   40 미만    위만
 *   나이별     숫자 하나로 못 적는 것(AMH)
 *   —         비어 있음
 */
function baselineSaying(row) {
  if (!row) return "—";
  if (row.by_age) return "나이별";
  var low = trimNumber(row.low);
  var high = trimNumber(row.high);
  if (low && high) return low + "~" + high;
  if (low) return low + " 이상";
  if (high) return high + " 미만";
  return "—";
}

/** 「21.00」을 「21」로. 서버는 소수 둘로 주는데 화면에 그대로 두면
    「21.00~35.00」이 되어 원문(「21~35」)과 달라진다. */
function trimNumber(value) {
  if (value === null || value === undefined || value === "") return "";
  var text = String(value);
  if (text.indexOf(".") === -1) return text;
  return text.replace(/0+$/, "").replace(/\.$/, "");
}

/* 저장하기 전에 화면이 먼저 재는 것. 서버와 같은 이유로 막는다 —
   눌러 보고서야 아는 것보다 치는 동안 아는 편이 낫다. */
function baselineProblem(row) {
  if (!row) return "";
  if (!String(row.name || "").trim()) return "검사 항목 이름을 적어 주세요";
  var low = numberOr(row.low);
  var high = numberOr(row.high);
  if (low === false || high === false) return "기준선은 숫자로 적어 주세요";
  if (low !== null && high !== null && low > high)
    return "기준선의 아래가 위보다 클 수 없습니다";
  return "";
}

/** 숫자면 숫자, 비었으면 null, 숫자가 아니면 false. */
function numberOr(value) {
  if (value === null || value === undefined || String(value).trim() === "")
    return null;
  var found = Number(value);
  return isNaN(found) ? false : found;
}

/* 한 판 안에서 겹치는 줄 — 같은 질환에 같은 이름. */
function duplicateBaselines(rows) {
  var seen = {};
  var found = [];
  (rows || []).forEach(function (row) {
    var key = row.disease + "|" + String(row.name || "").trim();
    if (seen[key]) found.push(row.name);
    seen[key] = true;
  });
  return found;
}

/* 질환으로 묶어 보인다 — 원문이 「다낭성난소증후군」·「자궁내막증 · 선근증」
   두 덩이로 그린다. **차례는 받은 그대로** 둔다: 화면이 보여 준 차례가 곧
   저장되는 차례라, 여기서 다시 세우면 저장할 때마다 순서가 바뀐다. */
function baselinesByDisease(rows) {
  var order = [];
  var blocks = {};
  (rows || []).forEach(function (row) {
    if (!blocks[row.disease]) {
      blocks[row.disease] = [];
      order.push(row.disease);
    }
    blocks[row.disease].push(row);
  });
  return order.map(function (disease) {
    return {
      disease: disease,
      title: DISEASE_LABELS[disease] || disease,
      rows: blocks[disease],
    };
  });
}

/* 원문의 「누구 기준」 — **의사가 둘 이상일 때만** 보인다. 한 명뿐인 의원에
   「누구 기준」을 띄우면 고를 것이 하나뿐인 칸이 자리만 차지한다. */
function showsWhosePicker(doctors) {
  return (doctors || []).length >= 2;
}
