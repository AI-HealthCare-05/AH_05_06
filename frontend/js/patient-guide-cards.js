/* 환자 v3.0.0 안내문 카드 — 스탭·의사 화면의 미리보기가 쓰는 한 벌. KEY-286.
 *
 * 「환자가 받는 그대로」라고 적어 둔 미리보기가 **실제 환자 화면과 완전히 다른
 * 렌더러**였다. 환자는 `.card` 레이아웃을 받는데 미리보기는 납작한 `.ph__block`
 * 을 보였다 — 라벨이 거짓이었다.
 *
 * ## 🚩 데이터가 `sections` 뿐이다
 *
 * 스탭 종점(`GET /visits/{id}/guide`)은 `sections` 와 `summary` 를 준다. 환자
 * 종점은 거기에 **`medication`·`goals` 파생**을 더해 준다 —
 * `_patient_response()`(`app/apis/v1/patient_link_routers.py`)가 짓는다.
 *
 *     오늘 진료 요약      summary            ✅ 스탭 종점에도 있다
 *     이 약을 왜 드시나요   sections.medication ✅
 *     주의사항 · 응급      sections.caution/emergency ✅
 *     생활관리            sections.life       ✅
 *     나의 목표           goals               ❌ 없다
 *     처방받은 약         medication          ❌ 없다
 *     약별 복용 방법       medication.directions ❌ 없다
 *
 * 그래서 **못 채우는 카드는 아예 안 그린다.** 빈 카드를 세우면 스탭·의사가
 * 승인 전에 「목표가 안 잡혔네」로 읽는다 — 모양은 같은데 내용이 비어 보이는
 * 것이 지금(모양이 다른 것)보다 나쁘다.
 *
 * **이것은 미리보기가 지어낸 규칙이 아니다.** 환자 렌더러 자신이 그렇게 한다 —
 * `if (g.drug)` · `if (g.why && g.why.length)` · `if (g.how)` · `if (g.next)`
 * (`patient_wireframe/js/guide.js`). 값이 없는 카드는 환자 화면에서도 안 선다.
 *
 * ## 클래스 이름과 빈 상태 문구는 환자 것을 그대로 쓴다
 *
 * 스타일은 환자 자신의 `patient_wireframe/css/guide.css` 를 그대로 신는다
 * (미리보기가 iframe 이라 스탭 화면과 안 섞인다). 그래서 이름이 하나라도
 * 어긋나면 모양이 무너진다 — `patient-preview.test.js` 가 그 이름들을 환자
 * 렌더러 소스에 대고 확인한다.
 */

/* 환자 렌더러의 빈 상태 문구. **여기서 새로 짓지 않는다** — 지어내면 환자가
   보는 말과 스탭이 보는 말이 갈린다. */
var PATIENT_EMPTY = {
  medication: "표시할 승인 복약 안내가 아직 없어요.",
  caution: "표시할 승인 주의사항이 아직 없어요.",
  life: "표시할 승인 생활관리 안내가 아직 없어요.",
};


/* 환자 화면의 탭 — `patient_wireframe/js/guide.js` 의 `TABS` 그대로다.
 *
 * **넷이다.** 옛 미리보기는 다섯을 그렸고 그중 「챗봇」은 환자 탭 바에 없다 —
 * 「환자가 받는 그대로」가 거짓이던 자리가 여기에도 있었다.
 *
 * 이름표를 따로 두지 않는다. 환자 렌더러가 `b.textContent = key` 로 키를 그대로
 * 쓴다 — 옮겨 적으면 두 벌이 된다. */
var PATIENT_TAB_KEYS = ["현황", "복약지도", "주의사항", "생활관리"];

/** 스탭 화면의 항목 키 → 환자 탭 이름. 응급은 주의사항 탭 안이다(KEY-161). */
function patientTabOf(sectionKey) {
  if (sectionKey === "life") return "생활관리";
  if (sectionKey === "caution" || sectionKey === "emergency") return "주의사항";
  return "복약지도";
}

/* 미리보기 iframe 이 실을 스타일시트 — **`frontend/guide.html` 과 같은 벌.**
 *
 * 여기는 `tokens.css` + `guide.css`(버전 없음) 둘뿐이었다. 환자 화면은
 * `guide.css?v=11` 과 `chat.css?v=5` 까지 신는다. 버전 쿼리가 없으면 미리보기만
 * **옛 캐시본**을 볼 수 있다 — 이 티켓이 없애려던 drift 의 축소판이다
 * (이희진 님 `#253` ②).
 *
 * 손으로 적은 목록이라 또 갈릴 수 있다. 그래서 검사가 `frontend/guide.html`
 * 을 읽어 이 목록과 대 본다 — 환자 화면이 스타일시트를 더하거나 버전을 올리면
 * 그 검사가 운다.
 *
 * `chat.css` 는 미리보기에 챗봇 마크업이 없어 그리는 것이 없다. 그래도 뺀
 * 목록을 따로 들면 「무엇을 빼도 되는가」를 사람이 판단해야 하고, 그 판단이
 * 다음 drift 다. **같은 벌**이라는 규칙 하나만 둔다.
 */
var PATIENT_STYLESHEETS = [
  "/patient_wireframe/css/tokens.css",
  "/patient_wireframe/css/guide.css?v=11",
  "/patient_wireframe/css/chat.css?v=5",
];

function patientStylesheetLinks() {
  return PATIENT_STYLESHEETS.map(function (href) {
    return '<link rel="stylesheet" href="' + href + '">';
  }).join("");
}

function patientTabBarHtml(current) {
  var on = patientTabOf(current);
  return (
    '<div class="tab-bar" role="tablist">' +
    PATIENT_TAB_KEYS.map(function (key) {
      return (
        '<button class="tab-bar__btn' +
        (key === on ? " tab-bar__btn--active" : "") +
        '" type="button" role="tab" aria-selected="' +
        (key === on ? "true" : "false") +
        '" disabled>' +
        esc(key) +
        "</button>"
      );
    }).join("") +
    "</div>"
  );
}

/** 환자 화면의 카드 하나.
 *
 * 제목이 없으면 **제목 칸 자체를 안 세운다.** 빈 `<div>` 를 두면 환자 CSS 가
 * 그 자리에 여백을 주어 🚨 카드 위가 벌어진다. 전에는 세워 두고 만든 문자열을
 * 다시 `.replace` 로 도려냈는데, 그리는 규칙이 두 곳으로 갈라진다 —
 * 제목 칸 모양이 바뀌면 그 치환이 조용히 안 맞게 된다 (이희진 님 `#253` ③). */
function patientCardHtml(title, bodyHtml, extraClass) {
  return (
    '<div class="card' +
    (extraClass ? " " + extraClass : "") +
    '">' +
    (title ? '<div class="card__section-title">' + esc(title) + "</div>" : "") +
    bodyHtml +
    "</div>"
  );
}

function patientEmptyHtml(message) {
  return '<div class="guide-empty">' + esc(message) + "</div>";
}

function patientTabTitleHtml(main, sub) {
  return (
    '<div class="tab-title"><div class="tab-title__main">' +
    esc(main) +
    "</div>" +
    (sub ? '<div class="tab-title__sub">' + esc(sub) + "</div>" : "") +
    "</div>"
  );
}

/* 「나의 목표」의 막대 — 환자 렌더러의 계산을 **그대로** 옮긴다.
 *
 * 목표값을 가운데(50%)에 고정하고 나머지를 상대 위치로 잡는다. 목표가 없으면
 * (추이 관찰) 시작값을 가운데로 삼는다. 숫자를 여기서 다시 정하지 않는다 —
 * `patient_wireframe/js/guide.js` 의 `pctNum` 과 같은 식이어야 두 화면의 삼각형이
 * 같은 자리에 선다.
 *
 * 미리보기 iframe 에는 스크립트가 없다(`sandbox` 에 `allow-scripts` 가 없다).
 * 그래서 환자가 그리듯 DOM 을 세우지 않고 같은 값을 인라인 style 로 적는다. */
function goalChartPct(value, center, half) {
  return Math.min(95, Math.max(5, 50 + ((value - center) / half) * 50)) + "%";
}

function patientGoalItemHtml(goal, first) {
  var body = '<div class="goal-name">' + esc(goal.n) + "</div>";
  if (goal.rangeLabel) body += '<div class="goal-range-label">' + esc(goal.rangeLabel) + "</div>";

  var nowNum = parseFloat(goal.now);
  var startNum = parseFloat(goal.a);
  var targetNum = parseFloat(goal.t);
  var hasStart = !isNaN(startNum);
  var hasTarget = !isNaN(targetNum);

  if (goal.hasChart && !isNaN(nowNum) && (hasStart || hasTarget)) {
    var center = hasTarget ? targetNum : startNum;
    var half =
      Math.max(Math.abs(nowNum - center), hasStart ? Math.abs(startNum - center) : 0, 1) * 1.5;

    var chart =
      '<div class="goal-chart__pointer-row">' +
      '<div class="goal-chart__pointer" style="left:' +
      goalChartPct(nowNum, center, half) +
      '">' +
      '<span class="goal-chart__now-val">' +
      esc(goal.now) +
      "</span>" +
      '<div class="goal-chart__arrow"></div>' +
      "</div>" +
      "</div>" +
      '<div class="goal-chart__bar-wrap">' +
      (hasTarget ? '<span class="goal-chart__target-line" style="left:50%"></span>' : "") +
      (hasStart
        ? '<span class="goal-chart__start-line" style="left:' +
          (hasTarget ? goalChartPct(startNum, center, half) : "50%") +
          '"></span>'
        : "") +
      "</div>" +
      '<div class="goal-chart__scale-labels">' +
      [
        hasTarget ? "목표보다 낮음" : "시작보다 낮음",
        hasTarget ? "목표 " + goal.t : "추이 관찰",
        hasTarget ? "목표보다 높음" : "시작보다 높음",
      ]
        .map(function (label) {
          return '<span class="goal-chart__scale-label">' + esc(label) + "</span>";
        })
        .join("") +
      "</div>" +
      '<div class="goal-chart__start-summary">' +
      esc((hasStart ? "시작 " + goal.a + " · " : "") + "지금 " + goal.now) +
      "</div>";
    body += '<div class="goal-chart">' + chart + "</div>";
  } else {
    /* 값이 없어도 목표를 **숨기지 않는다** — 환자도 이 문장을 본다. */
    body +=
      '<div class="goal-no-chart">' +
      esc(goal.now ? "현재 " + goal.now : "결과가 나오면 채워드릴게요 · 지금 ─") +
      "</div>";
  }

  return '<div class="goal-item' + (first ? " goal-item--first" : "") + '">' + body + "</div>";
}

/** 「나의 목표」 — 목표가 없어도 **카드는 선다.** 환자 렌더러가 그렇게 한다. */
function patientGoalCardHtml(detail, visitDate) {
  var goals = (detail && detail.goals) || [];
  var head =
    '<div class="goal-head"><span class="card__section-title">나의 목표</span>' +
    (visitDate ? '<span class="goal-date">' + esc(visitDate) + "</span>" : "") +
    "</div>";

  var body = goals.length
    ? goals
        .map(function (goal, i) {
          return patientGoalItemHtml(goal, i === 0);
        })
        .join("")
    : patientEmptyHtml("등록된 검사 목표가 없어 차트를 표시하지 않아요.");

  if (detail && detail.goalSay) body += '<div class="goal-say">' + esc(detail.goalSay) + "</div>";
  return '<div class="card">' + head + body + "</div>";
}

/* 「더 자세히 보기」 안에 드는 카드들 — 환자 v3 정본이 처방약부터 접는다.
 *
 * **미리보기에서는 펼친 채로 둔다.** 여기는 승인 전에 읽는 자리라, 접어 두면
 * 스탭·의사가 자기가 승인하는 것을 못 본다. 단추는 환자 화면과 같은 자리에
 * 같은 모양으로 두되 **끌 수 없다**(`disabled`) — 탭 바와 같은 규칙이다. */
function patientDeeperHtml(inner) {
  if (!inner) return "";
  return (
    '<button class="expand-btn expand-btn--open" type="button" aria-expanded="true" disabled>' +
    "<span>접기</span>" +
    '<span class="expand-btn__icon">⌄</span>' +
    "</button>" +
    '<div class="expand-body expand-body--open">' +
    inner +
    "</div>"
  );
}

/** 복약지도 (P2) — 환자 화면의 카드 차례 그대로.
 *
 * `preview` 는 스탭 종점의 새 파생이다(KEY-294). 없으면 예전처럼 요약과
 * 「왜 드시나요」만 그린다 — 목업이나 옛 응답을 받아도 무너지지 않는다. */
function patientMedicationHtml(summary, why, preview) {
  var detail = (preview && preview.guide) || null;
  var cards = patientCardHtml(
    "오늘 진료 요약",
    summary ? '<div class="care-body-text">' + esc(summary) + "</div>" : patientEmptyHtml(PATIENT_EMPTY.medication),
  );

  /* **파생을 안 받았으면 목표 카드도 안 세운다.** 환자 화면은 목표가 없어도
     이 카드를 세우지만, 그건 「목표가 없다」를 **아는** 상태다. 값을 아예 못
     받은 미리보기가 같은 문장을 띄우면 모르는 것을 안다고 말하는 셈이다 —
     KEY-286 이 없앤 거짓의 다른 얼굴이다. */
  if (preview) cards += patientGoalCardHtml(detail, preview.visit);

  /* 환자 렌더러의 `if (g.drug)` · `if (g.why && g.why.length)` · `if (g.how)` ·
     `if (g.next)` 와 같은 차례·같은 조건이다. */
  var deeper = "";
  if (detail && detail.drug) {
    var drug = detail.drug;
    deeper += patientCardHtml(
      "처방받은 약",
      '<div class="drug-row">' +
        (drug.n ? '<div class="drug-row__name">' + esc(drug.n) + "</div>" : "") +
        (drug.s ? '<div class="drug-row__sub">' + esc(drug.s) + "</div>" : "") +
        (drug.d ? '<div class="drug-row__sub">' + esc(drug.d) + "</div>" : "") +
        "</div>",
    );
  }
  if (why) deeper += patientCardHtml("이 약을 왜 드시나요", '<div class="care-body-text">' + esc(why) + "</div>");
  if (detail && detail.how) {
    deeper += patientCardHtml("약별 복용 방법", '<div class="care-body-text">' + esc(detail.how) + "</div>");
  }
  if (detail && detail.next) {
    deeper += patientCardHtml("다음 방문 계획", '<div class="care-body-text">' + esc(detail.next) + "</div>");
  }

  return cards + patientDeeperHtml(deeper);
}

/** 주의사항 (P3) — 일반 주의와 🚨 응급이 한 탭에 이어 붙는다. */
function patientCautionHtml(caution, emergency) {
  var body = patientTabTitleHtml("주의사항", "미리 알아두시면 걱정을 덜 수 있어요");
  if (!caution && !emergency) return body + patientEmptyHtml(PATIENT_EMPTY.caution);
  if (caution) body += patientCardHtml("주의사항", '<div class="care-body-text">' + esc(caution) + "</div>");
  if (emergency) {
    body += patientCardHtml(
      "",
      '<div class="danger-title">🚨 바로 병원에 연락하세요</div><div class="danger-item">' +
        esc(emergency) +
        "</div>",
      "card--danger",
    );
  }
  return body;
}

/** 생활관리 (P4). **부제를 안 붙인다** — 환자 화면의 부제는 질환명인데
    스탭 종점이 그것을 안 준다. 없는 것을 지어내지 않는다. */
function patientLifeHtml(life) {
  var body = patientTabTitleHtml("생활관리", "");
  if (!life) return body + patientEmptyHtml(PATIENT_EMPTY.life);
  return body + patientCardHtml("생활관리", '<div class="axis-body-text">' + esc(life) + "</div>");
}

/** 지금 탭의 환자 화면 **본문**. `sections` 에서 나오는 것만 그린다.
 *
 * **탭 바는 여기 안 붙인다.** 환자 화면에서 탭 줄은 `.header` 안에 있고 카드는
 * `<main class="body">` 안에 있다 — 둘을 한 자루에 담으면 `.body` 의
 * `gap: 12px` 가 탭 줄에도 걸려 카드 간격이 환자 화면과 달라진다.
 * 골격은 부르는 쪽(`guidePreviewHtml`)이 환자 것 그대로 세운다. */
function patientPreviewBodyHtml(bodyOf, current, summary, preview) {
  if (current === "life") return patientLifeHtml(bodyOf("life"));
  if (current === "caution" || current === "emergency") {
    return patientCautionHtml(bodyOf("caution"), bodyOf("emergency"));
  }
  return patientMedicationHtml(summary, bodyOf("medication"), preview);
}
