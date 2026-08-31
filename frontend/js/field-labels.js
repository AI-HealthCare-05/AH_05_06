/* **판독 항목의 한글 이름표** — 서버 코드를 사람 말로 옮긴다.
 *
 * 서버는 `MEDICATION_NAME` 같은 영문 코드를 주고, 화면은 그것을 그대로 찍고
 * 있었다. 스탭이 판독 화면에서 「MEDICATION_NAME」을 읽어야 했다.
 *
 * 목업은 처음부터 한글을 줬다(`ocr-api.js`). 그래서 `?mock=1` 로 볼 때는
 * 멀쩡했고 실서버에서만 영문이 떴다 — 구조 진단이 「목업이 자기 자신을 정본으로
 * 삼는다」고 적은 그 모양이다.
 *
 * **옮기는 것은 화면 몫이다.** 서버가 한국어를 주면 화면마다 다른 말이 섞이고,
 * 문구를 바꿀 때 서버와 화면 두 곳을 고쳐야 한다 (`doctor.js` 의 섹션 이름표도
 * 같은 이유로 화면이 갖는다).
 *
 * 이름표를 한 곳에 두는 것은 WP-S③ 「공용 모듈 강제」다 — 판독 화면·안내문·
 * 의사 화면이 같은 항목을 다르게 부르면 같은 값인지 알 수 없다.
 */
var FIELD_LABELS = {
  /* 처방 — EMR 처방 표에서 읽는다 */
  DIAGNOSIS: "진단",
  MEDICATION_NAME: "약품명",
  DOSAGE: "1회량",
  FREQUENCY: "일일횟수",
  DURATION_DAYS: "처방일수",
  PRESCRIPTION_DATE: "처방일",

  /* 검사 — EMR 과거기록의 「수치 : / 참고치 :」 줄과 검사 결과지에서 읽는다 */
  LAB_DATE: "검사일",
  HEMOGLOBIN: "혈색소",
  ENDOMETRIOMA_SIZE: "자궁내막종",
  ENDOMETRIAL_THICKNESS: "내막 두께",
  AMH: "AMH",
  AST_ALT: "간수치 AST/ALT",
  CRP: "CRP",

  /* 종양표지자 — 자궁내막증에서 CA-125 가 오르는 일이 있어 추출기가 읽는다.
     한글 이름표 검사에서 이 둘이 빠진 것을 잡았다. 서버 어휘를 눈으로 훑어
     옮겨 적었더니 두 개를 놓쳤고, 추출기 원문을 대조하는 검사가 잡았다. */
  CA_125: "CA-125",
  CA19_9: "CA 19-9",

  /* 에스트라디올. 「E2」로 부르는 것이 병원 관례라 그대로 둔다.
     이 항목도 검사가 아니라 **내가 눈으로 훑다가** 놓쳤다 — 두 글자라
     정규식 `{2,}` 에 안 걸렸다. 거르는 기준을 길이에서 모양으로 바꿨다. */
  E2: "E2 (에스트라디올)",

  /* ── 구버전 이름 (KEY-187 개명 이전) ──────────────────────────────
   *
   * 판독 항목 이름이 2026-08-28 에 바뀌었다 (`82a2fc2`).
   * 그 전에 쌓인 행은 DB 에 **그대로 남는다** — `unique_together` 가
   * (결과, 항목이름) 이라 새 이름으로 다시 넣어도 옛 행은 안 사라진다.
   *
   * 이름표가 없으면 화면이 코드를 그대로 찍는다. 실제로 그렇게 떴고,
   * 처음엔 내 이름표 누락인 줄 알았는데 원인은 **ai-worker 컨테이너가 개명
   * 이전 이미지로 돌고 있는 것**이었다. 컨테이너를 되살려도 이미 쌓인 행은
   * 남으므로, 화면은 옛 이름도 읽을 줄 알아야 한다.
   *
   * 새로 만들지 않는다 — 추출기는 이 이름들을 안 만들고, 안 만드는지 보는
   * 검사도 있다 (`ai_worker/tests/test_field_extractor.py`). 읽기만 한다. */
  PRESCRIPTION_NAME: "약품명",
  PRESCRIPTION_DURATION: "처방일수",
};

/* 모르는 코드는 **그대로 보여 준다.** 빈칸이나 「알 수 없음」으로 두면 새 항목이
   생겼을 때 화면에서 사라져, 값이 있는데 없는 것처럼 보인다. 영문이라도 보이는
   편이 낫고, 그것이 이름표에 무엇을 더해야 하는지도 알려 준다. */
function fieldLabel(fieldType) {
  var key = String(fieldType || "");
  return FIELD_LABELS[key] || key;
}

/* 단위는 값에 붙어 오지만, 서버가 안 줄 때 기본으로 쓸 것을 여기 둔다.
   와이어프레임 S1-6 의 값 줄이 「혈색소 [10.2] g/dL」처럼 단위를 따로 세운다. */
var FIELD_UNITS = {
  HEMOGLOBIN: "g/dL",
  ENDOMETRIOMA_SIZE: "cm",
  ENDOMETRIAL_THICKNESS: "cm",
  AMH: "ng/mL",
  AST_ALT: "U/L",
  CRP: "mg/L",
  DURATION_DAYS: "일",
  CA_125: "U/mL",
  CA19_9: "U/mL",
  E2: "pg/mL",
  PRESCRIPTION_DURATION: "일",
};

function fieldUnit(fieldType, given) {
  if (given) return given;
  return FIELD_UNITS[String(fieldType || "")] || "";
}
