/* **설정 왼쪽 레일** — 와이어프레임 D2-3.
 *
 *   안내문        2/5     (D2-1 · D2-2)
 *   처방          9       질환별로 묶이고, **고른 묶음만 펼쳐진다**
 *   그 밖에               검사 기준선 · 문자 문구 · 챌린지 목록 · 의원 정보
 *
 * 원문 주석: 「9개가 늘 다 펼쳐져 있으면 왼쪽이 길어져 「그 밖에」가 화면 밖으로
 * 밀린다」. 그래서 접었다 편다.
 *
 * 여기 있는 것은 **순수 함수**다 — 화면 요소를 찾지 않으므로 검사가 부를 수
 * 있다. 자리 셈과 묶음 나누기는 눈으로 확인하기 어렵다.
 */

/* 질환 코드 → 사람 말. 서버는 코드로 주고 화면이 옮긴다 — 판독 항목 이름표와
   같은 규칙이다(`js/field-labels.js`). */
var DISEASE_LABELS = { ENDOMETRIOSIS: "자궁내막증", PCOS: "다낭성난소증후군" };
var PHASE_LABELS = {
  FIRST: "초회 처방",
  CONTINUE: "계속 복용",
  REST: "휴약기",
};
var DAYS_MODE_LABELS = { PACK: "통 · 상자 수", DAYS: "일수 직접 입력" };

/* 질환 차례. 이름순으로 세우면 「다낭성」이 「자궁내막증」 앞에 와서, 원문의
   차례(자궁내막증 먼저)와 어긋난다. */
var DISEASE_ORDER = ["ENDOMETRIOSIS", "PCOS"];

function diseaseLabel(code) {
  return DISEASE_LABELS[String(code || "")] || String(code || "");
}

function phaseLabel(code) {
  return PHASE_LABELS[String(code || "")] || String(code || "");
}

/** 처방을 질환으로 묶는다. **빈 묶음은 내지 않는다** — 세트가 하나도 없는
    질환이 개수 0 으로 서 있으면 눌러 볼 것이 없다. */
function setsByDisease(sets) {
  var all = sets || [];
  var out = [];

  for (var i = 0; i < DISEASE_ORDER.length; i++) {
    var code = DISEASE_ORDER[i];
    var mine = all.filter(function (row) {
      return row.disease === code;
    });
    if (mine.length)
      out.push({ key: code, title: diseaseLabel(code), sets: mine });
  }

  /* 모르는 질환도 버리지 않는다 — 서버가 값을 늘렸는데 화면이 모르면
     그 처방이 목록에서 사라진다. 사라진 것과 없는 것은 다르다. */
  var known = {};
  DISEASE_ORDER.forEach(function (code) {
    known[code] = true;
  });
  var rest = all.filter(function (row) {
    return !known[row.disease];
  });
  if (rest.length)
    out.push({ key: "other", title: "그 밖의 질환", sets: rest });

  return out;
}

/* **왼쪽은 큰 갈래 셋이다** — 안내문 · 처방 · 기타. 원문 D2-1~D2-5 의 레일이
   그 차례로 서 있다.
 *
 * 안내문을 「기타」에 섞어 두었었는데, 그것은 처방과 나란한 큰 갈래다 —
 * 약마다 한 장씩 확인하는 자리라 「2/5」 같은 진도가 붙는다. 섞어 두면 무엇이
 * 큰 일이고 무엇이 곁다리인지 화면이 말해 주지 않는다.
 *
 * 「그 밖에」를 「기타」로 부른다.
 */
var RAIL_SECTIONS = [
  { key: "guide", title: "안내문" },
  { key: "sets", title: "처방" },
  { key: "rest", title: "기타" },
];

/* 갈래 안의 줄들. **아직 없는 것은 없다고 적는다** — 자리만 비워 두면 다음
   사람이 무엇을 만들어야 하는지 모르고, 채워 두면 되는 것처럼 보인다. */
var RAIL_GROUPS = [
  {
    key: "guide",
    section: "guide",
    title: "약별 안내문",
    note: "D2-1 · D2-2",
    saying: "약별 기본 안내문을 관리합니다 · 준비 중",
  },
  {
    key: "baseline",
    section: "rest",
    title: "검사 기준선",
    note: "D2-4",
    saying: "검사 항목의 기준선을 설정합니다 · 준비 중",
  },
  {
    key: "sms",
    section: "rest",
    title: "문자 문구",
    note: "D2-5",
    saying: "의원 공통 문자 문구를 관리합니다",
  },
  {
    key: "clinic",
    section: "rest",
    title: "의원 정보",
    note: "→ 어드민 A1-4",
    saying: "의원 정보는 어드민 화면에서 관리합니다",
  },
];

/** 한 갈래에 드는 줄들. */
function groupsIn(section) {
  return RAIL_GROUPS.filter(function (row) {
    return row.section === section;
  });
}

/** 처방일수를 실제 일수로 — **소진 예정일이 이 셈으로 정해진다.**
 *
 * EMR 「총투」 칸의 「3」이 3통일 수도 3일일 수도 있어서 의원마다 다르다.
 * 통으로 세는데 한 통이 며칠인지 모르면 **셈하지 않는다**(`null`) — 지어낸
 * 날짜로 예약하면 엉뚱한 날 문자가 간다.
 */
function courseDaysOf(setting, written) {
  var n = parseInt(String(written), 10);
  if (isNaN(n) || n <= 0) return null;

  var mode = setting && setting.days_mode;
  if (mode !== "PACK") return n;

  var per = parseInt(String(setting && setting.days_per_pack), 10);
  if (isNaN(per) || per <= 0) return null;
  return n * per;
}

/* **어느 묶음이 실제로 열리는가.** 자리만 세운 것과 만든 것을 여기서 가른다 —
   화면 여러 곳이 이 사실을 물으므로 한 곳에 둔다. */
var RAIL_GROUP_READY = { sms: true };
