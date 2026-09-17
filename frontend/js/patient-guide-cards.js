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
 * KEY-294 부터 스탭 종점도 `preview` 로 그 파생을 준다. KEY-365 부터는
 * 본문의 「■ 소제목」을 서버가 카드로 나누므로 **`preview` 가 있으면 그것만
 * 그린다** — `sections` 로 따로 그리면 환자와 카드가 갈린다.
 *
 *     오늘 진료 요약      preview.guide.summary   (없으면 카드 없음)
 *     이 약을 왜 드시나요   preview.guide.why
 *     약별 복용 방법       preview.guide.how
 *     소제목 카드         preview.guide.blocks
 *     주의사항 · 응급      preview.care
 *     생활관리            preview.life
 *     현황               preview.stat
 *
 * `preview` 가 없는 응답(목업·옛 응답)만 예전처럼 `sections` 로 그린다.
 *
 * **못 채우는 카드는 아예 안 그린다.** 빈 카드를 세우면 스탭·의사가
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
  if (sectionKey === "status") return "현황";
  if (sectionKey === "life") return "생활관리";
  if (sectionKey === "caution" || sectionKey === "emergency") return "주의사항";
  return "복약지도";
}

/* 미리보기 iframe 이 실을 스타일시트 — **`frontend/guide.html` 과 같은 벌.**
 *
 * 여기는 `tokens.css` + `guide.css`(버전 없음) 둘뿐이었다. 환자 화면은
 * `guide.css?v=12` 과 `chat.css?v=5` 까지 신는다. 버전 쿼리가 없으면 미리보기만
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
  "/patient_wireframe/css/guide.css?v=12",
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
        '" data-preview-tab="' +
        ["status", "medication", "caution", "life"][PATIENT_TAB_KEYS.indexOf(key)] +
        '">' +
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

/* 「더 자세히 보기」 안에 드는 카드들 — 환자 v3 정본이 처방약부터 접는다.
 *
 * **미리보기에서는 펼친 채로 둔다.** 여기는 승인 전에 읽는 자리라, 접어 두면
 * 스탭·의사가 자기가 승인하는 것을 못 본다. 단추는 환자 화면과 같은 자리에 둔다.
 * 여닫기는 iframe 밖의 공용 이벤트 처리기가 담당한다(KEY-348). */
function patientDeeperHtml(inner) {
  if (!inner) return "";
  return (
    '<button class="expand-btn expand-btn--open" type="button" aria-expanded="true" data-preview-expand>' +
    "<span>접기</span>" +
    '<span class="expand-btn__icon">⌄</span>' +
    "</button>" +
    '<div class="expand-body expand-body--open">' +
    inner +
    "</div>"
  );
}

/** 문단들 — 환자 렌더러처럼 첫 문단은 제목에 바로 붙인다. */
function patientParagraphsHtml(paragraphs, className) {
  return (paragraphs || [])
    .map(function (text, i) {
      return '<div class="' + className + '"' + (i === 0 ? ' style="margin-top:0"' : "") + ">" + esc(text) + "</div>";
    })
    .join("");
}

/** 복약지도 (P2) — 환자 화면의 카드 차례 그대로.
 *
 * `preview` 는 스탭 종점의 파생이다(KEY-294). 있으면 **그것만** 그린다 —
 * 요약은 서버가 확정 데이터로 지은 문장이고, 없으면 카드가 안 선다(KEY-365).
 * 없으면(목업·옛 응답) 예전처럼 `summary` 와 `sections.medication` 으로 그린다. */
function patientMedicationHtml(summary, why, preview) {
  var derived = !!preview;
  var detail = (preview && preview.guide) || null;

  /* 환자 렌더러의 `if (g.drug)` · `if (g.why && g.why.length)` · `if (g.how)` ·
     `g.blocks` · `if (g.next)` 와 같은 차례·같은 조건이다. */
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
  var whys = derived ? (detail && detail.why) || [] : why ? [why] : [];
  if (whys.length) deeper += patientCardHtml("이 약을 왜 드시나요", patientParagraphsHtml(whys, "care-body-text"));
  if (detail && detail.how) {
    deeper += patientCardHtml("약별 복용 방법", '<div class="care-body-text">' + esc(detail.how) + "</div>");
  }
  ((detail && detail.blocks) || []).forEach(function (block) {
    deeper += patientCardHtml(block.t, patientParagraphsHtml(block.p, "care-body-text"));
  });
  if (detail && detail.next) {
    deeper += patientCardHtml("다음 방문 계획", '<div class="care-body-text">' + esc(detail.next) + "</div>");
  }

  if (!derived) {
    return (
      patientCardHtml(
        "오늘 진료 요약",
        summary ? '<div class="care-body-text">' + esc(summary) + "</div>" : patientEmptyHtml(PATIENT_EMPTY.medication),
      ) + patientDeeperHtml(deeper)
    );
  }
  var head = (detail && detail.summary) || "";
  if (!head && !deeper) return patientCardHtml("", patientEmptyHtml(PATIENT_EMPTY.medication));
  /* 접어 둘 위 카드가 없으면 환자 화면도 단추 없이 펼친 채로 둔다. */
  if (!head) return '<div class="expand-body expand-body--open">' + deeper + "</div>";
  return (
    patientCardHtml("오늘 진료 요약", '<div class="care-body-text">' + esc(head) + "</div>") +
    patientDeeperHtml(deeper)
  );
}

/** 주의사항 (P3) — 소제목 카드들과 🚨 응급이 한 탭에 이어 붙는다.
 *
 * 제목은 환자 화면과 같은 「복약 중 주의사항」이다(`mapCare`). */
function patientCautionHtml(caution, emergency, preview) {
  var derived = !!preview;
  var care = derived ? preview.care : null;
  var body = patientTabTitleHtml((care && care.title) || "복약 중 주의사항", "미리 알아두시면 걱정을 덜 수 있어요");
  var blocks = derived ? (care && care.blocks) || [] : caution ? [{ t: "주의사항", p: [caution] }] : [];
  var danger = derived ? (care && care.danger) || [] : emergency ? [emergency] : [];
  if (!blocks.length && !danger.length) return body + patientEmptyHtml(PATIENT_EMPTY.caution);
  blocks.forEach(function (block) {
    body += patientCardHtml(block.t, patientParagraphsHtml(block.p, "care-body-text"));
  });
  if (danger.length) {
    body += patientCardHtml(
      "",
      '<div class="danger-title">🚨 바로 병원에 연락하세요</div>' +
        danger
          .map(function (item) {
            return '<div class="danger-item">' + esc(item) + "</div>";
          })
          .join(""),
      "card--danger",
    );
  }
  return body;
}

/** 생활관리 (P4) — 칩으로 카드 하나를 고른다(환자 `renderLife`).
 *
 * 부제는 환자 화면과 같은 값이다. `preview` 가 없으면 부제를 안 붙인다 —
 * 스탭 종점이 질환명을 안 주던 때다. 없는 것을 지어내지 않는다. */
function patientLifeHtml(life, preview, axis) {
  var derived = !!preview;
  var data = derived ? preview.life : null;
  var sub = derived ? (data ? data.sub || "" : "담당 의료진이 확인한 생활관리 안내") : "";
  var body = patientTabTitleHtml("생활관리", sub);
  var axes = derived ? (data && data.axes) || {} : life ? { 생활관리: { title: "생활관리", p: [life] } } : {};
  var keys = Object.keys(axes);
  if (!keys.length) return body + patientEmptyHtml(PATIENT_EMPTY.life);
  var active = keys.indexOf(axis) >= 0 ? axis : keys[0];
  body +=
    '<div class="axis-tabs" role="tablist">' +
    keys
      .map(function (key) {
        var on = key === active;
        return (
          '<button class="axis-tab ' +
          (on ? "axis-tab--active" : "axis-tab--inactive") +
          '" type="button" role="tab" aria-selected="' +
          (on ? "true" : "false") +
          '" data-preview-axis="' +
          esc(key) +
          '">' +
          esc(key) +
          "</button>"
        );
      })
      .join("") +
    "</div>";
  return body + patientCardHtml(axes[active].title || active, patientParagraphsHtml(axes[active].p, "axis-body-text"));
}

/** 지금 탭의 환자 화면 **본문**.
 *
 * **탭 바는 여기 안 붙인다.** 환자 화면에서 탭 줄은 `.header` 안에 있고 카드는
 * `<main class="body">` 안에 있다 — 둘을 한 자루에 담으면 `.body` 의
 * `gap: 12px` 가 탭 줄에도 걸려 카드 간격이 환자 화면과 달라진다.
 * 골격은 부르는 쪽(`guidePreviewHtml`)이 환자 것 그대로 세운다. */
function patientPreviewBodyHtml(bodyOf, current, summary, preview, axis) {
  if (current === "status") return patientStatusHtml(preview, bodyOf("medication"));
  if (current === "life") return patientLifeHtml(bodyOf("life"), preview, axis);
  if (current === "caution" || current === "emergency") {
    return patientCautionHtml(bodyOf("caution"), bodyOf("emergency"), preview);
  }
  return patientMedicationHtml(summary, bodyOf("medication"), preview);
}

function patientPreviewBodyOf(sections) {
  var tuckedUnder = { emergency: "caution" };
  return function (key) {
    var row = (sections || []).find(function (section) {
      return section.key === key || tuckedUnder[section.key] === key;
    });
    return row && row.body ? row.body : "";
  };
}

/** 현황도 환자 renderStatus + mapStat의 값/빈 상태 규칙을 따른다. 진행률은 서버 값이다. */
function patientStatusHtml(preview, medication) {
  var data = preview || {};
  var s = data.stat || {};
  /* 서버 파생이 있으면 복약지도 본문을 현황에 또 싣지 않는다 — 환자 `mapStat` 과 같다(KEY-365). */
  var body = data.stat || data.guide ? "" : medication;
  var drugName = data.stat ? s.drugName : body ? "복약 현황" : "";
  var hint = [data.visit ? data.visit + " 처방" : "", data.clinic].filter(Boolean).join(" · ");
  var html = hint ? '<div class="page-hint">' + esc(hint) + "</div>" : "";
  var card = "";
  if (drugName) card += '<div class="stat-drug-name">' + esc(drugName) + "</div>";
  if (s.drugSub) card += '<div class="stat-drug-sub">' + esc(s.drugSub) + "</div>";
  var parts = [];
  if (s.prescribed > 0) parts.push(s.prescribed + "일분");
  if (s.dayOn != null) parts.push(s.dayOn + "일째");
  if (s.remaining != null) parts.push(s.remaining + "일 남음");
  if (parts.length) card += '<div class="stat-progress-copy">' + esc(parts.join(" · ")) + "</div>";
  if (typeof s.pct === "number" && Number.isFinite(s.pct) && s.pct >= 0 && s.pct <= 100) {
    card +=
      '<div class="stat-bar-wrap" role="progressbar" aria-label="복약 진행률" aria-valuemin="0" aria-valuemax="100" aria-valuenow="' +
      s.pct + '"><span class="stat-bar-fill" style="width:' + s.pct + '%"></span></div>' +
      '<div class="stat-bar-pct">' + s.pct + "% 복용했어요</div>";
  } else if (s.prescribed === 0) {
    card += '<div class="stat-progress-empty">처방 일수가 없어 복약 기간을 표시하지 않아요.</div>';
  } else if (s.prescribed > 0) {
    card += '<div class="stat-progress-empty">복약 시작일이 없어 진행률과 남은 일수를 표시하지 않아요.</div>';
  }
  if (body && !s.why) card += '<div class="care-body-text">' + esc(body) + "</div>";
  if (!drugName && !body) card += patientEmptyHtml(PATIENT_EMPTY.medication);
  html += patientCardHtml("", card);
  if (s.out || s.why) {
    var pink = s.out ? '<div class="stat-out">' + esc(s.out) + "</div>" : "";
    if (s.why) pink += '<div class="stat-why">' + esc(s.why) + "</div>";
    pink += '<div class="stat-cta-note">재진 예약을 잡거나 병원에 문의해 주세요.</div>';
    html += patientCardHtml("", pink, "card--pink");
  }
  return html +
    '<button class="btn btn--full btn--accent" type="button" data-preview-tab="medication">복약지도 보기</button>';
}

function patientGuidePreviewHtml(sections, current, summary, preview) {
  var bodyOf = patientPreviewBodyOf(sections);
  var doc =
    '<!doctype html><meta charset="utf-8">' +
    '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">' +
    patientStylesheetLinks() +
    '<div class="app"><header class="header">' +
    patientTabBarHtml(current) +
    '</header><main class="body">' +
    patientPreviewBodyHtml(bodyOf, current, summary || "", preview) +
    "</main></div>";
  return (
    '<iframe class="pv" title="환자 화면 미리보기" aria-label="환자 화면 미리보기"' +
    ' data-patient-preview="' +
    esc(JSON.stringify({ sections: sections || [], summary: summary || "", preview: preview || null })) +
    '" sandbox="allow-same-origin" loading="lazy" srcdoc="' +
    doc.replace(/&/g, "&amp;").replace(/"/g, "&quot;") +
    '"></iframe>'
  );
}

/** 부모만 실행한다. 모든 진입점의 새 iframe load를 한 곳에서 받는다.
 * iframe 안에는 스크립트·환자 링크·읽음 기록 요청을 추가하지 않는다. */
document.addEventListener("load", function (event) {
  var frame = event.target;
  if (!frame || !frame.matches || !frame.matches("iframe[data-patient-preview]")) return;
  var doc = frame.contentDocument;
  if (!doc || doc.patientPreviewBound) return;
  doc.patientPreviewBound = true;
  var data = JSON.parse(frame.getAttribute("data-patient-preview"));
  doc.addEventListener("click", function (click) {
    var target = click.target.closest("[data-preview-tab], [data-preview-expand], [data-preview-axis]");
    if (!target) return;
    var tab = target.getAttribute("data-preview-tab");
    var axis = target.getAttribute("data-preview-axis");
    if (axis !== null) {
      doc.querySelector("main.body").innerHTML = patientPreviewBodyHtml(
        patientPreviewBodyOf(data.sections),
        "life",
        data.summary,
        data.preview,
        axis,
      );
      var chip = Array.prototype.find.call(doc.querySelectorAll("[data-preview-axis]"), function (button) {
        return button.getAttribute("data-preview-axis") === axis;
      });
      if (chip) chip.focus();
    } else if (tab) {
      doc.querySelectorAll('[role="tab"]').forEach(function (button) {
        var active = button.getAttribute("data-preview-tab") === tab;
        button.classList.toggle("tab-bar__btn--active", active);
        button.setAttribute("aria-selected", String(active));
      });
      var body = doc.querySelector("main.body");
      body.innerHTML = patientPreviewBodyHtml(patientPreviewBodyOf(data.sections), tab, data.summary, data.preview);
      body.scrollTop = 0;
      doc.querySelector('[role="tab"][aria-selected="true"]').focus();
    } else {
      var open = target.getAttribute("aria-expanded") !== "true";
      target.setAttribute("aria-expanded", String(open));
      target.classList.toggle("expand-btn--open", open);
      target.querySelector("span").textContent = open ? "접기" : "더 자세히 보기";
      target.nextElementSibling.classList.toggle("expand-body--open", open);
    }
  });
  // iframe에 포커스가 있어도 기존 부모 모달의 ESC 닫기 처리를 재사용한다.
  doc.addEventListener("keydown", function (key) {
    if (key.key === "Escape") {
      document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    }
  });
}, true);
