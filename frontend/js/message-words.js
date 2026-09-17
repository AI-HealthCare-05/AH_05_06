/* 문자 한 통을 사람 말로 — 와이어프레임 D1-6 · D1-7 · S2-3. KEY-234.
 *
 * **화면 둘이 같은 낱말을 쓴다.** 현황 탭(`status-view.js`)은 한 환자의 다섯
 * 통을 세우고, 관리 · 발송 예정(`manage.js`)은 의원 전체에서 안 나간 것을
 * 훑는다. 같은 문자가 두 화면에서 다른 이름으로 뜨면 안 된다.
 *
 * `status-view.js` 에 있던 것을 여기로 옮겼다 — 그 파일은 현황 탭을 그리는
 * 자리라 `guide-view.js` 를 함께 물고 오는데, 낱말 몇 개 쓰려고 남의 화면
 * 파일을 통째로 실을 수는 없다. `roleLabel` 을 `session.js` 로 옮긴 것과
 * 같은 까닭이다.
 */

/* ① 발송 · 예정 — **이제 서버가 준다.**
 *
 * 승인이 나갈 문자를 전부 세워 둔다(`GuideService._schedule_messages`).
 * 화면은 셈하지 않고 받은 것을 그린다 — 화면이 따로 셈하면 서버가 잡은
 * 날짜와 다른 날짜를 보여 주게 되고, 어느 쪽이 진짜인지 알 수 없다.
 */
var MESSAGE_SAYING = {
  GUIDE: "진료 안내문",
  CHECK_D7: "일주일 뒤 확인",
  CHECK_D15: "보름 뒤",
  CHECK_D30: "한 달 뒤",
  RUN_OUT: "소진 임박",
};

/* **못 나간 이유는 넷뿐이다** — 와이어프레임 D1-7 「실패 이유 넷 — 잘못된
   번호 · 수신 거부 · 통신사 오류 · 발신번호 미등록」. 발신번호 미등록만
   처리 경로가 다르다(어드민 A1-5 에서 등록한다). */
var FAILURE_SAYING = {
  INVALID_PHONE: "잘못된 번호",
  OPT_OUT: "수신 거부",
  CARRIER: "통신사 오류",
  SENDER_UNREGISTERED: "발신번호 미등록",
};

/* **여기 적는 것은 「사람이 손댈 수 있는」 보류 사유다** — 와이어프레임 S2-3
   「스탭이 손댈 일은 보류 두 가지뿐이다 — 번호가 잘못됐을 때와 문자가
   떨어졌을 때」. 원문 표기가 「보류 · 번호」라 짧게 적는다.

   서버의 `GuideMessageHold` 에는 이보다 많다(`NOT_APPROVED` ·
   `SAFETY_CHECK_FAILED`). 그것들은 **일부러 여기
   없다** — 스탭이 손댈 자리가 없고, 사유를 적어 봐야 그 줄에서 할 수 있는
   일이 생기지 않는다. KEY-362의 SOURCE_NOT_DELETED는 안전한 삭제 복구
   동작이 생겼으므로 상세 사유와 함께 표시한다.

   **`BOOKING_URL_MISSING` 이 셋째다** — KEY-331. 이것은 손댈 수 있다:
   관리자가 어드민 A1-4 에서 예약 링크를 적으면 그 문자가 다시 나간다.
   사유를 안 적으면 스탭은 「보류」만 보고 누구에게 무엇을 말해야 할지
   모른다.

   **`RECIPIENT_NOT_APPROVED` 는 예외다** — KEY-338. 손댈 수 없다(보류는
   끝 상태고, 승인 목록은 배포 설정이라 스탭이 못 고친다). 그래도 적는다
   — KEY-6 운영 승인 전까지는 이 사유가 「검증 단계라 일부러 막았다」는
   뜻이다. 안 적으면 스탭이 그냥 안 나간 것으로 읽고 발송 실패를 의심해
   엉뚱한 곳을 고치려 든다. */
var HOLD_SAYING = {
  INVALID_PHONE: "번호",
  NO_CREDIT: "문자 잔량",
  BOOKING_URL_MISSING: "예약 링크 없음",
  RECIPIENT_NOT_APPROVED: "승인되지 않은 번호",
  SOURCE_NOT_DELETED: "원본 삭제 확인 필요 (SOURCE_NOT_DELETED)",
};

/* 한 통이 지금 어디에 있는가. **「예정」과 「못 나감」과 「보류」를 또렷이
   가른다.**

   실패와 보류를 한 무더기로 뭉치면 「이미 벌어진 것」과 「고치면 아직 막을 수
   있는 것」이 섞인다 — 스탭이 무엇을 손대야 하는지 안 보인다. 와이어프레임
   S2-3 도 「안 나간 것 3건 (실패 1 · 보류 2)」로 합쳐 세면서 따로 적는다. */
var MESSAGE_STATE = {
  SCHEDULED: { say: "예정", mark: "○", done: false, bad: false },
  SENT: { say: "발송 완료", mark: "●", done: true, bad: false },
  FAILED: { say: "발송 실패", mark: "⚠", done: false, bad: true },
  HELD: { say: "보류", mark: "⏸", done: false, bad: true },
  CANCELED: { say: "꺼짐", mark: "○", done: false, bad: false },
};

function messageState(status) {
  return (
    MESSAGE_STATE[status] || {
      say: String(status || ""),
      mark: "○",
      done: false,
      bad: false,
    }
  );
}

/** 그 줄에 적을 한 마디 — 「발송 실패」 · 「보류 · 문자 잔량」.
 *
 * **실패에는 까닭을 붙이지 않는다** (팀장 지적 2026-09-01). 나간 것이
 * 안 됐다는 것만 우리가 아는 사실이고, 「잘못된 번호」는 그 번호가 정말
 * 틀렸다는 뜻으로 읽힌다 — 확인할 방법이 없다. 코드(`failure_code`)는
 * 계속 담아 두되 화면이 단정하지 않는다.
 *
 * D1-7의 「사유를 보고 재시도한다」는 이 결정과 안 부딪힌다 — **재시도
 * 단추 자체**가 사유를 몰라도 뜬다(`canResend`는 `status`만 본다).
 * 사유를 사람 말로 보여 주지 않아도 다시 보낼 수는 있다.
 *
 * 보류는 다르다. **우리가 붙들기로 정한 것**이라 그 까닭을 우리가 안다.
 *
 * 모르는 코드는 **적지 않는다** — 코드를 그대로 보이면 사람 말이 아니다.
 */
function messageSaying(row) {
  var state = messageState(row && row.status);
  var why = row && row.status === "HELD" ? HOLD_SAYING[row.hold_reason] : null;
  var saying = why ? state.say + " · " + why : state.say;
  if (row && row.status === "HELD" && row.hold_reason === "SOURCE_NOT_DELETED") {
    var failures = {
      PURGE_RETRY_EXHAUSTED: "자동 삭제 재시도 소진",
      DELETION_RECORD_MISMATCH: "삭제 기록과 실제 파일 불일치",
      STORAGE_UNAVAILABLE: "저장소 확인 불가",
      PURGE_RETRY_FAILED: "삭제 또는 부재 확인 실패",
      RECOVERY_FAILED: "복구 처리 실패",
    };
    saying += " · " + (failures[row.source_failure_type] || "이전 보류 — 실패 유형 기록 없음");
    if (failures[row.source_failure_type]) saying += " (" + row.source_failure_type + ")";
    if (row.source_failure_at) {
      var stamp =
        typeof window.clinicStamp === "function"
          ? window.clinicStamp(row.source_failure_at)
          : String(row.source_failure_at).slice(0, 16).replace("T", " ");
      saying += " · " + stamp;
    }
    if (row.source_retry_requested) saying += " · 삭제 재시도 대기/처리 중";
  }
  return saying;
}

var sourceRetryRoles = [];
function sourceRetryButton(row) {
  if (!row || row.status !== "HELD" || row.hold_reason !== "SOURCE_NOT_DELETED" ||
      !sourceRetryRoles.some(function (role) { return role === "doctor" || role === "staff"; })) return "";
  return '<button type="button" class="button-ghost button-ghost--sm" data-source-retry="' +
    esc(row.guide_message_id) + '" data-generation="' + esc(row.source_retry_generation || 0) + '"' +
    (row.source_retry_requested ? " disabled" : "") + '>원본 삭제 재시도</button>';
}

function requestSourceRetry(button, onDone) {
  if (button.disabled) return;
  if (!window.confirm("원본 삭제와 파일 부재 확인을 다시 요청합니다. 성공하면 기존 문자가 발송됩니다. 진행할까요?")) return;
  button.disabled = true;
  button.textContent = "삭제 재시도 요청 중…";
  request("/messages/" + encodeURIComponent(button.dataset.sourceRetry) + "/source-retry", {
    method: "POST", body: { generation: Number(button.dataset.generation) },
  }).then(function () {
    button.textContent = "삭제 재시도 대기/처리 중";
    onDone();
  }).catch(function (error) {
    /* 409는 요청 결과를 모르는 네트워크 실패가 아니라, 워커가 이미 집었거나
       상태·세대가 바뀌었다는 확정 응답이다. 같은 세대로 버튼만 되살리면
       누를 때마다 같은 409가 반복되므로 최신 행을 다시 읽는다. */
    if (error && error.status === 409) {
      button.textContent = "상태 다시 확인 중…";
      onDone();
      return;
    }
    button.disabled = false;
    button.textContent = "원본 삭제 재시도";
    window.alert("요청 결과를 확인하지 못했습니다. 새로고침 후 상태를 확인해 주세요.");
  });
}

/** 「08-20 10:00」 — 날짜와 시각을 함께 적는다. 회차는 며칠 뒤라 날짜가 있어야 한다. */

/** 이 줄에 「다시 보내기」를 붙일 수 있는가 — D1-7.
 *
 * FAILED만 대상이다. HELD는 발송 게이트가 막은 상태라 사유만 보여 주고,
 * SCHEDULED는 아직 나갈 차례를 기다리는 중이라 다시 보낼 것이 없다.
 * SENT는 이미 갔고, CANCELED는 사람이 끈 것이라 이 화면의 재시도 대상이 아니다.
 *
 * KEY-306의 재발송은 **원본 메시지 하나당 한 번**만 새 작업을 만든다 —
 * 이미 재발송 요청이 걸려 있으면(원본이 아니라 재발송으로 생긴 행이면)
 * 또 누를 이유가 없다. `resend_of_message_id`는 서버 응답에 없으므로
 * (KEY-251 범위 밖 — 이 화면은 상태만 본다) 여기서는 상태만으로 가른다.
 */
function canResend(status) {
  return status === "FAILED";
}
