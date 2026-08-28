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

/* ── 화면과 무관한 규칙 ─────────────────────────────────────────────────
 *
 * 아래 둘은 DOM 을 모른다. IIFE **밖**에 두는 것은 검사가 부를 수 있게 하려는
 * 것이다 — 안에 두면 파일을 불러도 꺼낼 방법이 없다 (KEY-158).
 *
 * 그리는 함수는 옮기지 않는다. 그건 브라우저가 할 일이고, 껍데기로 흉내내면
 * 「검사에서는 되는데 화면에서는 안 되는」 거리가 벌어진다.
 */

/* 진료를 바꿀 때 **버려야 하는 것 전부**.
 *
 * 하나라도 남으면 앞 환자의 편집·충돌·저장 표시가 새 환자 줄에 붙는다.
 * 값을 세는 자리를 **한 곳**으로 모아 둔 것이 요점이다 — 상태 칸이 늘어날 때
 * 초기화를 잊는 것이 이 화면에서 제일 흔한 사고다(`#40` 리뷰).
 */
function blankReviewState() {
  return {
    result: null,
    activeDoc: null,
    threshold: LOW_CONFIDENCE_FALLBACK,
    openCandidates: {},
    editing: {}, // 직접 입력 칸을 열어 둔 필드 — 값은 **지금 쳐 넣은 글자**다
    saving: {}, // 저장 요청이 나가 있는 필드
    saved: {}, // 방금 저장에 성공한 필드
    failed: {}, // 저장이 실패한 필드 — { code, mine }
    conflict: {}, // 409 — { mine, theirs }
    focusOn: null, // 방금 연 입력칸. 다시 그린 뒤 여기로 커서를 돌려준다
    generating: false, // 안내문 생성 요청이 나가 있다 (KEY-204)
  };
}

/* 판독 작업 하나가 화면을 어디로 보내는가.
 *
 *   processing  아직이다. 기다리는 화면을 두고 다시 묻는다
 *   failed      못 읽었다. **막지 않는다** — 판독은 거들 뿐이고 재업로드로 푼다
 *   ready       읽었다. 결과 화면으로 넘어간다
 *
 * 「실패해도 막지 않는다」가 규칙의 핵심이라 `retryByReupload` 를 함께 준다.
 * 예전에는 눌러도 아무 일 없는 버튼이 둘 있었다(`#40` 리뷰).
 */
function jobPhase(job) {
  if (!job || !job.status) return { phase: "ready", showsWork: true, retryByReupload: false };
  if (job.status === "PROCESSING") return { phase: "processing", showsWork: false, retryByReupload: false };
  if (job.status === "FAILED") return { phase: "failed", showsWork: false, retryByReupload: true };
  return { phase: "ready", showsWork: true, retryByReupload: false };
}

/* 판독이 왜 실패했는지를 **스탭의 말**로 옮긴다 — KEY-126.
 *
 * 예전에는 `OCR_ENGINE_TIMEOUT` 을 그대로 보여 줬다. 기계 말이라 스탭이 이걸
 * 보고 내릴 수 있는 판단이 없고, 「내가 뭘 잘못했나」로 읽힌다.
 *
 * **코드 목록은 닫혀 있지 않다.** 서버의 `failure_code` 는 `CharField(64)` 라
 * 아무 값이나 올 수 있고, 실제 판독기는 아직 안 붙었다(KEY-56). 그래서 아는
 * 것만 옮기고 나머지를 코드로 흘리면 결국 원문이 보이는 화면이 남는다 —
 * **모르는 코드에도 사람 말을 준다.**
 *
 * 프런트가 이 표를 들고 있는 것이 근본은 아니다. 서버가 사유 문구를 함께 주는
 * 편이 맞고, 그건 판독기를 붙이는 KEY-56 이 정할 일이다 (이희진 님 `#121`
 * 리뷰). 그때까지의 임시 표다.
 */
var FAILURE_SAYINGS = [
  { code: "OCR_ENGINE_TIMEOUT", say: "판독이 정해진 시간 안에 끝나지 않았습니다." },
  { code: "OCR_ENGINE_ERROR", say: "판독기가 문서를 처리하지 못했습니다." },
  { code: "UNREADABLE", say: "문서의 글자를 알아볼 수 없었습니다." },
  { code: "CLOVA_API_ERROR", say: "판독 서버에 일시적인 문제가 있었습니다. 잠시 후 다시 올려 주세요." },
  { code: "OCR_NOT_CONFIGURED", say: "판독 서비스가 준비되지 않았습니다. 관리자에게 문의해 주세요." },
  { code: "FALLBACK_ERROR", say: "판독에 실패했습니다. 파일을 확인한 뒤 다시 올려 주세요." },
  { code: "NO_DOCUMENTS", say: "올라간 문서가 없습니다. 파일을 다시 올려 주세요." },
  { code: "PROCESSING_ERROR", say: "판독 처리 중 오류가 발생했습니다. 다시 올려 주세요." },
];

/* 왜 실패했는지와, 문의할 때 쓸 코드. **그것뿐이다.**
 *
 * 예전에는 title·next 까지 담아 매번 네 칸짜리 객체를 만들었는데, 그 둘은 어떤
 * 코드가 와도 같은 상수였다 (이희진 님 `#121` 리뷰). 부르는 쪽에 상수로 둔다. */
/* 생성 버튼을 잠글 것인가 — KEY-204.
 *
 * **`submit.disabled = true` 만 걸면 안 된다.** `renderSummary()` 가 매번
 * 이 값을 다시 쓰는데, 필드 하나를 저장하면 2.5 초 뒤 타이머가 `redraw()` 를
 * 불러 그 자리를 지난다. 그러면 요청이 아직 돌고 있는데 버튼이 조용히
 * 풀린다 — 두 번 눌리는 정확한 경로다.
 *
 * 그래서 잠금 여부를 **한 군데 규칙**으로 모으고 `renderSummary()` 가 이것을
 * 부르게 한다. 세 가지 중 하나라도 참이면 잠근다.
 *
 *     못 읽은 값이 남았다      빈칸으로 만든 안내문이 환자에게 그대로 나간다
 *     안 푼 충돌이 남았다      같다
 *     이미 요청이 나가 있다     두 번 만들면 409 가 나거나 두 건이 생긴다
 */
function generateBlocked(counts, clashes, generating) {
  var missing = counts && counts.missing ? counts.missing : 0;
  return missing > 0 || (clashes || 0) > 0 || generating === true;
}

/* 잠근 이유를 사람 말로 — 버튼 `title` 에 쓴다. 이유가 다르면 말도 달라야 한다. */
function generateBlockedSaying(counts, clashes, generating) {
  if (generating === true) return "안내문을 만드는 중입니다";
  if (generateBlocked(counts, clashes, false)) return "못 읽은 값과 충돌을 정리한 뒤 생성할 수 있습니다";
  return "";
}

/* 안내문 생성이 실패했을 때 화면에 뭐라고 쓸 것인가 — KEY-204.
 *
 * **서버 `message` 를 그대로 흘리지 않는다.** 그 자리에 OCR 원문이나 값이
 * 실릴 수 있고, 인수조건이 「오류 응답·로그에 OCR 원문·토큰·비밀값이
 * 노출되지 않는다」를 요구한다. 코드만 보고 우리 말로 갈아 끼운다.
 */
var GENERATE_SAYINGS = [
  { code: "OCR_NOT_CONFIRMED", say: "확정한 항목이 아직 없습니다 — 값을 확인해 저장한 뒤 다시 눌러 주세요" },
  { code: "VISIT_NOT_FOUND", say: "이 진료를 찾을 수 없습니다 — 목록에서 다시 골라 주세요" },
  { code: "FORBIDDEN", say: "안내문을 만들 권한이 없습니다" },
  { status: 401, say: "로그인이 풀렸습니다 — 다시 로그인해 주세요" },
  { status: 0, say: "서버에 닿지 못했습니다 — 잠시 뒤 다시 눌러 주세요" },
];

function generateFailureSaying(error) {
  return errorMessage(error, GENERATE_SAYINGS, "안내문을 만들지 못했습니다 — 잠시 뒤 다시 눌러 주세요");
}

/* `409 GUIDE_ALREADY_EXISTS` 는 **실패가 아니다.**
 *
 * 새로고침 뒤 다시 누르거나 두 사람이 같이 누르면 서버가 이것으로 막는다.
 * 화면이 이걸 빨간 오류로 보여 주면 스탭은 무엇이 잘못됐는지 찾게 되는데,
 * 실제로는 **원하던 것이 이미 있는 상태**다. 그래서 「있습니다」로 읽는다.
 */
function guideAlreadyThere(error) {
  return !!error && error.code === "GUIDE_ALREADY_EXISTS";
}

function failureSaying(code) {
  return {
    why: errorMessage({ code: code }, FAILURE_SAYINGS, "판독기가 문서를 읽지 못했습니다."),
    code: code || null,
  };
}

/* 화면 전체 상태의 **갈래**. 무게와 「다음 행동」이 여기서 함께 정해진다.
 *
 *   busy   도는 중이다. 기다리면 된다 — 사람이 할 일이 없다
 *   warn   멈췄다. **사람이 손대야 다음이 있다**
 *   info   그냥 알림
 *
 * `#121` 리뷰에서 이 둘이 어긋나 있던 것이 잡혔다.
 *
 *   `not_ready`   busy 로 그렸는데 폴링이 재시작되지 않아 **영영 기다린다**
 *   `poll_failed` warn 인데 누를 것이 없어 **화면에 갇힌다**
 *
 * 그래서 규칙을 하나로 못 박는다 — **warn 이면 반드시 다음 행동이 있다.**
 * 아래 `stateRules()` 를 검사가 그 불변식으로 잰다.
 *
 * 자동 재시도는 넣지 않았다. 지금 판독 작업은 AI 워커가 안 붙어 `PROCESSING`
 * 에서 못 벗어나는데(KEY-148 검수 문서), 자동으로 계속 돌면 **영원히 돌면서
 * 문제를 감춘다.** 「다시 확인」을 사람이 누르는 편이 정직하다.
 */
var STATE_RULES = {
  loading: { tone: "busy", action: null },
  processing: { tone: "busy", action: null },
  no_job: { tone: "info", action: null },
  job_failed: { tone: "warn", action: "reupload" },
  not_ready: { tone: "warn", action: "recheck" },
  poll_failed: { tone: "warn", action: "recheck" },
  result_failed: { tone: "warn", action: "recheck" },
};

function stateRules() {
  return STATE_RULES;
}

function stateRule(kind) {
  return STATE_RULES[kind] || { tone: "info", action: null };
}

function stateTakesFocus(tone) {
  return tone === "warn";
}

(function () {
  /* **자기 칸이 없는 페이지에서는 아무것도 하지 않는다.** 이 파일은
     `ocr-review.html` 에만 실린다. 뿌리가 없으면 조용히 돌아간다 — 위 순수
     규칙은 그대로 남아서 검사가 부를 수 있다 (KEY-158). */
  if (!document.getElementById("fields")) return;

  var docTabs = document.getElementById("doc-tabs");
  var rawBox = document.getElementById("raw");
  var fieldsBox = document.getElementById("fields");
  var summary = document.getElementById("summary");
  var stateBox = document.getElementById("state");
  var submit = document.getElementById("submit");
  var saveNote = document.getElementById("save-note");

  /* 왼쪽에서 고른 진료가 이 화면의 주인이다. 예전에는 `JOB_ID` 가 고정값이라
     어느 환자를 골라도 같은 판독 결과가 떴다 — **다른 환자의 의료정보를
     고칠 수 있는 상태**였다 (`#40` 리뷰). */
  /* 판독은 보통 수십 초다. 1.5초는 사람이 「멈췄나」 싶기 전이고 서버에도 가볍다. */
  var POLL_MS = 1500;

  var visit = null;
  var jobId = null;

  /* 진료를 바꾸면 앞의 요청이 아직 날아오고 있다. 그 응답이 새 화면을 덮으면
     또 남의 값이 뜬다. 세대를 세어 **지금 것만** 그린다 —
     `doctor.js` 의 `loadSeq` 와 같은 장치다. */
  var loadSeq = 0;
  var pollTimer = null;

  /* 상태 칸의 **처음 값도** `blankReviewState()` 에서 받는다. 선언과 초기화가
     따로 놀면 「새로 열었을 때」와 「환자를 바꿨을 때」가 달라진다. */
  var view = blankReviewState();
  var result = view.result;
  var threshold = view.threshold;
  var activeDoc = view.activeDoc;
  var openCandidates = view.openCandidates;

  /* 필드별 저장 상태. 화면 전체를 잠그지 않는다 — 한 항목을 저장하는 동안
     다른 항목은 계속 보고 고칠 수 있어야 한다. */
  var editing = view.editing;
  var saving = view.saving;
  var saved = view.saved;
  var failed = view.failed;
  var conflict = view.conflict;
  var focusOn = view.focusOn;
  var generating = view.generating; // 안내문 생성 요청이 나가 있다 (KEY-204)

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
    skipped: "이번 미시행",
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
    /* 사람이 「이번엔 안 했다」고 한 것이 맨 앞이다. 기계가 못 읽었든 문서가
       「추후 보고 예정」이라 했든, **사람이 그 위에서 판정한 것**이라 그 말이
       이긴다 — `docs/api/hospital.md` §4 (판독 항목의 상태 어휘). */
    var state =
      field.field_status === "NOT_PERFORMED"
        ? "skipped"
        : field.pending_report
          ? "pending"
          : fieldState(field, threshold);
    var head =
      '<div class="field__name">' +
      escapeHtml(field.field_type) +
      (STATE_TEXT[state]
        ? ' <span class="field__tag field__tag--' + state + '">' + STATE_TEXT[state] + "</span>"
        : "") +
      (field.is_confirmed ? ' <span class="field__tag field__tag--locked">🔒 확정</span>' : "") +
      "</div>";

    /* 확정된 값은 아무 데서도 못 고친다. 예전에는 이 검사가 **정상 상태의
       「고치기」에만** 걸려 있어서, 확정됐는데 못 읽은 항목이면 「직접 입력」이,
       후보가 여럿이면 「이 값 사용」이 그대로 떴다 (`#40` 리뷰).
       상태별로 다시 챙기면 또 빠뜨린다 — 맨 위에서 한 번에 가른다. */
    var locked = !!field.is_confirmed;

    var body;
    if (locked) {
      body =
        '<div class="field__value">' +
        escapeHtml(field.value === null || field.value === undefined ? "?" : field.value) +
        ' <span class="field__unit">' +
        escapeHtml(field.unit || "") +
        "</span></div>";
    } else if (isEditing(id)) {
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
        '">직접 입력</button>' +
        /* **여기가 「이번 미시행」이 가장 필요한 자리다.**

           기계는 「못 읽었다」와 「그 줄이 아예 없다」를 구별하지 못한다. 문서를
           눈으로 보는 사람만 안다. 구별이 없으면 이 항목이 「확인할 항목」에
           남아 **안내문 생성이 영영 막힌다** — 안 한 검사를 채울 방법은 없다.

           별도 보고 검사(`pending`)에도 같은 버튼을 두지만 그쪽은 이미 셈에서
           빠져 있어 표시만 바뀐다. 막힌 것을 푸는 것은 이 자리다. */
        '<button class="field__act field__act--quiet" type="button" data-skip="' +
        id +
        '">이번 미시행</button>';
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
        '">직접 입력</button>' +
        /* 「이번 미시행」을 되살린다. **「값이 없다」와 「안 했다」는 다르다** —
           앞은 채워야 하고 뒤는 비어 있는 게 맞다. 구별이 없으면 이 항목이
           「확인할 항목」에 영원히 남아 안내문 생성이 막힌다.

           「이전 값 유지」는 되살리지 않는다. 앞 진료 값을 이번 자리에 복사하면
           **옛 측정치가 이번 측정치로 읽힌다** — 안내문이 그 자리를 「지금」이라
           말한다. 안 하기로 정했다(계약 §3). */
        '<button class="field__act field__act--quiet" type="button" data-skip="' +
        id +
        '">이번 미시행</button>';
    } else if (state === "skipped") {
      body =
        '<div class="field__value field__value--pending">이번엔 검사하지 않았습니다</div>' +
        '<span class="field__hint">안내문에서 빠집니다</span>' +
        /* 잘못 눌렀을 때 빠져나갈 길을 둔다. 없으면 스탭은 판독을 새로 올린다. */
        '<button class="field__act field__act--quiet" type="button" data-unskip="' +
        id +
        '">되돌리기</button>';
    } else {
      body =
        '<div class="field__value">' +
        escapeHtml(field.value) +
        ' <span class="field__unit">' +
        escapeHtml(field.unit || "") +
        "</span></div>";
      body += '<button class="field__act" type="button" data-fill="' + id + '">고치기</button>';
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
    if (state === "candidates" && !isEditing(id) && !locked) {
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
      /* 확정된 항목은 더 볼 것이 없다 — 못 읽었든 후보가 여럿이든, 이미
         끝난 항목을 「확인할 항목」에 넣으면 고칠 방법이 없는데도 생성이
         막힌 채로 남는다 (`renderField()` 의 `locked` 와 같은 이유). */
      /* 「안 했다」고 표시한 항목도 뺀다. 비어 있는 게 맞는 것을 세면 스탭이
         할 일이 없는데도 생성이 막힌 채로 남는다 (`pending_report` 와 같은 이유). */
      if (field.is_confirmed || field.pending_report || field.field_status === "NOT_PERFORMED") return;
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
       빈칸으로 만든 안내문은 환자에게 그대로 나간다.

       **생성 중인지도 함께 본다** (KEY-204). 여기서 안 보면, 요청이 도는 사이
       필드 저장 타이머가 이 줄을 다시 지나며 버튼을 조용히 풀어 준다. */
    submit.disabled = generateBlocked(counts, clashes, generating);
    submit.title = generateBlockedSaying(counts, clashes, generating);
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

    /* 저장이 오가는 동안 진료를 바꾸면 `resetState()` 가 `result` 를 지운다.
       그 뒤에 이 응답이 와도 그리면 안 된다 — 다른 진료의 화면에 이 필드를
       끼워 넣거나, `result` 가 비어 있어 그 자리에서 죽는다. 로드와 같은
       세대(`loadSeq`)를 찍어 두고 늦게 와도 버린다. */
    var seq = loadSeq;
    body.base_version = field.version;
    ocrApi
      .updateField(fieldId, body)
      .then(function (updated) {
        if (seq !== loadSeq) return;
        delete saving[fieldId];
        delete editing[fieldId];
        replaceField(updated);
        saved[fieldId] = true;
        redraw();
        /* 「저장됨」은 잠깐만 둔다. 계속 붙어 있으면 다음에 볼 때
           방금 저장한 것인지 예전에 저장한 것인지 알 수 없다. */
        setTimeout(function () {
          if (seq !== loadSeq) return;
          delete saved[fieldId];
          redraw();
        }, 2500);
      })
      .catch(function (error) {
        if (seq !== loadSeq) return;
        delete saving[fieldId];
        var code = error && error.code;
        if (code === "VERSION_CONFLICT") return onConflict(fieldId, mine, body);
        failed[fieldId] = code || "unknown";
        redraw();
      });
  }

  /* 409 를 받으면 서버의 지금 값을 다시 읽어 와 내 값과 나란히 놓는다.
     계약에 단건 조회(GET /ocr/fields/{id})가 없어 목록을 다시 부른다. */
  /* `body` 를 함께 들고 있는 이유 — 「내 값으로 덮기」가 **원래 보낸 것과 같은
     종류**로 다시 보내야 하기 때문이다. 예전에는 무조건 `corrected_value` 로
     다시 보냈는데, 「이번 미시행」처럼 값이 아니라 상태를 바꾸는 요청이 충돌하면
     보낼 값이 없어 `undefined` 가 그대로 나갔다(이희진 님 `#81` 리뷰). */
  function onConflict(fieldId, mine, body) {
    var seq = loadSeq;
    ocrApi
      .fields(jobId)
      .then(function (fields) {
        if (seq !== loadSeq) return;
        var theirs = null;
        fields.forEach(function (item) {
          if (item.ocr_field_id === fieldId) theirs = item;
        });
        if (!theirs) {
          failed[fieldId] = "NOT_FOUND";
          return redraw();
        }
        replaceField(theirs);
        conflict[fieldId] = { mine: mine, theirs: theirs.value, body: body };
        delete editing[fieldId];
        redraw();
      })
      .catch(function () {
        if (seq !== loadSeq) return;
        failed[fieldId] = "unknown";
        redraw();
      });
  }

  /* ── 예외 ─────────────────────────────────────────────────── */

  /* 방금 그린 **갈래**. 같은 갈래를 다시 그릴 때 초점을 또 뺏지 않으려고 둔다 —
     판독 중에는 되묻기가 반복해서 이 함수를 부른다.

     예전에는 `무게 + "|" + html` 을 통째로 키로 썼다. 그런데 그건 「같은 warn 이
     연달아 두 번 그려지는 경로가 지금 없다」는 **우연**에 기댄 것이지 코드가
     보장하는 불변식이 아니었다 (이희진 님 `#121` 리뷰). 갈래로 비교한다. */
  var shownKind = null;

  function actionHtml(action) {
    if (action === "reupload") return '<button class="button" type="button" id="reupload">재업로드</button>';
    /* 「다시 확인」은 `loadVisit()` 을 다시 탄다 — 환자를 다시 고른 것과 같은
       길이다. 작업을 다시 묻고, 아직 도는 중이면 폴링에 다시 들어간다. */
    if (action === "recheck") return '<button class="button" type="button" id="recheck">다시 확인</button>';
    return "";
  }

  /* 갈래 하나를 그린다. **무게와 다음 행동은 규칙이 정한다** — 부르는 쪽이
     고르지 않는다. 그래야 「warn 인데 누를 것이 없는」 화면이 안 생긴다. */
  function showState(kind, body) {
    var rule = stateRule(kind);
    var acts = actionHtml(rule.action);

    stateBox.className = "state state--" + rule.tone;
    stateBox.innerHTML = body + (acts ? '<div class="state__acts">' + acts + "</div>" : "");
    stateBox.hidden = false;
    document.getElementById("work").hidden = true;

    if (shownKind !== kind) {
      /* 진행률이 바뀔 때마다 읽어 주면 수십 초짜리 판독에서 20~40 번을 연달아
         듣는다 — 이 화면이 고치려던 것과 반대다 (이희진 님 `#121` 리뷰).
         그래서 소리로 알리는 것은 **갈래가 바뀔 때뿐**이다. */
      say(stateBox.querySelector(".state__title"));
      if (stateTakesFocus(rule.tone)) {
        /* 손대야 다음이 있는 상태다. 키보드로 일하는 사람을 여기로 데려온다. */
        stateBox.focus();
      }
    }
    shownKind = kind;
  }

  /* 소리로만 읽히는 한 줄. 화면 전체를 라이브 리전으로 두면 진행률·탭 이동까지
     전부 읽힌다. */
  function say(titleNode) {
    var box = document.getElementById("state-say");
    if (box) box.textContent = titleNode ? titleNode.textContent : "";
  }

  function showWork() {
    stateBox.hidden = true;
    shownKind = null;
    document.getElementById("work").hidden = false;
  }

  function renderJobState(job) {
    var phase = jobPhase(job).phase;
    if (phase === "processing") {
      /* 숫자만 있으면 **멈춘 건지 도는 건지** 알 수 없다. 막대를 함께 준다.
         움직임은 `--motion` 을 타므로 「움직임 줄이기」를 켠 사람에게는
         멈춰 있는 막대만 남는다 (tokens.css). */
      showState(
        "processing",
        '<p class="state__title">판독 중입니다</p>' +
          '<div class="bar bar--pulse"><div class="bar__fill" style="width:' +
          Math.max(0, Math.min(100, Number(job.progress) || 0)) +
          '%"></div></div>' +
          '<p class="state__body">' +
          escapeHtml(String(job.progress)) +
          "% · 끝나면 이 화면이 저절로 바뀝니다</p>",
      );
      return false;
    }
    if (phase === "failed") {
      /* 실패했다고 화면을 막지 않는다. 판독은 거들 뿐이고
         값은 사람이 직접 넣어도 진행할 수 있어야 한다. */
      /* 예전에는 「직접 입력」·「재업로드」 둘 다 식별자도 처리기도 없어서
         눌러도 아무 일이 없었다 (`#40` 리뷰).

         「직접 입력」은 지금 계약으로 못 짠다 — 작업이 FAILED 면 결과가 없고,
         결과가 없으면 채워 넣을 항목 목록 자체가 없다. 빈 항목을 만들어 주는
         길이 계약에 없다(KEY-109 에 적는다). 눌러도 안 되는 버튼을 두느니
         지운다 — 이 파일이 「이전 값 유지」·「이번 미시행」에 한 것과 같다.

         「재업로드」는 지금 된다. 이 진료의 진료기록 칸으로 돌려보낸다. */
      var saying = failureSaying(job.failure_code);
      showState(
        "job_failed",
        '<p class="state__title">판독하지 못했습니다</p>' +
          '<p class="state__body">' +
          escapeHtml(saying.why) +
          " 진료기록을 다시 올리면 판독을 다시 시작합니다.</p>" +
          (saying.code
            ? '<p class="state__code">문의할 때 알려 주세요 · ' + escapeHtml(saying.code) + "</p>"
            : ""),
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

    /* 판독 실패에서 빠져나가는 유일한 길. 이 진료의 진료기록 칸으로 보낸다. */
    /* 막다른 상태에서 빠져나오는 길. 환자를 다시 고른 것과 같은 경로다 —
       작업을 다시 묻고, 아직 도는 중이면 폴링에 다시 들어간다. */
    if (target.id === "recheck") {
      if (visit) loadVisit(visit);
      return;
    }

    if (target.id === "reupload") {
      if (!visit) return;
      location.href = "/patients.html?visit=" + encodeURIComponent(visit.visit_id) + "&tab=record";
      return;
    }


    if (target.id === "submit") {
      /* KEY-204 — 여기서 안내문을 만든다.

         **`visit_id` 를 지금 붙잡는다.** 응답이 오는 사이 사람이 왼쪽 목록에서
         다른 진료를 고르면 모듈 지역 `visit` 이 바뀐다. 그러면 A 를 눌러 놓고
         B 의 안내문을 만든 것처럼 보이게 된다 — `doctor.js` 가 승인에서 같은
         이유로 `approvingId` 를 따로 잡는다. */
      if (!visit || !visit.visit_id) return;
      var wantedId = visit.visit_id;
      var mine = loadSeq;

      if (generating) return; // 이미 나가 있다
      generating = true;
      redraw(); // 버튼을 잠근다 — 잠금은 renderSummary 가 규칙으로 계산한다

      saveNote.textContent = "안내문을 만드는 중입니다…";
      saveNote.hidden = false;

      ocrApi
        .generateGuide(wantedId)
        .then(function () {
          /* 늦게 온 응답은 버린다. 이미 다른 진료를 보고 있다면 이 소식은
             지금 화면과 무관하다 — 이 파일이 판독 폴링에서 쓰는 규율과 같다. */
          if (mine !== loadSeq) return;
          generating = false;
          redraw();
          saveNote.textContent = "안내문을 만들었습니다 — 의사 승인 화면에서 이어서 보실 수 있습니다";
          saveNote.hidden = false;
        })
        .catch(function (error) {
          if (mine !== loadSeq) return;
          generating = false;
          redraw();

          /* 409 는 실패가 아니다. 새로고침 뒤 다시 눌렀거나 두 사람이 같이
             누른 것이고, **원하던 것은 이미 있다.** 빨간 오류로 보여 주면
             스탭이 없는 문제를 찾게 된다. */
          saveNote.textContent = guideAlreadyThere(error)
            ? "이 진료의 안내문은 이미 있습니다 — 의사 승인 화면에서 보실 수 있습니다"
            : generateFailureSaying(error);
          saveNote.hidden = false;
        });
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

    var skip = target.closest("[data-skip]");
    if (skip) {
      var skipId = Number(skip.getAttribute("data-skip"));
      delete editing[skipId]; // 열어 두고 눌렀으면 그 칸은 닫는다
      saveField(skipId, { field_status: "NOT_PERFORMED" }, "이번 미시행");
      return;
    }

    var unskip = target.closest("[data-unskip]");
    if (unskip) {
      saveField(Number(unskip.getAttribute("data-unskip")), { field_status: "READ" }, "되돌리기");
      return;
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
      var clash = conflict[forceId];
      /* 충돌 기록이 없으면 보낼 것도 없다. 예전에는 이때 `corrected_value: ""`
         가 나갔다 — 빈 값으로 덮어쓰는 셈이다. */
      if (!clash) return;
      delete conflict[forceId];
      return saveField(forceId, clash.body, clash.mine);
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

  /* ── 진료 갈아 끼우기 ─────────────────────────────────────── */

  /* 화면에 남아 있던 것을 전부 버린다. 하나라도 남으면 앞 환자의 편집·충돌·
     저장 표시가 새 환자 줄에 붙는다. */
  function resetState() {
    if (pollTimer) {
      clearTimeout(pollTimer);
      pollTimer = null;
    }
    /* **한 곳에서 받아 온다.** 여기에 손으로 나열하면 상태 칸이 늘 때
       하나를 빠뜨리고, 그 하나가 앞 환자의 표시로 남는다. */
    var blank = blankReviewState();
    result = blank.result;
    activeDoc = blank.activeDoc;
    threshold = blank.threshold;
    openCandidates = blank.openCandidates;
    editing = blank.editing;
    saving = blank.saving;
    saved = blank.saved;
    failed = blank.failed;
    conflict = blank.conflict;
    focusOn = blank.focusOn;
      generating = blank.generating;
    fieldsBox.innerHTML = "";
    rawBox.innerHTML = "";
    docTabs.innerHTML = "";
    summary.textContent = "—";
    if (saveNote) saveNote.textContent = "";
    if (submit) submit.disabled = true;
  }

  /* 진료 객체는 평평하다 — 목록이 내주는 그 모양 그대로 쓴다
     (`patients-api.js`: name · hospital_patient_no · birth_date · doctor …). */
  function renderPatientHead(next) {
    var name = document.getElementById("p-name");
    var chart = document.getElementById("p-id");
    var line = document.getElementById("p-visit");
    if (name) name.textContent = next.name || "—";
    if (chart) {
      chart.textContent = [
        next.hospital_patient_no ? "차트 " + next.hospital_patient_no : "",
        next.birth_date || "",
        next.age ? next.age + "세" : "",
      ]
        .filter(Boolean)
        .join(" · ");
    }
    if (line) {
      line.textContent = [
        next.diagnosis_name,
        next.doctor && next.doctor.name,
        next.visited_at ? shortDate(next.visited_at) : "",
      ]
        .filter(Boolean)
        .join(" · ");
    }
  }

  /* 판독 중이면 끝날 때까지 되묻는다. 화면이 「저절로 바뀝니다」라고 말하는데
     아무것도 안 하고 있었다 (`#40` 리뷰). 진료를 바꾸면 `resetState()` 가 끈다. */
  function pollJob(mine) {
    pollTimer = setTimeout(function () {
      if (mine !== loadSeq) return;
      ocrApi
        .job(jobId)
        .then(function (job) {
          if (mine !== loadSeq) return;
          if (job.status === "PROCESSING") {
            renderJobState(job);
            return pollJob(mine);
          }
          if (!renderJobState(job)) return;
          return loadResult(mine);
        })
        .catch(function () {
          if (mine !== loadSeq) return;
          showState(
            "poll_failed",
            '<p class="state__title">판독 상태를 확인하지 못했습니다</p>' +
              '<p class="state__body">연결이 끊겼을 수 있습니다. 다시 확인해 주세요.</p>',
          );
        });
    }, POLL_MS);
  }

  function loadResult(mine) {
    return ocrApi
      .result(jobId)
      .then(function (data) {
        if (mine !== loadSeq) return;
        result = data;
        if (typeof result.low_confidence_threshold === "number") threshold = result.low_confidence_threshold;
        activeDoc = result.documents.length ? result.documents[0].document_id : null;
        showWork();
        renderDocTabs();
        renderRaw(null);
        redraw();
      })
      .catch(function (error) {
        if (mine !== loadSeq) return;
        if (error && error.code === "OCR_RESULT_NOT_READY") {
          return showState(
            "not_ready",
            '<p class="state__title">판독 결과가 아직 없습니다</p>' +
              '<p class="state__body">판독은 끝났다고 하는데 결과가 아직 안 왔습니다. 다시 확인해 주세요.</p>',
          );
        }
        showState(
          "result_failed",
          '<p class="state__title">결과를 불러오지 못했습니다</p><p class="state__body">다시 확인해 주세요.</p>',
        );
      });
  }

  function loadVisit(next) {
    resetState();
    visit = next;
    jobId = null;
    var mine = ++loadSeq;
    renderPatientHead(next);
    showState("loading", '<p class="state__title">판독 결과를 불러오는 중…</p>');

    ocrApi
      .jobForVisit(next.visit_id)
      .then(function (link) {
        if (mine !== loadSeq) return null;
        jobId = link.ocr_job_id;
        return ocrApi.job(jobId);
      })
      .then(function (job) {
        if (mine !== loadSeq || !job) return null;
        if (job.status === "PROCESSING") {
          renderJobState(job);
          return pollJob(mine);
        }
        if (!renderJobState(job)) return null;
        return loadResult(mine);
      })
      .catch(function (error) {
        if (mine !== loadSeq) return;
        if (error && error.code === "NOT_FOUND") {
          return showState(
            "no_job",
            '<p class="state__title">판독한 기록이 없습니다</p>' +
              '<p class="state__body">진료기록을 올리면 판독이 시작됩니다.</p>',
          );
        }
        showState(
          "result_failed",
          '<p class="state__title">결과를 불러오지 못했습니다</p><p class="state__body">다시 확인해 주세요.</p>',
        );
      });
  }

  /* ── 시작 ─────────────────────────────────────────────────── */

  document.addEventListener("visit:selected", function (event) {
    if (event.detail) loadVisit(event.detail);
  });
})();
