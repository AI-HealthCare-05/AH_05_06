/* S1-7 · S1-8 판독 결과 확인 — KEY-62
 *
 * 이 화면이 하는 일은 하나다. 「기계가 읽은 값」과 「그 값이 나온 원문」을
 * 나란히 놓아서, 스탭이 눈으로 대조할 수 있게 하는 것.
 *
 * 그래서 지키는 원칙 셋 —
 *   ① 못 읽은 값을 추측해서 채우지 않는다. 비워 두고 못 읽었다고 말한다.
 *   ② 값 옆에는 늘 출처가 붙는다. 누르면 그 원문 줄로 간다.
 *   ③ 같은 항목이 두 곳에 있으면 숨기지 않는다. 검사일이 최근인 쪽을
 *      먼저 쓰되, 다른 값이 있다는 사실은 보이게 둔다.
 *
 * 값을 고쳐 서버에 저장하는 것은 KEY-63 이다. 여기서 고른 후보는
 * 화면 안에만 남는다 — 아래 막대에 그렇게 적어 둔다.
 */

(function () {
  var docTabs = document.getElementById("doc-tabs");
  var rawBox = document.getElementById("raw");
  var fieldsBox = document.getElementById("fields");
  var summary = document.getElementById("summary");
  var stateBox = document.getElementById("state");
  var submit = document.getElementById("submit");
  var saveNote = document.getElementById("save-note");

  var JOB_ID = "ocr_synthetic_501";

  var result = null;
  var threshold = LOW_CONFIDENCE_FALLBACK;
  var activeDoc = null;
  var openCandidates = {};

  function escapeHtml(text) {
    return String(text).replace(/[&<>"]/g, function (ch) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[ch];
    });
  }

  function docById(id) {
    for (var i = 0; i < result.documents.length; i++) {
      if (result.documents[i].document_id === id) return result.documents[i];
    }
    return null;
  }

  function shortDate(iso) {
    return iso ? iso.slice(5).replace("-", "-") : "";
  }

  /* ── 왼쪽 · 원문 ───────────────────────────────────────────── */

  function renderDocTabs() {
    docTabs.innerHTML = result.documents
      .map(function (doc) {
        var on = doc.document_id === activeDoc ? " is-on" : "";
        return (
          '<button class="doc-tab' +
          on +
          '" type="button" data-doc="' +
          doc.document_id +
          '">' +
          escapeHtml(doc.label || doc.document_type) +
          "</button>"
        );
      })
      .join("");
  }

  function renderRaw(highlightLine) {
    var doc = docById(activeDoc);
    if (!doc) return;
    var lines = (doc.raw_text || "").split("\n");
    rawBox.innerHTML = lines
      .map(function (line, index) {
        var on = index === highlightLine ? " is-hit" : "";
        return '<div class="raw__line' + on + '" data-line="' + index + '">' + escapeHtml(line) + "</div>";
      })
      .join("");
    if (highlightLine === null || highlightLine === undefined) return;
    var hit = rawBox.querySelector(".raw__line.is-hit");
    if (hit) hit.scrollIntoView({ block: "center" });
  }

  /* 출처를 누르면 그 문서로 옮겨 가고 해당 줄에 표시가 붙는다.
     화면을 두 개 띄우지 않고 한 화면에서 대조하려는 것이 이 티켓의 전부다. */
  function jumpTo(documentId, line) {
    if (!documentId) return;
    activeDoc = documentId;
    renderDocTabs();
    renderRaw(typeof line === "number" ? line : null);
  }

  /* ── 오른쪽 · 구조화 필드 ──────────────────────────────────── */

  var STATE_TEXT = {
    missing: "⚠ 인식 실패",
    low: "⚠ 확인 필요",
    candidates: "값 2개",
  };

  function sourceChip(field) {
    var doc = docById(field.document_id);
    if (!doc) return "";
    var label = escapeHtml(doc.label || doc.document_type);
    return (
      '<button class="chip chip--src" type="button" data-jump="' +
      field.document_id +
      '" data-line="' +
      (field.source_line === undefined ? "" : field.source_line) +
      '">' +
      label +
      "</button>"
    );
  }

  function candidateRows(field) {
    return field.candidates
      .map(function (item) {
        var doc = docById(item.document_id);
        var where = doc ? doc.label || doc.document_type : "출처 미상";
        var mark = item.is_selected
          ? '<span class="cand__now">최근 값 · 사용 중</span>'
          : '<button class="cand__use" type="button" data-use="' +
            field.ocr_field_id +
            '" data-cand="' +
            item.ocr_field_candidate_id +
            '">이 값 사용</button>';
        return (
          '<div class="cand' +
          (item.is_selected ? " is-on" : "") +
          '">' +
          '<button class="chip chip--src" type="button" data-jump="' +
          item.document_id +
          '" data-line="' +
          item.source_line +
          '">' +
          escapeHtml(where) +
          " · " +
          escapeHtml(shortDate(item.source_date)) +
          "</button>" +
          '<span class="cand__value">' +
          escapeHtml(item.value) +
          " " +
          escapeHtml(field.unit || "") +
          "</span>" +
          mark +
          "</div>"
        );
      })
      .join("");
  }

  function renderField(field) {
    var state = field.pending_report ? "pending" : fieldState(field, threshold);
    var head =
      '<div class="field__name">' +
      escapeHtml(field.field_type) +
      (STATE_TEXT[state] ? ' <span class="field__tag field__tag--' + state + '">' + STATE_TEXT[state] + "</span>" : "") +
      "</div>";

    var body;
    if (state === "missing") {
      /* 빈 칸이 아니라 「못 읽었다」로 보여야 한다. 빈 칸은 안 읽은 것처럼 보인다. */
      body =
        '<div class="field__value field__value--missing">?</div>' +
        '<button class="field__act" type="button" data-fill="' +
        field.ocr_field_id +
        '">직접 입력</button>';
    } else if (state === "pending") {
      body =
        '<div class="field__value field__value--pending">' +
        escapeHtml(field.value) +
        "</div>" +
        '<span class="field__hint">별도 보고 검사</span>' +
        '<button class="field__act" type="button" data-keep="' +
        field.ocr_field_id +
        '">이전 값 유지</button>' +
        '<button class="field__act" type="button" data-skip="' +
        field.ocr_field_id +
        '">이번 미시행</button>';
    } else {
      body =
        '<div class="field__value">' +
        escapeHtml(field.value) +
        ' <span class="field__unit">' +
        escapeHtml(field.unit || "") +
        "</span></div>";
    }

    var tail = sourceChip(field);
    if (field.source_date) tail += '<span class="field__date">' + escapeHtml(shortDate(field.source_date)) + "</span>";

    var more = "";
    if (state === "candidates") {
      var open = !!openCandidates[field.ocr_field_id];
      more =
        '<button class="field__more" type="button" data-more="' +
        field.ocr_field_id +
        '">다른 값 보기 ' +
        (open ? "▴" : "▾") +
        "</button>" +
        (open
          ? '<div class="cands">' +
            candidateRows(field) +
            '<p class="cands__note">ⓘ 검사일이 최근인 쪽을 씁니다 · 바꾸면 기록에 남습니다</p></div>'
          : "");
    }

    return '<li class="field field--' + state + '">' + head + '<div class="field__row">' + body + tail + "</div>" + more + "</li>";
  }

  function renderFields() {
    fieldsBox.innerHTML = result.fields
      .map(function (field) {
        return renderField(field);
      })
      .join("");
  }

  /* 위에 몇 개를 봐야 하는지 먼저 말한다. 목록을 훑기 전에 알아야
     「다 맞다」와 「셋만 보면 된다」를 구분할 수 있다. */
  function renderSummary() {
    var counts = { missing: 0, low: 0, candidates: 0 };
    result.fields.forEach(function (field) {
      if (field.pending_report) return;
      var state = fieldState(field, threshold);
      if (counts[state] !== undefined) counts[state]++;
    });
    var total = counts.missing + counts.low + counts.candidates;
    var parts = [];
    if (counts.missing) parts.push("못 읽음 " + counts.missing);
    if (counts.candidates) parts.push("값 2개 " + counts.candidates);
    if (counts.low) parts.push("확인 필요 " + counts.low);

    summary.className = "summary" + (total ? " summary--warn" : " summary--ok");
    summary.textContent = total ? "확인할 항목 " + total + "개 — " + parts.join(" · ") : "모두 읽혔습니다";

    /* 못 읽은 값이 남아 있으면 안내문을 만들지 않는다.
       빈칸으로 만든 안내문은 환자에게 그대로 나간다. */
    submit.disabled = counts.missing > 0;
    submit.title = counts.missing ? "못 읽은 값을 채운 뒤 생성할 수 있습니다" : "";
  }

  /* ── 예외 ─────────────────────────────────────────────────── */

  function showState(html) {
    stateBox.innerHTML = html;
    stateBox.hidden = false;
    document.getElementById("work").hidden = true;
  }

  function showWork() {
    stateBox.hidden = true;
    document.getElementById("work").hidden = false;
  }

  function renderJobState(job) {
    if (job.status === "PROCESSING") {
      showState(
        '<p class="state__title">판독 중입니다</p>' +
          '<p class="state__body">' +
          job.progress +
          "% · 끝나면 이 화면이 저절로 바뀝니다</p>"
      );
      return false;
    }
    if (job.status === "FAILED") {
      /* 실패했다고 화면을 막지 않는다. 판독은 거들 뿐이고
         값은 사람이 직접 넣어도 진행할 수 있어야 한다. */
      showState(
        '<p class="state__title">판독하지 못했습니다</p>' +
          '<p class="state__body">사유 ' +
          escapeHtml(job.failure_code || "알 수 없음") +
          " · 값을 직접 입력하거나 다시 올릴 수 있습니다</p>" +
          '<div class="state__acts"><button class="button" type="button">직접 입력</button>' +
          '<button class="button button--ghost" type="button">재업로드</button></div>'
      );
      return false;
    }
    return true;
  }

  /* ── 이벤트 ───────────────────────────────────────────────── */

  document.addEventListener("click", function (event) {
    var jump = event.target.closest("[data-jump]");
    if (jump) {
      var line = jump.getAttribute("data-line");
      return jumpTo(Number(jump.getAttribute("data-jump")), line === "" ? null : Number(line));
    }

    var tab = event.target.closest(".doc-tab");
    if (tab) return jumpTo(Number(tab.getAttribute("data-doc")), null);

    var more = event.target.closest("[data-more]");
    if (more) {
      var id = Number(more.getAttribute("data-more"));
      openCandidates[id] = !openCandidates[id];
      return renderFields();
    }

    /* 안내문 생성은 KEY-64 다. 여기서 아무 반응이 없으면 스탭은
       버튼이 고장 난 줄 알고 계속 누른다 — 어디까지 됐는지 말해 준다. */
    if (event.target.id === "submit") {
      saveNote.textContent = "안내문 생성 연동은 KEY-64 입니다 — 이 화면에서는 값 확인까지만 합니다";
      saveNote.hidden = false;
      return;
    }

    var use = event.target.closest("[data-use]");
    if (use) {
      var fieldId = Number(use.getAttribute("data-use"));
      var candId = Number(use.getAttribute("data-cand"));
      result.fields.forEach(function (field) {
        if (field.ocr_field_id !== fieldId) return;
        field.candidates.forEach(function (item) {
          item.is_selected = item.ocr_field_candidate_id === candId;
          if (item.is_selected) field.value = item.value;
        });
      });
      renderFields();
      renderSummary();
      /* 저장은 KEY-63 이다. 여기서 조용히 넘어가면 스탭은 저장된 줄 안다. */
      saveNote.textContent = "고른 값은 아직 저장되지 않습니다 — 저장 연동은 KEY-63 입니다";
      saveNote.hidden = false;
      return;
    }
  });

  /* ── 시작 ─────────────────────────────────────────────────── */

  ocrApi
    .job(JOB_ID)
    .then(function (job) {
      if (!renderJobState(job)) return null;
      return ocrApi.result(JOB_ID);
    })
    .then(function (data) {
      if (!data) return;
      result = data;
      if (typeof result.low_confidence_threshold === "number") threshold = result.low_confidence_threshold;
      activeDoc = result.documents.length ? result.documents[0].document_id : null;
      showWork();
      renderDocTabs();
      renderRaw(null);
      renderFields();
      renderSummary();
    })
    .catch(function (error) {
      if (error && error.code === "OCR_RESULT_NOT_READY") {
        return showState('<p class="state__title">판독 결과가 아직 없습니다</p>');
      }
      showState(
        '<p class="state__title">결과를 불러오지 못했습니다</p><p class="state__body">잠시 뒤 다시 시도해 주세요</p>'
      );
    });
})();
