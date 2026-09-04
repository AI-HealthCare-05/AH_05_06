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
  { key: "sets", title: "대표 처방" },
  { key: "rest", title: "기타" },
];

/* 갈래 안의 줄들. **아직 없는 것은 없다고 적는다** — 자리만 비워 두면 다음
   사람이 무엇을 만들어야 하는지 모르고, 채워 두면 되는 것처럼 보인다. */
/* 「안내문 문구」 한 줄은 여기 없다 — 안내문은 갈래 밑에 **장이 그대로 선다.**
   목록 바로 아래 같은 자리를 가리키는 줄이 또 있으면, 고른 장과 그 줄이 함께
   굵어져 어느 것을 보고 있는지 화면이 두 가지로 말한다. */
var RAIL_GROUPS = [
  {
    key: "baseline",
    section: "rest",
    title: "검사 기준선",
    note: "D2-4",
    saying: "검사 항목의 기준선을 설정합니다",
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

/* `courseDaysOf` 는 여기 없다 — 처방일수를 세는 규칙이라 설정 화면만의
   것이 아니고, 판독 화면(S1-6)의 처방약 내역도 같은 셈을 쓴다.
   `js/drug-lines.js` 에 있다. */

/* **어느 묶음이 실제로 열리는가.** 자리만 세운 것과 만든 것을 여기서 가른다 —
   화면 여러 곳이 이 사실을 물으므로 한 곳에 둔다.
   `guide` 는 여기 없다 — 안내문은 줄 하나가 아니라 갈래 밑에 장이 그대로
   서므로 여닫을 「묶음 줄」이 아예 없다. 안 쓰는 열쇠를 남겨 두면 다음 사람이
   있지도 않은 줄을 찾는다. */
var RAIL_GROUP_READY = { sms: true, baseline: true };

/** 한 처방이 **레일에서 어느 묶음에 드는가.**
 *
 * `setsByDisease` 는 모르는 질환을 「그 밖의 질환」(`other`) 한 칸에 몰아넣는다.
 * 그래서 처방의 `disease` 값을 그대로 묶음 열쇠로 쓰면 안 된다 — 모르는 질환의
 * 처방을 고르면 열려는 묶음이 없어 조용히 접힌 채로 남는다. 나누는 규칙과 찾는
 * 규칙이 갈라지지 않도록 **나눈 결과에서 되찾는다.**
 */
function railGroupKey(sets, setId) {
  var blocks = setsByDisease(sets);
  for (var i = 0; i < blocks.length; i++) {
    var mine = blocks[i].sets.filter(function (row) {
      return row.prescription_set_id === setId;
    });
    if (mine.length) return blocks[i].key;
  }
  return null;
}

/** 레일에 붙는 안내문 한 장의 표시. **모르면 모른다고 한다** — 아직 안 받아
    온 목록을 「확인 전」으로 적으면 다 안 본 것처럼 보인다. */
function copyRailMark(copy, setId) {
  if (!copy || !copy.items) return { say: "", done: false };
  var found = copy.items.filter(function (row) {
    return row.prescription_set_id === setId;
  })[0];
  if (!found) return { say: "", done: false };
  return { say: found.reviewed ? "✓" : "확인 전", done: !!found.reviewed };
}

/** 레일에서 묶음을 가리키는 열쇠. **갈래를 함께 담는다** — 안내문과 처방에
    같은 질환이 있어서, 질환 열쇠만으로는 한쪽을 열면 다른 쪽도 열린다.
    질환 코드는 A–Z 라 `|` 가 들어올 일이 없다. */
function railFoldKey(section, key) {
  return String(section) + "|" + String(key);
}

/** 레일 자식 줄에 **보일** 이름. 저장값은 그대로 둔다.
 *
 * 이 문자열은 진료 기록의 스냅샷 조인 열쇠다 — `prescription_set` 열이
 * 「진료 당시 처방 세트 이름의 스냅샷」이라, 저장값을 바꾸면 KEY-165 의 주의
 * 문구가 이 이름으로 안내문을 못 찾는다. **화면에서만** 벗긴다.
 *
 * 접두사가 묶음마다 다르게 붙어 있다 — 자궁내막증은 이름으로(「자궁내막증 · 」),
 * PCOS 는 코드로(「PCOS · 」). 그래서 **둘 다** 후보로 본다. 묶음 이름으로만
 * 자르면 PCOS 다섯 줄이 그대로 남는다.
 *
 * 「`·` 앞을 자른다」로 하면 「선근증 · 생리과다」의 앞토막까지 없어진다 —
 * 그 가운뎃점은 이름의 일부다. **이 묶음의 열쇠나 이름과 정확히 맞을 때만** 뗀다.
 * 그래서 「그 밖의 질환」 묶음에서는 아무것도 안 떨어진다 — 모르는 질환이
 * 몰려 있는 칸이라 질환 이름이 곧 알아야 할 정보다.
 */
function railSetName(block, name) {
  var full = String(name == null ? "" : name);
  if (!block) return full;

  var at = full.indexOf(" · ");
  if (at < 0) return full;

  var head = full.slice(0, at);
  if (head !== block.key && head !== block.title) return full;

  /* 벗기고 나면 빈 줄이 되는 이름은 그대로 둔다 — 이름 없는 줄은 못 고른다 */
  return full.slice(at + 3).trim() || full;
}

/** 한 묶음의 안내문 진도 — 「1/3」.
 *
 * 처방 갈래는 개수(`3`)를, 안내문 갈래는 진도(`1/3`)를 단다. 접두사를 떼면
 * 두 갈래가 글자까지 같은 나무 두 그루가 되는데, 숫자의 뜻이 다르면 접혀
 * 있을 때도 갈린다. 꾸밈이 아니라 볼 사람이 알고 싶은 값이다.
 *
 * **아직 못 받아 온 목록은 「0/3」이라 하지 않는다** — 그건 「세 장 다 안
 * 봤다」는 뜻이라 「아직 모른다」와 다르다. 그때는 개수만 적는다.
 */
function copyBlockMark(copy, sets) {
  var rows = sets || [];
  if (!copy || !copy.items) return { say: String(rows.length), done: false };

  var done = rows.filter(function (row) {
    return copyRailMark(copy, row.prescription_set_id).done;
  }).length;

  return {
    say: done + "/" + rows.length,
    done: rows.length > 0 && done === rows.length,
  };
}
