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
  /* 와이어프레임 S1-11 · D1-1 의 탭 이름이 「생활지도」다. 환자 화면(P4)은
     같은 것을 「생활관리」로 부르는데, 이 화면은 의료진이 보는 자리라
     의료진 쪽 이름을 쓴다 — 원장님이 탭 이름으로 찾는다. */
  life: "생활지도",
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
function guideSectionHtml(section, canEdit, editingKey) {
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
  } else if (editingKey === section.key) {
    /* 고치는 중. **제자리에서 고친다** — 창을 띄우면 옆의 미리보기가 가려져
       무엇이 나갈지 못 보면서 고치게 된다. 그러려고 두 칸을 나란히 뒀다. */
    tail =
      '<textarea class="block__edit-box" data-edit-box="' +
      esc(section.key) +
      '" aria-label="' +
      esc(title) +
      ' 본문">' +
      esc(section.body) +
      "</textarea>" +
      '<div class="block__edit-acts">' +
      '<button class="button-primary button-primary--sm" type="button" data-edit-save="' +
      esc(section.key) +
      '">저장</button>' +
      '<button class="button-ghost button-ghost--sm" type="button" data-edit-cancel="1">취소</button>' +
      "</div>";
  } else {
    /* **「수정」 버튼은 여기 없다.** 판 머리 오른쪽 끝으로 올렸다
       (`guideHeadEditHtml` — 와이어프레임 S1-11 · D1-1 이 그 자리에 둔다).
       항목마다 버튼이 있으면 한 탭에 둘이 뜨는데(주의사항 + 응급), 그중
       하나는 잠겨 있어서 「왜 하나만 눌리지」가 된다.

       왜 못 고치는지는 여기 그대로 둔다 — 그건 그 항목의 사정이다. */
    tail = "";
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

function guidePanelHtml(sections, current, canEdit, editingKey) {
  return guideSectionsOf(sections, current)
    .map(function (s) {
      return guideSectionHtml(s, canEdit, editingKey);
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


/* ── 안내문 화면 한 판 (와이어프레임 S1-11 · D1-1) ─────────────────────
 *
 * **두 프레임은 같은 화면이다.** 다른 것은 제목과 아래 버튼뿐이다:
 *
 *   S1-11  「환자가 받게 될 안내문 · 스탭 확인」   [진료기록 재업로드] [의사 승인 요청]
 *   D1-1   「환자가 받게 될 안내문 · 미리보기」     [스탭에 되돌리기]   [승인]
 *
 * 그래서 한 벌로 그린다. 두 벌이면 한쪽만 고쳐지고, 스탭이 본 것과 의사가
 * 보는 것이 달라진다 — 그건 「의사가 보지 않은 글이 환자에게 간다」와 같은
 * 종류의 사고다.
 *
 * 왼쪽이 원문(고칠 수 있는 것), 오른쪽이 환자가 받을 모양이다. 나란히 두는
 * 것이 이 화면의 전부다 — 고치면서 환자 눈에 어떻게 보이는지 함께 본다.
 */

var GUIDE_SCREEN_TITLE = {
  guide: "환자가 받게 될 안내문 · 스탭 확인",
  final: "환자가 받게 될 안내문 · 미리보기",
};

/* 가로 탭 — 와이어프레임은 칸막이로 이어 붙인 한 덩어리다(`height:26px`,
   고른 것만 검정 채움). 세로 목록이 아니라 가로라, 네 항목이 한눈에 든다. */
function guideSegmentsHtml(sections, current) {
  return (
    '<div class="seg" role="tablist" aria-label="안내문 항목">' +
    guideTabSections(sections)
      .map(function (s) {
        return (
          '<button class="seg__one' +
          (s.key === current ? " is-on" : "") +
          '" type="button" role="tab" aria-selected="' +
          (s.key === current ? "true" : "false") +
          '" data-section="' +
          esc(s.key) +
          '">' +
          esc(GUIDE_SECTION_LABEL[s.key] || s.key) +
          (s.warn ? ' <span class="seg__warn">⚠</span>' : "") +
          "</button>"
        );
      })
      .join("") +
    "</div>"
  );
}

/* 환자가 받을 모양 — **환자 앱 화면을 그대로 축소해 세운다.**
 *
 * 우리가 읽는 원문과 환자가 보는 것이 다르면, 고치는 사람은 무엇이 나갈지
 * 모른 채 고친다. 그래서 카드 몇 장이 아니라 **기기 화면을 흉내낸다.**
 *
 * 와이어프레임 원문(`wireframe-patient-2.3.1.html` P2)에서 확인한 것:
 *   · 폭 375px · 높이 지정 없음(내용대로 늘어난다) · 테두리 2px · radius 12
 *   · 상태바 · 노치 · 홈 인디케이터는 **그린 적이 없다** — 흉내내지 않는다
 *   · 탭 다섯은 **맨 위**에 있다(44px). 아래가 아니다
 *   · 본문 `padding:16px · gap:18px`
 *   · 묶음 제목은 카드가 아니라 **3×18 검정 막대 + 18px/600 글자**
 *   · 「본문만」은 56px 머리와 아래 안내상자·푸터를 뺀다 — 탭 줄은 남긴다
 *   · 축소는 `zoom:.8` 이다. `transform:scale` 로 바꾸면 안쪽 폭이 375 가
 *     아니라 300 이 되어 **줄바꿈이 달라진다** — 환자가 볼 줄 모양과 다르다
 */

/* 환자 화면의 탭. 의료진 화면과 이름이 다르다 — 「생활지도」가 환자에게는
   「생활관리」다. 각자 자기 쪽 이름을 쓴다. */
var PATIENT_TABS = [
  { key: "medication", label: "복약지도" },
  { key: "caution", label: "주의사항" },
  { key: "life", label: "생활관리" },
  { key: "status", label: "현황" },
  { key: "chat", label: "챗봇" },
];

function guidePreviewHtml(sections, current) {
  var rows = guideSectionsOf(sections, current);

  var tabs = PATIENT_TABS.map(function (t) {
    return (
      '<span class="ph__tab' +
      (t.key === current || (current === "emergency" && t.key === "caution") ? " is-on" : "") +
      '">' +
      esc(t.label) +
      "</span>"
    );
  }).join("");

  var body = rows.length
    ? rows
        .map(function (s) {
          return (
            '<section class="ph__block">' +
            '<h4 class="ph__title"><span class="ph__bar" aria-hidden="true"></span>' +
            esc(GUIDE_SECTION_LABEL[s.key] || s.key) +
            "</h4>" +
            '<p class="ph__body">' +
            esc(s.body) +
            "</p></section>"
          );
        })
        .join("")
    : '<p class="ph__body">이 항목에는 아직 내용이 없습니다</p>';

  return (
    '<div class="ph" aria-label="환자 화면 미리보기">' +
    '<div class="ph__tabs">' +
    tabs +
    "</div>" +
    '<div class="ph__body-wrap">' +
    body +
    "</div></div>"
  );
}

/* 판 머리 오른쪽 끝의 「수정」 — 와이어프레임 S1-11 · D1-1.
 *
 * **이 탭의 주인 항목**을 고친다. 주의사항 탭에는 응급 문장이 함께 오는데
 * 그건 식약처 기준이라 못 고친다 — 고칠 수 있는 것은 탭 이름이 가리키는
 * 항목 하나뿐이다.
 *
 * 못 고치는 상황에서는 아무것도 안 그린다. 이유는 항목 블록이 말한다 —
 * 머리에도 적으면 같은 말이 두 번 뜬다.
 */
function guideHeadEditHtml(sections, current, canEdit, editingKey) {
  if (canEdit === false || editingKey === current) return "";

  var own = null;
  var rows = guideSectionsOf(sections, current);
  for (var i = 0; i < rows.length; i++) {
    if (rows[i].key === current) own = rows[i];
  }
  if (!own || own.locked || GUIDE_NOT_IMPLEMENTED[own.key]) return "";

  return '<button class="gs__edit" type="button" data-edit="' + esc(own.key) + '">수정</button>';
}

function guideScreenHtml(sections, current, mode, canEdit, editingKey) {
  var title = GUIDE_SCREEN_TITLE[mode] || GUIDE_SCREEN_TITLE.guide;

  return (
    '<section class="gs">' +
    '<div class="gs__head">' +
    '<span class="gs__title">' +
    esc(title) +
    "</span>" +
    guideSegmentsHtml(sections, current) +
    "</div>" +
    /* **「문자 설정」은 다른 화면이다** (S1-14). 원문·미리보기 두 칸이 아니라
       회차·문구를 다루는 자리라, 그 탭에서는 통째로 갈아 끼운다. */
    (current === "messages"
      ? smsScreenHtml(smsPlanOf(sections, mode))
      : guideBodyHtml(sections, current, canEdit, editingKey)) +
    "</section>"
  );
}

/* 문자 설정에 넘길 값. 서버가 회차·문구를 주지 않으므로 **화면이 아는 것만**
   모은다 — 진료일과 소진 예정일은 판독 값에서 오고, 문구는 기본 템플릿이다. */
function smsPlanOf(sections, mode) {
  /* 진료에서 오는 값(진료일 · 소진 예정일 · 환자 번호)은 화면이 준다.
     사람이 만진 값(회차 · 시각 · 문구)은 `guideSmsState` 가 들고 있다. */
  var seed = (typeof guideSmsPlan === "function" && guideSmsPlan(mode)) || {};
  return smsStateNow(seed);
}

function guideBodyHtml(sections, current, canEdit, editingKey) {
  return (
    '<div class="gs__body">' +
    /* 왼쪽 — 원문 */
    '<section class="gs__pane">' +
    '<div class="gs__paneHead">' +
    '<span class="gs__paneTitle">원문</span>' +
    '<span class="gs__paneNote">환자 화면과 같은 차례</span>' +
    guideHeadEditHtml(sections, current, canEdit, editingKey) +
    "</div>" +
    '<div class="gs__paneBody">' +
    guidePanelHtml(sections, current, canEdit, editingKey) +
    "</div>" +
    "</section>" +
    /* 오른쪽 — 환자 화면 미리보기 */
    '<section class="gs__pane gs__pane--pv">' +
    '<div class="gs__paneHead">' +
    '<span class="gs__paneTitle">환자 화면 미리보기</span>' +
    '<span class="gs__paneNote">환자가 받는 그대로</span>' +
    "</div>" +
    '<div class="gs__paneBody">' +
    guidePreviewHtml(sections, current) +
    "</div>" +
    "</section>" +
    "</div>" +
    /* 병원에서만 보는 메모 — 환자 화면에 안 나간다 */
    '<p class="gs__memo">병원에서만 보는 메모 — 환자 화면에 안 나갑니다 · ' +
    "안내 문구가 없는 약이 섞이면 그 항목만 「약사 복약지도를 참고하세요」로 나갑니다</p>"
  );
}

/* ── 안내문 화면의 하단 버튼 ──────────────────────────────────────────
 *
 *   S1-11 (안내문 · 스탭 확인)   [진료기록 재업로드]  … [의사 승인 요청]
 *   D1-1  (최종 확인 · 미리보기)  [스탭에 되돌리기]    … [승인]
 *
 * 넘긴 뒤에는 스탭이 더 할 일이 없다 — 버튼을 지우고 어디까지 왔는지 말한다.
 * 눌러도 409 로 떨어지는 버튼을 두면 「내가 뭘 잘못했나」로 읽힌다.
 */
function guideActionsFor(status, roles) {
  var isDoctor = (roles || []).indexOf("doctor") !== -1;

  if (status === "STAFF_REVIEW") {
    return { canSubmit: true, say: "스탭 확인 후 의사에게 전달됩니다 · 승인은 의사 역할만 가능합니다" };
  }
  if (status === "APPROVAL_RETURNED") {
    /* 반려된 것은 다시 스탭 차례다 — 고치고 다시 넘긴다. */
    return { canSubmit: true, say: "반려된 안내문입니다 — 고친 뒤 다시 넘겨 주세요" };
  }
  if (status === "APPROVAL_PENDING") {
    return {
      canSubmit: false,
      say: isDoctor
        ? "의사 승인을 기다리는 중입니다 — 「최종 확인」에서 승인하실 수 있습니다"
        : "의사에게 넘겼습니다 — 승인을 기다리는 중입니다",
    };
  }
  if (status === "SCHEDULED_TO_SEND") {
    return { canSubmit: false, say: "승인되어 발송을 기다리는 중입니다" };
  }
  return { canSubmit: false, say: "" };
}

/* ── 고치기 배선 ───────────────────────────────────────────────────────
 *
 * 스탭 화면(`patients.html`)과 의사 화면(`doctor.html`)이 **같은 배선**을
 * 쓴다. 두 벌이면 한쪽만 고쳐지고, 어느 화면에서 고쳤느냐에 따라 되고 안
 * 되고가 달라진다 — 이 저장소에서 이미 여러 번 그랬다.
 *
 * 지금까지 양쪽 다 이어져 있지 않았다. 의사 화면은 「항목 편집은 승인 API 가
 * 붙은 뒤입니다」라는 안내창을 띄웠고(그 API 는 그 뒤에 붙었다), 스탭 화면은
 * 처리기 자체가 없었다.
 *
 * 화면마다 다른 것은 **어느 진료인지**와 **다시 그리는 법**뿐이라, 그 둘만
 * 받는다.
 */
var guideEditingKey = null;

function guideEditingNow() {
  return guideEditingKey;
}

function wireGuideEditing(opts) {
  var getVisitId = opts.visitId;
  var reRender = opts.reRender;
  var say = opts.say || function () {};

  document.addEventListener("click", function (event) {
    var t = event.target;
    if (!t || !t.closest) return;

    var open = t.closest("[data-edit]");
    if (open) {
      guideEditingKey = open.getAttribute("data-edit");
      reRender();
      /* 열자마자 칠 수 있게 — 키보드로 다니는 사람이 판이 열린 것을 알
         방법이 그것뿐이다. */
      var box = document.querySelector('[data-edit-box="' + guideEditingKey + '"]');
      if (box) box.focus();
      return;
    }

    if (t.closest("[data-edit-cancel]")) {
      guideEditingKey = null;
      reRender();
      return;
    }

    var save = t.closest("[data-edit-save]");
    if (!save) return;

    var key = save.getAttribute("data-edit-save");
    var field = document.querySelector('[data-edit-box="' + key + '"]');
    var text = field ? String(field.value || "").trim() : "";
    var visitId = getVisitId();
    if (!visitId) return;

    /* **빈 글로 덮지 않는다.** 환자가 받는 글이라, 지우고 저장하면 그 항목이
       빈 채로 나간다. 지우는 것이 목적이면 그건 다른 일이다. */
    if (!text) {
      say("내용을 비울 수는 없습니다 — 환자가 받는 글입니다");
      return;
    }

    /* 두 번 눌리지 않게 잠근다. 저장이 두 번 가면 판(version)이 두 번 오른다. */
    save.disabled = true;
    var wantedId = visitId;
    doctorApi
      .editSection(wantedId, key, { body: text })
      .then(function () {
        if (getVisitId() !== wantedId) return;
        guideEditingKey = null;
        say("고쳤습니다");
        reRender(true);
      })
      .catch(function (error) {
        if (getVisitId() !== wantedId) return;
        save.disabled = false;
        say((error && error.message) || "저장하지 못했습니다. 다시 시도해 주세요.");
      });
  });
}


/* ── 문자 설정 (와이어프레임 S1-14) ───────────────────────────────────
 *
 * 안내문 화면의 네 번째 탭이다. 확인 문자 회차 · 소진 임박 · 재진 안내를 한
 * 자리에 모아, 스탭이 S2-1 에서 이탈 환자를 발견하면 곧바로 조치할 수 있게 한다.
 *
 * 왼쪽에서 발송 항목을 고르면 오른쪽에서 그 문자의 문구를 고치고 미리보기로
 * 확인한다. 미리보기는 **변수가 치환된 실제 발송본**이고 바이트 수도 치환 후
 * 기준이다 — 치환 전 글을 보여 주면 무엇이 나갈지 모른 채 고치게 된다.
 *
 * 셈은 `js/sms-plan.js` 가 갖는다. 여기는 그리는 것만 한다.
 *
 * **저장할 자리가 서버에 아직 없다.** 회차·문구를 담는 표가 없다
 * (`check_in` 은 환자의 D+7 응답이지 회차가 아니다). 화면은 그것을 감추지
 * 않는다 — 켤 수 있게 두면 스탭이 켜 두고 갔다고 믿는다.
 */

var SMS_NOT_SAVED = "회차와 문구를 저장하는 자리가 서버에 아직 없습니다 — 지금은 보기만 됩니다";

/** 회차 줄 하나. 고른 줄만 진한 테두리에 「◀ 미리보기 중」이 붙는다.
 *
 * **줄 전체가 고르는 버튼이고, 체크는 따로 켜고 끈다.** 둘을 한 버튼에 두면
 * 「보려고 눌렀는데 꺼졌다」가 생긴다 — 회차를 보려면 골라야 하는데, 고르는
 * 것과 켜는 것은 다른 일이다.
 */
function smsRoundRow(round, startIso, on, picked) {
  var when = smsWhen(smsDateAfter(startIso, round.days));
  var tail = on ? when + " 예정" : "꺼짐 · 켜면 " + when;

  return (
    '<div class="sms__row' +
    (picked ? " is-on" : "") +
    (on ? "" : " is-off") +
    '">' +
    /* 켜고 끄기 — 고정 회차는 잠긴다 */
    '<button class="sms__check" type="button" data-sms-toggle="' +
    esc(round.key) +
    '"' +
    (round.fixed ? ' aria-disabled="true"' : "") +
    ' aria-pressed="' +
    (on ? "true" : "false") +
    '" aria-label="' +
    esc(round.label + (on ? " 끄기" : " 켜기")) +
    '">' +
    (on ? "☑" : "☐") +
    "</button>" +
    /* 고르기 — 오른쪽 문구·미리보기가 이 회차로 바뀐다 */
    '<button class="sms__pick" type="button" data-sms-pick="' +
    esc(round.key) +
    '" aria-pressed="' +
    (picked ? "true" : "false") +
    '">' +
    esc(round.label) +
    (round.fixed ? ' <span class="sms__fixed">(고정)</span>' : "") +
    "</button>" +
    '<span class="sms__when">' +
    esc(tail) +
    "</span>" +
    (picked ? '<span class="sms__now">◀ 미리보기 중</span>' : "") +
    "</div>"
  );
}

/** 왼쪽 칸 — 확인 문자 · 소진 임박 · 재진 안내 */
function smsLeftHtml(plan) {
  var startIso = plan.startIso || "";
  var runOutIso = plan.runOutIso || "";
  var before = plan.runOutBefore || 3;
  var noticeIso = smsRunOutNotice(runOutIso, before);

  var rounds = SMS_ROUNDS.map(function (r) {
    /* 일주일 뒤는 끌 수 없다 — 켜짐이 아니라 **고정**이다 */
    var on = r.fixed || (plan.on || {})[r.key] === true;
    return smsRoundRow(r, startIso, on, plan.picked === r.key);
  }).join("");

  return (
    '<section class="sms__card">' +
    '<h3 class="sms__title">확인 문자 <span class="sms__sub">· 처방 세트 기본값 · 이 환자만 바꾼다</span></h3>' +
    rounds +
    '<p class="sms__note">확인 문자 시각 ' +
    '<select class="sms__time" data-sms-at aria-label="확인 문자 시각">' +
    SMS_TIMES.map(function (t) {
      return (
        '<option value="' +
        esc(t.key) +
        '"' +
        (t.key === (plan.at || "10:00") ? " selected" : "") +
        ">" +
        esc(t.label) +
        "</option>"
      );
    }).join("") +
    "</select>" +
    " — 확인 · 재진 문자에 적용 · 안내문은 승인 시각(기본 18:00) 규칙을 따릅니다</p>" +
    "</section>" +
    '<section class="sms__card">' +
    '<h3 class="sms__title">소진 임박 안내</h3>' +
    '<div class="sms__row">' +
    '<span class="sms__check" aria-hidden="true">☑</span>소진 ' +
    '<input class="sms__days" type="number" min="1" max="90" value="' +
    esc(String(before)) +
    '" data-sms-before aria-label="소진 며칠 전에 보낼지" /> 일 전' +
    '<span class="sms__when">' +
    (noticeIso
      ? esc(smsWhen(noticeIso)) + " 예정 · 소진 " + esc(smsWhen(runOutIso))
      : "처방일수를 확인하면 셈합니다") +
    "</span></div></section>" +
    '<section class="sms__card">' +
    '<h3 class="sms__title">재진 안내</h3>' +
    '<div class="sms__row">마지막 발송 — 없음<span class="sms__when">' +
    "발송하는 자리가 아직 없습니다</span></div>" +
    '<p class="sms__note">ⓘ 문자 동의 「거부」면 비활성 · 잔량 0이면 대기</p>' +
    "</section>"
  );
}

/** 오른쪽 칸 — 문구와 미리보기 */
function smsRightHtml(plan) {
  var round = smsRoundOf(plan.picked) || SMS_ROUNDS[0];

  var text = plan.text || "";
  /* **「일차」는 고른 회차의 날수다.** 7일째 문자를 보면서 「15일째」가 뜨면
     스탭은 어느 회차를 고쳤는지 알 수 없다. */
  var values = {};
  var src = plan.values || {};
  for (var k in src) {
    if (Object.prototype.hasOwnProperty.call(src, k)) values[k] = src[k];
  }
  values["일차"] = round.days;
  var filled = smsFill(text, values);
  var kind = smsKind(filled);
  var missing = smsLinkMissingSaying(text);
  var whenIso = smsDateAfter(plan.startIso, round.days);

  return (
    '<section class="sms__card">' +
    '<div class="sms__head">' +
    '<h3 class="sms__title">문구</h3>' +
    '<span class="sms__tpl">' +
    esc(round.label) +
    " 확인 · 기본 템플릿</span>" +
    '<span class="sms__bytes' +
    (kind.long ? " is-long" : "") +
    '">' +
    esc(kind.label + " · " + kind.bytes + "바이트") +
    "</span></div>" +
    '<textarea class="sms__text" data-sms-text aria-label="문자 문구">' +
    esc(text) +
    "</textarea>" +
    '<div class="sms__acts">' +
    '<button class="button-ghost button-ghost--sm" type="button" data-sms-put="{링크}">+ 링크</button>' +
    SMS_VARS.filter(function (v) {
      return v.token !== "{링크}";
    })
      .map(function (v) {
        return (
          '<button class="button-ghost button-ghost--sm" type="button" data-sms-put="' +
          esc(v.token) +
          '">+ ' +
          esc(v.label) +
          "</button>"
        );
      })
      .join("") +
    "</div>" +
    (missing ? '<p class="sms__warn">⚠ ' + esc(missing) + "</p>" : "") +
    '<p class="sms__note">ⓘ {링크}는 지울 수 없습니다 · ' +
    esc(SMS_NOT_SAVED) +
    "</p>" +
    "</section>" +
    /* 미리보기 — 환자 휴대폰에 이렇게 간다 */
    '<section class="sms__card">' +
    '<h3 class="sms__title">미리보기 <span class="sms__sub">· 환자 화면에 이렇게 갑니다</span></h3>' +
    '<div class="sms__phone">' +
    '<p class="sms__meta">' +
    esc((plan.phone || "") + (whenIso ? " · " + smsWhen(whenIso) + " " + smsTimeLabel(plan.at) : "")) +
    "</p>" +
    '<p class="sms__bubble">' +
    esc(filled) +
    "</p>" +
    '<p class="sms__meta">변수 치환 후 ' +
    esc(kind.bytes + "바이트 · " + kind.label) +
    "</p></div>" +
    '<p class="sms__note">ⓘ 링크는 발송 시 이 환자 · 이 건의 고유 주소로 발급됩니다 (3일 만료) — 미리보기는 예시입니다</p>' +
    "</section>"
  );
}

/** 문자 설정 탭 한 판 — 왼쪽 11 : 오른쪽 9 (와이어프레임 원문) */
function smsScreenHtml(plan) {
  return (
    '<div class="sms">' +
    '<div class="sms__side sms__side--left">' +
    smsLeftHtml(plan) +
    "</div>" +
    '<div class="sms__side sms__side--right">' +
    smsRightHtml(plan) +
    "</div></div>"
  );
}

/* ── 문자 설정 배선 ────────────────────────────────────────────────────
 *
 * 스탭 화면과 의사 화면이 **같은 배선**을 쓴다 — 고치기(`wireGuideEditing`)와
 * 같은 이유다. 두 벌이면 어느 화면에서 만졌느냐에 따라 되고 안 되고가 갈린다.
 *
 * **고른 것은 화면 안에만 있다.** 회차·문구를 담는 표가 서버에 없어서다.
 * 저장된 척하지 않는다 — 카드 아래 줄이 그 사실을 말한다. 판독 화면에서
 * 직접 적은 값을 「저장 안 됨」으로 둔 것과 같은 판단이다.
 */
var guideSmsState = null;

/** 지금 상태. 처음 부를 때 화면이 아는 값으로 채운다. */
function smsStateNow(seed) {
  if (!guideSmsState) {
    guideSmsState = {
      picked: "d7",
      on: { d15: true },
      at: "10:00",
      runOutBefore: 3,
      texts: {},
    };
  }
  var st = guideSmsState;
  var base = seed || {};
  return {
    startIso: base.startIso || "",
    runOutIso: base.runOutIso || "",
    courseDays: base.courseDays || 0,
    phone: base.phone || "",
    values: base.values || {},
    picked: st.picked,
    on: st.on,
    at: st.at,
    runOutBefore: st.runOutBefore,
    text: st.texts[st.picked] !== undefined ? st.texts[st.picked] : smsDefaultText(st.picked),
  };
}

/** 회차별 기본 문구. 「이 환자만 적용」 > 의원 템플릿 > 기본 — 지금은 기본뿐이다. */
function smsDefaultText(key) {
  var r = smsRoundOf(key);
  var days = r ? r.days : 7;
  return "{환자명}님, 복약 " + days + "일째 확인입니다. 잘 드시고 계신가요? {링크}";
}

/** 다른 환자로 옮기면 지운다 — 앞 사람에게 고친 문구가 남으면 안 된다. */
function smsForget() {
  guideSmsState = null;
}

function wireSmsSettings(opts) {
  var reRender = opts.reRender;
  var say = opts.say || function () {};

  function state() {
    smsStateNow();
    return guideSmsState;
  }

  document.addEventListener("click", function (event) {
    var t = event.target;
    if (!t || !t.closest) return;

    /* 켜고 끄기 */
    var toggle = t.closest("[data-sms-toggle]");
    if (toggle) {
      var key = toggle.getAttribute("data-sms-toggle");
      var fixed = smsFixedSaying(key);
      if (fixed) {
        /* 아무 반응 없으면 「고장」으로 읽힌다 — 왜 안 되는지 말한다 */
        say(fixed);
        return;
      }
      state().on = smsToggled({ on: state().on }, key);
      say("");
      reRender();
      return;
    }

    /* 고르기 — 오른쪽 문구와 미리보기가 그 회차로 바뀐다 */
    var pick = t.closest("[data-sms-pick]");
    if (pick) {
      state().picked = pick.getAttribute("data-sms-pick");
      say("");
      reRender();
      return;
    }

    /* 문구에 토큰 끼워 넣기 — 커서 자리에 넣는다 */
    var put = t.closest("[data-sms-put]");
    if (put) {
      var box = document.querySelector("[data-sms-text]");
      var st = state();
      var text = box ? box.value : st.texts[st.picked] || smsDefaultText(st.picked);
      var at = box && typeof box.selectionStart === "number" ? box.selectionStart : text.length;
      st.texts[st.picked] = smsInsert(text, put.getAttribute("data-sms-put"), at);
      reRender();
      return;
    }
  });

  /* 치는 대로 바이트 수와 미리보기가 따라와야 한다 — 다 치고 나서 알면
     90 을 넘긴 뒤에 지우게 된다. */
  document.addEventListener("input", function (event) {
    var t = event.target;
    if (!t || !t.getAttribute) return;

    if (t.hasAttribute("data-sms-text")) {
      state().texts[state().picked] = t.value;
      reRender(true); // 커서를 지키며 다시 그린다
      return;
    }
    if (t.hasAttribute("data-sms-before")) {
      state().runOutBefore = smsClampBefore(t.value, opts.courseDays && opts.courseDays());
      reRender();
    }
  });

  document.addEventListener("change", function (event) {
    var t = event.target;
    if (!t || !t.hasAttribute || !t.hasAttribute("data-sms-at")) return;
    state().at = t.value;
    reRender();
  });
}
