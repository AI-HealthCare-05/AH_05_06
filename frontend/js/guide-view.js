/* 안내문을 그리는 규칙 — 의사 화면과 환자 카드가 **같은 것을 쓴다**.
 *
 * 원래 이 코드는 `doctor.js` 안에만 있었다. 그런데 와이어프레임에서 `D1` 은
 * 별도 화면이 아니라 **환자 카드의 5단계 탭 뒷칸**이다.
 *
 *     1 기본정보   2 진료기록   3 안내문        4 최종 확인      5 현황
 *                              S1-11~13       D1-1~D1-5       D1-6·D1-7
 *
 * 두 자리가 같은 안내문을 그리는데 코드가 두 벌이면, 한쪽만 고쳐지고 화면마다
 * 다른 말이 나온다 — 이 저장소가 이미 겪은 일이다(구조 진단 §5.1: 같은 5단계를
 * 한 화면은 `<li>`, 다른 화면은 `<button role="tab">` 으로 만들었다).
 *
 * **여기 있는 것은 전부 순수 함수다.** 데이터를 받아 문자열을 돌려준다.
 * 화면 요소를 찾지 않으므로 IIFE 밖에 있고, 검사가 닿는다 — 화면 파일의 84%가
 * 검사에서 한 줄도 안 도는 지금 상태에서 이 부분만이라도 재려는 것이다.
 */

/* 서버는 `key` 를 계약대로 주고, **한국어로 옮기는 것은 화면 몫이다.**
   서버가 한국어를 주면 화면마다 다른 말이 섞이고, 문구를 바꿀 때 두 곳을 고쳐야 한다. */
var GUIDE_SECTION_LABEL = {
  medication: "복약지도",
  caution: "주의사항",
  emergency: "🚨 바로 병원에 연락하세요",
  life: "생활 안내",
  messages: "문자 설정",
};

/* **응급 문장은 탭을 갖지 않는다.** 서버가 주는 다섯 갈래 중 `emergency` 만
   탭에서 빼고 「주의사항」 탭 본문 안에 이어 붙인다(와이어프레임 D1-2).

   따로 탭을 만들면 그 탭을 안 열고 승인할 수 있다. 열지 않아도 되는 문장이
   아니다 — 일반 주의 문구를 읽으러 들어온 자리에서 함께 보인다.

   서버가 나눈 까닭은 **잠금 단위**다. `locked` 는 섹션 단위라, 한 칸에 두면
   응급 문장을 지키려다 일반 문구까지 잠긴다 (KEY-161). */
var GUIDE_TUCKED_UNDER = { emergency: "caution" };

/* **아직 받아 줄 서버가 없는 섹션.**

   `messages` 는 본문 자체는 서버가 주지만 회차·문구를 **저장할 자리가 없다**
   (구조화된 문자 설정은 `GuideResponse` 에 없고 `S1-14` 후속 계약이다).
   그래서 [수정] 을 열지 않는다 — 이 저장소가 「고칠 수 있어 보이는데 저장이
   안 되는 칸이 제일 나쁘다」로 정해 둔 자리다.

   `locked` 로 표현하지 않는다. `locked` 는 「식약처 기준 문장이라 사람이 고칠
   자리가 아니다」라는 뜻이고, 여기는 「아직 안 만들었다」라서 이유가 다르다.
   섞으면 나중에 문자 설정이 붙었을 때 무엇을 풀어야 하는지 알 수 없다(KEY-160). */
var GUIDE_NOT_IMPLEMENTED = {
  messages: "회차·문구를 저장할 자리가 아직 없습니다 — S1-14 후속 계약입니다",
};

/* 탭으로 세울 섹션 — 접어 넣는 것(응급)은 뺀다. 차례는 서버가 준 그대로다. */
function guideTabSections(sections) {
  return (sections || []).filter(function (s) {
    return !GUIDE_TUCKED_UNDER[s.key];
  });
}

/* 이 탭에서 함께 보여 줄 섹션들 — 자기 자신과, 자기 밑에 접힌 것. */
function guideSectionsOf(sections, key) {
  return (sections || []).filter(function (s) {
    return s.key === key || GUIDE_TUCKED_UNDER[s.key] === key;
  });
}

/* 고른 탭이 사라졌으면(안내문이 바뀌었다) 첫 탭으로 돌아간다.
   없는 탭을 붙들고 있으면 본문이 통째로 비어 화면이 고장난 것처럼 보인다. */
function guideCurrentSection(sections, wanted) {
  var tabs = guideTabSections(sections);
  for (var i = 0; i < tabs.length; i++) {
    if (tabs[i].key === wanted) return tabs[i];
  }
  return tabs[0] || null;
}

function guideTabsHtml(sections, current) {
  return guideTabSections(sections)
    .map(function (s) {
      return (
        '<button class="vtab' +
        (s.key === current ? " is-on" : "") +
        '" type="button" data-section="' +
        esc(s.key) +
        '">' +
        esc(GUIDE_SECTION_LABEL[s.key] || s.key) +
        (s.warn ? ' <span class="vtab__warn">⚠</span>' : "") +
        "</button>"
      );
    })
    .join("");
}

/* 서버는 섹션마다 **본문 한 덩이**(`body`)를 준다. 예전 목업은 제목·표·목록으로
   쪼갠 `blocks` 를 그렸는데, 그건 렌더 편의로 만든 모양이지 계약이 아니었다.

   `canEdit` 는 역할이 정한다 — **화면을 감추지 않고 버튼만 잠근다.** 스탭도
   의사 화면을 다 볼 수 있어야 하고(와이어프레임은 한 화면이다), 고칠 수 있는
   범위만 다르다. 실제 차단은 서버가 한다(KEY-9). */
function guideSectionHtml(section, canEdit) {
  var title = GUIDE_SECTION_LABEL[section.key] || section.key;

  /* 잠긴 섹션은 왜 잠겼는지를 함께 적는다. 이유 없이 안 눌리는 버튼은
     「고장났다」로 읽히고, 보는 사람은 그것을 확인하느라 시간을 쓴다. */
  var pending = GUIDE_NOT_IMPLEMENTED[section.key];
  var tail;
  if (section.locked) {
    tail = '<p class="block__locked">🔒 식약처 기준 문장이라 고칠 수 없습니다 — 약이 바뀌면 문장도 바뀝니다</p>';
  } else if (pending) {
    tail = '<p class="block__locked">[demo] ' + esc(pending) + "</p>";
  } else if (canEdit === false) {
    tail = '<p class="block__locked">안내문 수정은 의사 계정에서 할 수 있습니다</p>';
  } else {
    tail = '<button class="block__edit" type="button" data-edit="' + esc(title) + '">수정</button>';
  }

  return (
    '<section class="block' +
    (section.warn ? " block--warn" : "") +
    (section.locked ? " block--locked" : "") +
    '">' +
    '<h3 class="block__title">' +
    esc(title) +
    "</h3>" +
    (section.warn ? '<p class="block__warnline">⚠ ' + esc(section.warn) + "</p>" : "") +
    '<p class="block__body">' +
    esc(section.body) +
    "</p>" +
    (section.edited ? '<p class="block__hint">이 항목은 수정되었습니다</p>' : "") +
    tail +
    "</section>"
  );
}

function guidePanelHtml(sections, current, canEdit) {
  return guideSectionsOf(sections, current)
    .map(function (s) {
      return guideSectionHtml(s, canEdit);
    })
    .join("");
}

/* 위에 몇 개를 봐야 하는지 먼저 말한다. 없으면 「없다」고 분명히 말한다 —
   그래야 읽지 않고 승인해도 된다는 것이 전해진다. */
function guideWarnLine(sections) {
  var n = 0;
  for (var i = 0; i < (sections || []).length; i++) {
    if (sections[i].warn) n++;
  }
  return {
    count: n,
    className: "warnline" + (n ? " warnline--warn" : " warnline--ok"),
    text: n
      ? "확인 부탁드리는 곳 " + n + "군데 — ⚠ 표시만 보시면 됩니다"
      : "확인 부탁드릴 곳이 없습니다 — 그대로 승인하셔도 됩니다",
  };
}
