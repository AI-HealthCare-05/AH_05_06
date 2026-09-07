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

/** 환자 화면의 카드 하나. */
function patientCardHtml(title, bodyHtml, extraClass) {
  return (
    '<div class="card' +
    (extraClass ? " " + extraClass : "") +
    '"><div class="card__section-title">' +
    esc(title) +
    "</div>" +
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

/** 복약지도 (P2) — 채울 수 있는 카드 둘만. */
function patientMedicationHtml(summary, why) {
  var cards = patientCardHtml(
    "오늘 진료 요약",
    summary ? '<div class="care-body-text">' + esc(summary) + "</div>" : patientEmptyHtml(PATIENT_EMPTY.medication),
  );
  /* 환자 렌더러의 `if (g.why && g.why.length)` 와 같다 — 없으면 카드가 안 선다. */
  if (why) cards += patientCardHtml("이 약을 왜 드시나요", '<div class="care-body-text">' + esc(why) + "</div>");
  return cards;
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
    ).replace('<div class="card__section-title"></div>', "");
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

/** 지금 탭의 환자 화면 본문. `sections` 에서 나오는 것만 그린다. */
function patientPreviewBodyHtml(bodyOf, current, summary) {
  var body;
  if (current === "life") body = patientLifeHtml(bodyOf("life"));
  else if (current === "caution" || current === "emergency") {
    body = patientCautionHtml(bodyOf("caution"), bodyOf("emergency"));
  } else body = patientMedicationHtml(summary, bodyOf("medication"));

  /* 탭 바는 **끌 수 없다**(`disabled`). 미리보기는 읽는 자리이고, 여기서 탭이
     움직이면 스탭 화면의 항목 탭과 어느 쪽이 진짜인지 흐려진다. */
  return patientTabBarHtml(current) + body;
}
