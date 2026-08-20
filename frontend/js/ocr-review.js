/* S1-7 · S1-8 판독 결과 확인 — KEY-62 (표시) · KEY-63 (수정·저장)
 *
 * 이 화면이 하는 일은 하나다. 「기계가 읽은 값」과 「그 값이 나온 원문」을
 * 나란히 놓아서, 스탭이 눈으로 대조하고 고칠 수 있게 하는 것.
 *
 * 그래서 지키는 원칙 넷 —
 *   ① 못 읽은 값을 추측해서 채우지 않는다. 비워 두고 못 읽었다고 말한다.
 *   ② 값 옆에는 늘 출처가 붙는다. 누르면 그 원문 줄로 간다.
 *   ③ 같은 항목이 두 곳에 있으면 숨기지 않는다. 검사일이 최근인 쪽을
 *      먼저 쓰되, 다른 값이 있다는 사실은 보이게 둔다.
 *   ④ 저장은 필드 하나씩이고, 결과를 반드시 말한다. 「저장했다」를
 *      말하지 않으면 스탭은 저장됐는지 확인하려고 새로고침을 한다.
 *
 * 동시 수정(KEY-63) — 접수대는 한 컴퓨터를 여럿이 쓴다. 내가 보던 사이
 * 옆자리가 같은 항목을 고쳤으면 서버가 409 로 막고, 이 화면은 앞사람 값을
 * 덮지 않는다. 대신 두 값을 나란히 보여 주고 사람이 고르게 한다 —
 * 내가 쓴 값을 지우지 않는 것이 이 처리의 핵심이다.
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

  /* 필드별 저장 상태. 화면 전체를 잠그지 않는다 — 한 항목을 저장하는 동안
     다른 항목은 계속 보고 고칠 수 있어야 한다. */
  var editing = {}; // 직접 입력 칸을 열어 둔 필드 — 값은 **지금 쳐 넣은 글자**다
  var saving = {}; // 저장 요청이 나가 있는 필드
  var saved = {}; // 방금 저장에 성공한 필드
  var failed = {}; // 저장이 실패한 필드 — { code, mine }
  var conflict = {}; // 409 — { mine, theirs }
  var focusOn = null; // 방금 연 입력칸. 다시 그린 뒤 여기로 커서를 돌려준다

  /* 칸이 열려 있는지는 **키가 있는지**로 본다. 값으로 보면 칸을 비웠을 때
     ""(falsy)가 되어 입력칸이 저 혼자 닫힌다 — 지우고 다시 치는 것이 값
     고치기의 절반이다. */
  function isEditing(id) {
    return Object.prototype.hasOwnProperty.call(editing, id);
  }

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

  function fieldById(id) {
    for (var i = 0; i < result.fields.length; i++) {
      if (result.fields[i].ocr_field_id === id) return result.fields[i];
    }
    return null;
  }

  /* `source_line` 은 계약에 없어서 목업이 얹은 값이다(PR 본문 §2) — 서버가
     무엇을 줄지 아직 안 정해졌다. 숫자로 못 읽히면 빈 칸으로 두고, 속성 안에
     날것으로 흘려보내지 않는다. */
  function lineAttr(value) {
    var n = Number(value);
    return value === null || value === undefined || value === "" || isNaN(n) ? "" : String(n);
  }

  function shortDate(iso) {
    return iso ? iso.slice(5) : "";
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

  var ERROR_TEXT = {
    EMPTY: "값을 입력해 주세요",
    OCR_FIELD_CONFIRMED: "이미 확정된 항목이라 고칠 수 없습니다",
    INVALID_CANDIDATE: "고른 후보가 이 항목의 값이 아닙니다",
    NOT_FOUND: "항목을 찾을 수 없습니다",
  };

  function sourceChip(field) {
    var doc = docById(field.document_id);
    if (!doc) return "";
    return (
      '<button class="chip chip--src" type="button" data-jump="' +
      field.document_id +
      '" data-line="' +
      lineAttr(field.source_line) +
      '">' +
      escapeHtml(doc.label || doc.document_type) +
      "</button>"
    );
  }

  function candidateRows(field) {
    return field.candidates
      .map(function (item) {
        var doc = docById(item.document_id);
        var where = doc ? doc.label || doc.document_type : "출처 미상";
        /* 기본값은 검사일이 최근인 rank 1 이지만, 사람이 바꾸면 「사용 중」이
           최근 값이 아니게 된다. 그때도 「최근 값」이라고 적으면 거짓말이 된다. */
        var mark = item.is_selected
          ? '<span class="cand__now">' + (item.rank === 1 ? "최근 값 · 사용 중" : "사용 중") + "</span>"
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
          lineAttr(item.source_line) +
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

  /* 옆자리가 먼저 고쳤을 때. 어느 쪽이 맞는지는 화면이 모른다 —
     두 값을 그대로 놓고 사람이 고르게 한다. 자동으로 하나를 고르면
     그게 무엇이든 누군가의 수정이 소리 없이 사라진다. */
  function conflictBox(field) {
    var clash = conflict[field.ocr_field_id];
    return (
      '<div class="clash">' +
      '<p class="clash__title">다른 사람이 먼저 고쳤습니다</p>' +
      '<div class="clash__row"><span class="clash__who">지금 저장된 값</span>' +
      "<b>" +
      escapeHtml(clash.theirs) +
      "</b>" +
      '<button class="field__act" type="button" data-drop="' +
      field.ocr_field_id +
      '">이 값 두기</button></div>' +
      '<div class="clash__row"><span class="clash__who">내가 쓴 값</span>' +
      "<b>" +
      escapeHtml(clash.mine) +
      "</b>" +
      '<button class="field__act" type="button" data-force="' +
      field.ocr_field_id +
      '">내 값으로 덮기</button></div>' +
      "</div>"
    );
  }

  function renderField(field) {
    var id = field.ocr_field_id;
    var state = field.pending_report ? "pending" : fieldState(field, threshold);
    var head =
      '<div class="field__name">' +
      escapeHtml(field.field_type) +
      (STATE_TEXT[state]
        ? ' <span class="field__tag field__tag--' + state + '">' + STATE_TEXT[state] + "</span>"
        : "") +
      (field.is_confirmed ? ' <span class="field__tag field__tag--locked">🔒 확정</span>' : "") +
      "</div>";

    var body;
    if (isEditing(id)) {
      body =
        '<input class="field__input" type="text" data-input="' +
        id +
        '" value="' +
        escapeHtml(editing[id]) +
        '" aria-label="' +
        escapeHtml(field.field_type) +
        ' 값 입력" />' +
        '<button class="field__act field__act--go" type="button" data-save="' +
        id +
        '">저장</button>' +
        '<button class="field__act" type="button" data-cancel="' +
        id +
        '">취소</button>';
    } else if (state === "missing") {
      /* 빈 칸이 아니라 「못 읽었다」로 보여야 한다. 빈 칸은 안 읽은 것처럼 보인다. */
      body =
        '<div class="field__value field__value--missing">?</div>' +
        '<button class="field__act" type="button" data-fill="' +
        id +
        '">직접 입력</button>';
    } else if (state === "pending") {
      /* 「이전 값 유지」·「이번 미시행」 버튼이 있었는데 처리기가 없어서 눌러도
         아무 일이 없었다. 둘 다 지금 계약으로는 못 짠다 — 앞 진료 값은 이
         화면에 없고, 「미시행」을 담을 칸이 PATCH 에 없다(KEY-109).

         눌러도 안 되는 버튼을 두느니 지운다. 대신 결과지를 손에 들고 있으면
         바로 넣을 수 있게 「직접 입력」은 남긴다 — 이건 실제로 저장된다. */
      body =
        '<div class="field__value field__value--pending">' +
        escapeHtml(field.value) +
        "</div>" +
        /* 값을 넣은 뒤에도 「결과가 나오면 넣으라」고 하면 이미 한 일을 또
           하라는 말이 된다. 넣기 전에만 안내한다. */
        '<span class="field__hint">' +
        (field.corrected_value === null || field.corrected_value === undefined
          ? "별도 보고 검사 — 결과가 나오면 여기에 넣습니다"
          : "별도 보고 검사") +
        "</span>" +
        '<button class="field__act" type="button" data-fill="' +
        id +
        '">직접 입력</button>';
    } else {
      body =
        '<div class="field__value">' +
        escapeHtml(field.value) +
        ' <span class="field__unit">' +
        escapeHtml(field.unit || "") +
        "</span></div>";
      if (!field.is_confirmed) {
        body += '<button class="field__act" type="button" data-fill="' + id + '">고치기</button>';
      }
    }

    var tail = isEditing(id) ? "" : sourceChip(field);
    if (field.source_date && !isEditing(id)) {
      tail += '<span class="field__date">' + escapeHtml(shortDate(field.source_date)) + "</span>";
    }
    /* 사람이 고친 값에는 그 사실이 남아야 한다. 판독값과 구별되지 않으면
       나중에 「기계가 이렇게 읽었다」와 「사람이 이렇게 고쳤다」를 못 가른다. */
    if (field.corrected_value !== null && field.corrected_value !== undefined) {
      tail += '<span class="field__edited">수정됨 · 판독값 ' + escapeHtml(field.extracted_value || "없음") + "</span>";
    }
    if (saving[id]) tail += '<span class="field__save">저장 중…</span>';
    if (saved[id]) tail += '<span class="field__save field__save--ok">저장됨</span>';
    if (failed[id]) {
      tail +=
        '<span class="field__save field__save--bad">' +
        escapeHtml(ERROR_TEXT[failed[id]] || "저장하지 못했습니다") +
        "</span>";
    }

    var more = "";
    if (state === "candidates" && !isEditing(id)) {
      var open = !!openCandidates[id];
      more =
        '<button class="field__more" type="button" data-more="' +
        id +
        '">다른 값 보기 ' +
        (open ? "▴" : "▾") +
        "</button>" +
        (open
          ? '<div class="cands">' +
            candidateRows(field) +
            '<p class="cands__note">ⓘ 검사일이 최근인 쪽을 씁니다 · 바꾸면 기록에 남습니다</p></div>'
          : "");
    }
    if (conflict[id]) more += conflictBox(field);

    return (
      '<li class="field field--' +
      state +
      (conflict[id] ? " field--clash" : "") +
      '">' +
      head +
      '<div class="field__row">' +
      body +
      tail +
      "</div>" +
      more +
      "</li>"
    );
  }

  /* 다시 그리면 `innerHTML` 이 통째로 바뀌어 커서와 캐럿이 사라진다. 저장
     타이머(2.5초)처럼 사람이 아무것도 안 눌러도 도는 길이 있어서, 치던
     자리를 안 챙기면 입력 도중에 커서가 튄다.

     첫 번째 입력칸을 잡으면 안 된다 — 두 칸이 열려 있을 때 나중에 연 칸에
     쓰려던 값이 먼저 연 칸에 들어간다. */
  function renderFields() {
    var active = document.activeElement;
    var typingIn =
      active && active.getAttribute && active.getAttribute("data-input") !== null
        ? Number(active.getAttribute("data-input"))
        : null;
    var caret = typingIn === null ? null : [active.selectionStart, active.selectionEnd];

    fieldsBox.innerHTML = result.fields
      .map(function (field) {
        return renderField(field);
      })
      .join("");

    /* 방금 「고치기」를 누른 칸이 먼저다. 치던 칸을 지키는 것보다 앞서야
       하는 이유는, 두 칸이 열려 있을 때 새로 연 칸으로 커서가 안 가면
       거기 쓰려던 숫자가 먼저 연 칸에 들어가기 때문이다. */
    var wanted = focusOn !== null ? focusOn : typingIn;
    focusOn = null;
    if (wanted === null) return;
    var box = fieldsBox.querySelector('[data-input="' + wanted + '"]');
    if (!box) return;
    box.focus();
    if (caret && typingIn === wanted) box.setSelectionRange(caret[0], caret[1]);
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

    var clashes = Object.keys(conflict).length;
    summary.className = "summary" + (total || clashes ? " summary--warn" : " summary--ok");
    if (clashes) {
      summary.textContent = "다른 사람이 먼저 고친 항목 " + clashes + "개 — 어느 값을 둘지 골라 주세요";
    } else {
      summary.textContent = total ? "확인할 항목 " + total + "개 — " + parts.join(" · ") : "모두 읽혔습니다";
    }

    /* 못 읽은 값이나 안 푼 충돌이 남아 있으면 안내문을 만들지 않는다.
       빈칸으로 만든 안내문은 환자에게 그대로 나간다. */
    submit.disabled = counts.missing > 0 || clashes > 0;
    submit.title = submit.disabled ? "못 읽은 값과 충돌을 정리한 뒤 생성할 수 있습니다" : "";
  }

  function redraw() {
    renderFields();
    renderSummary();
  }

  /* ── 저장 (KEY-63) ────────────────────────────────────────── */

  /* 서버가 돌려준 필드로 화면의 그 줄만 갈아 끼운다. 전체를 다시 부르지
     않는 이유는, 다른 항목을 고치던 중이면 그 입력이 사라지기 때문이다. */
  function replaceField(updated) {
    for (var i = 0; i < result.fields.length; i++) {
      if (result.fields[i].ocr_field_id !== updated.ocr_field_id) continue;
      var before = result.fields[i];
      for (var key in updated) before[key] = updated[key];
      return before;
    }
    return null;
  }

  function saveField(fieldId, body, mine) {
    var field = fieldById(fieldId);
    if (!field) return;
    delete failed[fieldId];
    delete conflict[fieldId];
    saving[fieldId] = true;
    redraw();

    body.base_version = field.version;
    ocrApi
      .updateField(fieldId, body)
      .then(function (updated) {
        delete saving[fieldId];
        delete editing[fieldId];
        replaceField(updated);
        saved[fieldId] = true;
        redraw();
        /* 「저장됨」은 잠깐만 둔다. 계속 붙어 있으면 다음에 볼 때
           방금 저장한 것인지 예전에 저장한 것인지 알 수 없다. */
        setTimeout(function () {
          delete saved[fieldId];
          redraw();
        }, 2500);
      })
      .catch(function (error) {
        delete saving[fieldId];
        var code = error && error.code;
        if (code === "VERSION_CONFLICT") return onConflict(fieldId, mine);
        failed[fieldId] = code || "unknown";
        redraw();
      });
  }

  /* 409 를 받으면 서버의 지금 값을 다시 읽어 와 내 값과 나란히 놓는다.
     계약에 단건 조회(GET /ocr/fields/{id})가 없어 목록을 다시 부른다. */
  function onConflict(fieldId, mine) {
    ocrApi
      .fields(JOB_ID)
      .then(function (fields) {
        var theirs = null;
        fields.forEach(function (item) {
          if (item.ocr_field_id === fieldId) theirs = item;
        });
        if (!theirs) {
          failed[fieldId] = "NOT_FOUND";
          return redraw();
        }
        replaceField(theirs);
        conflict[fieldId] = { mine: mine, theirs: theirs.value };
        delete editing[fieldId];
        redraw();
      })
      .catch(function () {
        failed[fieldId] = "unknown";
        redraw();
      });
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
          "% · 끝나면 이 화면이 저절로 바뀝니다</p>",
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
          '<button class="button button--ghost" type="button">재업로드</button></div>',
      );
      return false;
    }
    return true;
  }

  /* ── 이벤트 ───────────────────────────────────────────────── */

  function inputValue(fieldId) {
    var box = fieldsBox.querySelector('[data-input="' + fieldId + '"]');
    return box ? box.value.trim() : "";
  }

  document.addEventListener("click", function (event) {
    var target = event.target;

    if (target.id === "submit") {
      saveNote.textContent = "안내문 생성 연동은 KEY-64 입니다 — 이 화면에서는 값 확인까지만 합니다";
      saveNote.hidden = false;
      return;
    }

    var jump = target.closest("[data-jump]");
    if (jump) {
      var line = jump.getAttribute("data-line");
      return jumpTo(Number(jump.getAttribute("data-jump")), line === "" ? null : Number(line));
    }

    var tab = target.closest(".doc-tab");
    if (tab) return jumpTo(Number(tab.getAttribute("data-doc")), null);

    var more = target.closest("[data-more]");
    if (more) {
      var moreId = Number(more.getAttribute("data-more"));
      openCandidates[moreId] = !openCandidates[moreId];
      return redraw();
    }

    var fill = target.closest("[data-fill]");
    if (fill) {
      var fillId = Number(fill.getAttribute("data-fill"));
      var current = fieldById(fillId);
      /* 별도 보고 검사의 `value` 는 값이 아니라 「추후 보고 예정」이라는 안내다.
         그걸 채워 두면 결과지를 보고 치려는 사람이 먼저 지워야 한다. */
      var seed = current && !current.pending_report && current.value !== null && current.value !== undefined;
      editing[fillId] = seed ? String(current.value) : "";
      delete failed[fillId];
      focusOn = fillId; // 방금 연 칸으로 커서를 보낸다 — 첫 칸이 아니라
      return redraw();
    }

    var cancel = target.closest("[data-cancel]");
    if (cancel) {
      delete editing[Number(cancel.getAttribute("data-cancel"))];
      return redraw();
    }

    var save = target.closest("[data-save]");
    if (save) {
      var saveId = Number(save.getAttribute("data-save"));
      var typed = inputValue(saveId);
      /* 서버도 공백을 거부한다(#32). 요청을 보내 400 을 받느니 여기서 멈춘다. */
      if (!typed) {
        failed[saveId] = "EMPTY";
        return redraw();
      }
      return saveField(saveId, { corrected_value: typed }, typed);
    }

    var use = target.closest("[data-use]");
    if (use) {
      var useId = Number(use.getAttribute("data-use"));
      var candId = Number(use.getAttribute("data-cand"));
      var picked = null;
      var owner = fieldById(useId);
      if (owner) {
        owner.candidates.forEach(function (item) {
          if (item.ocr_field_candidate_id === candId) picked = item;
        });
      }
      return saveField(useId, { candidate_id: candId }, picked ? picked.value : "");
    }

    /* 충돌 정리 — 앞사람 값을 두거나, 내 값으로 덮는다.
       덮을 때는 방금 다시 읽어 온 판(version)을 base 로 보낸다. */
    var drop = target.closest("[data-drop]");
    if (drop) {
      delete conflict[Number(drop.getAttribute("data-drop"))];
      return redraw();
    }

    var force = target.closest("[data-force]");
    if (force) {
      var forceId = Number(force.getAttribute("data-force"));
      var mine = conflict[forceId] ? conflict[forceId].mine : "";
      delete conflict[forceId];
      return saveField(forceId, { corrected_value: mine }, mine);
    }
  });

  /* 친 글자를 `editing` 에 바로 옮겨 둔다.
     이게 없으면 `editing[id]` 는 「고치기를 누른 순간의 값」에 머무는데,
     다시 그릴 때 화면은 그 값으로 되돌아간다. 저장 타이머는 사람이
     아무것도 안 눌러도 도니까, 친 값이 저 혼자 사라지는 길이 된다.
     검사값 화면에서 제일 나쁜 것은 틀린 값이 조용히 저장되는 쪽이다. */
  document.addEventListener("input", function (event) {
    var box = event.target.getAttribute && event.target.getAttribute("data-input");
    if (box === null || box === undefined) return;
    editing[Number(box)] = event.target.value;
  });

  /* 값 하나 고치는 데 마우스를 두 번 쓰게 하지 않는다 */
  document.addEventListener("keydown", function (event) {
    var box = event.target.closest ? event.target.closest("[data-input]") : null;
    if (!box) return;
    var id = Number(box.getAttribute("data-input"));
    if (event.key === "Enter") {
      var typed = box.value.trim();
      if (!typed) {
        failed[id] = "EMPTY";
        return redraw();
      }
      saveField(id, { corrected_value: typed }, typed);
    }
    if (event.key === "Escape") {
      delete editing[id];
      redraw();
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
      redraw();
    })
    .catch(function (error) {
      if (error && error.code === "OCR_RESULT_NOT_READY") {
        return showState('<p class="state__title">판독 결과가 아직 없습니다</p>');
      }
      showState(
        '<p class="state__title">결과를 불러오지 못했습니다</p><p class="state__body">잠시 뒤 다시 시도해 주세요.</p>',
      );
    });
})();
