/* D+7 확인 응답 API — KEY-98 (와이어프레임 P7-1~P7-6)
 *
 *   GET  /api/v1/checkins/{token}   무엇을 물을지 — 회차 · 약 · 선택지별 안내
 *   POST /api/v1/checkins/{token}   답을 저장한다
 *
 * 주소가 `visit_id` 가 아니라 **링크 토큰**인 것이 중요하다. 환자는 로그인하지
 * 않고 문자로 받은 주소로 들어온다. 토큰 발급·검증은 `P1` 몫이라 아직 없다 —
 * 여기서는 계약만 적어 두고 `?mock=1` 로 확인한다.
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
    return checkinRequest("/checkins/" + encodeURIComponent(token), { method: "POST", body: answer });
  },

  /* 고르는 즉시 의료진 화면에 「이 환자를 봐 주세요」를 보낸다.

     **이것은 기록이 아니다.** 의무기록은 [저장] 이 남기는 답이고, 이 신호는
     「14:23 에 환자가 중단을 눌렀다」는 사실일 뿐이다. 나중에 답을 바꿔도 그
     사실은 참이라 앞 신호를 지우지 않는다 — `docs/api/patient.md` 3절.

     `session` · `sequence` 를 함께 싣는다. **보낸 순서와 닿는 순서가 다르기
     때문이다** — 첫 요청이 느리면 나중에 고른 답이 먼저 도착해서, 서버가
     받은 차례대로 믿으면 「지금 답」이 뒤집힌다.

     실패해도 화면을 막지 않는다. 환자는 자기가 알림을 보내는 줄 모른다. */
  signal: function (token, answerKey, session, sequence) {
    return checkinRequest("/checkins/" + encodeURIComponent(token) + "/signals", {
      method: "POST",
      body: {
        answer_key: answerKey,
        client_session_id: session,
        client_sequence: sequence,
      },
    });
  },
};

/* 한 화면이 신호를 언제 보낼지 정하는 자리 — KEY-138.

   **`checkin.js` 밖에 두는 이유가 있다.** 그 파일은 IIFE 로 감싸여 있어 검사가
   안을 부를 수 없다(`KEY-158` 이 다루는 문제다). 그런데 유가은 님이 요청한
   검사 넷은 전부 **이 판단**을 재는 것이다 — 순서 역전 · 연속 선택 · 실패 후
   정정 · 새로고침. 그래서 판단만 여기로 꺼내 검사가 닿게 한다.

   `checkin.js` 는 이것을 부르기만 한다. */
const SIGNAL_SESSION_KEY = "checkinSignalSession";
const SIGNAL_SEQUENCE_KEY = "checkinSignalSequence";

function createSignalTracker(newId, box) {
  /* **순번을 기기 하나에서 이어 간다.** 새로고침해도, 탭을 새로 열어도, 다음
     번호를 받는다.

     화면마다 1 부터 다시 시작하면 두 화면을 견줄 수가 없다. 서버가 「먼저 본
     쪽이 앞」으로 정해도 안 된다 — 새로고침 직전에 **이미 출발해 지연 중이던**
     요청은 나중에 닿으므로 오히려 늦게 본 것이 된다. 유가은 님이 `#79`
     재검토에서 그 경우를 재현해 주셨다.

     그래서 **누가 앞인지를 화면 쪽에서 정한다.** 순번은 기기에 남는 저장소
     (`localStorage`)에 두어 탭과 새로고침을 넘어 단조증가한다. 망이 어떻게
     흔들려도 순서는 뒤집히지 않는다.

     `session` 은 어느 화면이 보냈는지 되짚을 때만 쓴다 — 판정에는 안 들어간다. */
  var store = box || (typeof localStorage !== "undefined" ? localStorage : null);
  var session = store && store.getItem(SIGNAL_SESSION_KEY);
  if (!session) {
    session = (newId || defaultSessionId)();
    if (store) store.setItem(SIGNAL_SESSION_KEY, session);
  }
  var sequence = Number((store && store.getItem(SIGNAL_SEQUENCE_KEY)) || 0) || 0;

  /* `lastSent` 는 이어 가지 않는다. 새로고침하면 화면이 비어 있어 환자가
     다시 고르는데, 그것을 「연달아 같은 답」으로 접으면 아무 신호도 안 간다. */
  var lastSent = null;

  return {
    session: session,

    /* 보낼 것이면 `{ session, sequence }` 를, 안 보낼 것이면 `null` 을 준다. */
    next: function (answerKey) {
      /* **연달아** 같은 답을 다시 눌렀을 때만 접는다. `P7-2`~`P7-5` 는 펼침
         화면이라 설명을 읽으려고 눌렀다 되돌릴 수 있다. 다만 다른 답을 거쳐
         돌아온 것은 새 신호다 — 아니면 마지막 신호가 실제로 고른 답과
         어긋난다. */
      if (!answerKey || answerKey === lastSent) return null;
      lastSent = answerKey;
      /* 저장소를 매번 다시 읽는다. 다른 탭이 그 사이에 올려 뒀을 수 있다. */
      var shared = Number((store && store.getItem(SIGNAL_SEQUENCE_KEY)) || 0) || 0;
      sequence = Math.max(sequence, shared) + 1;
      if (store) store.setItem(SIGNAL_SEQUENCE_KEY, String(sequence));
      return { session: session, sequence: sequence };
    },

    /* 못 갔으면 되돌린다. 다시 누르면 한 번 더 가야 한다.

       순번은 **되돌리지 않는다.** 이미 나간 번호이고, 서버는 큰 쪽을 나중으로
       보므로 비워 두는 편이 안전하다. */
    failed: function (answerKey, previous) {
      if (lastSent === answerKey) lastSent = previous;
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
 * 와이어프레임의 김서연(자궁내막증 · 비잔 2mg)이 복약 7일째에 받은 링크다.
 *
 * ?case= 로 다른 상황을 본다.
 *   last     남은 확인 문자가 없을 때 — 완료 화면이 다음 진료일을 알린다
 *   expired  링크가 3일을 넘겼을 때
 *   done     이미 답한 회차
 */
var CHECKIN_CASE = (function () {
  var q = new URLSearchParams(location.search).get("case");
  if (q !== null) sessionStorage.setItem("mockCheckinCase", q);
  return sessionStorage.getItem("mockCheckinCase") || "";
})();

function mockCheckin() {
  return {
    round_label: "복약 7일째 · 첫 확인",
    drug_name: "비잔정 2mg",
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

/* 두 신호 중 어느 쪽이 나중인가 — **`sequence` 하나로 정한다.**

   순번은 화면이 매기고 기기 하나에서 단조증가한다. 그래서 새로고침이든 새 탭이든
   비교가 선다. 도착 순서는 보지 않는다 — 그것으로 정하면 지연된 옛 요청이 새
   답을 덮는다(유가은 님 `#79` 재검토). */
function mockSignalIsNewer(candidate, current) {
  if (!current) return true;
  return candidate.sequence > current.sequence;
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
          session: body.client_session_id,
          sequence: body.client_sequence,
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
        if (MEDICATION_ANSWERS.indexOf(body.medication) === -1) {
          return reject(new ApiError("MEDICATION_REQUIRED", 422, {}));
        }
        /* **저장이 마지막으로 바로잡는다.** 신호가 하나도 못 갔거나 마지막
           것만 실패했으면 서버에는 옛 답이 「지금 답」으로 남아 있다. 저장은
           환자가 확정한 답이라, 그것으로 신호 상태를 맞춘다.

           신호를 지우지는 않는다 — 눌렀던 사실은 그대로 두고 판정만 옮긴다. */
        MOCK_SIGNALS.push({
          answer_key: body.medication,
          session: "save",
          /* 저장은 환자가 확정한 답이라 **늘 가장 나중**이다. 지연 중이던
             신호가 뒤에 닿아도 이것을 못 덮게 가장 큰 번호를 준다. */
          sequence: Number.MAX_SAFE_INTEGER,
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
