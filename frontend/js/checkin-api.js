/* D+7 확인 응답 API — KEY-98 (와이어프레임 P7-1~P7-6)
 *
 *   GET  /api/v1/checkins/{token}   무엇을 물을지 — 회차 · 약 · 선택지별 안내
 *   POST /api/v1/checkins/{token}   답을 저장한다
 *
 * 주소가 `visit_id` 가 아니라 **링크 토큰**인 것이 중요하다. 환자는 로그인하지
 * 않고 개발용 환자 링크로 들어온다. KEY-151은 KEY-90의 승인 안내 링크 검증을
 * 그대로 재사용하며, 실제 SMS와 운영용 OTP는 구현하지 않는다.
 *
 * ── 화면이 문구를 만들지 않는다 ─────────────────────────────
 *
 * 선택지를 눌렀을 때 펼쳐지는 안내는 **전부 서버가 준다.** 와이어프레임 P7-3 의
 * 노트가 그 이유를 적어 두었다 —
 *
 *   「새 의학 정보를 만들지 않는다. 주의사항에 이미 승인된 문장을 그대로 다시
 *    인용한 것이다. 약마다 다르므로 그 약의 문구를 가져온다 — 피임 효과가
 *    걸린 약은 규칙이 다르다.」
 *
 * 화면에 문장을 박아 두면 약이 바뀌어도 그대로 나가고, 그것은 **승인되지 않은
 * 의학 정보**가 된다. 원장님이 승인한 것만 환자에게 간다는 규칙이 여기서
 * 깨진다. 그래서 이 파일의 목업에도 「이 약의 문구」로 들어 있다.
 */

function checkinRequest(path, options) {
  options = options || {};
  if (MOCK) return mockCheckinRequest(path, options);
  return request(path, options);
}

var checkinApi = {
  read: function (token) {
    return checkinRequest("/checkins/" + encodeURIComponent(token));
  },
  save: function (token, answer) {
    /* KEY-151 최소 저장 계약은 복약·통증뿐이다. 목업은 KEY-138 신호 순번을
       계속 검증해야 하므로 전체 값을 쓰고, 실제 API에는 확정된 두 필드만 보낸다. */
    var body = MOCK ? answer : { medication: answer.medication, pain: answer.pain };
    return checkinRequest("/checkins/" + encodeURIComponent(token), { method: "POST", body: body });
  },

  /* D+7 저장에서 세션이 끝났을 때만 쓰는 재인증 경로 — KEY-128.

     안내·양식 조회는 링크 자체가 접근 증명이고, 쓰기만 30분 환자 세션을
     요구한다(KEY-92 확정 계약). 화면은 이 둘을 섞어 조회까지 새로 막지 않는다. */
  issueOtp: function (token) {
    return checkinRequest("/patient-auth/otp/issue", {
      method: "POST",
      body: { link_token: token },
    });
  },
  verifyOtp: function (token, code) {
    return checkinRequest("/patient-auth/otp/verify", {
      method: "POST",
      body: { link_token: token, code: code },
    });
  },

  /* 고르는 즉시 의료진 화면에 「이 환자를 봐 주세요」를 보낸다.

     **이것은 기록이 아니다.** 의무기록은 [저장] 이 남기는 답이고, 이 신호는
     「14:23 에 환자가 중단을 눌렀다」는 사실일 뿐이다. 나중에 답을 바꿔도 그
     사실은 참이라 앞 신호를 지우지 않는다 — `docs/api/patient.md` 3절.

     `session` · `sequence` 를 함께 싣는다. **보낸 순서와 닿는 순서가 다르기
     때문이다** — 첫 요청이 느리면 나중에 고른 답이 먼저 도착해서, 서버가
     받은 차례대로 믿으면 「지금 답」이 뒤집힌다.

     실패해도 화면을 막지 않는다. 환자는 자기가 알림을 보내는 줄 모른다. */
  signal: function (token, answerKey, stamp) {
    return checkinRequest("/checkins/" + encodeURIComponent(token) + "/signals", {
      method: "POST",
      body: {
        answer_key: answerKey,
        client_id: stamp.clientId,
        client_session_id: stamp.session,
        client_sequence: stamp.sequence,
      },
    });
  },
};

var PATIENT_LINK_CLOSED_CODES = ["LINK_EXPIRED", "LINK_NOT_FOUND", "LINK_REVOKED", "LINK_REISSUED"];

function isPatientLinkClosed(error) {
  var code = typeof error === "string" ? error : error && error.code;
  return PATIENT_LINK_CLOSED_CODES.indexOf(code) !== -1;
}

/* 서버 오류 코드를 환자가 이해할 수 있는 원인과 다음 행동으로 옮긴다.

   서버가 구분하지 않는 상태는 화면도 추측하지 않는다. `LINK_NOT_FOUND`는
   없는 링크·폐기·재발급으로 교체된 예전 링크를 같은 문구로 안내해 링크의
   내부 상태가 새지 않게 한다. 토큰·OTP 값은 인자로도 받지 않는다. */
function patientAuthGuidance(error) {
  var code = error && error.code;
  var data = (error && error.data) || {};
  var retry = Math.max(0, Number(data.retry_after_seconds) || 0);

  if (code === "PATIENT_SESSION_EXPIRED") {
    return {
      kind: "session",
      title: "본인 확인이 다시 필요해요",
      message:
        "인증 시간이 끝났거나 새로 접속했어요. 작성한 답은 이 화면에 그대로 두고 인증 후 저장할게요. 새로고침하거나 창을 닫으면 작성한 답이 사라져 다시 입력해야 해요.",
      action: "issue",
    };
  }
  if (code === "LINK_EXPIRED") {
    return {
      kind: "link-closed",
      title: "링크가 만료됐어요",
      message: "보내드린 링크는 3일 동안 열려 있어요. 병원에서 새 문자를 받으면 그 링크로 다시 들어와 주세요.",
      action: "latest-link",
    };
  }
  if (isPatientLinkClosed(error)) {
    return {
      kind: "link-closed",
      title: "이 링크는 더 이상 사용할 수 없어요",
      message: "폐기되었거나 새 링크로 바뀌었을 수 있어요. 병원에서 가장 최근에 받은 문자를 확인해 주세요.",
      action: "latest-link",
    };
  }
  if (code === "OTP_INVALID") {
    var remaining = Number(data.remaining_attempts);
    return {
      kind: "otp",
      title: "인증번호가 맞지 않아요",
      message: Number.isFinite(remaining)
        ? "문자로 받은 6자리 번호를 확인해 주세요. " + remaining + "번 더 입력할 수 있어요."
        : "문자로 받은 6자리 번호를 다시 확인해 주세요.",
      action: "verify",
    };
  }
  if (code === "OTP_LOCKED") {
    return {
      kind: "locked",
      title: "본인 확인에 여러 번 실패했어요",
      message: retry
        ? "안전을 위해 잠시 막았어요. " + Math.ceil(retry / 60) + "분 뒤 다시 시도해 주세요."
        : "잠금 시간을 확인하지 못했어요. 인증번호 받기를 다시 눌러 상태를 확인해 주세요.",
      action: retry ? "wait" : "retry",
      retryAfterSeconds: retry,
    };
  }
  if (code === "OTP_EXPIRED" || code === "OTP_ALREADY_USED" || code === "OTP_NOT_ISSUED") {
    return {
      kind: "otp-new",
      title: code === "OTP_EXPIRED" ? "인증번호가 만료됐어요" : "새 인증번호가 필요해요",
      message: "인증번호를 다시 받은 뒤 새 6자리 번호를 입력해 주세요.",
      action: "issue",
    };
  }
  if (code === "OTP_RESEND_TOO_SOON") {
    return {
      kind: "otp-wait",
      title: "인증번호를 이미 보내드렸어요",
      message: retry ? retry + "초 뒤에 다시 받을 수 있어요." : "잠시 뒤에 다시 받을 수 있어요.",
      action: "wait-resend",
      retryAfterSeconds: retry,
    };
  }
  if (code === "SMS_OPT_OUT") {
    return {
      kind: "contact",
      title: "인증번호를 보내드릴 수 없어요",
      message: "문자 수신 설정을 확인하려면 진료받으신 병원에 문의해 주세요.",
      action: "contact",
    };
  }
  if (code === "OTP_DELIVERY_UNAVAILABLE") {
    return {
      kind: "delivery",
      title: "인증번호 전송이 지연되고 있어요",
      message: "잠시 뒤 다시 시도해 주세요. 계속 받지 못하면 진료받으신 병원에 문의해 주세요.",
      action: "issue",
    };
  }
  return {
    kind: "retry",
    title: "잠시 연결하지 못했어요",
    message: "인터넷 연결을 확인한 뒤 다시 시도해 주세요.",
    action: "retry",
  };
}

function patientCheckinSaveFailureMessage(error) {
  var code = error && error.code;
  if (code === "CHECKIN_ALREADY_ANSWERED") {
    return "이미 저장된 기록이에요. 화면을 다시 열어 저장된 내용을 확인해 주세요.";
  }
  if (code === "INVALID_REQUEST" || code === "MEDICATION_REQUIRED" || code === "UNKNOWN_ANSWER") {
    return "입력한 내용을 확인한 뒤 다시 저장해 주세요.";
  }
  return "기록을 저장하지 못했어요. 잠시 뒤 다시 눌러 주세요. 계속되면 진료받으신 병원에 문의해 주세요.";
}

/* D+7 저장과 재인증 사이의 상태 전이만 떼어 낸다.

   DOM 을 흉내 낸 검사는 실제 브라우저 동작을 보장하지 못한다. 대신 환자 답을
   언제 들고 있고, 언제 다시 보내며, 언제 버리는지는 화면과 무관한 이 작은
   컨트롤러가 맡는다. `checkin.js`도 이 경로를 그대로 사용하므로 세션 만료 때
   답을 버리거나 재인증 뒤 저장을 빼거나 죽은 링크에서 답을 남기는 회귀가
   자동 검사에 걸린다. 답은 메모리에만 있고 브라우저 저장소에는 넣지 않는다. */
function createPatientAuthRecovery() {
  var pendingAnswer = null;

  return {
    onSaveFailed: function (error, answer) {
      var code = error && error.code;
      if (code === "PATIENT_SESSION_EXPIRED") {
        pendingAnswer = answer;
        return "reauth";
      }
      pendingAnswer = null;
      if (isPatientLinkClosed(error)) {
        return "link-closed";
      }
      return "form";
    },
    discardIfLinkClosed: function (error) {
      if (!isPatientLinkClosed(error)) return false;
      pendingAnswer = null;
      return true;
    },
    retryAfterVerification: function (retry) {
      if (pendingAnswer === null) return false;
      retry(pendingAnswer);
      return true;
    },
    complete: function () {
      pendingAnswer = null;
    },
  };
}

/* 한 화면이 신호를 언제 보낼지 정하는 자리 — KEY-138.

   **`checkin.js` 밖에 두는 이유가 있다.** 그 파일은 IIFE 로 감싸여 있어 검사가
   안을 부를 수 없다(`KEY-158` 이 다루는 문제다). 그런데 유가은 님이 요청한
   검사 넷은 전부 **이 판단**을 재는 것이다 — 순서 역전 · 연속 선택 · 실패 후
   정정 · 새로고침. 그래서 판단만 여기로 꺼내 검사가 닿게 한다.

   `checkin.js` 는 이것을 부르기만 한다. */
const SIGNAL_CLIENT_KEY = "checkinSignalClient";
const SIGNAL_SEQUENCE_KEY = "checkinSignalSequence";
const SIGNAL_SESSION_KEY = "checkinSignalSession";

function createSignalTracker(newId, deviceBox, tabBox) {
  /* 식별값이 셋인 이유 — 각각 다른 것을 가리킨다.

       client_id           기기 하나 (`localStorage`)   순번이 통하는 범위
       client_sequence     그 기기 안에서 단조증가        같은 기기 안의 앞뒤
       client_session_id   탭 하나 (`sessionStorage`)   어느 화면이 보냈나

     **순번은 기기 안에서만 뜻이 있다.** 다른 기기는 1 부터 시작하므로 큰
     번호가 나중이라는 보장이 없다 — 나중에 켠 기기의 답이 앞 기기의 큰
     번호에 막힌다. 그래서 서버는 `client_id` 가 같을 때만 순번으로 견주고,
     다르면 닿은 차례로 정한다. 기기가 다르면 사람이 옮겨 앉은 것이라
     사이가 벌어져 있어 도착 순서가 맞다.

     같은 기기 안에서는 새로고침·새 탭을 넘어 순번이 이어지므로, 새로고침
     직전에 떠난 지연 요청도 제대로 밀린다(유가은 님 `#79` 재검토).

     `client_session_id` 는 **탭마다 다르다.** 어느 화면이 보냈는지 되짚을
     때만 쓰고 판정에는 들어가지 않는다. */
  var device = deviceBox || (typeof localStorage !== "undefined" ? localStorage : null);
  var tab = tabBox || (typeof sessionStorage !== "undefined" ? sessionStorage : null);
  var mint = newId || defaultSessionId;

  var clientId = device && device.getItem(SIGNAL_CLIENT_KEY);
  if (!clientId) {
    clientId = mint();
    if (device) device.setItem(SIGNAL_CLIENT_KEY, clientId);
  }

  var session = tab && tab.getItem(SIGNAL_SESSION_KEY);
  if (!session) {
    session = mint();
    if (tab) tab.setItem(SIGNAL_SESSION_KEY, session);
  }

  var sequence = Number((device && device.getItem(SIGNAL_SEQUENCE_KEY)) || 0) || 0;

  /* `lastSent` 는 이어 가지 않는다. 새로고침하면 화면이 비어 있어 환자가
     다시 고르는데, 그것을 「연달아 같은 답」으로 접으면 아무 신호도 안 간다. */
  var lastSent = null;

  /* **마지막으로 나간 호출의 순번.** 실패 되돌리기를 값이 아니라 이것으로
     판정한다 — 아래 `failed()` 주석 참고. */
  var lastCall = null;

  return {
    clientId: clientId,
    session: session,

    /* 순번 하나를 뗀다. **답을 접지 않는다** — 저장처럼 「무조건 지금이 마지막」
       이어야 하는 호출이 쓴다. */
    mark: function () {
      /* 저장소를 매번 다시 읽는다. 다른 탭이 그 사이에 올려 뒀을 수 있다. */
      var shared = Number((device && device.getItem(SIGNAL_SEQUENCE_KEY)) || 0) || 0;
      sequence = Math.max(sequence, shared) + 1;
      if (device) device.setItem(SIGNAL_SEQUENCE_KEY, String(sequence));
      return { clientId: clientId, session: session, sequence: sequence };
    },

    next: function (answerKey) {
      /* **연달아** 같은 답을 다시 눌렀을 때만 접는다. `P7-2`~`P7-5` 는 펼침
         화면이라 설명을 읽으려고 눌렀다 되돌릴 수 있다. 다만 다른 답을 거쳐
         돌아온 것은 새 신호다. */
      if (!answerKey || answerKey === lastSent) return null;
      lastSent = answerKey;
      var stamp = this.mark();
      lastCall = stamp.sequence;
      return stamp;
    },

    /* 못 갔으면 되돌린다. 순번은 되돌리지 않는다 — 이미 나간 번호다.

       **값이 아니라 그 호출이 아직 마지막인지로 판정한다.** 값으로 보면 늦게
       실패한 옛 요청이 그 사이 되살아난 같은 값을 지운다 (이희진 님 `#79` 리뷰).

           taking/1 출발 → stopped/2 출발 → stopped/2 즉시 실패 → 지금 답 taking
           그 뒤 taking/1 이 늦게 실패 → 값만 보면 taking 을 지운다

       `1` 은 이미 마지막 호출이 아니므로 되돌리지 않는다. */
    failed: function (stamp, previous) {
      if (stamp && stamp.sequence === lastCall) {
        lastSent = previous;
        lastCall = null;
      }
    },

    lastSent: function () {
      return lastSent;
    },
  };
}

function defaultSessionId() {
  if (typeof crypto !== "undefined" && crypto.randomUUID) return crypto.randomUUID();
  // 구형 브라우저용. 신호 짝짓기에만 쓰므로 추측 불가성이 필요 없다.
  return "s-" + Math.random().toString(36).slice(2) + Date.now().toString(36);
}

/* 복약 답 다섯. **순서가 뜻을 만든다** — 잘 되는 쪽에서 안 되는 쪽으로 간다.
   「중단」을 둘로 나눈 것이 이 화면의 핵심이다. 같은 중단이라도
   불편해서 끊은 것과 좋아져서 끊은 것은 정반대의 설명이 필요하다. */
var MEDICATION_ANSWERS = ["taking", "uncomfortable", "missing", "stopped_side_effect", "stopped_improved"];

/* 아프다고 답했을 때만 묻는다. 유형은 자궁내막증 세트의 넷이다. */
var PAIN_TYPES = [
  { key: "menstrual", label: "월경통" },
  { key: "intercourse", label: "성교통" },
  { key: "defecation", label: "배변통" },
  { key: "chronic_pelvic", label: "만성골반통" },
];

/* ── 목업 ──────────────────────────────────────────────────────
 * 와이어프레임의 김서연(자궁내막증 · 비잔정(디에노게스트) 2mg)이 복약 7일째에 받은 링크다.
 *
 * ?case= 로 다른 상황을 본다.
 *   last     남은 확인 문자가 없을 때 — 완료 화면이 다음 진료일을 알린다
 *   expired  링크가 3일을 넘겼을 때
 *   done     이미 답한 회차
 *   session-expired  저장 때 재인증이 필요한 흐름 (합성 OTP 123456)
 *   locked   OTP 잠금 안내 (`t` 없이도 합성 링크로 진입)
 *   locked-no-retry  잠금 남은 시간을 받지 못한 복구 안내
 */
var CHECKIN_CASE = (function () {
  var q = new URLSearchParams(location.search).get("case");
  if (q !== null) sessionStorage.setItem("mockCheckinCase", q);
  return sessionStorage.getItem("mockCheckinCase") || "";
})();
var MOCK_PATIENT_AUTHENTICATED = false;

function mockCheckin() {
  return {
    round_label: "복약 7일째 · 첫 확인",
    drug_name: "비잔정(디에노게스트) 2mg",
    /* 선택지별 안내 — **승인된 주의사항에서 그대로 가져온 문장이다.**
       `notify` 는 의료진 화면에 알림을 만들지 여부다. 「가끔 놓쳐요」만
       false 인 이유는 P7-3 노트에 있다 — 응급이 아니고, 문의를 권하면
       「이건 문제다」로 읽혀 다음엔 솔직히 답하지 않게 된다. */
    answers: {
      taking: null,
      uncomfortable: {
        lead: "복용 초기 몇 달간 피가 조금씩 비칠 수 있어요. 흔한 반응입니다.",
        body: "대개 3개월 안에 줄어드니 그대로 드셔도 괜찮아요. 불편하신 점은 원장님께 전해드릴게요 — 다음 진료 때 함께 봐요.",
        urgent: {
          title: "🚨 이런 증상이면 바로 병원에 오세요",
          list: ["한쪽 다리가 붓고 아플 때", "갑자기 숨이 찰 때", "가슴이 아플 때"],
        },
        ask: true,
        notify: true,
      },
      missing: {
        lead: "괜찮아요. 가끔 놓치는 분이 많아요.",
        body: "복용을 잊으셨다면 생각난 즉시 드시고, 다음 약은 원래 시간에 드세요.",
        tips: ["매일 같은 시간에 알람을 맞춰 두세요", "칫솔처럼 매일 보는 자리에 약을 두세요"],
        note: "이 답은 기록으로만 남습니다 — 따로 연락드리지 않아요",
        ask: false,
        notify: false,
      },
      stopped_side_effect: {
        lead: "복용 초기 몇 달간 생리가 불규칙하거나 출혈이 있을 수 있어요. 흔한 반응입니다.",
        body: "임의로 중단하시면 치료가 어려워질 수 있어요. 병원에 문의해 주세요.",
        ask: true,
        notify: true,
      },
      stopped_improved: {
        lead: "좋아진 것은 약이 잘 듣고 있다는 뜻이에요.",
        body:
          "통증이 사라졌다고 병변까지 없어진 것은 아니라서, 지금 끊으면 다시 자랄 수 있어요. " +
          "끊을 시기는 진료 때 함께 정해요. 병원에 문의해 주세요.",
        ask: true,
        notify: true,
      },
    },
    pain_types: PAIN_TYPES,
    /* 완료 화면이 알릴 다음 일정. **날짜를 사람이 넣지 않는다** —
       안내문이 나간 날을 0일로 놓고 회차에서 계산한다(P7-1 노트). */
    next_checkin: CHECKIN_CASE === "last" ? null : "8월 20일 (목)",
    next_visit: "11월 11일 (수)",
    answered: CHECKIN_CASE === "done",
  };
}

/* 쌓인 신호. append-only 라 지우지 않는다 — **지금 답은 「가장 나중 것」이다.**

   「가장 나중」을 받은 차례로 정하면 안 된다. 첫 요청이 느리면 나중에 고른 답이
   먼저 닿아서 순서가 뒤집힌다. 그래서 `(session, sequence)` 로 판정한다. */
var MOCK_SIGNALS = [];

/* 두 신호 중 어느 쪽이 나중인가.

   **같은 기기면 `sequence`, 다른 기기면 닿은 차례.**

   순번은 기기 안에서만 뜻이 있다. 다른 기기는 1 부터 시작하므로 큰 번호가
   나중이라는 보장이 없다 — 나중에 켠 기기의 답이 앞 기기의 큰 번호에 막힌다
   (유가은 님 `#79` 재검토). 기기가 다르면 사람이 옮겨 앉은 것이라 사이가
   벌어져 있어 도착 순서가 맞다.

   같은 기기 안에서는 새로고침·새 탭을 넘어 순번이 이어지므로, 새로고침 직전에
   떠난 지연 요청도 순번으로 제대로 밀린다. */
function mockSignalIsNewer(candidate, current) {
  if (!current) return true;
  /* **저장에도 같은 규칙을 쓴다.** 예전에는 `from_save` 면 무조건 도착 차례로
     갈랐는데, 그러면 저장이 든 순번을 아무도 안 읽어 「늘 가장 나중」이 실제로는
     도착 차례에 기대는 상태가 됐다 (이희진 님 `#79` 리뷰). 저장이 자기 순번을
     들고 오면 특례가 필요 없다 — 같은 기기면 순번, 다른 기기면 도착 차례. */
  if (candidate.client_id && candidate.client_id === current.client_id) {
    return candidate.sequence > current.sequence;
  }
  return candidate.received > current.received;
}

function mockCurrentSignal() {
  return MOCK_SIGNALS.reduce(function (best, one) {
    return mockSignalIsNewer(one, best) ? one : best;
  }, null);
}

function mockCheckinRequest(path, options) {
  var body = options.body || {};
  return new Promise(function (resolve, reject) {
    setTimeout(function () {
      if (CHECKIN_CASE === "expired") {
        // 링크는 3일 뒤 닫힌다(P8 노트). 만료는 오류가 아니라 안내다.
        return reject(new ApiError("LINK_EXPIRED", 410, {}));
      }
      if (path === "/patient-auth/otp/issue") {
        if (CHECKIN_CASE === "locked") {
          return reject(new ApiError("OTP_LOCKED", 429, { retry_after_seconds: 600 }));
        }
        if (CHECKIN_CASE === "locked-no-retry") return reject(new ApiError("OTP_LOCKED", 429, {}));
        return resolve({ expires_at: new Date(Date.now() + 180000).toISOString(), retry_after_seconds: 60 });
      }
      if (path === "/patient-auth/otp/verify") {
        if (body.code !== "123456") {
          return reject(new ApiError("OTP_INVALID", 401, { remaining_attempts: 4 }));
        }
        MOCK_PATIENT_AUTHENTICATED = true;
        return resolve({ verified: true, session_expires_in_seconds: 1800 });
      }
      /* 신호는 저장보다 먼저 온다. 화면은 **고른 것을 그대로** 보내고, 알릴지는
         여기서 정한다 — 그래야 답을 바꿨을 때 앞 신호가 덮인다. */
      if (options.method === "POST" && /\/signals$/.test(path)) {
        var key = body.answer_key;
        if (MEDICATION_ANSWERS.indexOf(key) === -1) {
          return reject(new ApiError("UNKNOWN_ANSWER", 400, {}));
        }
        var info = mockCheckin().answers[key];
        var record = {
          answer_key: key,
          client_id: body.client_id,
          session: body.client_session_id,
          sequence: body.client_sequence,
          received: MOCK_SIGNALS.length, // 닿은 차례 — 기기가 다를 때만 쓴다
        };
        /* **늦게 닿은 옛 신호도 버리지 않는다.** 「14:23 에 중단을 눌렀다」는
           그것대로 참이라 이력에 남는다. 다만 「지금 답」 판정에서 밀릴 뿐이다. */
        MOCK_SIGNALS.push(record);
        var current = mockCurrentSignal();
        return resolve({
          signal_id: 8800 + MOCK_SIGNALS.length,
          answer_key: key,
          // `missing`(가끔 놓쳐요)은 여기서 조용해진다. 기록은 남고 연락은 안 간다.
          notify: !!(info && info.notify),
          // 이 신호가 「지금 답」이 됐는지. 늦게 닿은 옛 신호면 false 다.
          current: current === record,
          current_answer_key: current ? current.answer_key : null,
        });
      }

      if (options.method === "POST") {
        if (
          (CHECKIN_CASE === "session-expired" || CHECKIN_CASE === "locked" || CHECKIN_CASE === "locked-no-retry") &&
          !MOCK_PATIENT_AUTHENTICATED
        ) {
          return reject(new ApiError("PATIENT_SESSION_EXPIRED", 401, {}));
        }
        if (MEDICATION_ANSWERS.indexOf(body.medication) === -1) {
          return reject(new ApiError("MEDICATION_REQUIRED", 422, {}));
        }
        /* **저장이 마지막으로 바로잡는다.** 신호가 하나도 못 갔거나 마지막
           것만 실패했으면 서버에는 옛 답이 「지금 답」으로 남아 있다. 저장은
           환자가 확정한 답이라, 그것으로 신호 상태를 맞춘다.

           신호를 지우지는 않는다 — 눌렀던 사실은 그대로 두고 판정만 옮긴다. */
        /* **저장도 신호와 같은 규칙으로 판정한다.**

           예전에는 `sequence` 에 고정값(`Number.MAX_SAFE_INTEGER`)을 박아
           「늘 가장 나중」을 표현했다. 그러면 저장을 두 번 했을 때 두 값이
           같아져 뒤엣것이 앞엣것을 못 덮는다 — 지금까지는 아래 비교가
           `from_save` 를 만나면 도착 차례로 새 버리고 있어서 **그 고정값을
           아무도 안 읽었다.** 죽은 값이 옳은 것처럼 보이던 자리다
           (이희진 님 `#79` 리뷰).

           화면이 저장 시점에 뗀 순번을 그대로 쓴다. 같은 기기에서는 저장이
           늘 마지막에 뗀 번호라 자연히 가장 나중이고, 다른 기기면 신호와
           똑같이 도착 차례로 견준다. 특례가 필요 없다. */
        MOCK_SIGNALS.push({
          answer_key: body.medication,
          client_id: body.client_id || null,
          session: body.client_session_id || "save",
          sequence: body.client_sequence || 0,
          received: MOCK_SIGNALS.length,
          /* 판정에는 안 쓴다. 「이건 저장이 바로잡은 것」이라는 표시일 뿐이다. */
          from_save: true,
        });
        return resolve({
          /* 저장 뒤 「복약지도 다시 보기」가 갈 곳. 화면은 `visit_id` 를 모르고
             토큰만 안다 — 어느 진료인지는 서버가 안다. 그래서 **서버가 주소를
             만들어 준다**. 안 주면 화면이 링크를 안 그린다 (`#55` 리뷰). */
          guide_url: "/guide.html?visit=8801",
          saved: true,
          medication: body.medication,
          pain: body.pain,
          /* 정정한 결과를 돌려준다. 이것이 없으면 **저장이 신호를 맞췄는지
             밖에서 확인할 방법이 없다** — 확인하려고 신호를 하나 더 보내면
             그것이 지금 답이 돼 버려서 정작 재려던 것을 가린다. */
          signal_answer_key: (mockCurrentSignal() || {}).answer_key || null,
          next_checkin: mockCheckin().next_checkin,
          next_visit: mockCheckin().next_visit,
        });
      }
      return resolve(mockCheckin());
    }, 200);
  });
}
