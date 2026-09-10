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
function guideSourcesHtml(sources) {
  if (!sources || !sources.length) return "";
  return '<details class="block__sources"><summary>생성 당시 근거 · 의료진 검토용</summary><ul>' +
    sources.map(function (source) {
      if (source.generation_mode === "template") {
        var reason = source.fallback_reason === "search_infrastructure_exhausted"
          ? "검색 장애 → 템플릿" : "근거 없음 → 템플릿";
        return "<li>" + esc(reason) + " · 템플릿 " + esc(source.template_id || "") +
          " · 버전 " + esc(source.version) + "</li>";
      }
      return "<li>RAG · " + esc(source.source_org || "") +
        " · 문서 " + esc(source.document_id || "") + " · 버전 " + esc(source.version) +
        " · 확인일 " + esc(source.verified_at || "") +
        " · 출처 " + esc(source.source_url || "") + "</li>";
    }).join("") + "</ul></details>";
}

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
    guideSourcesHtml(section.sources) +
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

/* **환자가 받는 그대로** — KEY-286.
 *
 * 여태 이 자리는 `.ph__block` 이라는 **제 목업**이었다. 「환자가 받는 그대로」
 * 라고 적어 두었는데 환자는 `.card` 레이아웃을 받았다 — 라벨이 거짓이었다.
 *
 * ## 왜 iframe 인가
 *
 * 모양이 같으려면 **환자 자신의 스타일시트**를 써야 한다. 그런데 그 파일은
 * `.card` · `.btn` · `body` 같은 흔한 이름을 쓴다 — 스탭 화면에 그냥 실으면
 * 그 화면을 덮는다.
 *
 * 골라 베껴 오는 길도 있는데, 그러면 **모양이 두 벌**이 된다. 환자 화면이
 * 바뀌는 날 미리보기만 옛 모양으로 남고, 그것이 바로 이 티켓이 없애려는 것이다.
 *
 * iframe 은 그 둘을 다 피한다 — 환자 CSS 를 **그대로** 신되 스탭 화면과 안
 * 섞인다. 그리고 `srcdoc` 은 문자열이라, 이 함수는 여전히 문자열을 돌려주고
 * 검사도 그 문자열을 그대로 읽는다.
 *
 * **스크립트를 안 싣는다.** 미리보기는 읽는 자리다 — 탭·펼치기 같은 환자 화면의
 * 손놀림은 여기서 필요 없고, 넣으면 스탭 화면 안에서 도는 코드가 하나 더 는다.
 *
 * 모래상자는 `allow-same-origin` 하나만 연다. **`allow-scripts` 는 안 준다** —
 * 그 둘을 함께 주면 모래상자가 제 스스로를 풀 수 있게 되고, 하나만이면 안에서
 * 코드가 아예 안 돈다. 여는 까닭은 스타일시트 때문이다: 안 열면 문서가 opaque
 * origin 이 되어 `/patient_wireframe/css/guide.css` 를 못 싣고, 그러면 이
 * 티켓이 하려던 「같은 모양」이 통째로 무너진다(브라우저에서 실제로 그랬다).
 *
 * ## 못 채우는 카드는 안 그린다
 *
 * 이 화면이 가진 것은 `sections` 와 `summary` 뿐이다. 「나의 목표」·「처방받은
 * 약」·「약별 복용 방법」은 환자 종점의 파생(`medication`·`goals`)에서 오는데
 * 스탭 종점은 그것을 안 준다.
 *
 * 빈 카드를 세우면 승인 전에 「목표가 안 잡혔네」로 읽힌다 — **모양은 같은데
 * 내용이 비어 보이는 것**이 지금(모양이 다른 것)보다 나쁘다. 안 그리는 것은
 * 환자 렌더러 자신의 규칙이기도 하다(`if (g.drug)` …).
 */
function guidePreviewHtml(sections, current, summary, preview) {
  var bodyOf = function (key) {
    var row = guideSectionsOf(sections, key)[0];
    return row && row.body ? row.body : "";
  };
  var inner = patientPreviewBodyHtml(bodyOf, current, summary || "", preview);

  /* **골격도 환자 것을 그대로 세운다** (유가은 님 `#253`).
   *
   * 여기는 `<div class="guide-body">` 하나로 감싸고 있었다. 환자 CSS 에는 그런
   * 이름이 없다 — 카드 사이 간격(`gap: 12px`)·좌우 여백·스크롤을 만드는 규칙은
   * `<main class="body">` 에 붙어 있고, 그 이름을 안 쓰면 **CSS 는 실었는데
   * 본문 배치만 환자와 다른** 상태가 된다. 카드가 서로 붙고, 주의사항 탭처럼
   * 카드가 여럿 이어지는 자리에서 바로 드러난다.
   *
   * 그래서 `frontend/guide.html` 의 골격을 그대로 쓴다 — `.app` 안에 탭 줄을
   * 이고 있는 `.header`, 그 아래 `<main class="body">`.
   *
   * 머리의 로고·환자 이름·[PDF 저장] 은 안 넣는다. 스탭 종점이 안 주는 값이라
   * 넣으려면 지어내야 하고, 이 티켓이 없애려는 것이 바로 그 종류의 거짓이다.
   *
   * 탭 바는 **끌 수 없다**(`disabled`). 미리보기는 읽는 자리이고, 여기서 탭이
   * 움직이면 스탭 화면의 항목 탭과 어느 쪽이 진짜인지 흐려진다.
   *
   * `<style>` 로 `body` 를 다시 손대지 않는다. `guide.css` 가 이미 여백을
   * 0 으로 두고 배경을 정한다 — 여기서 덧칠하면 그것이 곧 새 drift 다.
   *
   * `srcdoc` 안에서 큰따옴표가 속성을 닫는다. 본문은 이미 `esc` 를 지났고,
   * 여기서는 그 결과 문자열을 속성에 담기 위해 한 번 더 감싼다. */
  var doc =
    '<!doctype html><meta charset="utf-8">' +
    '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">' +
    patientStylesheetLinks() +
    '<div class="app">' +
    '<header class="header">' +
    patientTabBarHtml(current) +
    "</header>" +
    '<main class="body">' +
    inner +
    "</main>" +
    "</div>";

  return (
    '<iframe class="pv" title="환자 화면 미리보기" aria-label="환자 화면 미리보기"' +
    ' sandbox="allow-same-origin" loading="lazy" srcdoc="' +
    doc.replace(/&/g, "&amp;").replace(/"/g, "&quot;") +
    '"></iframe>'
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

function guideScreenHtml(sections, current, mode, canEdit, editingKey, summary, preview) {
  var title = GUIDE_SCREEN_TITLE[mode] || GUIDE_SCREEN_TITLE.guide;

  return (
    /* **기본정보와 같은 상자다.** 예전에는 회색 머리띠를 두른 제 어휘였는데,
       한 화면 안에서 탭을 옮길 때마다 블록 모양이 바뀌어 눈이 자리를 새로
       찾았다. 담는 모양은 `.box` 하나로 모은다. */
    '<section class="box gs">' +
    '<div class="box__head gs__head">' +
    '<span class="box__title gs__title">' +
    esc(title) +
    "</span>" +
    guideSegmentsHtml(sections, current) +
    "</div>" +
    /* **「문자 설정」은 다른 화면이다** (S1-14). 원문·미리보기 두 칸이 아니라
       회차·문구를 다루는 자리라, 그 탭에서는 통째로 갈아 끼운다. */
    (current === "messages"
      ? smsScreenHtml(smsPlanOf(sections, mode))
      : guideBodyHtml(sections, current, canEdit, editingKey, summary, preview)) +
    "</section>"
  );
}

/* 문자 설정에 넘길 값. 진료에서 오는 것(진료일 · 소진 예정일 · 환자 번호)과
   사람이 만진 것(회차 · 시각 · 문구)을 합친다. 뒤엣것은 이제 서버에 담긴다
   (`GET·PUT /guide/messages`) — `guideSmsPlan()` 이 저장 가능 여부도 준다. */
function smsPlanOf(sections, mode) {
  /* 진료에서 오는 값(진료일 · 소진 예정일 · 환자 번호)은 화면이 준다.
     사람이 만진 값(회차 · 시각 · 문구)은 `guideSmsState` 가 들고 있다. */
  var seed = (typeof guideSmsPlan === "function" && guideSmsPlan(mode)) || {};
  return smsStateNow(seed);
}

function guideBodyHtml(sections, current, canEdit, editingKey, summary, preview) {
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
    guidePreviewHtml(sections, current, summary, preview) +
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
function guideActionsFor(status, roles, reason) {
  var isDoctor = (roles || []).indexOf("doctor") !== -1;

  if (status === "STAFF_REVIEW") {
    return { canSubmit: true, say: "스탭 확인 후 의사에게 전달됩니다 · 승인은 의사 역할만 가능합니다" };
  }
  if (status === "APPROVAL_RETURNED") {
    /* 반려된 것은 다시 스탭 차례다 — 고치고 다시 넘긴다.
       **무엇을 고칠지 함께 적는다.** 서버가 `returned_reason` 으로 주는데
       화면이 안 쓰고 있었다 — 「고친 뒤 다시 넘겨 주세요」만 보면 무엇을
       고쳐야 하는지 알 길이 없어, 의사에게 다시 물어야 한다. */
    return {
      canSubmit: true,
      say: "반려된 안내문입니다 — 고친 뒤 다시 넘겨 주세요",
      why: reason || "",
    };
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

/* 의원 템플릿(D2-5)은 아직 없다. 원문의 「템플릿으로 저장」이 그 자리인데,
   담을 표가 없어 단추를 그리지 않는다 — 눌러도 아무 일 없는 단추보다 낫다. */
var SMS_NO_TEMPLATE = "저장은 이 환자에게만 적용됩니다 — 의원 템플릿은 아직 없습니다";

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
    /* **끌 수 있다.** 예전에는 늘 ☑ 로 그려 둔 글자였다 — 처방일수를 모르는
       진료에서도 켜진 것처럼 보였고, 끄고 싶어도 누를 데가 없었다. */
    '<button class="sms__check" type="button" data-sms-runout aria-pressed="' +
    (plan.runOutOn !== false) +
    '" aria-label="소진 임박 안내 켜고 끄기">' +
    (plan.runOutOn !== false ? "☑" : "☐") +
    "</button>소진 " +
    '<input class="sms__days" type="number" min="1" max="30" value="' +
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
    /* 「이 환자만 적용」 — 원문의 저장 단추다. 문구뿐 아니라 회차 · 시각 ·
       소진 며칠 전을 한 판으로 보낸다. */
    '<div class="sms__save">' +
    (plan.saying ? '<span class="sms__said">' + esc(plan.saying) + "</span>" : "") +
    '<button class="button-primary button-primary--sm" type="button" data-sms-save' +
    (plan.canSave ? "" : " disabled") +
    ">이 환자만 적용</button>" +
    "</div>" +
    '<p class="sms__note">ⓘ {링크}는 지울 수 없습니다 · ' +
    esc(plan.canSave ? SMS_NO_TEMPLATE : plan.lockedSaying || SMS_NO_TEMPLATE) +
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
    /* **「3일」이 아니다** — `LINK_TTL` 이 168 시간(7일)이다(KEY-223, `#224`).
       바로 아래 링크 블록이 실제 만료일을 띄우므로, 이 줄이 3일이라고 하면
       **같은 화면 안에서 대놓고 어긋난다.** */
    '<p class="sms__note">ⓘ 링크는 발송 시 이 환자 · 이 건의 고유 주소로 발급됩니다 (7일 만료) — 미리보기는 예시입니다</p>' +
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
    /* **문구 블록 아래에 링크 블록** — 문구의 `{링크}` 가 이것이다(KEY-275).
       규칙도 모양도 `patient-link-view.js` 가 갖는다. 현황 화면도 같은 것을
       그린다 — 두 벌이면 같은 링크가 화면마다 다르게 보인다. */
    patientLinkBlockHtml(plan.link || null, plan.guideStatus, new Date()) +
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
/** 서버가 준 설정을 화면 상태로 삼는다. **고르고 있던 회차는 지킨다** —
    저장한 뒤 다시 읽을 때 보던 문구가 첫 회차로 튀면 안 된다. */
function smsAdopt(plan) {
  var next = smsPlanFromServer(plan);
  var picked = (guideSmsState && guideSmsState.picked) || "d7";
  guideSmsState = {
    picked: picked,
    on: next.on,
    at: next.at,
    runOutOn: next.runOutOn !== false,
    runOutBefore: next.runOutBefore,
    texts: next.texts,
  };
  return guideSmsState;
}

function smsStateNow(seed) {
  if (!guideSmsState) {
    guideSmsState = {
      picked: "d7",
      on: { d15: true },
      at: "10:00",
      runOutOn: true,
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
    runOutOn: st.runOutOn !== false,
    runOutBefore: st.runOutBefore,
    canSave: base.canSave !== false,
    lockedSaying: base.lockedSaying || "",
    saying: base.saying || "",
    /* 링크 블록이 읽는 둘 — KEY-275. **이 함수가 안 통과시키면 블록이 늘
       「아직 없음」이다**(안 넘긴 값은 `undefined` 라 승인 여부를 못 본다). */
    guideStatus: base.guideStatus || "",
    link: base.link || null,
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
    /* 소진 임박 켜고 끄기 */
    if (t.closest("[data-sms-runout]")) {
      state().runOutOn = state().runOutOn === false;
      say("");
      reRender();
      return;
    }

    var pick = t.closest("[data-sms-pick]");
    if (pick) {
      state().picked = pick.getAttribute("data-sms-pick");
      say("");
      reRender();
      return;
    }

    /* 「이 환자만 적용」 — 회차 · 시각 · 문구 · 소진 며칠 전을 한 판으로 보낸다 */
    var save = t.closest("[data-sms-save]");
    if (save) {
      if (save.disabled || typeof opts.save !== "function") return;
      save.disabled = true;
      opts.save(smsPlanToServer(state()));
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

/* ── 승인 확인 모달 (와이어프레임 D1-5) ──────────────────────────────
 *
 * 원문 주석: 「화면을 갈아끼우지 않는다 — 뒤에 최종 확인 탭이 흐려진 채
 * 남는다」. 승인은 되돌리기 어려운 일이라, 무엇을 승인했는지 뒤에 그대로
 * 보이는 채로 결과를 말한다.
 *
 * 의사 화면과 최종 확인 탭이 **같은 모달**을 쓴다. 예전에는 `doctor.js` 안에만
 * 있어서 최종 확인 탭에서 승인하면 아무 창도 안 떴다.
 */

/* 「오늘 18:00」 — 원문의 표기다. 「9월 1일 18:00」이라고 적으면 원장님이
   달력을 짚어 오늘인지 확인해야 한다. 오늘·내일만 말로 바꾸고 그 밖은
   날짜를 적는다.

   `now` 를 받는 이유는 검사가 시각을 정할 수 있어야 하기 때문이다. 안 주면
   지금으로 본다. */
function sendWhenText(iso, now) {
  var m = String(iso || "").match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}:\d{2})/);
  if (!m) return "곧";

  var at = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  var today = now ? new Date(now.getFullYear(), now.getMonth(), now.getDate()) : null;
  if (!today) {
    var t = new Date();
    today = new Date(t.getFullYear(), t.getMonth(), t.getDate());
  }

  var days = Math.round((at - today) / 86400000);
  if (days === 0) return "오늘 " + m[4];
  if (days === 1) return "내일 " + m[4];
  return Number(m[2]) + "월 " + Number(m[3]) + "일 " + m[4];
}

/* 승인 뒤에 뜨는 창.
 *
 *   view.scheduledAt  승인이 잡아 둔 발송 시각 (서버가 준 `scheduled_at`)
 *   view.name         환자 이름
 *   view.now          지금 (검사용. 안 주면 진짜 지금)
 *
 * **없는 발송을 약속하지 않는다.** 원문은 「자동 발송됩니다」라고 적지만, 이
 * 저장소에는 아직 문자를 보내는 것이 없다 — `GuideMessage` 를 `SENT` 로 바꾸는
 * 코드가 검사 밖에 없다. 원장님이 그 문장만 읽고 「환자에게 갔다」고 믿으면,
 * 안 간 것을 갔다고 아는 상태가 된다. 원문 문구는 그대로 두고 **아직 없는
 * 것만** 아래에 덧붙인다 (`KEY-148` §6 · `KEY-160` 이 정한 방식이다).
 */
function approvedModalHtml(view) {
  var name = (view && view.name) || "";
  return (
    '<p class="modal__mark">✓</p>' +
    '<h2 class="modal__title">승인 완료</h2>' +
    '<div class="modal__said">' +
    '<p class="modal__lead"><b>' +
    esc(sendWhenText(view && view.scheduledAt, view && view.now)) +
    "</b> " +
    esc(name ? name + " 님께 발송 예정" : "발송 예정") +
    "</p>" +
    '<p class="modal__sub">확인 문자(일주일 뒤 · 보름 뒤)와 소진 임박 안내는 자동 발송됩니다</p>' +
    "</div>" +
    '<div class="modal__box">' +
    "<span>발송 실패 시 알림 창에서 확인할 수 있습니다</span>" +
    "<span>문자 잔량 · 발신번호 문제는 실패 처리하지 않고 발송 대기합니다</span>" +
    "</div>" +
    '<p class="modal__note">[demo] 문자 발송기는 아직 붙지 않았습니다 — 지금 승인은 <b>발송 예약까지</b>입니다.</p>' +
    '<div class="modal__acts">' +
    '<button class="button-ghost" type="button" data-go-status>현황 보기</button>' +
    '<button class="button-primary" type="button" data-close>닫기</button>' +
    "</div>"
  );
}

/* 「현황 보기」를 **그리는 파일이 누르는 일까지 맡는다** — KEY-302.
 *
 * 이 단추의 마크업은 위 `approvedModalHtml()` 이 그리고, 그 함수는 스탭 화면과
 * 의사 화면이 함께 쓴다. 그런데 누르는 일은 `visit-guide.js` 에만 있었고
 * `doctor.html` 은 그 파일을 안 싣는다 — **의사 화면에서는 눌러도 아무 일도
 * 안 일어났다.** 승인 직후 모달의 단추라 원장님이 매번 만난다.
 *
 * KEY-310 과 같은 모양의 결함이다: 마크업은 공용 파일이 그리는데 그것을 살리는
 * 것(모양이든 손이든)이 화면 하나에만 있었다. 그래서 여기, **마크업 옆에** 둔다.
 *
 * 모달을 닫는 방법은 화면마다 다르다(의사 화면은 발급한 링크도 함께 잊는다).
 * 그래서 닫는 일은 각자에게 알리고, 여기서는 **어디로 가는지**만 정한다.
 *
 * **알림은 물음이기도 하다.** 닫는 쪽이 「지금은 안 된다」고 할 수 있어야 한다 —
 * 의사 화면의 링크 발급 창은 아직 복사도 열지도 않은 링크를 들고 있을 수 있고,
 * 그것을 잊으면 **토큰을 되찾을 길이 없다**(`canDiscardPatientLink`). 그래서
 * 되돌릴 수 있는 사건으로 보내고, 막히면 **가지 않는다** (2heej, #274).
 *
 * 가는 방법은 탭 단추를 대신 누르는 것이다 — 탭을 바꾸는 규칙(스탭은 제자리,
 * 의사는 `data-href` 로 이동)이 화면마다 다르고, 여기서 흉내내면 표시(✓ · ● · ○)
 * 가 갈린다. */
function goToStatusTab() {
  /* 단계 줄은 두 화면 다 늘 그린다 — `step-nav.js` 가 다섯 칸을 세운다.
     그것이 없으면 화면이 이미 깨진 것이라, 여기서 대신할 길을 짓지 않는다.
     자리가 있는지는 `approve-modal.test.js` 가 두 화면 원문에 대고 잰다. */
  var tab = document.querySelector('.tab[data-tab="status"]');
  if (tab) tab.click();
}

document.addEventListener("click", function (event) {
  var target = event.target;
  if (!target || !target.closest || !target.closest("[data-go-status]")) return;

  /* `cancelable` 이라 닫는 쪽이 막을 수 있다. 막히면 창도 그대로, 자리도 그대로다 —
     사람이 「닫지 않겠다」고 답한 것을 여기서 뒤집지 않는다. */
  var asked = new CustomEvent("guide:modal-close", { bubbles: true, cancelable: true });
  if (!document.dispatchEvent(asked)) return;

  goToStatusTab();
});
