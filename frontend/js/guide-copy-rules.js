/* 안내문 고치기 — 와이어프레임 D2-1 · D2-2 의 규칙들. KEY-234.
 *
 * 원문 주석: 「의사마다 말하는 방식이 다르고 같은 의사도 일정하지 않다. 문구를
 * 하나로 강제하면 원장님이 안 쓰신다. 대신 **원본을 위에 두어 무엇이 사실이고
 * 무엇이 표현인지 보이게 한다.** 원본은 지워지지 않으므로 언제든 되돌아간다.」
 *
 * **와이어프레임은 「약 하나에 한 장」인데 우리는 처방 세트 한 장이다.**
 * 원본(`drug_caution_content`)이 처방 세트에 붙어 있고 약 목록이 아직 비어
 * 있기 때문이다 — 약 이름은 의사가 처방 설정(D2-3)에서 채운다.
 */

/* 구역 이름 — 원문 D2-2 의 네 구역.
 *
 * 한동안 주의사항 둘뿐이었고, 「복약지도·생활지도는 환자마다 판독값으로
 * 만들어지는 것이라 고칠 문구가 없다」고 적어 두었다. **그것이 틀렸다** —
 * 판독값이 들어가는 것과 문구를 못 고치는 것은 다른 얘기다. 원문은 넷 다
 * [수정] 이고, 두 갈래의 문장이 `guides.py` 에 박혀 있었을 뿐이다.
 *
 * 차례는 환자가 읽는 차례다 — 복약지도 → 주의사항 → 생활지도. 응급은
 * 주의사항 바로 뒤에 붙는다(같은 이야기의 끝이라 떨어뜨리면 안 읽힌다). */
var COPY_SECTION_SAYING = {
  medication: "복약지도",
  caution: "주의할 점",
  emergency: "🚨 바로 병원에 오셔야 하는 경우",
  life: "생활지도",
};

function copySectionSaying(key) {
  return COPY_SECTION_SAYING[key] || key || "";
}

/** 지금 환자에게 나가는 글. **원장님 문구가 있으면 그것, 없으면 원본.** */
function copyShown(section) {
  if (!section) return "";
  return section.body != null && section.body !== ""
    ? section.body
    : section.origin || "";
}

/** 고친 자리인가 — 화면이 「원장님 문구」 표를 붙일지 정한다. */
function copyIsMine(section) {
  return !!section && section.body != null && section.body !== "";
}

/* 「안내문 2/5」 진도 — 원문 레일의 수. **확인한 장 / 전체 장**이다.
   구역이 아니라 장을 센다: 원문이 「조각을 하나씩 승인하게 하면 확인할 것이
   54개가 되지만 약 단위로 묶으면 5장이면 끝난다」고 적는다. */
function copyProgress(items) {
  var rows = items || [];
  var done = rows.filter(function (row) {
    return row.reviewed;
  }).length;
  return { done: done, total: rows.length, say: done + "/" + rows.length };
}

/* 질환으로 묶는다 — 원문 레일이 「✓ 다낭성난소증후군 / 자궁내막증」 두 덩이다.
 **받은 차례를 지킨다** — 서버가 준 순서가 곧 화면 순서다. */
function copyByDisease(items) {
  var order = [];
  var blocks = {};
  (items || []).forEach(function (row) {
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

/* 한 장의 표시 — 원문 레일의 「✓ 비잔」·「야즈 확인 전」. */
function copyMark(row) {
  return row && row.reviewed ? "✓" : "확인 전";
}

/* 저장하기 전에 화면이 먼저 재는 것. 서버와 같은 이유로 막는다. */
function copyProblem(section, body) {
  if (section && section.editable === false)
    return "이 문구는 안전을 위해 수정할 수 없습니다";
  if (!String(body == null ? "" : body).trim())
    return "문구를 비워 둘 수 없습니다";
  return "";
}
