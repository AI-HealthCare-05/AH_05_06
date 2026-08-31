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
  { code: "REQUIRED_FIELD_MISSING", say: "필수 항목(진단·약품명·처방일수)을 읽지 못했습니다. 직접 입력하거나 파일을 다시 올려 주세요." },
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
  /* **못 읽은 값은 길을 막지 않는다** — 와이어프레임 S1-7.
   *
   * 전에는 `counts.missing > 0` 이면 버튼을 잠갔다. 그런데 S1-7 은 「못 읽은
   * 항목이 있을 때」를 그린 프레임이고, 거기서 「확인 완료 · 안내문 생성」은
   * **살아 있는 색**이다. 흐름 줄도 「못 읽은 값 없이 생성」이라 적는다.
   * 프레임 캡션이 못 박는다 — 「그 줄만 점선 + ? · 다른 줄과 확인 항목은
   * 그대로다 — 추측해서 채우지 않는다」. 한 줄이 실패해도 화면 전체를 막지
   * 않는다는 뜻이다.
   *
   * 잠가 두면 어떻게 되는지는 이미 봤다. 못 읽은 값을 푸는 유일한 길이었던
   * 「이번 미시행」은 서버에 `field_status` 가 없어 실서버에서 버튼조차 안
   * 그려진다 — 잠긴 채로 남는다. 1차 시연이 멈춘 것과 같은 모양이다.
   *
   * 충돌(같은 항목이 두 곳에 있음)은 그대로 막는다. 그건 **어느 값이 맞는지
   * 사람이 골라야** 하는 것이라, 고르지 않고 만들면 둘 중 아무거나 실린다. */
  return (clashes || 0) > 0 || generating === true;
}

/* 잠근 이유를 사람 말로 — 버튼 `title` 에 쓴다. 이유가 다르면 말도 달라야 한다. */
function generateBlockedSaying(counts, clashes, generating) {
  if (generating === true) return "안내문을 만드는 중입니다";
  if ((clashes || 0) > 0) return "같은 항목이 두 곳에 있습니다 — 어느 값을 쓸지 골라 주세요";
  return "";
}

/* 못 읽은 값이 남았는데 그냥 만들려 할 때 한 번 알린다. 막지는 않는다 —
   묻지도 않고 만들면 스탭은 빠진 줄을 못 보고 넘어간다. */
function missingSaying(counts) {
  var missing = counts && counts.missing ? counts.missing : 0;
  return missing > 0 ? "못 읽은 값 " + missing + "개는 빈 채로 만듭니다" : "";
}

/* **「확인 완료」를 누를 때 서버로 확정을 보낼 항목** — 와이어프레임 `S1-6`.
 *
 * 그 화면의 버튼은 「확인 완료 · 안내문 생성」 하나다. 확정과 생성이 한 동작이다.
 * 그런데 화면이 `confirm` 을 한 번도 안 보내고 있었고, 서버는 확정된 항목이
 * 하나도 없으면 생성을 422 `OCR_NOT_CONFIRMED` 로 막는다
 * (`app/services/guides.py`). 그래서 **실서버에서는 안내문이 한 번도 안 만들어졌다.**
 *
 * 이미 확정된 항목은 뺀다 — 다시 보내면 409 `OCR_FIELD_CONFIRMED` 다.
 * 값이 없는 항목도 뺀다. 못 읽은 칸을 확정하면 빈 값이 안내문에 그대로 나간다
 * (생성 버튼도 같은 이유로 `counts.missing` 을 보고 잠근다).
 */
function fieldsToConfirm(fields) {
  var out = [];
  for (var i = 0; i < (fields || []).length; i++) {
    var field = fields[i];
    if (!field || field.is_confirmed) continue;
    if (field.value === null || field.value === undefined || field.value === "") continue;
    out.push(field);
  }
  return out;
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
  /* 확정을 먼저 보내므로 저장 쪽 오류도 이 자리로 온다. 「안내문을 만들지
     못했습니다」로만 말하면 스탭이 값을 다시 볼 생각을 못 한다. */
  { code: "VERSION_CONFLICT", say: "그 사이 값이 바뀌었습니다 — 화면을 새로 고쳐 확인해 주세요" },
  { code: "OCR_FIELD_CONFIRMED", say: "이미 확정된 항목이 있습니다 — 화면을 새로 고쳐 주세요" },
  { status: 401, say: "로그인이 풀렸습니다 — 다시 로그인해 주세요" },
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
/* 늦게 온 결과를 지금 화면에 써도 되는가 — 이희진 님 `#162` ③.
 *
 * 처음에는 세대 번호(`loadSeq`)로 갈랐다. 그러면 A 에서 누르고 B 로 갔다가
 * **다시 A 로 돌아오면** 세대가 달라져 결과를 버린다. 안내문은 실제로
 * 만들어졌는데 화면은 아무 말이 없고, 사람은 다시 눌러 409 를 받아야 안다.
 *
 * 물어야 할 것은 「같은 세대인가」가 아니라 **「지금 보고 있는 진료가 그것인가」**다.
 * `doctor.js` 가 승인에서 `approvingId` 로 하는 것과 같은 뜻이다 — 붙잡은
 * 대상에 결과를 붙이지, 화면의 판 번호에 붙이지 않는다.
 */
/* 이 응답이 **지금 잠금을 쥔 요청**의 것인가 — 이희진 님 `KEY-210`.
 *
 * `#162` 에서 잠금 푸는 줄을 가림막 앞으로 옮겼는데, 그러면 **늦게 온 옛 응답이
 * 새 요청의 잠금까지 푼다.** A 에서 누르고 → B 로 갔다 → A 로 돌아와 → 다시
 * 누르면, 첫 응답이 도착하는 순간 두 번째가 아직 나가 있는데도 버튼이 열린다.
 * 이희진 님이 그 자리를 짚어 티켓으로 냈다.
 *
 * 세대 번호를 하나 더 둔다. **화면 세대(`loadSeq`)가 아니라 요청 세대다** —
 * 물어야 할 것이 「지금 어느 화면인가」가 아니라 「지금 나가 있는 요청이
 * 무엇인가」이기 때문이다.
 */
function generateLockIsMine(mySeq, latestSeq) {
  return mySeq === latestSeq;
}

function outcomeBelongsToScreen(wantedId, shownVisit) {
  return !!shownVisit && shownVisit.visit_id === wantedId;
}

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
/* `keepsWork` — 이 상태에서 **아래 작업 칸을 그대로 두는가.**
 *
 * 판독이 실패해도 화면을 덮지 않는다. 값은 사람이 눈으로 읽어 넣어도 되고,
 * 덮어 버리면 그 길이 막힌다 — 사진은 멀쩡한데 표 한 칸을 못 읽어서 화면이
 * 통째로 막히던 것이 1차 시연이 멈춘 방식이다.
 *
 * 나머지는 덮는다. 아래에 보여 줄 것이 아직 없거나(판독 중 · 결과 없음),
 * 무엇이 맞는지 화면이 모르는 상태(결과를 못 불러옴)라, 반쯤 그린 값을
 * 보여 주면 그것을 판독 결과로 읽는다. */
var STATE_RULES = {
  loading: { tone: "busy", action: null, keepsWork: false },
  processing: { tone: "busy", action: null, keepsWork: false },
  no_job: { tone: "info", action: null, keepsWork: false },
  job_failed: { tone: "warn", action: "reupload", keepsWork: true },
  not_ready: { tone: "warn", action: "recheck", keepsWork: false },
  poll_failed: { tone: "warn", action: "recheck", keepsWork: false },
  result_failed: { tone: "warn", action: "recheck", keepsWork: false },
};

function stateRules() {
  return STATE_RULES;
}

function stateRule(kind) {
  return STATE_RULES[kind] || { tone: "info", action: null, keepsWork: false };
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

  /* 안내문 생성 요청의 세대. 화면 세대와 따로 센다 (KEY-210). */
  var generateSeq = 0;
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
  /* 판독이 못 찾아 서버에 줄이 없는 항목을 스탭이 눈으로 읽어 적은 값.
     **화면 안에만 있다** — 보낼 자리가 없다 (`js/ocr-groups.js` 의 localSaying). */
  var local = {};
  var localEditing = null;

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

  /* `2026-08-31T17:04:42+09:00` → `08-31`.
     `slice(5)` 만 하면 시각까지 통째로 남아 머리말이 「박연 ·
     08-31T17:04:42+09:00」로 떴다. 진료 머리말에서 궁금한 것은 날짜다. */
  function shortDate(iso) {
    var m = /^\d{4}-(\d{2}-\d{2})/.exec(String(iso || ""));
    return m ? m[1] : "";
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
          /* 올린 차례로 번호를 매긴다 — 종류는 짐작이라 틀리면 값보다
             이름을 먼저 의심하게 된다 (`js/ocr-groups.js` 의 documentName). */
          escapeHtml(documentName(result.documents, doc.document_id)) +
          "</button>"
        );
      })
      .join("");
  }

  function renderRaw(highlightLine) {
    var doc = docById(activeDoc);
    if (!doc) return;

    /* 지금 보고 있는 것이 몇 번째 이미지인지 — 값 옆 출처 배지와 같은 이름을
       써야 눌러서 옮겨 온 뒤에 제대로 왔는지 알 수 있다. */
    var note = document.getElementById("raw-note");
    if (note) note.textContent = rawTextNote(result.documents, activeDoc);

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
      escapeHtml(documentName(result.documents, field.document_id)) +
      "</button>"
    );
  }

  function candidateRows(field) {
    return field.candidates
      .map(function (item) {
        var where = documentName(result.documents, item.document_id) || "출처 미상";
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
      /* 서버 코드를 사람 말로 — 전에는 「MEDICATION_NAME」이 그대로 떴다.
         이름표는 `js/field-labels.js` 가 갖는다 (WP-S③ 공용 모듈). */
      escapeHtml(fieldLabel(field.field_type)) +
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
        /* 화면 읽기 프로그램도 사람 말을 들어야 한다 — 전에는
           「MEDICATION_NAME 값 입력」이라 읽혔다. */
        escapeHtml(fieldLabel(field.field_type)) +
        ' 값 입력" />' +
        '<button class="field__act field__act--go" type="button" data-save="' +
        id +
        '">저장</button>' +
        '<button class="field__act" type="button" data-cancel="' +
        id +
        '">취소</button>';
    } else if (field.is_absent && localEditing === field.field_type) {
      /* 적는 중. 「저장」이라 쓰지 않는다 — 서버로 안 가는데 저장이라고
         하면 남았다고 믿는다. 「확인」은 이 화면에서 값을 굳힌다는 뜻이고,
         남지 않는다는 것은 아래 「저장 안 됨」 배지가 말한다. */
      body =
        '<input class="field__input" type="text" data-local-input="' +
        escapeHtml(field.field_type) +
        '" value="' +
        escapeHtml(local[field.field_type] || "") +
        '" aria-label="' +
        escapeHtml(fieldLabel(field.field_type)) +
        ' 값 적기" />' +
        '<button class="field__act field__act--go" type="button" data-local-keep="' +
        escapeHtml(field.field_type) +
        '">확인</button>' +
        '<button class="field__act" type="button" data-local-cancel="1">취소</button>';
    } else if (field.is_absent && local[field.field_type]) {
      /* 적어 둔 값. **저장된 척하지 않는다** — 배지로 못 박는다. */
      body =
        '<div class="field__value field__value--local">' +
        escapeHtml(local[field.field_type]) +
        "</div>" +
        '<span class="field__unit">' +
        escapeHtml(fieldUnit(field.field_type, "")) +
        "</span>" +
        '<span class="field__tag field__tag--local">저장 안 됨</span>' +
        '<button class="field__act" type="button" data-local-fill="' +
        escapeHtml(field.field_type) +
        '">고치기</button>';
    } else if (state === "missing" && field.is_absent) {
      /* **서버가 이 항목의 줄을 아예 안 만들었다.**
       *
       * 판독이 찾지 못한 항목은 레코드로 남지 않는다 (화면 지도의 S1-7 걸림돌).
       * 그래서 고칠 대상이 없고, 「직접 입력」을 눌러도 보낼 곳이 없다 —
       * 값을 새로 만드는 자리(POST)가 아직 없다.
       *
       * 그래도 **줄은 세운다.** 안 세우면 스탭 눈에는 「그 항목이 없는 진료」로
       * 보이고 빠진 채로 안내문이 만들어진다. 자리는 있고, 왜 지금 못 채우는지
       * 를 말한다 — 눌러도 아무 일 없는 버튼을 두는 것보다 낫다. */
      body =
        '<div class="field__value field__value--missing">?</div>' +
        '<button class="field__act" type="button" data-local-fill="' +
        escapeHtml(field.field_type) +
        '">직접 입력</button>' +
        '<span class="field__hint">판독 실패</span>';
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

    /* **몸통을 따로 꺼낼 수 있게 둔다.** 맨 위 진단·처방 줄이 같은 몸통을
       가로로 세우는데(`topRowHtml`), 거기서 다시 그리면 「고치기」·「직접
       입력」·충돌 처리가 두 벌이 되어 한쪽만 고쳐진다. */
    lastBody = {
      state: state,
      clash: !!conflict[id],
      body: '<div class="field__row">' + body + tail + "</div>" + more,
    };

    return (
      '<li class="field field--' +
      state +
      (conflict[id] ? " field--clash" : "") +
      '">' +
      head +
      lastBody.body +
      "</li>"
    );
  }

  /* `renderField` 가 방금 만든 몸통. 가로줄이 그것만 꺼내 쓴다 —
     함수를 둘로 쪼개는 것보다 부르는 자리가 적어 어긋날 여지가 없다. */
  var lastBody = null;

  function fieldBody(field) {
    renderField(field);
    return lastBody;
  }

  /* ── 맨 위 진단 · 처방 줄 (와이어프레임 S1-6) ────────────────────────
   *
   * 「진단 [자궁내막증] · 처방 [비잔 2mg · 계속] [84] 일」.
   *
   * 여기 서는 셋은 **서버가 필수로 보는 셋과 같다** —
   * `ocr_task.py` 의 `_REQUIRED_OCR_FIELDS = {DIAGNOSIS, MEDICATION_NAME,
   * DURATION_DAYS}`. 이 셋이 없으면 판독 작업 자체가 실패하고, 안내문도
   * 「무슨 약을 며칠」을 못 쓴다. 그래서 맨 위에 크게 세운다.
   *
   * 와이어프레임은 처방 칸에 「비잔 2mg · 계속」처럼 약과 용량을 붙여 놓는데,
   * 그건 처방 세트를 목록에서 고르는 설계라 그렇다. 우리는 판독이 항목별로
   * 따로 주므로 **붙이지 않는다** — 붙여 놓고 아래에 1회량을 또 세우면 같은
   * 값이 두 번 보이고, 어느 쪽을 고쳐야 하는지 묻게 된다. */
  var TOP_ROW = [
    { type: "DIAGNOSIS", label: "진단", wide: false },
    /* 와이어프레임 S1-6 의 이름표가 「처방」이다 — 스탭이 EMR 에서 옮겨 적는
       칸의 이름과 맞춘다. 항목 이름(`fieldLabel`)은 「약품명」 그대로 두고
       이 자리의 이름표만 바꾼다: 아래 값 줄에서는 「약품명」이 맞다. */
    { type: "MEDICATION_NAME", label: "처방", wide: true },
    { type: "DURATION_DAYS", label: "처방일수", unit: "일", wide: false },
  ];

  function topRowHtml(rows) {
    var cells = TOP_ROW.map(function (spec) {
      var field = null;
      for (var i = 0; i < rows.length; i++) {
        if (rows[i].field_type === spec.type) field = rows[i];
      }
      if (!field) return "";

      var made = fieldBody(field);
      return (
        '<div class="top__cell' +
        (spec.wide ? " top__cell--wide" : "") +
        (made.clash ? " field--clash" : "") +
        '">' +
        '<span class="top__label">' +
        escapeHtml(spec.label) +
        "</span>" +
        '<div class="field field--' +
        made.state +
        '">' +
        made.body +
        "</div>" +
        "</div>" +
        (spec.unit ? '<span class="top__unit">' + escapeHtml(spec.unit) + "</span>" : "")
      );
    }).join("");

    return cells ? '<div class="top">' + cells + "</div>" : "";
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

    fieldsBox.innerHTML = groupsHtml();

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

  /* ── 오른쪽 블록 넷 (와이어프레임 S1-6) ──────────────────────────────
   *
   * 서버는 값을 한 줄로 준다. 가르는 규칙은 `js/ocr-groups.js` 가 갖는다 —
   * 검사가 닿아야 해서 IIFE 밖이다.
   *
   * ①은 안내문의 뼈대(무슨 약을 며칠)고 ②는 참고값이다. 한 줄로 두면 스탭이
   * 「처방일수 84」와 「혈색소 10.2」를 같은 무게로 훑는다. 84가 틀리면
   * 환자가 약을 잘못 먹는다.
   *
   * 와이어프레임은 구획을 가로줄로 나누지만 우리는 **블록**으로 세운다 —
   * 기본정보(S1-4)와 같은 상자다. 안의 치수는 원문 그대로. */
  function groupsHtml() {
    var split = splitFields(result.fields);
    /* 처방 여섯은 판독이 못 읽어도 자리에 세운다 — 안내문이 그것으로
       만들어져서, 화면에서 사라지면 빠진 채로 만들어진다 (S1-7). */
    var rx = withMissingRows(split.prescription, PRESCRIPTION_CORE);
    /* 검사값도 자리를 세운다 — 안 세우면 못 읽은 것과 안 한 것을 구별할 수 없다 */
    var labs = withMissingRows(split.labs, LAB_CORE);
    return prescriptionHtml(rx) + labsHtml(labs) + notReadyHtml();
  }

  /* ① 진단 · 처방 */
  function prescriptionHtml(rows) {
    if (!rows.length) return "";

    var days = fieldValueOf(result.fields, "DURATION_DAYS");
    var start = fieldValueOf(result.fields, "PRESCRIPTION_DATE");
    var until = runOutDate(start, days);
    var warn = courseWarn(days);

    var meta = [];
    if (start) meta.push("처방일 " + escapeHtml(shortDate(start)));
    /* 소진 예정일은 서버 값이 아니라 처방일 + 처방일수다. 계산한 값이라고
       밝힌다 — 판독한 값처럼 보이면 스탭이 원문에서 찾으려 든다. */
    if (until) meta.push("소진 예정일 " + escapeHtml(shortDate(until)) + " (계산)");

    /* 맨 위 셋은 가로로, 나머지는 아래에 줄로. 같은 값을 두 번 세우지 않는다. */
    var topTypes = TOP_ROW.map(function (spec) {
      return spec.type;
    });
    var rest = rows.filter(function (field) {
      return topTypes.indexOf(field.field_type) === -1;
    });

    return (
      '<section class="box"><div class="box__head">' +
      '<h2 class="box__title">진단 · 처방</h2>' +
      (warn ? '<span class="box__warn">ⓘ ' + escapeHtml(warn) + "</span>" : "") +
      "</div>" +
      topRowHtml(rows) +
      (meta.length ? '<p class="box__meta box__meta--top">' + meta.join(" · ") + "</p>" : "") +
      (rest.length ? '<div class="rows">' + rest.map(renderField).join("") + "</div>" : "") +
      "</section>"
    );
  }

  /* ② 이번 판독 값 — 검사일은 값 줄이 아니라 블록 머리에 붙는다 */
  function labsHtml(rows) {
    if (!rows.length) return "";
    var on = labDateOf(result.fields);

    return (
      '<section class="box"><div class="box__head">' +
      '<h2 class="box__title">이번 판독 값</h2>' +
      (on ? '<span class="box__note">검사일 ' + escapeHtml(shortDate(on)) + "</span>" : "") +
      "</div>" +
      '<div class="rows">' +
      rows.map(renderField).join("") +
      "</div></section>"
    );
  }

  /* ③④ 아직 서버에 자리가 없는 블록.
   *
   * **눌러도 아무 일 없는 버튼을 두지 않는다** — 그 자리에 무엇이 없는지 쓴다.
   * 목업 값을 채워 두면 되는 것처럼 보이고, 그게 1차 시연이 멈춘 방식이다. */
  function notReadyHtml() {
    return GROUPS_WITHOUT_SERVER.map(function (group) {
      return (
        '<section class="box box--waiting"><div class="box__head">' +
        '<h2 class="box__title">' +
        escapeHtml(group.title) +
        "</h2>" +
        '<span class="box__note">' +
        escapeHtml(group.note) +
        "</span></div>" +
        (group.key === "checks" ? checkListHtml() : "") +
        '<p class="box__soon">' +
        escapeHtml(group.saying) +
        "</p></section>"
      );
    }).join("");
  }

  /* ④ 확인 항목의 **모양**을 세운다 — 와이어프레임 S1-6.
   *
   * 항목은 처방에 따라 달라지고 그것을 주는 자리가 아직 없다. 그런데 자리만
   * 비워 두면 이 블록이 무엇이 될지가 안 보이고, 판독 API 를 붙이는 사람이
   * 무엇을 만들어야 하는지도 안 보인다.
   *
   * 그래서 **꺼진 채로** 세운다. 켤 수 있게 두면 스탭이 「우울증 병력」을
   * 체크하고 저장됐다고 믿는데 아무 데도 안 남는다 — 안전에 걸리는 항목이라
   * 그 오해가 가장 나쁘다. 눌리지 않고, 왜 아직 안 눌리는지 아래 줄이 말한다. */
  function checkListHtml() {
    return (
      '<ul class="checks" aria-label="확인 항목 (아직 저장되지 않습니다)">' +
      CHECK_ITEMS.map(function (item) {
        return (
          '<li class="checks__item"><label class="checks__label">' +
          '<input type="checkbox" disabled />' +
          escapeHtml(item) +
          "</label></li>"
        );
      }).join("") +
      "</ul>"
    );
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

    /* **할 일이 없으면 안 뜬다.** 「모두 읽혔습니다」는 판을 차지하면서 아무
       일도 안 시킨다 — 값이 다 읽힌 것은 아래 블록을 보면 안다. 손봐야 하는
       것이 있을 때만 뜨고, 그때는 눈에 걸려야 한다. */
    summary.hidden = !(total || clashes);
    summary.className = "summary summary--warn";
    if (clashes) {
      summary.textContent = "다른 사람이 먼저 고친 항목 " + clashes + "개 — 어느 값을 둘지 골라 주세요";
    } else if (total) {
      summary.textContent = "확인할 항목 " + total + "개 — " + parts.join(" · ");
    } else {
      summary.textContent = "";
    }

    /* 못 읽은 값이나 안 푼 충돌이 남아 있으면 안내문을 만들지 않는다.
       빈칸으로 만든 안내문은 환자에게 그대로 나간다.

       **생성 중인지도 함께 본다** (KEY-204). 여기서 안 보면, 요청이 도는 사이
       필드 저장 타이머가 이 줄을 다시 지나며 버튼을 조용히 풀어 준다. */
    /* 판독 값이 하나도 없으면 서버가 422 로 되돌린다 — 미리 잠그고 왜인지
       적는다. 그대로 두면 「내가 뭘 잘못했나」로 읽힌다. */
    var noFields = noFieldsSaying(result.fields);
    submit.disabled = !!noFields || generateBlocked(counts, clashes, generating);
    submit.title = noFields || generateBlockedSaying(counts, clashes, generating);

    /* **막지 않고 알린다.** 적어 넣은 값은 서버에 없어서 안내문에 안 실리는데,
       말 안 하면 스탭은 실린 줄 안다. 막으면 화면이 거기서 끝나므로, 무슨
       일이 일어날지만 정확히 적는다 (`missingSaying` 과 같은 판단). */
    var localNote = localSaying(local);
    saveNote.hidden = !localNote;
    if (localNote) saveNote.textContent = localNote;
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

  /* **화면에 뜬 값을 한꺼번에 확정한다** — 「확인 완료」의 실제 동작.
     항목마다 `PATCH` 를 보내고 돌아온 것으로 그 줄을 갈아 끼운다. 하나라도
     실패하면 그 오류를 그대로 올려 보낸다 — 생성으로 넘어가면 안 된다.
     확정이 반쯤 된 채로 안내문이 만들어지면 무엇이 굳었는지 알 수 없다. */
  function confirmShownFields() {
    var targets = fieldsToConfirm(result && result.fields);
    if (!targets.length) return Promise.resolve();

    var sending = [];
    for (var i = 0; i < targets.length; i++) {
      sending.push(
        ocrApi
          .updateField(targets[i].ocr_field_id, {
            base_version: targets[i].version,
            confirm: true,
          })
          .then(replaceField),
      );
    }
    return Promise.all(sending);
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

    stateBox.className = "state state--" + rule.tone + (rule.keepsWork ? " state--strip" : "");
    stateBox.innerHTML = body + (acts ? '<div class="state__acts">' + acts + "</div>" : "");
    stateBox.hidden = false;
    /* **덮을 것과 위에 붙을 것을 가른다** (`STATE_RULES` 의 `keepsWork`). */
    document.getElementById("work").hidden = !rule.keepsWork;

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
      /* **실패해도 화면을 덮지 않는다.**
       *
       * 예전에는 이 자리가 화면 전체를 막았고, 「직접 입력」은 짤 수가 없었다 —
       * 작업이 FAILED 면 결과가 없고, 결과가 없으면 채워 넣을 항목 목록 자체가
       * 없었기 때문이다.
       *
       * 이제는 그 목록을 **화면이 안다** (`PRESCRIPTION_CORE` — 서버가 필수로
       * 보는 셋과 같다). 빈 프레임을 세우면 스탭이 눈으로 읽은 값을 적을 수
       * 있다. 판독은 거들 뿐이고, 못 읽었다고 진료가 멈추면 안 된다.
       *
       * 특히 `REQUIRED_FIELD_MISSING` 이 그렇다 — 워커의 필수 필드 게이트가
       * 진단·약품명·처방일수 중 하나라도 못 읽으면 **저장 앞에서 돌아선다**
       * (`ocr_task.py` Phase 2). 사진은 멀쩡한데 표 한 칸을 못 읽어서 화면이
       * 통째로 막히던 것이 1차 시연이 멈춘 방식이다.
       *
       * 「재업로드」는 그대로 둔다. 사진이 흐린 것이 원인일 때가 많다. */
      var saying = failureSaying(job.failure_code);

      /* 결과가 없으니 빈 것을 세운다 — 프레임은 값 없이도 서야 한다 */
      if (!result) result = { ocr_result_id: null, documents: [], fields: [] };

      showState(
        "job_failed",
        '<p class="state__title">판독하지 못했습니다</p>' +
          '<p class="state__body">' +
          escapeHtml(saying.why) +
          " 아래에서 직접 적거나, 진료기록을 다시 올리면 판독을 다시 시작합니다.</p>" +
          (saying.code
            ? '<p class="state__code">문의할 때 알려 주세요 · ' + escapeHtml(saying.code) + "</p>"
            : ""),
      );
      redraw();
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

    /* 「판독 결과 확인」 — 판독을 서버에서 다시 불러온다.
       사진을 더 올리면 판독이 다시 도는데, 언제 끝나는지는 화면이 모른다.
       올린 뒤 자동으로 한 번 부르지만(`send` 의 loadVisit), 그 사이에 끝난
       것을 스탭이 직접 확인할 길도 있어야 한다 — 새로고침하면 화면을 벗어난다. */
    if (target.id === "reread") {
      if (visit) loadVisit(visit);
      return;
    }

    /* ── 화면에서 직접 적기 ─────────────────────────────────────────
       판독이 못 찾아 서버에 줄이 없는 항목. 보낼 자리가 없어 화면 안에만
       둔다 — 저장된 척하지 않고, 안내문에 안 실린다는 것을 아래에 적는다. */
    var fill = target.getAttribute && target.getAttribute("data-local-fill");
    if (fill) {
      localEditing = fill;
      redraw();
      var box = fieldsBox.querySelector('[data-local-input="' + fill + '"]');
      if (box) box.focus();
      return;
    }

    var keep = target.getAttribute && target.getAttribute("data-local-keep");
    if (keep) {
      var input = fieldsBox.querySelector('[data-local-input="' + keep + '"]');
      var typed = input ? String(input.value || "").trim() : "";
      if (typed) local[keep] = typed;
      else delete local[keep]; /* 비우면 지운다 — 빈 값을 「적었다」로 세지 않는다 */
      localEditing = null;
      redraw();
      return;
    }

    if (target.getAttribute && target.getAttribute("data-local-cancel")) {
      localEditing = null;
      redraw();
      return;
    }

    /* 판독 실패 상태 상자의 「재업로드」. 왼쪽 판의 「진료기록 추가」와 같은
       일을 하되, 실패 화면에서는 `#work` 가 숨겨져 그 판이 안 보인다. */
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

      if (generating) return; // 이미 나가 있다
      generating = true;
      var mySeq = ++generateSeq; // 이 잠금은 내 것이다
      redraw(); // 버튼을 잠근다 — 잠금은 renderSummary 가 규칙으로 계산한다

      saveNote.textContent = "안내문을 만드는 중입니다…";
      saveNote.hidden = false;

      /* **확정을 먼저 보내고 생성한다.** 버튼이 「확인 완료 · 안내문 생성」인
         이유다 — 스탭이 화면의 값을 다 봤다는 뜻이므로, 그 값을 확정으로
         굳힌 뒤에 만든다. 확정이 실패하면 생성으로 넘어가지 않는다. */
      confirmShownFields()
        .then(function () {
          return ocrApi.generateGuide(wantedId);
        })
        .then(function () {
          /* **내가 쥔 잠금일 때만 푼다.** 늦게 온 옛 응답이 새 요청의 잠금을
             풀면, 나가 있는 요청이 있는데도 버튼이 열린다 (KEY-210). */
          var lockIsMine = generateLockIsMine(mySeq, generateSeq);
          if (lockIsMine) generating = false;

          /* 화면에 쓰는 것은 **내가 최신 요청이고, 그 진료를 보고 있을 때만.**
             다른 진료로 갔다면 무관하고, 돌아왔다면 여전히 관계있다. */
          if (!lockIsMine || !outcomeBelongsToScreen(wantedId, visit)) return;
          redraw();
          saveNote.textContent = "안내문을 만들었습니다 — 의사 승인 화면에서 이어서 보실 수 있습니다";
          saveNote.hidden = false;
        })
        .catch(function (error) {
          var lockIsMine = generateLockIsMine(mySeq, generateSeq);
          if (lockIsMine) generating = false;
          if (!lockIsMine || !outcomeBelongsToScreen(wantedId, visit)) return;
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
  /* ── 여기서 바로 올린다 ──────────────────────────────────────────────
   *
   * 판독을 보다가 「사진이 흐려서 못 읽었구나」를 알게 되는데, 그때 업로드
   * 화면으로 갔다 오면 보던 값을 잃는다. 접었다 펴는 판을 이 자리에 둔다.
   *
   * 올리는 알맹이(크기 제한 · 받는 형식 · 보내는 주소)는 `js/upload-core.js`
   * 가 갖는다 — 진료기록 탭과 두 벌이면 한쪽만 고쳐진다. */
  function wireAddPanel() {
    var button = document.getElementById("add-doc");
    var panel = document.getElementById("add-panel");
    var drop = document.getElementById("drop2");
    var input = document.getElementById("file2");
    var pick = document.getElementById("pick2");
    if (!button || !panel || !drop || !input || !pick) return;

    function addSay(text) {
      var box = document.getElementById("add-say");
      if (!box) return;
      box.textContent = text;
      /* 할 말이 없으면 자리도 비운다 — 빈 줄이 남으면 블록에 틈이 생긴다 */
      box.hidden = !text;
    }

    button.addEventListener("click", function () {
      var open = panel.hidden;
      panel.hidden = !open;
      button.setAttribute("aria-expanded", open ? "true" : "false");
      /* 열면 바로 고를 수 있게 초점을 옮긴다 — 키보드로 다니는 사람이
         판이 열린 것을 알 방법이 그것뿐이다. */
      if (open) pick.focus();
    });

    pick.addEventListener("click", function () {
      input.click();
    });

    input.addEventListener("change", function () {
      send(this.files);
      this.value = ""; // 같은 파일을 다시 골라도 change 가 나게 한다
    });

    wireDrop(drop, send);

    function send(fileList) {
      if (!visit || !visit.visit_id) return addSay("진료 건을 먼저 선택해 주세요.");

      var list = Array.prototype.slice.call(fileList).slice(0, roomFor(0));
      if (!list.length) return;

      /* **어느 진료에 올리는지 지금 붙잡는다.** 올라가는 사이 왼쪽 목록에서
         다른 환자를 고르면 `visit` 이 바뀐다 — 남의 진료에 사진이 붙는다. */
      var wantedId = visit.visit_id;
      var bad = null;
      list.forEach(function (file) {
        bad = bad || rejectFile(file, human2);
      });
      if (bad) return addSay(bad);

      addSay(list.length + "장 올리는 중입니다…");

      Promise.all(
        list.map(function (file) {
          return postDocument(wantedId, file);
        }),
      )
        .then(function () {
          if (!visit || visit.visit_id !== wantedId) return;
          addSay(list.length + "장 올렸습니다 — 판독을 다시 불러옵니다.");
          /* 새 사진이 붙으면 판독이 다시 돈다. 화면을 새로 여는 것과 같은
             경로로 다시 묻는다 — 반쪽만 갱신하면 원문과 값이 어긋난다. */
          loadVisit(visit);
        })
        .catch(function (err) {
          if (!visit || visit.visit_id !== wantedId) return;
          addSay(err.message || "올리지 못했습니다. 다시 시도해 주세요.");
        });
    }
  }

  /* 크기를 사람 말로. `upload.js` 의 것과 같은 규칙인데, 그 파일은 이 화면이
     싣지 않는다 — 한 줄짜리라 공용으로 올리지 않고 여기 둔다. */
  function human2(bytes) {
    return Math.round(bytes / (1024 * 1024)) + "MB";
  }

  wireAddPanel();

  function resetState() {
    /* **앞 환자에게 적은 값을 따라가면 안 된다.** 남겨 두면 새 환자 화면에
       그 사람 값이 뜨고, 배지가 「저장 안 됨」이라 더 헷갈린다. */
    local = {};
    localEditing = null;
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
    summary.textContent = "";
    summary.hidden = true;
    /* **글자만 지우고 숨기지 않으면 빈 칸이 자리를 차지한다** — 이희진 님 `#162` ④.
       쓰는 자리(901·914·925)는 전부 `textContent` 와 `hidden` 을 짝지어 다루는데
       치우는 자리만 한쪽을 빠뜨리고 있었다. */
    if (saveNote) {
      saveNote.textContent = "";
      saveNote.hidden = true;
    }
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
        next.visited_at ? shortDate(next.visited_at) + " 진료" : "",
      ]
        .filter(Boolean)
        .join(" · ");
    }

    /* 상태 배지 — `patients.html` 의 머리말과 같은 자리다. 전에는 이 화면에만
       없어서, 화면을 옮기면 「작성 중 · 판독 결과 확인」이 사라졌다
       (와이어프레임 S1-6 은 머리말 첫 줄에 이 배지를 그린다). */
    var state = document.getElementById("p-state");
    if (state) {
      state.hidden = !next.detail_status;
      state.textContent = typeof statusLabel === "function" ? statusLabel(next.detail_status) : "";
      state.className = typeof stateClass === "function" ? stateClass(next.work_category) : "row__state";
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
    renderSteps(); // 단계 줄은 진료가 정해져야 갈 곳을 안다
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

  /* ── 5단계 줄 ─────────────────────────────────────────────
     `patients.html` 과 같은 모듈이 그린다. 판독 화면은 「진료기록」 칸에 서
     있고, 다른 칸을 누르면 그 진료의 환자 카드로 돌아간다. 전에는 `<li>` 라
     눌리지 않아서 앞 화면으로 가려면 왼쪽 목록에서 환자를 다시 골라야 했다. */
  function renderSteps() {
    var box = document.getElementById("tabs");
    if (!box) return;
    var id = visit && visit.visit_id;
    box.innerHTML = id ? stepsHtml("record", "/ocr-review.html", id) : "";
  }

  (function bindSteps() {
    var box = document.getElementById("tabs");
    if (!box) return;
    box.addEventListener("click", function (event) {
      var tab = event.target.closest ? event.target.closest("[data-href]") : null;
      if (tab) location.href = tab.getAttribute("data-href");
    });
  })();

  document.addEventListener("visit:selected", function (event) {
    if (event.detail) loadVisit(event.detail);
  });
})();
