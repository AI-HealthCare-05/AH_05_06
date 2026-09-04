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
  var manualDrugs = [];

  /* 처방 세트 대표 약 키워드 — 백엔드 _BIZAN_RE/_YAZZ_RE/_METFORMIN_RE 와 동기화.
     DURATION_DAYS 표시 여부 및 base 약품 중복 행 판단에 공통으로 사용한다. */
  var _SET_DRUG_KWS = ["비잔", "야즈", "메트포르민", "메트포민", "metformin"];

  function isSetDrugValue(val) {
    if (!val) return false;
    var lower = String(val).toLowerCase();
    return _SET_DRUG_KWS.some(function (kw) { return lower.indexOf(kw.toLowerCase()) !== -1; });
  }

  /* 적는 **중**인 값. `local` 과 갈라 두는 이유는, 고르는 항목이 「있다」를
     고른 순간 크기 칸을 내보내려면 다시 그려야 하는데 그때 `local` 에 써
     버리면 「취소」로 되돌릴 것이 없다.
     확인을 눌러야 `local` 로 넘어간다. */
  var localDraft = {};

  /* 의사가 설정(D2-3)에서 정해 둔 약속처방. 화면이 뜰 때 한 번 불러 둔다 —
     환자를 옮길 때마다 다시 부르면 같은 목록을 하루에 수십 번 받는다. */
  var sets = [];
  var setsFailed = false;
  var pickedSet = null;

  /* OCR 이 추론한 처방 세트 이름(`PRESCRIPTION_SET` 필드)으로 드롭다운을 자동
     선택한다. sets 와 result 중 나중에 도착하는 쪽에서 호출한다.
     사람이 이미 고른 뒤에는 건드리지 않는다. */
  function applyPrescriptionSetSuggestion() {
    if (pickedSet) return;
    if (!result || !sets.length) return;
    var suggested = fieldValueOf(result.fields, "PRESCRIPTION_SET");
    if (!suggested) return;
    for (var i = 0; i < sets.length; i++) {
      if (sets[i].name === suggested) {
        pickedSet = sets[i];
        return;
      }
    }
  }

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

  var docView = document.getElementById("doc-view");

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

  /* <img src> 는 Authorization 헤더를 보내지 못해 401 이 된다.
     fetch 로 직접 받은 뒤 Blob URL 을 생성해 img 에 할당한다. */
  var _docViewBlobUrl = null;

  function _openLightbox(src) {
    var overlay = document.createElement("div");
    overlay.className = "doc-lightbox";
    overlay.setAttribute("role", "dialog");
    overlay.setAttribute("aria-modal", "true");
    overlay.setAttribute("aria-label", "문서 원본 확대");
    overlay.tabIndex = -1;

    var img = document.createElement("img");
    img.className = "doc-lightbox__img";
    img.src = src;
    img.alt = "문서 미리보기 확대";
    overlay.appendChild(img);

    document.body.appendChild(overlay);
    overlay.focus();

    function close() {
      if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
      document.removeEventListener("keydown", onKey);
    }

    overlay.addEventListener("click", function (e) {
      if (e.target === overlay) close();
    });

    function onKey(e) {
      if (e.key === "Escape") {
        e.stopPropagation();
        close();
      }
    }
    document.addEventListener("keydown", onKey);
  }

  function renderDocView() {
    if (!docView) return;
    if (!activeDoc) {
      docView.innerHTML = '<p class="doc-view__soon">문서를 선택하면 여기에 미리보기가 표시됩니다</p>';
      return;
    }

    docView.innerHTML = '<p class="doc-view__soon">불러오는 중…</p>';

    if (_docViewBlobUrl) {
      URL.revokeObjectURL(_docViewBlobUrl);
      _docViewBlobUrl = null;
    }

    var token = session.token();
    var headers = token ? { Authorization: "Bearer " + token } : {};
    var url = "/api/v1/ocr/documents/" + encodeURIComponent(activeDoc) + "/image";
    /* 요청 시점의 문서 id를 클로저로 캡처한다 — 응답 도착 시 activeDoc이 바뀌었으면
       stale 이미지가 현재 문서 미리보기를 덮어쓰는 레이스 컨디션을 막는다. */
    var requestedDoc = activeDoc;

    fetch(url, { headers: headers, credentials: "include" })
      .then(function (res) {
        if (!res.ok) throw new Error(res.status);
        return res.blob();
      })
      .then(function (blob) {
        if (activeDoc !== requestedDoc) return;
        _docViewBlobUrl = URL.createObjectURL(blob);
        if (docView) {
          docView.innerHTML =
            '<img class="doc-view__img" src="' +
            _docViewBlobUrl +
            '" alt="문서 미리보기" tabindex="0">';
          var img = docView.querySelector(".doc-view__img");
          if (img) {
            img.addEventListener("click", function () {
              _openLightbox(_docViewBlobUrl);
            });
            img.addEventListener("keydown", function (e) {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                _openLightbox(_docViewBlobUrl);
              }
            });
          }
        }
      })
      .catch(function () {
        if (activeDoc !== requestedDoc) return;
        if (docView) {
          docView.innerHTML = '<p class="doc-view__soon">원본 이미지가 삭제됐거나 불러올 수 없습니다</p>';
        }
      });
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
    renderDocView();
    renderRaw(typeof line === "number" ? line : null);
  }

  /* ── 오른쪽 · 구조화 필드 ──────────────────────────────────── */

  /* **못 읽었다는 말을 글자로 적지 않는다.** 점선 네모 안의 `?` 가 이미 그
     말이다. 이름 옆에 「⚠ 인식 실패」, 값 옆에 「판독 실패」까지 붙이면 한 줄에
     같은 말이 세 가지 모양으로 서고, 그만큼 항목 이름이 밀려 잘린다.
     보이는 것으로 말할 수 있으면 글자를 더하지 않는다. */
  var STATE_TEXT = {
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

  /* **「있다 / 없다」는 고르게 한다.** 손으로 치게 두면 「有」·「있음」·「Y」가
     섞여 들어와 같은 뜻이 세 가지 글자로 남는다. 난소 부속기 혹은 「있다」일
     때 크기를 함께 적는다 — 두 칸으로 갈라 두면 「있다인데 크기가 빈」 상태가
     남는다.

     `hook` 은 값을 어디로 보낼지다(`data-input` 이냐 `data-local-input` 이냐).
     서버에 있는 줄과 아직 없는 줄이 **같은 모양**이어야 한다. */
  function choiceHtml(field, hook, value) {
    var picks = fieldChoices(field.field_type) || [];
    var now = splitChoiceValue(field.field_type, value);

    return (
      '<select class="field__pick" data-owns="' +
      escapeHtml(field.field_type) +
      '" ' +
      hook +
      ' aria-label="' +
      escapeHtml(fieldLabel(field.field_type)) +
      ' 고르기">' +
      '<option value=""' +
      (now.pick ? "" : " selected") +
      ">선택</option>" +
      picks
        .map(function (pick) {
          return (
            '<option value="' +
            escapeHtml(pick) +
            '"' +
            (now.pick === pick ? " selected" : "") +
            ">" +
            escapeHtml(pick) +
            "</option>"
          );
        })
        .join("") +
      "</select>" +
      (fieldChoiceSized(field.field_type) && now.pick === picks[0]
        ? '<input class="field__input field__input--size" type="text" inputmode="decimal" data-choice-size="' +
          escapeHtml(field.field_type) +
          '" value="' +
          escapeHtml(now.size) +
          '" aria-label="' +
          escapeHtml(fieldLabel(field.field_type)) +
          ' 크기" /><span class="field__unit">cm</span>'
        : "")
    );
  }

  /** 점선 칸 오른쪽의 단위. **무엇을 적어야 하는지가 그 글자에 있다** —
      `?` 만 있으면 cm 인지 개수인지 점수인지 물어봐야 안다.
      고르는 항목(있다/없다)과 단위 없는 항목에는 안 붙인다. */
  function unitHtml(field) {
    /* 고르는 항목에도 **빈 칸**을 세운다 — 안 세우면 그 줄만 버튼이 앞으로
       당겨져 옆 줄과 어긋난다. 자리는 지키고 글자만 없다. */
    if (fieldChoices(field.field_type)) return '<span class="field__unit"></span>';

    var unit = fieldUnit(field.field_type, field.unit);
    /* 맨 위 줄(진단 · 처방)은 자리를 지킬 필요가 없다 — 세 칸이 각자 서 있어
       빈 칸을 두면 값과 단추 사이가 까닭 없이 벌어진다. */
    if (!unit && PRESCRIPTION_TYPES.indexOf(field.field_type) !== -1) return "";
    return '<span class="field__unit">' + escapeHtml(unit) + "</span>";
  }

  function renderField(field) {
    var id = field.ocr_field_id;
    /* 사람이 「이번엔 안 했다」고 한 것이 맨 앞이다. 기계가 못 읽었든 문서가
       「추후 보고 예정」이라 했든, **사람이 그 위에서 판정한 것**이라 그 말이
       이긴다 — `docs/api/hospital.md` §4 (판독 항목의 상태 어휘). */
    var state =
      field.field_status === "NOT_PERFORMED"
        ? "skipped"
        : field.is_pending_report
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
    if (!locked && fieldChoices(field.field_type)) {
      /* **있음 / 없음은 줄에 바로 세운다.**
       *
       * 전에는 `?` 와 「직접 입력」이 서 있고, 눌러야 고르개가 나왔다. 칠 것이
       * 없는 항목인데 「입력」을 한 번 더 누르게 하는 셈이고, 스탭은 그 줄에
       * 무엇을 넣어야 하는지도 눌러 봐야 알았다.
       *
       * 고르면 바로 담긴다 — 서버에 있는 줄은 서버로, 아직 없는 줄은 화면에.
       * 「저장 안 됨」은 배지가 말한다. */
      var picked = id
        ? isEditing(id)
          ? editing[id]
          : field.value
        : localDraft[field.field_type] !== undefined
          ? localDraft[field.field_type]
          : local[field.field_type] || "";

      body =
        choiceHtml(
          field,
          id ? 'data-input="' + id + '"' : 'data-local-input="' + escapeHtml(field.field_type) + '"',
          picked,
        ) +

        "";
    } else if (locked) {
      body =
        '<div class="field__value">' +
        escapeHtml(field.value === null || field.value === undefined ? "?" : field.value) +
        "</div>" +
        unitHtml(field);
    } else if (isEditing(id)) {
      body =
        (fieldChoices(field.field_type)
          ? choiceHtml(field, 'data-input="' + id + '"', editing[id])
          : '<input class="field__input" type="text" data-input="' +
            id +
            '" value="' +
            escapeHtml(editing[id]) +
            '" aria-label="' +
            /* 화면 읽기 프로그램도 사람 말을 들어야 한다 — 전에는
               「MEDICATION_NAME 값 입력」이라 읽혔다. */
            escapeHtml(fieldLabel(field.field_type)) +
            ' 값 입력" />') +
        '<button class="field__act field__act--go" type="button" data-save="' +
        id +
        '">저장</button>' +
        '<button class="field__act" type="button" data-cancel="' +
        id +
        '">취소</button>';
    } else if (field.is_absent && localEditing === field.field_type) {
      /* 적는 중. 「저장」이라 쓰지 않는다 — 서버로 안 가는데 저장이라고
         하면 남았다고 믿는다. 「확인」은 이 화면에서 값을 굳힌다는 뜻이고,
         담는 것은 블록 머리의 「저장」이 한 번에 한다. */
      body =
        (fieldChoices(field.field_type)
          ? choiceHtml(
              field,
              'data-local-input="' + escapeHtml(field.field_type) + '"',
              localDraft[field.field_type] !== undefined
                ? localDraft[field.field_type]
                : local[field.field_type] || "",
            )
          : '<input class="field__input" type="text" data-local-input="' +
            escapeHtml(field.field_type) +
            '" value="' +
            escapeHtml(local[field.field_type] || "") +
            '" aria-label="' +
            escapeHtml(fieldLabel(field.field_type)) +
            ' 값 적기" />') +
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
        '<button class="field__act" type="button" data-local-fill="' +
        escapeHtml(field.field_type) +
        '">수정</button>';
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
        unitHtml(field) +
        '<button class="field__act" type="button" data-local-fill="' +
        escapeHtml(field.field_type) +
        '">직접 입력</button>' +
        "";
    } else if (state === "missing") {
      /* 빈 칸이 아니라 「못 읽었다」로 보여야 한다. 빈 칸은 안 읽은 것처럼 보인다. */
      body =
        '<div class="field__value field__value--missing">?</div>' +
        unitHtml(field) +
        '<button class="field__act" type="button" data-fill="' +
        id +
        '">직접 입력</button>' +
        /* **여기가 「이번 미시행」이 가장 필요한 자리다.**

           기계는 「못 읽었다」와 「그 줄이 아예 없다」를 구별하지 못한다. 문서를
           눈으로 보는 사람만 안다. 구별이 없으면 이 항목이 「확인할 항목」에
           남아 **안내문 생성이 영영 막힌다** — 안 한 검사를 채울 방법은 없다.

           별도 보고 검사(`pending`)에도 같은 버튼을 두지만 그쪽은 이미 셈에서
           빠져 있어 표시만 바뀐다. 막힌 것을 푸는 것은 이 자리다. */
        /* **「이번 미시행」은 검사값의 말이다.** 진단과 처방은 「이번엔 안
           했다」가 성립하지 않는다 — 안 한 진료가 아니라 못 읽은 것이고,
           안내문이 그 값으로 만들어지므로 채워야 끝난다. */
        (PRESCRIPTION_TYPES.indexOf(field.field_type) !== -1
          ? ""
          : '<button class="field__act field__act--quiet" type="button" data-skip="' +
            id +
            '">이번 미시행</button>');
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
        "</div>" +
        unitHtml(field) +
        '<button class="field__act" type="button" data-fill="' + id + '">수정</button>';
    }

    var tail = isEditing(id) ? "" : sourceChip(field);
    /* 사람이 고친 값에는 그 사실이 남아야 한다 — 나중에 「기계가 이렇게
       읽었다」와 「사람이 이렇게 고쳤다」를 가르려면.

       **견줄 것이 없으면 적지 않는다.** 기계가 아무것도 못 읽은 칸에 「수정됨 ·
       판독값 없음」이라고 붙이면, 사람이 적었다는 뻔한 사실을 값보다 먼저 읽게
       된다 — 그 줄에서 봐야 할 것은 값이다. */
    if (field.corrected_value !== null && field.corrected_value !== undefined && field.extracted_value) {
      tail += '<span class="field__edited">수정됨 · 판독값 ' + escapeHtml(field.extracted_value) + "</span>";
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
      /* 줄이 자기 항목 이름을 들고 있는다 — 값을 읽는 자리(`boxValue`)가
         「이게 고르는 항목인가」를 알아야 하는데, 서버에 없는 줄은 `id` 가
         없어서 되찾을 길이 이것뿐이다. */
      '" data-field-type="' +
      escapeHtml(field.field_type) +
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
    /* 「처방」은 판독이 읽은 약 이름이 아니라 **설정(D2-3)에서 정해 둔 세트**
       에서 고른다. 세트에 약 목록 · 확인 항목 · 주의 문구가 함께 묶여 있어서,
       자유 입력이면 붙일 문구를 못 찾는다. `pick: true` 인 칸은 값 줄 대신
       고르는 칸으로 그린다. */
    { type: "MEDICATION_NAME", label: "처방", wide: true, pick: true },
    { type: "DURATION_DAYS", label: "처방일수", unit: "일", wide: false },
  ];

  /* 약속처방 고르는 칸.
   *
   * 목록이 없으면 **빈 드롭다운을 두지 않는다** — 열어도 아무것도 없는 칸은
   * 「고장」으로 읽힌다. 대신 왜 비었는지와 어디서 채우는지를 적는다.
   *
   * 판독이 읽은 약 이름은 아래 곁말로 남긴다. 어느 세트를 골라야 하는지의
   * 실마리이지, 그 자체가 처방은 아니다. */
  function setPickerHtml(field) {
    var readName = field && field.value ? String(field.value) : "";
    var note = setsMissingSaying(sets, setsFailed);

    if (note) {
      /* 판독된 약품명이 있으면 그것을 처방 칸에 크게 보인다.
         세트 로드 실패 메시지는 아래 곁말로 내린다. */
      if (readName) {
        return (
          '<div class="top__pick top__pick--static">' +
          escapeHtml(readName) +
          "</div>" +
          '<div class="top__read">' +
          escapeHtml(note) +
          "</div>"
        );
      }
      return '<div class="top__note">' + escapeHtml(note) + "</div>";
    }

    /* **여기가 감춤을 거르는 유일한 자리다.**
       감춤은 「없다」가 아니라 「새로 못 고른다」는 뜻이다. 목록 자체는 감춘
       것까지 다 받는다 — 이미 그 처방으로 저장된 진료를 다시 열 때 확인
       항목을 이름으로 되찾고(`ocr-groups.js`), 설정에서 되살려야 하기
       때문이다. 서버 쪽 조회(`filter(name=…)`)도 거르지 않는다. 거기서
       거르면 지난 환자들의 안내문 문구가 조용히 범용으로 바뀐다. */
    var options = sets
      .filter(function (set) {
        /* 이미 고른 것이면 감췄어도 남긴다 — 안 그러면 고른 값이 풀린다 */
        return (
          !set.hidden ||
          (pickedSet && pickedSet.prescription_set_id === set.prescription_set_id)
        );
      })
      .map(function (set) {
        return (
          '<option value="' +
          escapeHtml(String(set.prescription_set_id)) +
          '"' +
          (pickedSet && pickedSet.prescription_set_id === set.prescription_set_id ? " selected" : "") +
          ">" +
          escapeHtml(set.name) +
          "</option>"
        );
      })
      .join("");

    return (
      '<select class="top__pick" id="set-pick" aria-label="약속처방 고르기">' +
      '<option value="">처방을 고르세요</option>' +
      options +
      "</select>" +
      (readName ? '<div class="top__read">판독: ' + escapeHtml(readName) + "</div>" : "")
    );
  }

  function topRowHtml(rows) {
    /* OCR이 추출한 MEDICATION_NAME[_N] 중 처방 세트 대표 약이 하나라도 있으면 true.
       없으면 처방일수 셀을 숨긴다 — DURATION_DAYS는 세트 대표 약에 연결된 일수인데,
       그 약이 없으면 값의 맥락이 모호해진다. */
    var anySetDrugInOcr = rows.some(function (f) {
      return /^MEDICATION_NAME(_\d+)?$/.test(f.field_type) && isSetDrugValue(f.value);
    });

    var cells = TOP_ROW.map(function (spec) {
      var field = null;
      for (var i = 0; i < rows.length; i++) {
        if (rows[i].field_type === spec.type) field = rows[i];
      }
      if (!field) return "";

      /* 처방 세트 대표 약이 OCR에 없으면 처방일수 셀을 표시하지 않는다. */
      if (spec.type === "DURATION_DAYS" && !anySetDrugInOcr) return "";

      /* 약속처방은 값 줄이 아니라 **고르는 칸**이다.
         비잔 감지 여부와 무관하게 항상 드롭다운을 표시한다.
         비잔이 감지되면 자동 선택, 아니면 「처방을 고르세요」 상태로 둔다. */
      if (spec.pick) {
        return (
          '<div class="top__cell top__cell--wide">' +
          '<span class="top__label">' +
          escapeHtml(spec.label) +
          "</span>" +
          setPickerHtml(field) +
          "</div>"
        );
      }

      var made = fieldBody(field);
      return (
        /* 🚩 **`data-field-type` 을 여기서도 붙인다.**
         *
         * 값을 읽는 자리(`typeOfBox`)가 `closest("[data-field-type]")` 로 항목
         * 이름을 찾는데, 그 속성은 `renderField` 가 만드는 `<li>` 에 붙는다.
         * 맨 윗줄은 `made.body` 만 꺼내 제 `<div>` 로 감싸므로 **그 속성이
         * 없었다.**
         *
         * 그래서 진단을 골라도 `fieldChoices("")` 가 거짓이 돼 **서버로 보내는
         * 분기를 통째로 건너뛰었다.** 값은 화면에만 남고 탭을 옮기면 사라졌고,
         * 확정이 안 되니 안내문 생성이 계속 막혔다. */
        '<div class="top__cell' +
        (spec.wide ? " top__cell--wide" : "") +
        (made.clash ? " field--clash" : "") +
        '" data-field-type="' +
        escapeHtml(field.field_type) +
        '">' +
        '<span class="top__label">' +
        escapeHtml(spec.label) +
        "</span>" +
        '<div class="field field--' +
        made.state +
        '">' +
        /* **단위는 값칸 바로 뒤, 단추 앞이다.** 여기서 따로 붙이지 않는다 —
           칸 밖에 두면 오른쪽 끝으로 떨어지고, 칸 안 끝에 두면 단추 뒤로
           밀린다. 값을 그리는 자리(`renderField` 의 `unitHtml`)가 값 바로
           뒤에 세우므로 그쪽 하나에 맡긴다. */
        made.body +
        "</div>" +
        "</div>"
      );
    }).join("");

    return cells ? '<div class="top">' + cells + drugsHtml(rows) + "</div>" : "";
  }

  /* 고른 처방에 든 약 — 맨 위 줄 **바로 아래**에 붙는다.
   *
   * 2heej 님 `#176` 리뷰. 「처방」 칸은 세트 **이름** 하나만 보여 주는데,
   * 「자궁내막증 · 비잔 (처음)」이라는 이름만으로는 무엇을 며칠 드시는지가
   * 안 보인다 — 그 답이 안내문에 그대로 나가는 값이라 스탭이 여기서 확인할
   * 수 있어야 한다.
   *
   * **아직 안 골랐으면 아무것도 안 그린다.** 고르기 전의 빈 목록은 「약이
   * 없는 처방」으로 읽힌다.
   */
  function drugsHtml(rows) {
    if (!pickedSet) return "";

    var written = null;
    for (var i = 0; i < rows.length; i++) {
      if (rows[i].field_type === "DURATION_DAYS") written = rows[i].value;
    }

    var lines = drugLines(pickedSet, written);

    if (!lines.length) {
      /* **비었다고 지어내지 않는다.** 어디서 채우는지를 적는다 — 설정(D2-3)의
         「처방 약」이 그 자리다. */
      return '<p class="drugs__none">이 처방에 등록된 약이 없습니다 · 설정 › 처방에서 추가할 수 있습니다</p>';
    }

    return (
      '<ul class="drugs">' +
      lines
        .map(function (line) {
          return (
            '<li class="drugs__one"><span class="drugs__name">' +
            escapeHtml(line.name) +
            "</span>" +
            /* 일수를 못 셈했으면 **칸을 비운다.** 「0일」이나 「-」를 적으면
               읽는 사람이 그것을 값으로 센다. */
            (line.days === null
              ? '<span class="drugs__days drugs__days--none"></span>'
              : '<span class="drugs__days">' + escapeHtml(String(line.days)) + "일</span>") +
            '<span class="drugs__saying">' +
            escapeHtml(line.saying) +
            "</span></li>"
          );
        })
        .join("") +
      "</ul>"
    );
  }

  /* 수동으로 추가한 약 행 — 비잔 세트가 선택됐지만 등록 약이 없거나 추가가
     필요할 때 스탭이 직접 입력한 약품명·처방일수를 렌더링한다. */
  function manualDrugRowsHtml() {
    return manualDrugs.map(function (drug, i) {
      return (
        '<div class="top">' +
        '<div class="top__cell" aria-hidden="true"></div>' +
        '<div class="top__cell top__cell--wide">' +
        '<input class="top__pick drugs__manual-name" type="text" placeholder="약품명 입력" ' +
        'data-manual-drug-name="' + i + '" value="' + escapeHtml(drug.name) + '" />' +
        '</div>' +
        '<div class="top__cell">' +
        '<span class="top__label">처방일수</span>' +
        '<div class="field field--confirmed">' +
        '<input class="field__val drugs__manual-days" type="number" min="1" placeholder="일수" ' +
        'data-manual-drug-days="' + i + '" value="' + escapeHtml(String(drug.days || "")) + '" />' +
        '<span class="field__unit">일</span>' +
        '</div>' +
        '</div>' +
        '</div>'
      );
    }).join("");
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
    /* 🚩 **커서는 글 치는 칸에만 있다.**
     *
     * `<select>` 에는 `selectionStart` 가 없어 `undefined` 가 나오는데, 배열로
     * 감싸면 `[undefined, undefined]` 가 되어 **참으로 읽힌다.** 그 뒤 복원에서
     * `box.setSelectionRange` 를 부르면 `<select>` 에 그 함수가 없어 터진다.
     *
     * 그 예외가 `renderFields` → `redraw` → `onTyped` 를 통째로 중단시켜,
     * **고른 값을 서버로 보내는 줄이 아예 안 돌았다** — 진단을 골라도 화면에만
     * 남고 탭을 옮기면 사라졌다. 고르는 칸이 늘면서 드러난 자리다. */
    var canCaret = !!active && typeof active.selectionStart === "number";
    var caret = typingIn === null || !canCaret ? null : [active.selectionStart, active.selectionEnd];

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
    if (caret && typingIn === wanted && typeof box.setSelectionRange === "function") {
      box.setSelectionRange(caret[0], caret[1]);
    }
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
       만들어져서, 화면에서 사라지면 빠진 채로 만들어진다 (S1-7).
       인덱스형 필드(MEDICATION_NAME_2 등)는 prescriptionHtml 안에서
       extraDrugRowsHtml이 별도로 처리한다. */
    var rx = withMissingRows(split.prescription, PRESCRIPTION_CORE);
    /* 인덱스형 처방 필드를 rx에 추가한다 — prescriptionHtml의 extraDrugRowsHtml이
       분류해 가로 레이아웃으로 세운다. */
    for (var i = 0; i < split.prescription.length; i++) {
      if (/^[A-Z_]+_\d+$/.test(split.prescription[i].field_type)) {
        rx.push(split.prescription[i]);
      }
    }
    /* 검사값도 자리를 세운다 — 안 세우면 못 읽은 것과 안 한 것을 구별할 수 없다 */
    var labs = withMissingRows(split.labs, LAB_CORE);
    return prescriptionHtml(rx) + labsHtml(labs) + notReadyHtml();
  }

  /* 추가 약품 행 — MEDICATION_NAME_2 / DURATION_DAYS_2 등을 상단 처방 줄과
     같은 가로 레이아웃으로 세운다. 각 인덱스(2, 3 …)별로 짝을 지어 .top 행을 만든다. */
  function extraDrugRowsHtml(rows) {
    var pairs = {};
    var order = [];
    for (var i = 0; i < rows.length; i++) {
      var ft = rows[i].field_type;
      var m = ft.match(/^(MEDICATION_NAME|DURATION_DAYS)_(\d+)$/);
      if (!m) continue;
      var idx = m[2];
      if (!pairs[idx]) { pairs[idx] = {}; order.push(idx); }
      pairs[idx][m[1]] = rows[i];
    }
    if (!order.length) return "";

    return order.map(function (idx) {
      var nameField = pairs[idx]["MEDICATION_NAME"];
      var daysField = pairs[idx]["DURATION_DAYS"];

      /* 약품명 셀 — 첫 번째 처방 행의 setPickerHtml(static) 과 같은 방식으로
         값만 표시한다. fieldBody를 쓰면 [수정]·[이미지1]이 이 칸에도 붙어
         오른쪽 처방일수 셀과 중복된다. */
      var nameCell = "";
      if (nameField) {
        var nameVal = nameField.value != null ? String(nameField.value) : "";
        nameCell = (
          '<div class="top__cell top__cell--wide">' +
          '<div class="top__pick top__pick--static">' + escapeHtml(nameVal) + "</div>" +
          "</div>"
        );
      }

      /* 처방일수 셀 — fieldBody 그대로([수정]·[이미지1] 포함). */
      var daysCell = "";
      if (daysField) {
        var madeDays = fieldBody(daysField);
        daysCell = (
          '<div class="top__cell' + (madeDays.clash ? " field--clash" : "") + '">' +
          '<span class="top__label">처방일수</span>' +
          '<div class="field field--' + madeDays.state + '">' + madeDays.body + "</div>" +
          "</div>"
        );
      }

      /* 진단 셀(flex: 0 0 206px)과 너비를 맞추는 빈 자리 — 처방 텍스트의
         왼쪽이 첫 번째 행과 정렬된다. */
      var spacer = '<div class="top__cell" aria-hidden="true"></div>';
      return '<div class="top">' + spacer + nameCell + daysCell + "</div>";
    }).join("");
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

    /* 인덱스형 약품 쌍(MEDICATION_NAME_2 / DURATION_DAYS_2 등)은 .top 가로 행으로,
       나머지(1회량·일일횟수·처방일 등)는 기존 rows 목록으로 세운다. */
    var extraRows = rest.filter(function (f) {
      return /^(MEDICATION_NAME|DURATION_DAYS)_\d+$/.test(f.field_type);
    });
    var otherRest = rest.filter(function (f) {
      return !/^(MEDICATION_NAME|DURATION_DAYS)_\d+$/.test(f.field_type);
    });

    /* 첫 번째 약품(MEDICATION_NAME / DURATION_DAYS)을 드롭다운 아래에
       텍스트 행으로 표시한다.
       세트 대표 약이 하나라도 검출되면(anySetDrugInOcr) 상단 행에 DURATION_DAYS가
       이미 표시되므로 base 중복 행을 추가하지 않는다. base가 세트 약인 경우도
       드롭다운 힌트에 이미 나타나므로 마찬가지로 생략한다. */
    var baseExtraRows = [];
    var anySetDrug = rows.some(function (f) {
      return /^MEDICATION_NAME(_\d+)?$/.test(f.field_type) && isSetDrugValue(f.value);
    });
    if (!anySetDrug) {
      rows.forEach(function (f) {
        if (f.field_type === "MEDICATION_NAME")
          baseExtraRows.push(Object.assign({}, f, { field_type: "MEDICATION_NAME_1" }));
        if (f.field_type === "DURATION_DAYS")
          baseExtraRows.push(Object.assign({}, f, { field_type: "DURATION_DAYS_1" }));
      });
    }

    return (
      '<section class="box"><div class="box__head">' +
      '<h2 class="box__title">진단 · 처방</h2>' +
      (warn ? '<span class="box__warn">ⓘ ' + escapeHtml(warn) + "</span>" : "") +
      /* 고른 처방도 여기서 담는다 — 전에는 화면이 기억만 하고 새로고침하면
         사라졌다. 안내문이 그 값으로 만들어지는데도. */
      '<span class="grow"></span>' +
      (rxSaying || !canSaveFields()
        ? '<span class="box__note">' + escapeHtml(rxSaying || SAVE_LOCKED) + "</span>"
        : "") +
      '<button class="button-primary button-primary--sm" type="button" id="rx-save"' +
      (canSaveFields() && (localOf(true).length || pickedSet || manualDrugs.some(function (d) { return d.name; })) ? "" : " disabled") +
      ">저장</button>" +
      "</div>" +
      topRowHtml(rows) +
      extraDrugRowsHtml(baseExtraRows.concat(extraRows)) +
      manualDrugRowsHtml() +
      (pickedSet && canSaveFields()
        ? '<div class="top top--drug-add">' +
          '<div class="top__cell" aria-hidden="true"></div>' +
          '<button class="field__act drugs__add" type="button" id="drug-add">+ 약 추가</button>' +
          '</div>'
        : "") +
      (meta.length ? '<p class="box__meta box__meta--top">' + meta.join(" · ") + "</p>" : "") +
      (otherRest.length ? '<div class="rows">' + otherRest.map(renderField).join("") + "</div>" : "") +
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
      /* **적은 것을 한 번에 담는다.** 스무 줄을 하나씩 저장하게 하면 어느 줄이
         담겼는지 세어야 하고, 하나만 빼먹으면 안내문에서야 안다. */
      '<span class="grow"></span>' +
      (labSaying || !canSaveFields()
        ? '<span class="box__note">' + escapeHtml(labSaying || SAVE_LOCKED) + "</span>"
        : "") +
      '<button class="button-primary button-primary--sm" type="button" id="labs-save"' +
      (canSaveFields() && localOf(false).length ? "" : " disabled") +
      ">저장</button>" +
      "</div>" +
      /* **두 칸으로 세운다.** 왼쪽은 사람이 보고 적는 것(증상 · 초음파),
         오른쪽은 뽑아 잰 것(혈액)이다. 스물한 줄을 한 줄기로 늘어놓으면
         아래가 화면 밖으로 나가고, 묶음 이름이 없으면 못 읽었을 때 어디를
         다시 봐야 하는지도 안 보인다. */
      '<div class="labs">' +
      labColumnsOf(labGroupsOf(rows))
        .map(function (column) {
          return (
            '<div class="labs__col">' +
            column.groups
              .map(function (group) {
                return (
                  '<p class="rows__group">' +
                  escapeHtml(group.title) +
                  "</p>" +
                  '<div class="rows">' +
                  group.rows.map(renderField).join("") +
                  "</div>"
                );
              })
              .join("") +
            "</div>"
          );
        })
        .join("") +
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
        /* 확인 항목은 이제 저장된다 — 「아직 없다」는 말을 그대로 두면 켜 놓고도
           안 남는 줄 안다. 나머지 블록은 그대로다. */
        (group.key === "checks" ? "" : '<p class="box__soon">' + escapeHtml(group.saying) + "</p>") +
        "</section>"
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
  /* 확인 항목의 답. `null` 은 **아직 안 여쭌 것**이고 `false` 는 여쭤서
     아니라고 한 것이다 — 하나로 뭉치면 안내문이 「없음」을 확인한 것처럼 적을
     수 있는데 실제로는 아무도 안 물었을 수 있다. */
  /* 확인 항목의 답.
   *
   * **켠 것만 담는다.** 처음에는 끈 것을 「여쭤서 아니라고 했다」(`false`)로
   * 담았는데, 화면에서는 안 켠 상자와 끈 상자가 같아 보여서 「아니오」라는
   * 글자를 옆에 붙여야 했다 — 체크를 풀었더니 글자가 나타나는 꼴이라 더
   * 헷갈렸다. 켜면 「예」, 끄면 「아직」이다. 표는 셋을 다 담을 수 있으므로
   * (`checked` 가 `null` 이면 안 여쭌 것), 세 갈래를 제대로 묻는 칸이 필요해질
   * 때 화면만 바꾸면 된다.
   */
  var checkAnswers = {};
  var checkSaying = "";

  /* 저장 뒤 한 줄. 눌렀는데 아무 말이 없으면 「됐나」가 된다.
     블록마다 따로 둔다 — 한 줄을 나눠 쓰면 처방을 저장했는데 판독 값 쪽에
     「저장했습니다」가 뜬다. */
  var labSaying = "";
  var rxSaying = "";

  /* 적어 둔 값 중 **이 블록의 것**만. 두 블록이 같은 `local` 을 나눠 쓰는데,
     한쪽 단추가 남의 블록 값까지 담으면 「안 만진 칸이 저장됐다」가 된다. */
  /* **판독이 있어야 담을 수 있다.** 적어 넣는 값은 판독 결과에 붙는다
     (`ocr_field` 는 `ocr_result` 의 것이다). 아직 아무것도 안 올린 진료에는
     붙일 자리가 없다.

     빈 판을 세우면서 생긴 자리다 — 채울 칸은 보이는데 담을 곳이 없다. 담을 수
     없으면 **누를 수 없게** 하고 왜인지 말한다. 눌러서 실패하게 두면 적은 것이
     날아간 줄 안다. */
  function canSaveFields() {
    return !!(result && result.ocr_result_id);
  }

  var SAVE_LOCKED = "진료기록을 올리면 저장할 수 있습니다";

  function localOf(wantPrescription) {
    var out = [];
    for (var type in local) {
      if (!Object.prototype.hasOwnProperty.call(local, type)) continue;
      var isRx = PRESCRIPTION_TYPES.indexOf(type) !== -1;
      if (isRx === !!wantPrescription) out.push(type);
    }
    return out;
  }

  /* 고른 처방이 여쭙는 항목. 안 골랐으면 빈 목록이다.
     **고른 것(`pickedSet`)이 먼저다** — 판독이 읽어 온 이름은 스탭이 고르기
     전의 값이고, 고른 뒤에는 그쪽이 맞다. */
  function checkItemsNow() {
    return checkItemsOf(sets, pickedSet || fieldValueOf(result.fields, "MEDICATION_NAME"));
  }

  function checkListHtml() {
    var items = checkItemsNow();

    /* **처방을 안 고르면 여쭐 것도 없다.** 다섯을 미리 세워 두면 처방을 고르는
       순간 항목이 바뀌면서 이미 체크한 것이 사라진 것처럼 보인다. */
    if (!items.length) {
      return '<p class="box__soon">처방을 고르면 그 처방에서 여쭙는 항목이 여기에 섭니다</p>';
    }

    return (
      '<ul class="checks" aria-label="확인 항목">' +
      items.map(function (key) {
        var answer = checkAnswers[key];
        return (
          '<li class="checks__item"><label class="checks__label">' +
          '<input type="checkbox" data-check="' +
          escapeHtml(key) +
          '"' +
          (answer === true ? " checked" : "") +
          " />" +
          escapeHtml(checkItemLabel(key)) +
          "</label></li>"
        );
      }).join("") +
      "</ul>" +
      (checkSaying ? '<p class="box__meta">' + escapeHtml(checkSaying) + "</p>" : "")
    );
  }

  /* 눌린 것을 서버로. **한 판을 통째로 보낸다** — 항목 하나씩 보내면 중간에
     끊겼을 때 반쪽 상태가 남는다. */
  function saveCheckItems() {
    if (!visit || !visit.visit_id) return;
    var wanted = visit.visit_id;

    /* **보이는 것만 보낸다.** 처방이 안 여쭙는 항목까지 보내면, 그 항목을
       빼는 순간 지난 답이 조용히 지워진다 — 답은 질문이 바뀌어도 남아야 한다. */
    var answers = checkItemsNow().map(function (key) {
      return { item_key: key, checked: checkAnswers[key] === undefined ? null : checkAnswers[key] };
    });

    checkSaying = "저장하는 중…";
    redraw();

    ocrApi
      .saveCheckItems(wanted, answers)
      .then(function (data) {
        if (!visit || visit.visit_id !== wanted) return;
        adoptCheckItems(data);
        checkSaying = "저장했습니다";
        redraw();
      })
      .catch(function () {
        if (!visit || visit.visit_id !== wanted) return;
        checkSaying = "저장하지 못했습니다. 잠시 뒤 다시 시도해 주세요";
        redraw();
      });
  }

  function adoptCheckItems(data) {
    checkAnswers = {};
    ((data && data.answers) || []).forEach(function (row) {
      if (row.checked !== null && row.checked !== undefined) checkAnswers[row.item_key] = row.checked;
    });
  }

  function loadCheckItems(visitId) {
    checkAnswers = {};
    checkSaying = "";
    ocrApi
      .checkItems(visitId)
      .then(function (data) {
        if (!visit || visit.visit_id !== visitId) return;
        adoptCheckItems(data);
        redraw();
      })
      .catch(function () {
        /* 못 읽으면 빈 채로 둔다 — 지어낸 답을 보이지 않는다 */
      });
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
      if (field.is_confirmed || field.is_pending_report || field.field_status === "NOT_PERFORMED") return;
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
    /* 수동 추가 약이 저장 버튼 없이 남아 있으면 생성을 막는다.
       저장하지 않으면 안내문에 실리지 않으며, 클릭해도 경고 없이 유실된다. */
    var unsavedManual = manualDrugs.some(function (d) { return d.name; });
    submit.disabled = !!noFields || generateBlocked(counts, clashes, generating) || unsavedManual;
    submit.title = noFields || generateBlockedSaying(counts, clashes, generating) ||
      (unsavedManual ? "추가한 약을 먼저 저장해 주세요 — 저장 버튼을 눌러야 안내문에 실립니다" : "");

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
    /* **덮을 것과 위에 붙을 것을 가른다** (`STATE_RULES` 의 `keepsWork`).
       `"left"` 는 왼쪽만 남긴다 — 올릴 자리는 두고 읽은 값 칸만 감춘다. */
    document.getElementById("work").hidden = !rule.keepsWork;
    var review = document.querySelector(".review");
    if (review) review.classList.toggle("review--left", rule.keepsWork === "left");

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

  /* 고르는 항목은 값이 **두 칸에 걸쳐 있다** — 「있다/없다」와 크기.
     읽는 자리마다 따로 이으면 한 곳만 고쳐진다. 여기 한 번만 잇는다. */
  function boxValue(box, fieldType) {
    if (!box) return "";
    var picked = String(box.value || "").trim();
    if (!fieldChoices(fieldType)) return picked;

    var size = fieldsBox.querySelector('[data-choice-size="' + fieldType + '"]');
    return joinChoiceValue(fieldType, picked, size ? size.value : "");
  }

  function typeOfBox(box) {
    if (!box) return "";

    /* **줄이 제 이름을 들고 있으면 그것부터 본다.**
     *
     * 고르는 칸(`choiceHtml`)은 `data-owns` 에 제 항목 이름을 달고 나온다.
     * 조상만 뒤지면 감싸는 자리마다 `data-field-type` 을 붙여 줘야 하는데,
     * 맨 윗줄이 그것을 빠뜨려 **이름이 빈 문자열이 됐다** — 그러면
     * `fieldChoices("")` 가 거짓이라 서버로 보내는 분기를 통째로 건너뛰고,
     * 진단을 골라도 화면에만 남았다.
     *
     * 자기 이름을 먼저 읽으면 누가 감싸든 상관없다. */
    var own = box.getAttribute ? box.getAttribute("data-owns") : null;
    if (own) return own;

    var row = box.closest ? box.closest("[data-field-type]") : null;
    return row ? row.getAttribute("data-field-type") : "";
  }

  function inputValue(fieldId) {
    var box = fieldsBox.querySelector('[data-input="' + fieldId + '"]');
    return boxValue(box, typeOfBox(box));
  }

  document.addEventListener("click", function (event) {
    var target = event.target;

    /* 판독 실패에서 빠져나가는 유일한 길. 이 진료의 진료기록 칸으로 보낸다. */
    /* 막다른 상태에서 빠져나오는 길. 환자를 다시 고른 것과 같은 경로다 —
       작업을 다시 묻고, 아직 도는 중이면 폴링에 다시 들어간다. */
    /* **판독을 다시 불러오는 유일한 길이다.** 머리에 「판독 결과 확인」이
       하나 더 있었는데 하는 일이 똑같았다 — 늘 떠 있으면서 아무것도 더 해
       주지 않았고, 정작 필요한 때(판독이 안 끝났을 때)는 이 단추가 그 자리에
       뜬다. 같은 일을 하는 단추가 둘이면 어느 것이 「진짜」인지 눈이 센다. */
    if (target.id === "recheck") {
      if (visit) loadVisit(visit);
      return;
    }

    /* 수동 약 추가 버튼 — 처방 세트에 등록 약이 없을 때 직접 입력할 행을 추가한다. */
    if (target.id === "drug-add") {
      manualDrugs.push({ name: "", days: "" });
      renderFields();
      var lastNameInput = fieldsBox.querySelector('[data-manual-drug-name="' + (manualDrugs.length - 1) + '"]');
      if (lastNameInput) lastNameInput.focus();
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
      var typed = boxValue(input, keep);
      if (typed) local[keep] = typed;
      else delete local[keep]; /* 비우면 지운다 — 빈 값을 「적었다」로 세지 않는다 */
      delete localDraft[keep];
      localEditing = null;
      redraw();
      return;
    }

    if (target.getAttribute && target.getAttribute("data-local-cancel")) {
      /* 취소는 **적던 것을 버린다** — 초안을 남기면 다시 열었을 때 되살아난다 */
      if (localEditing) delete localDraft[localEditing];
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

      /* 수동 추가 약이 저장되지 않은 채로 생성을 시도하면 약이 조용히 유실된다.
         renderSummary 가 이미 버튼을 잠그지만, DOM 조작으로 우회된 경우도 막는다. */
      if (manualDrugs.some(function (d) { return d.name; })) {
        saveNote.textContent = "추가한 약을 먼저 저장해 주세요 — 저장 버튼을 눌러야 안내문에 실립니다";
        saveNote.hidden = false;
        return;
      }

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
          /* **바로 안내문 화면으로 데려간다.** 제대로 만들어졌는지 보는 것이
             스탭 몫이고(S1-11~13), 말만 하고 안 데려다주면 단계 줄에서
             「안내문」을 다시 찾아 눌러야 한다. */
          saveNote.textContent = "안내문을 만들었습니다 — 확인 화면으로 이동합니다";
          saveNote.hidden = false;
          location.href = guideScreenHref(wantedId);
        })
        .catch(function (error) {
          var lockIsMine = generateLockIsMine(mySeq, generateSeq);
          if (lockIsMine) generating = false;
          if (!lockIsMine || !outcomeBelongsToScreen(wantedId, visit)) return;
          redraw();

          /* 409 는 실패가 아니다. 새로고침 뒤 다시 눌렀거나 두 사람이 같이
             누른 것이고, **원하던 것은 이미 있다.** 빨간 오류로 보여 주면
             스탭이 없는 문제를 찾게 된다. */
          if (guideAlreadyThere(error)) {
            /* 409 는 실패가 아니다 — 원하던 것이 이미 거기 있다. 같은 곳으로 간다. */
            saveNote.textContent = "이 진료의 안내문은 이미 있습니다 — 확인 화면으로 이동합니다";
            saveNote.hidden = false;
            location.href = guideScreenHref(wantedId);
            return;
          }
          saveNote.textContent = generateFailureSaying(error);
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
      var seed = current && !current.is_pending_report && current.value !== null && current.value !== undefined;
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
  /* 확인 항목 체크. **누르는 순간 담긴다** — 「저장」을 따로 두면 눌러 놓고
     안 누른 채 넘어가는 길이 생기고, 안전에 걸리는 항목이라 그게 가장 나쁘다. */
  document.addEventListener("change", function (event) {
    var key = event.target.getAttribute && event.target.getAttribute("data-check");
    if (!key) return;
    if (event.target.checked) checkAnswers[key] = true;
    else delete checkAnswers[key]; /* 끄면 「아직 안 여쭌 것」으로 되돌린다 */
    saveCheckItems();
  });

  /** 막힌 줄을 사람 말로. **까닭을 감추지 않는다.**
   *
   * 예전에는 무엇이 막혔든 「저장하지 못했습니다. 잠시 뒤 다시 시도해 주세요」
   * 였다. 「잠시 뒤 다시」는 기다리면 될 것처럼 읽히는데, 확정된 항목은
   * 기다려도 안 된다 — 그 말 때문에 같은 것을 되풀이해 누르게 됐다. */
  function stuckSaying(stuck) {
    /* **까닭이 다르면 따로 말한다.**
     *
     * 예전에는 막힌 것 중 하나라도 확정이면 **전부** 「이미 확정돼」로 뭉뚱그렸다.
     * 확정된 약품명과 그물이 끊겨 못 간 1회량이 같이 막히면, 다시 하면 될
     * 1회량까지 「못 바꿉니다」로 읽혀 스탭이 엉뚱한 조치를 한다 (`#216` 리뷰). */
    function named(rows) {
      return rows
        .map(function (r) {
          return fieldLabel(r.type);
        })
        .join(" · ");
    }

    var confirmed = stuck.filter(function (r) {
      return r.code === "OCR_FIELD_CONFIRMED";
    });
    var others = stuck.filter(function (r) {
      return r.code !== "OCR_FIELD_CONFIRMED";
    });

    var says = [];
    if (confirmed.length) says.push(named(confirmed) + " 은 이미 확정돼 여기서는 못 바꿉니다");
    if (others.length) says.push(named(others) + " 을 저장하지 못했습니다");
    return says.join(" · ");
  }

  /* 적어 둔 값을 **한 번에** 서버로. 판독이 못 읽은 항목은 줄 자체가 없어서
     항목 이름으로 짚는다(`PUT /visits/{id}/ocr-fields/{type}`). */
  document.addEventListener("click", function (event) {
    var hit = event.target.closest && event.target.closest("#labs-save, #rx-save");
    if (!hit) return;
    if (!visit || !visit.visit_id) return;

    /* 두 블록이 같은 길로 담는다 — 담는 규칙이 두 벌이면 한쪽만 고쳐진다.
       다른 것은 **무엇을 담느냐**뿐이다. */
    var isRx = hit.id === "rx-save";
    var wanted = visit.visit_id;
    var typed = localOf(isRx);

    /* 고른 처방은 약품명 칸에 담는다 — 안내문이 그 값으로 만들어진다.
       전에는 화면이 기억만 하고 새로고침하면 사라졌다.

       🚩 **이미 그 값이면 안 보낸다.** `PUT` 은 확정된 줄에 409
       (`OCR_FIELD_CONFIRMED`)를 내는데, 무조건 다시 보내면 그 하나 때문에
       `Promise.all` 이 통째로 깨져 **같이 보낸 진단이 영영 저장되지 않았다.**
       처방을 한 번 저장하고 나면 그 뒤로 진단을 못 넣는 상태가 됐다. */
    var extra = {};
    if (isRx && pickedSet && fieldValueOf(result.fields, "MEDICATION_NAME") !== pickedSet.name) {
      extra.MEDICATION_NAME = pickedSet.name;
    }

    /* 수동 추가 약이 쓰는 항목 이름. **담겼는지는 이것으로만 판단한다** —
       옆에서 딴 항목이 막혔다고 수동 약을 안 비우면, 다시 저장할 때 그 약이
       새 번호로 **한 번 더** 들어간다 (`#216` 리뷰). */
    var manualTypes = [];

    /* 수동 추가 약은 기존 MEDICATION_NAME_N 인덱스 다음 번호로 저장한다. */
    if (isRx && manualDrugs.length) {
      var maxIdx = 1;
      if (result && result.fields) {
        result.fields.forEach(function (f) {
          var m = f.field_type.match(/^MEDICATION_NAME_(\d+)$/);
          if (m) maxIdx = Math.max(maxIdx, parseInt(m[1], 10));
        });
      }
      manualDrugs.forEach(function (drug, i) {
        if (!drug.name) return;
        var idx = maxIdx + i + 1;
        extra["MEDICATION_NAME_" + idx] = drug.name;
        manualTypes.push("MEDICATION_NAME_" + idx);
        if (drug.days) {
          extra["DURATION_DAYS_" + idx] = String(drug.days);
          manualTypes.push("DURATION_DAYS_" + idx);
        }
      });
    }

    if (!typed.length && !Object.keys(extra).length) return;

    function say(text) {
      if (isRx) rxSaying = text;
      else labSaying = text;
    }

    say("저장하는 중…");
    redraw();

    /* **한 줄이 막혀도 나머지는 담는다.**
     *
     * 예전에는 `Promise.all` 이라 한 줄만 거절돼도 묶음이 통째로 깨졌다.
     * 확정된 처방을 다시 보내다 409 가 나면 **같이 보낸 진단까지 안 담겼고**,
     * 화면은 「저장하지 못했습니다」 한 줄만 말해서 무엇이 막혔는지 알 수
     * 없었다. 담길 수 있는 것은 담고, 막힌 것만 이름을 대고 말한다. */
    var jobs = typed
      .map(function (type) {
        return { type: type, value: local[type] };
      })
      .concat(
        Object.keys(extra).map(function (type) {
          return { type: type, value: extra[type] };
        }),
      );

    Promise.all(
      jobs.map(function (job) {
        return ocrApi
          .writeField(wanted, job.type, job.value)
          .then(function () {
            return { type: job.type, ok: true };
          })
          .catch(function (err) {
            return { type: job.type, ok: false, code: (err && err.code) || "" };
          });
      }),
    ).then(function (results) {
      if (!visit || visit.visit_id !== wanted) return;

      var stuck = results.filter(function (r) {
        return !r.ok;
      });

      /* 담긴 것만 화면에서 지운다 — 막힌 줄을 지우면 적은 값이 사라진다. */
      results.forEach(function (r) {
        if (!r.ok) return;
        delete local[r.type];
        delete localDraft[r.type];
      });
      /* **수동 약 자신이 다 담겼을 때만 비운다.** 묶음 전체가 성공했는지가
         아니다 — 이미 확정된 진단이 같이 막혔다고 수동 약을 안 비우면, 스탭이
         다시 저장할 때 `maxIdx` 가 새로 세어져 같은 약이 다음 번호로 또 들어간다. */
      var manualStuck = results.some(function (r) {
        return !r.ok && manualTypes.indexOf(r.type) !== -1;
      });
      if (isRx && manualTypes.length && !manualStuck) manualDrugs = [];

      if (!stuck.length) {
        say("저장했습니다");
      } else if (stuck.length === results.length) {
        say(stuckSaying(stuck));
      } else {
        /* 일부만 담겼을 때가 제일 헷갈린다 — 담긴 수를 먼저 말한다. */
        say(results.length - stuck.length + "개 담았습니다 · " + stuckSaying(stuck));
      }
      return loadResult(loadSeq);
    });
  });

  document.addEventListener("input", onTyped);
  /* `<select>` 는 브라우저에 따라 `input` 이 안 나기도 한다 — 둘 다 받는다 */
  document.addEventListener("change", onTyped);

  function onTyped(event) {
    var target = event.target;
    if (!target || !target.getAttribute) return;

    /* 수동 추가 약품명 입력 — 값만 저장하고 renderSummary만 호출한다.
       renderFields(패널 전체 재구성)는 행 추가/삭제 시점에만 실행해 성능을 줄인다.
       rx-save 버튼은 renderFields가 담당하므로, 저장 가능 상태를 직접 동기화한다. */
    var manualName = target.getAttribute("data-manual-drug-name");
    if (manualName !== null) {
      var ni = parseInt(manualName, 10);
      if (!isNaN(ni) && manualDrugs[ni]) {
        manualDrugs[ni].name = target.value || "";
        renderSummary();
        var rxBtn = document.getElementById("rx-save");
        if (rxBtn && canSaveFields()) {
          rxBtn.disabled = !(localOf(true).length || pickedSet || manualDrugs.some(function (d) { return d.name; }));
        }
      }
      return;
    }

    /* 수동 추가 처방일수 입력 */
    var manualDays = target.getAttribute("data-manual-drug-days");
    if (manualDays !== null) {
      var di = parseInt(manualDays, 10);
      if (!isNaN(di) && manualDrugs[di]) {
        manualDrugs[di].days = target.value || "";
      }
      return;
    }

    /* 크기 칸을 고치면 「있다」와 이어서 담아 둔다 — 안 그러면 다시 그릴 때
       크기만 사라진다. */
    var sized = target.getAttribute("data-choice-size");
    if (sized) {
      var owner = fieldsBox.querySelector('[data-owns="' + sized + '"]');
      if (!owner) return;
      var ownerId = owner.getAttribute("data-input");
      if (ownerId !== null && ownerId !== undefined) editing[Number(ownerId)] = boxValue(owner, sized);
      else localDraft[sized] = boxValue(owner, sized);
      return;
    }

    /* 아직 서버에 없는 줄. 고른 것을 담아 둬야 크기 칸이 따라 나온다 —
       담을 데가 없으면 「있다」를 골라도 화면이 그대로다. */
    var localType = target.getAttribute("data-local-input");
    if (localType) {
      var value = boxValue(target, localType);
      localDraft[localType] = value;

      /* 고르는 항목은 **누르는 순간 담긴다** — 「확인」을 한 번 더 누르게 하면
         고른 것이 담겼는지 눌러 봐야 안다. 치는 항목은 그대로 「확인」을 쓴다. */
      if (fieldChoices(localType)) {
        if (value) local[localType] = value;
        else delete local[localType];
        redraw();
      }
      return;
    }

    var box = target.getAttribute("data-input");
    if (box === null || box === undefined) return;

    var type = typeOfBox(target);
    var next = boxValue(target, type);
    editing[Number(box)] = next;

    /* 고르는 항목은 누르는 순간 서버로 간다. 크기가 딸린 것은 크기를 적을
       틈을 줘야 하므로, 크기 칸이 채워졌을 때만 보낸다. */
    if (fieldChoices(type)) {
      var needsSize = fieldChoiceSized(type) && splitChoiceValue(type, next).pick === fieldChoices(type)[0];
      redraw();
      if (next && !needsSize) saveField(Number(box), { corrected_value: next }, next);
    }
  }

  /* 값 하나 고치는 데 마우스를 두 번 쓰게 하지 않는다 */
  document.addEventListener("keydown", function (event) {
    var box = event.target.closest ? event.target.closest("[data-input]") : null;
    if (!box) return;
    var id = Number(box.getAttribute("data-input"));
    if (event.key === "Enter") {
      var typed = boxValue(box, typeOfBox(box));
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

    function openPanel(open, focus) {
      panel.hidden = !open;
      button.setAttribute("aria-expanded", open ? "true" : "false");
      /* 열면 바로 고를 수 있게 초점을 옮긴다 — 키보드로 다니는 사람이
         판이 열린 것을 알 방법이 그것뿐이다. */
      if (open && focus) pick.focus();
    }

    /* **올릴 것이 없으면 저절로 펴진다.**
       방금 등록한 환자는 판독한 기록이 없다. 그때 「판독한 기록이 없습니다」만
       띄우고 올리는 판을 접어 두면, 스탭은 올릴 자리를 못 찾는다 — 등록 다음
       걸음이 바로 이것인데도. 볼 것이 있을 때만 접는다.
       초점은 안 옮긴다 — 화면에 막 들어온 참이라 읽을 것이 먼저다. */
    window.ocrOpenAddPanel = function () {
      if (panel.hidden) openPanel(true, false);
    };

    button.addEventListener("click", function () {
      openPanel(panel.hidden, true);
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

  /* 약속처방 목록을 한 번 불러 둔다. 못 불러와도 화면은 선다 —
     고르는 칸이 「왜 비었는지」를 대신 적는다. */
  ocrApi
    .prescriptionSets()
    .then(function (rows) {
      sets = rows || [];
      setsFailed = false;
      if (result) {
        applyPrescriptionSetSuggestion();
        redraw();
      }
    })
    .catch(function () {
      setsFailed = true;
      if (result) redraw();
    });

  /* 고른 것을 붙잡는다. **서버로 보내지 않는다** — 진료에 처방 세트를 붙이는
     자리가 아직 없다(`Prescription` 표는 있으나 운영 코드가 안 쓴다). 화면이
     기억만 하고, 그 사실을 아래 곁말이 말한다. */
  document.addEventListener("change", function (event) {
    var pick = event.target;
    if (!pick || pick.id !== "set-pick") return;
    var wanted = Number(pick.value);
    pickedSet = null;
    for (var i = 0; i < sets.length; i++) {
      if (sets[i].prescription_set_id === wanted) pickedSet = sets[i];
    }
    redraw();
  });

  function resetState() {
    /* **앞 환자에게 적은 값을 따라가면 안 된다.** 남겨 두면 새 환자 화면에
       그 사람 값이 뜨고, 배지가 「저장 안 됨」이라 더 헷갈린다. */
    local = {};
    localEditing = null;
    manualDrugs = [];
    /* 앞 환자에게 고른 처방이 남으면 남의 처방으로 안내문이 만들어진다 */
    pickedSet = null;
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
        renderDocView();
        renderRaw(null);
        applyPrescriptionSetSuggestion();
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
    /* 확인 항목은 판독과 **따로** 불러온다 — 판독이 실패해도 여쭌 답은 보여야
       하고, 반대로 답을 못 읽어도 판독은 보여야 한다. */
    loadCheckItems(next.visit_id);
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
          /* **아직 안 올린 것은 「상태」가 아니다.**
           *
           * 「판독한 기록이 없습니다」를 화면 가득 띄웠더니, 방금 등록한 환자는
           * 그 안내를 한 번 보고 → 올리고 → 그제야 판독 화면으로 **넘어가야**
           * 했다. 화면이 두 번 바뀌는데 두 번 다 할 일은 같다.
           *
           * 판을 그냥 세운다. 왼쪽은 올리는 자리, 오른쪽은 채울 칸이 빈 채로.
           * 무엇을 하는 화면인지가 첫눈에 보이고, 올리면 그 자리에서 값이
           * 찬다 — 넘어가는 순간이 없다. */
          if (typeof ocrOpenAddPanel === "function") ocrOpenAddPanel();
          result = { ocr_result_id: null, documents: [], fields: [] };
          showWork();
          redraw();
          return null;
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
