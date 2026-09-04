/* 의사 검토·승인 API — KEY-86
 *
 * 안내문을 읽고, 고치고, 승인하거나 스탭에게 되돌린다.
 *
 *   GET   /api/v1/visits/{visit_id}/guide                안내문 네 갈래 + ⚠ 표시
 *   PATCH /api/v1/visits/{visit_id}/guide/sections/{key}  그 항목만 고친다
 *   POST  /api/v1/visits/{visit_id}/guide/approve         승인 — 발송 예약
 *   POST  /api/v1/visits/{visit_id}/guide/unapprove       승인 철회 — 예약 끄기
 *   GET   /api/v1/visits/{visit_id}/guide/messages        문자 설정 읽기
 *   PUT   /api/v1/visits/{visit_id}/guide/messages        문자 설정 저장
 *   POST  /api/v1/visits/{visit_id}/guide/return          스탭에 되돌린다 (사유 필수)
 *   POST  /api/v1/visits/{visit_id}/guide/link            환자 링크 한 번 발급
 *   POST  /api/v1/visits/{visit_id}/guide/link/re-issue   기존 링크 교체
 *   DELETE /api/v1/visits/{visit_id}/guide/link            현재 링크 폐기
 *
 * **서버가 생겼습니다(KEY-111).** 이 파일은 이제 그 응답 모양을 그대로 흉내
 * 냅니다 — 예전에는 화면이 바라는 모양을 적어 두었는데 서버와 달라서
 * `?mock=0` 이 안 됐습니다. 정본은 `app/dtos/guides.py` 입니다.
 *
 * 상태 이름은 이미 얼어 있는 것을 그대로 씁니다 —
 * `docs/api/hospital.md` §6 의 `APPROVAL_PENDING`(승인 요청) ·
 * `APPROVAL_RETURNED`(보완). 화면이 새 이름을 만들지 않습니다.
 */

function doctorRequest(path, options) {
  options = options || {};
  if (MOCK) return mockDoctorRequest(path, options);
  return request(path, options);
}

var doctorApi = {
  guide: function (visitId) {
    return doctorRequest("/visits/" + encodeURIComponent(visitId) + "/guide");
  },
  editSection: function (visitId, section, body) {
    return doctorRequest("/visits/" + encodeURIComponent(visitId) + "/guide/sections/" + section, {
      method: "PATCH",
      body: body,
    });
  },
  /* 스탭이 확인을 마치고 의사에게 넘긴다 — 와이어프레임 S1-11.
     이 자리가 없어서 안내문이 만들어지자마자 원장님 목록에 떴다. */
  submit: function (visitId) {
    return doctorRequest("/visits/" + encodeURIComponent(visitId) + "/guide/submit", {
      method: "POST",
    });
  },

  /* 이 진료에 무슨 일이 있었는지 — 와이어프레임 D1-6.
     사람이 한 일 · 환자가 한 일 · 확인 응답을 한 줄기로 준다. */
  timeline: function (visitId) {
    return doctorRequest("/visits/" + encodeURIComponent(visitId) + "/timeline");
  },

  approve: function (visitId, body) {
    return doctorRequest("/visits/" + encodeURIComponent(visitId) + "/guide/approve", {
      method: "POST",
      body: body || {},
    });
  },
  /* 문자 설정 — 회차 · 문구 · 시각 (와이어프레임 S1-14).
     한 판을 통째로 주고받는다. 회차 하나씩 보내면 중간에 끊겼을 때
     「보름 뒤는 껐는데 한 달 뒤는 안 켜진」 반쪽 상태가 남는다. */
  messagePlan: function (visitId) {
    return doctorRequest("/visits/" + encodeURIComponent(visitId) + "/guide/messages");
  },

  saveMessagePlan: function (visitId, plan) {
    return doctorRequest("/visits/" + encodeURIComponent(visitId) + "/guide/messages", {
      method: "PUT",
      body: plan,
    });
  },

  /* 승인을 거둔다 — 승인했는데 잘못된 것을 발견했을 때 (와이어프레임 D1-6).
     이미 나간 문자가 있으면 서버가 409 `GUIDE_ALREADY_SENT` 로 막는다. */
  unapprove: function (visitId) {
    return doctorRequest("/visits/" + encodeURIComponent(visitId) + "/guide/unapprove", {
      method: "POST",
    });
  },

  issuePatientLink: function (visitId) {
    return doctorRequest("/visits/" + encodeURIComponent(visitId) + "/guide/link", {
      method: "POST",
    });
  },
  reIssuePatientLink: function (visitId) {
    return doctorRequest("/visits/" + encodeURIComponent(visitId) + "/guide/link/re-issue", {
      method: "POST",
    });
  },
  revokePatientLink: function (visitId) {
    return doctorRequest("/visits/" + encodeURIComponent(visitId) + "/guide/link", {
      method: "DELETE",
    });
  },
  /* 되돌리기에는 **사유가 반드시 붙는다.** 스탭의 알림에 그대로 뜨는 문장이라
     (와이어프레임 D1-7 「승인 반려 — 진료기록 재업로드 필요」) 없으면
     받는 사람이 무엇을 고쳐야 하는지 알 수 없다. */
  returnToStaff: function (visitId, reason) {
    return doctorRequest("/visits/" + encodeURIComponent(visitId) + "/guide/return", {
      method: "POST",
      body: { reason: reason },
    });
  },
};

/* 되돌리는 이유는 대개 넷 중 하나다. 진료 중에 문장을 짓게 하면
   그 시간이 아까워 그냥 승인해 버린다 — 고르고 필요하면 덧붙인다. */
var RETURN_REASONS = [
  "진료기록 재업로드 필요",
  "판독 값이 실제와 다름",
  "안내 문구 수정 필요",
  "처방 내용이 다름",
];

/* ── 목업 ──────────────────────────────────────────────────────
 * 와이어프레임 D1-1~D1-4 의 김서연(차트 12345 · 2026-08-13 진료)을 옮겼다.
 * 자궁내막증 · 비잔 2mg · 84일.
 *
 * ?case= 로 다른 상황을 본다.
 *   staff     스탭 확인 중(STAFF_REVIEW) 화면 — 승인·되돌리기가 잠긴다
 *   returned  이미 되돌린 건
 *   clean     ⚠ 가 하나도 없는 건 — 읽지 않고 승인해도 되는 상태
 *   approved  승인 완료 건 — 환자 본인 확인 연결을 확인하는 상태
 */
var DOCTOR_CASE = (function () {
  var q = new URLSearchParams(location.search).get("case");
  if (q !== null) sessionStorage.setItem("mockDoctorCase", q);
  return sessionStorage.getItem("mockDoctorCase") || "";
})();

/* 목록의 줄마다 다른 안내문을 갖는다.
   하나만 돌려주면 줄을 눌러도 오른쪽이 안 바뀌어, **고르기가 고장난 것처럼**
   보인다. 실제 서버는 visit_id 로 갈라 주므로 목업도 그렇게 한다.

   **여기 없는 진료는 없는 것으로 답한다** (`mockGuideBase` 참고). 예전에는
   `|| MOCK_GUIDE_PATIENTS[8801]` 로 김서연을 대신 돌려줬는데, 목록에서 박수빈
   (`8798`)을 눌러도 오른쪽에 김서연이 떴다 — **의무기록 화면이 다른 사람을
   보여 주는 것**이라 「고르기가 고장난 것처럼」보다 나쁘다.

   목록(`patients-api.js`)에서 의사 화면에 닿을 수 있는 줄은 셋이다.
     8798  박수빈  NEEDS_ATTENTION       보완 탭
     8801  김서연  APPROVAL_REQUESTED    승인 요청 탭
     8802  최다인  APPROVAL_REQUESTED    승인 요청 탭
   값은 목록 쪽과 같은 것을 쓴다 — 두 곳이 다르면 그 자체가 또 어긋남이다.

   **이름을 `MOCK_PATIENTS` 로 두면 안 된다.** `patients-api.js` 가 같은 이름의
   **배열**을 이미 전역에 얹는데, 한 화면이 둘 다 싣는다(`patients.html`).
   나중에 실린 이쪽이 앞의 것을 통째로 덮어서, 목록 목업이 `.find is not a
   function` 으로 죽었다 — 화면은 「환자가 없습니다」만 띄웠다. 파일은 모듈이
   아니라 전역에 얹히는 스크립트라, 이름이 곧 자리다. */
var MOCK_GUIDE_PATIENTS = {
  8798: {
    patient: { name: "박수빈", birth_date: "1992-09-18", age: 34, gender: "FEMALE", hospital_patient_no: "09871" },
    summary: "자궁내막증 · 비잔 (계속) · 84일 · 지난 방문 08-11",
    /* 목록이 `INVALID_PHONE` 로 보완에 올린 줄이다. 안내문 자체는 승인을
       기다리는 중이고, 막힌 것은 **보낼 곳**이라 상태는 그대로 둔다. */
  },
  8801: {
    patient: { name: "김서연", birth_date: "1990-03-14", age: 36, gender: "FEMALE", hospital_patient_no: "12345" },
    summary: "자궁내막증 · 비잔 (계속) · 84일 · 지난 방문 05-20",
  },
  8802: {
    patient: { name: "최다인", birth_date: "1997-06-02", age: 29, gender: "FEMALE", hospital_patient_no: "10982" },
    summary: "다낭성 · 야즈 (계속) · 84일 · 지난 방문 06-02",
  },
};

/* 서버 `GuideResponse` 를 그대로 흉내 낸다 — `app/dtos/guides.py`.

   섹션은 **본문 한 덩이**(`body`)다. 제목·표·목록으로 쪼갠 예전 모양은 렌더
   편의였지 계약이 아니었고, 8/27 여정에서 안내문은 고정 텍스트다(KEY-150).

   `warn` 은 **서버가 판정한다.** 「AI 가 자신 없는 곳」을 화면이 알 수 없다. */
/* 승인·반려·섹션 수정이 남긴 상태. **진료 번호마다 하나**, 필드를 부분
   갱신한다(승인이 반려로 남긴 사유를 지우지 않는 식).

   예전에는 `mockGuide()` 가 매번 새로 만들고 승인 핸들러가 그 사본을 고쳐
   돌려줬다 — 승인해도 다음 조회는 다시 「승인 요청」이라 목업으로는
   `GUIDE_NOT_PENDING` 같은 상태 규칙을 아예 잴 수 없었다. */
var MOCK_GUIDE_STATE = {};

/* 이 진료의 저장 칸을 돌려준다. 없으면 만들어서 돌려준다 — 승인·반려·PATCH가
   같은 객체를 부분 갱신하므로, 한쪽이 통째로 덮어써 다른 쪽 값을 지우는 일이
   없다(예: 섹션을 고친 뒤 승인해도 그 수정은 남는다). */
/* D1-6 현황이 읽는 이력 — 서버 `GET /visits/{id}/timeline` 과 **같은 모양**
   이어야 한다. 다르면 목업에서만 되는 화면이 생긴다.

   `messages` 는 안내문이 승인된 뒤에만 찬다 — 예약은 승인이 만든다. 그래서
   여기서도 상태를 보고 낸다. */

function mockGuideState(visitId) {
  return (
    MOCK_GUIDE_STATE[visitId] ||
    (MOCK_GUIDE_STATE[visitId] = {
      status: null,
      approved_at: null,
      scheduled_at: null,
      returned_reason: null,
      patient_link_issued: false,
      sections: {},
    })
  );
}

/* 현황(D1-6)이 읽는 이력. **서버가 만들지 않는 사건은 여기서도 안 만든다** —
   `app/timeline/api.py` 가 안내문 사건과 예약 문자만 모아 주므로 목업도 그만 준다.

   안내문이 없는 진료는 **빈 이력**이다. 오류가 아니다 — 아직 아무 일도 안
   일어난 진료와 같은 모양이라, 화면이 「기록이 아직 없습니다」를 그린다. */
function mockTimeline(visitId) {
  var guide = mockGuide(visitId);
  if (!guide) return { visit_id: visitId, entries: [], messages: [] };

  var state = mockGuideState(visitId);

  /* 진료가 열린 것이 첫 줄이다 — 등록만 하고 아무것도 안 한 진료의 화면이
     통째로 비지 않게. 서버가 `visit.visited_at` 에서 만들어 낸다. */
  var made = [
    entry("2026-09-02T09:02:00+09:00", "VISIT", "VISIT_CREATED", { actor_id: 900, actor: "박연" }),
    entry("2026-09-02T09:08:00+09:00", "DOCUMENT", "DOCUMENT_UPLOADED", {
      actor_id: 101,
      actor: "한소영",
      document_type: "EMR",
    }),
    entry("2026-09-02T09:09:00+09:00", "OCR", "OCR_STARTED", { actor_id: 101, actor: "한소영" }),
    entry("2026-09-02T09:11:00+09:00", "OCR", "OCR_COMPLETED", {}),
    entry("2026-09-02T09:13:00+09:00", "OCR", "OCR_CONFIRMED", { actor_id: 101, actor: "한소영" }),
    entry("2026-09-02T09:14:00+09:00", "GUIDE", "GUIDE_GENERATED", {}),
    entry("2026-09-02T09:31:00+09:00", "GUIDE", "GUIDE_EDITED", {
      actor_id: 101,
      actor: "한소영",
      section_key: "caution",
    }),
    entry("2026-09-02T09:36:00+09:00", "GUIDE", "GUIDE_SUBMITTED", { actor_id: 101, actor: "한소영" }),
  ];
  if (state.returned_reason) {
    made.push(
      entry("2026-09-02T10:02:00+09:00", "GUIDE", "GUIDE_RETURNED", {
        actor_id: 900,
        actor: "박연",
        note: state.returned_reason,
      }),
    );
  }
  if (guide.status === "SCHEDULED_TO_SEND") {
    made.push(entry("2026-09-02T10:12:00+09:00", "GUIDE", "GUIDE_APPROVED", { actor_id: 900, actor: "박연" }));
    /* 환자가 한 일 — **행위자는 비운다.** 화면이 `category` 로 「환자」라고
       적는다. 서버가 「환자」를 적어 보내면 이름이 「환자」인 직원과 못 가른다. */
    made.push(entry("2026-09-02T14:12:00+09:00", "PATIENT", "GUIDE_VIEWED", { section_key: "medication" }));
    made.push(entry("2026-09-02T14:15:00+09:00", "PATIENT", "GUIDE_VIEWED", { section_key: "caution" }));
  }

  /* **예약은 승인이 만든다.** 승인 전에는 비어 있다 — 서버 주석이 그렇게 적었고,
     미리 채워 두면 「승인 안 했는데 나갈 문자가 있다」로 읽힌다.

     칸 이름은 `at` 이다(`scheduled_at` 이 아니다) — 이력 항목과 같은 이름을
     쓴다. 화면이 두 목록을 같은 함수로 찍는다. */
  var messages =
    guide.status === "SCHEDULED_TO_SEND"
      ? [
          sending("GUIDE", "SENT", "2026-09-02T18:00:00+09:00", "2026-09-02T18:00:12+09:00"),
          sending("CHECK_D7", "SCHEDULED", "2026-09-09T18:00:00+09:00", null),
          sending("CHECK_D15", "SCHEDULED", "2026-09-17T18:00:00+09:00", null),
          sending("RUN_OUT", "SCHEDULED", "2026-11-22T18:00:00+09:00", null),
        ]
      : [];

  return { visit_id: visitId, entries: made, messages: messages };
}

/* 이력 한 줄 — **칸을 다 채운다.** 서버는 없는 값도 `null` 로 내려 주는데,
   목업이 칸을 빼면 「목업에만 있는 `undefined`」가 생겨 화면이 갈린다. */
function entry(at, category, event, over) {
  var row = {
    at: at,
    category: category,
    event: event,
    actor_id: null,
    actor: null,
    section_key: null,
    document_type: null,
    note: null,
  };
  for (var key in over) if (over.hasOwnProperty(key)) row[key] = over[key];
  return row;
}

function sending(kind, status, at, sentAt) {
  return { kind: kind, status: status, at: at, sent_at: sentAt, failure_code: null, hold_reason: null };
}

/* 모르는 진료는 **없다고 답한다.** 서버(`app/services/guides.py`)가 그 자리에서
   `404 GUIDE_NOT_FOUND` 를 주므로 목업도 같게 한다.

   예전에는 `|| MOCK_GUIDE_PATIENTS[8801]` 로 김서연을 대신 돌려줬다. 조용히 남의
   이름을 그리는 쪽이라 **화면은 멀쩡해 보이는데 다른 사람의 안내문**이 된다 —
   의무기록에서 제일 나쁜 실패다. 없으면 없다고 하는 편이 낫다. */
function mockGuideBase(visitId) {
  var warn = DOCTOR_CASE !== "clean";
  var who = MOCK_GUIDE_PATIENTS[visitId];
  if (!who) return null;
  return {
    visit_id: visitId,
    patient: who.patient,
    summary: who.summary,
    status:
      DOCTOR_CASE === "returned"
        ? "APPROVAL_RETURNED"
        : DOCTOR_CASE === "approved"
          ? "SCHEDULED_TO_SEND"
          : DOCTOR_CASE === "staff"
            ? "STAFF_REVIEW"
            : "APPROVAL_PENDING",
    version: 3,
    approved_at: DOCTOR_CASE === "approved" ? mockScheduledAt() : null,
    scheduled_at: DOCTOR_CASE === "approved" ? mockScheduledAt() : null,
    returned_reason: DOCTOR_CASE === "returned" ? "검사 결과지를 다시 올려 주세요" : null,
    sections: [
      {
        key: "medication",
        body:
          "자궁내막증으로 진료받으셨고, 통증 관리를 위한 약을 처방받으셨어요.\n\n" +
          "처방받은 약 — 비잔정(디에노게스트) 2mg · 1일 1회 · 84일분\n" +
          "빈혈 Hb 10.2 → 10.4 (목표 12) · 자궁내막종 2.8 → 2.4",
        edited: false,
        locked: false,
        warn: warn ? "AMH 결과가 아직 안 나왔습니다 — 값이 빠진 자리입니다" : null,
      },
      {
        key: "caution",
        /* 일반 주의 문구만 남는다. 예전에는 아래 🚨 문장이 여기 함께 있었고
           그것을 지키려고 **이 칸까지 잠겨** 있었다 — 원장님이 환자에 맞춰
           고쳐야 할 문구를 못 고쳤다 (KEY-161). */
        body: "비잔 복용 중에는 부정출혈이 있을 수 있어요. 대부분 3개월 안에 줄어듭니다.",
        edited: false,
        locked: false,
        warn: null,
      },
      {
        key: "emergency",
        /* 🚨 약에 따라 정해진 문장이다(와이어프레임 D1-2 — 「비잔 · 수정 불가」).
           식약처 의약품정보를 근거로 미리 써 둔 것이라 약이 바뀌면 문장도
           함께 바뀐다. 사람이 고칠 자리가 아니다. */
        body: "다리가 붓고 아프거나 갑자기 숨이 차면 바로 병원에 연락해 주세요.",
        edited: false,
        locked: true,
        warn: null,
      },
      {
        key: "life",
        body:
          "밤 10시~새벽 2시 사이에 잠들어 있는 것이 좋아요. 자기 전 2시간은 휴대폰을 보지 않으시면 더 좋아요.\n" +
          "우유 · 요거트 · 치즈 · 두부 · 녹색 잎채소를 매일 챙겨 드세요.\n" +
          "걷기 · 계단 오르기처럼 뼈에 체중이 실리는 운동이 특히 좋아요.",
        edited: false,
        locked: false,
        warn: null,
      },
      {
        key: "messages",
        body:
          /* **「자동 발송됩니다」라고 쓰지 않는다.** 보내는 것이 아직 없다
             (`KEY-160`). 목업이 서버보다 후하게 약속하면, 목업으로 보는
             사람이 없는 기능을 있다고 읽는다. */
          "일주일 뒤 · 보름 뒤 확인 문자와 소진 3일 전 안내가 예약됩니다.\n" +
          "「{환자명}님, 복약 {일차}일째 확인입니다. 잘 드시고 계신가요? {링크}」",
        edited: false,
        locked: false,
        warn: null,
      },
    ],
  };
}


/* 서버가 없는 진료·안내문에 주는 것과 같은 오류다 (`app/services/guides.py`).
   조회·승인·반려·섹션 수정 네 갈래가 같은 말을 하도록 한 곳에 둔다. */
function mockNoGuide() {
  return new ApiError("GUIDE_NOT_FOUND", 404, {});
}

/* 저장된 상태가 있으면 그것이 이긴다. 없으면 `DOCTOR_CASE` 가 정한 기본값이다.
   섹션 본문도 같은 방식이다 — PATCH 로 고친 적이 있으면 그 값을, 없으면
   `mockGuideBase()` 의 원문을 쓴다. 그래야 고치고 다시 조회해도 그대로다. */
function mockGuide(visitId) {
  var guide = mockGuideBase(visitId);
  if (!guide) return null; // 모르는 진료 — 부르는 쪽이 404 로 바꾼다
  var saved = MOCK_GUIDE_STATE[visitId];
  if (!saved) return guide;
  if (saved.status !== null) guide.status = saved.status;
  if (saved.approved_at !== null) guide.approved_at = saved.approved_at;
  if (saved.scheduled_at !== null) guide.scheduled_at = saved.scheduled_at;
  guide.returned_reason = saved.returned_reason;
  guide.sections.forEach(function (s) {
    if (Object.prototype.hasOwnProperty.call(saved.sections, s.key)) {
      s.body = saved.sections[s.key];
      s.edited = true;
    }
  });
  return guide;
}

/* 승인·반려가 걸리는 **상태 문**. 서버 `GuideService._require_pending()` 을
   그대로 옮긴 것이다 — 두 갈래인 것까지 같다.

   `SCHEDULED_TO_SEND` 를 따로 세는 까닭: 두 번 승인을 조용히 통과시키면
   **발송 예정 시각이 뒤로 밀린다.** 「승인했는데 왜 늦게 갔지」가 여기서 난다.
   목업이 한 덩어리로 뭉뚱그리면, 이 PR 이 고치려는 **승인 경합 자체를
   목업으로 잴 수가 없다** (이희진 님 `#76` 리뷰).

   반환값은 막을 `ApiError` 이거나 `null`(통과) 이다. */
function mockPendingBlock(guide) {
  if (guide.status === "APPROVAL_PENDING") return null;
  if (guide.status === "SCHEDULED_TO_SEND") return new ApiError("ALREADY_APPROVED", 409, {});
  return new ApiError("GUIDE_NOT_PENDING", 409, {});
}

/* 서버는 진료 시각 기준 그날 18:00 을 잡고, 지났으면 다음 날로 민다
   (`GuideService` 의 `SEND_HOUR`). 값에는 **병원 시간대가 붙어 나간다** —
   `_send_at` 이 `astimezone(Asia/Seoul)` 로 만들기 때문이다.

   예전에는 `toISOString()` 으로 **UTC** 를 줬다. 화면이 `new Date()` 로 되돌려
   찍고 있어서 KST 브라우저에서는 18:00 으로 맞아 보였지만, **두 오류가 서로
   상쇄된 것**이라 다른 시간대에서 열면 둘 다 틀렸다. 목업이 서버보다 헐거우면
   `?mock=1` 에서 멀쩡해 보이는 것을 이 파일이 이미 한 번 겪었다. */
function mockScheduledAt() {
  var now = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    hour12: false,
  })
    .formatToParts(new Date())
    .reduce(function (acc, part) {
      acc[part.type] = part.value;
      return acc;
    }, {});

  var day = now.year + "-" + now.month + "-" + now.day;
  if (Number(now.hour) >= 18) {
    // 정오 UTC 를 딛고 하루를 민다 — 날짜 경계에서 시간대가 끼어들지 않는다.
    var next = new Date(day + "T12:00:00Z");
    next.setUTCDate(next.getUTCDate() + 1);
    day = next.toISOString().slice(0, 10);
  }
  return day + "T18:00:00+09:00";
}

/* 문자 설정 목업. 서버와 **같은 기본값**이어야 한다 — 다르면 목업에서만
   보이는 화면이 생긴다 (`app/services/guides.py` 의 `_DEFAULT_ON`). */
var MOCK_PLANS = {};
var MOCK_PLAN_DEFAULT = [
  { kind: "CHECK_D7", enabled: true, body: null, days_before: null, fixed: true },
  { kind: "CHECK_D15", enabled: true, body: null, days_before: null, fixed: false },
  { kind: "CHECK_D30", enabled: false, body: null, days_before: null, fixed: false },
  { kind: "RUN_OUT", enabled: true, body: null, days_before: 3, fixed: false },
];

function mockPlan(visitId) {
  var saved = MOCK_PLANS[visitId];
  if (!saved) return { check_hour: 10, rounds: MOCK_PLAN_DEFAULT.slice() };

  var fixedOf = {};
  MOCK_PLAN_DEFAULT.forEach(function (r) {
    fixedOf[r.kind] = r.fixed;
  });
  return {
    check_hour: saved.check_hour,
    rounds: (saved.rounds || []).map(function (r) {
      return {
        kind: r.kind,
        /* 일주일 뒤는 끌 수 없다 — 서버가 그렇게 답한다 */
        enabled: fixedOf[r.kind] ? true : r.enabled,
        body: r.body || null,
        days_before: r.days_before === undefined ? null : r.days_before,
        fixed: !!fixedOf[r.kind],
      };
    }),
  };
}

function mockDoctorRequest(path, options) {
  var body = options.body || {};
  return new Promise(function (resolve, reject) {
    setTimeout(function () {
      /* **목업이 서버보다 헐거우면 경로 오류를 못 잡는다.** 예전 정규식은
         `/guide/{무엇이든}` 을 다 받아서, 화면이 없는 주소를 불러도 `?mock=1`
         에서는 멀쩡해 보였다. 서버가 실제로 가진 안내 조회·수정·승인·반려와
         환자 링크 관리 경로만 받는다. */
      var get = path.match(/^\/visits\/(\d+)\/guide$/);
      /* 키의 **모양**은 여기서 보지 않는다. 서버 경로도 `{key}: str` 이라
         무엇이든 받고, 그 키가 실제로 있는지는 핸들러가 판정해
         `SECTION_NOT_FOUND` 를 준다. 예전 `\w+` 는 한글 키를 아예 못 받아
         라우터 단에서 뭉뚱그린 `NOT_FOUND` 로 떨어졌다 — 서버와 코드가 갈리고,
         **「없는 섹션」 검사가 섹션 조회에 닿지도 못했다.**
         `/sections/` 를 요구하므로 approve·return 경로를 삼키지는 않는다. */
      var sec = path.match(/^\/visits\/(\d+)\/guide\/sections\/([^/]+)$/);
      var act = path.match(/^\/visits\/(\d+)\/guide\/(submit|approve|return|unapprove)$/);
      var issueLink = path.match(/^\/visits\/(\d+)\/guide\/link$/);
      var reIssueLink = path.match(/^\/visits\/(\d+)\/guide\/link\/re-issue$/);
      var msgs = path.match(/^\/visits\/(\d+)\/guide\/messages$/);
      /* **현황(D1-6)이 읽는 자리.** 이 분기가 없어서 `?mock=1` 로는 현황 탭이
         늘 「불러오지 못했습니다」였다 — 서버에는 있는데 목업만 없었다.
         목업이 서버보다 **좁으면** 화면을 목업으로 검수할 수 없다. */
      var tl = path.match(/^\/visits\/(\d+)\/timeline$/);
      var m = get || sec || act || issueLink || reIssueLink || msgs || tl;
      if (!m) return reject(new ApiError("NOT_FOUND", 404, {}));
      var visitId = Number(m[1]);

      if (tl) return resolve(mockTimeline(visitId));

      if (issueLink && options.method === "POST") {
        var linkedGuide = mockGuide(visitId);
        if (!linkedGuide) return reject(mockNoGuide());
        if (linkedGuide.status !== "SCHEDULED_TO_SEND" || !linkedGuide.approved_at) {
          return reject(new ApiError("GUIDE_NOT_APPROVED", 409, {}));
        }
        var linkedState = mockGuideState(visitId);
        if (linkedState.patient_link_issued) {
          return reject(new ApiError("LINK_ALREADY_ISSUED", 409, {}));
        }
        linkedState.patient_link_issued = true;
        return resolve({
          path: "/api/v1/guides/demo-key223-link",
          expires_at: "2026-09-11T18:00:00+09:00",
          demo_only: true,
        });
      }

      if (reIssueLink && options.method === "POST") {
        var replacementGuide = mockGuide(visitId);
        if (!replacementGuide) return reject(mockNoGuide());
        if (replacementGuide.status !== "SCHEDULED_TO_SEND" || !replacementGuide.approved_at) {
          return reject(new ApiError("GUIDE_NOT_APPROVED", 409, {}));
        }
        var replacementState = mockGuideState(visitId);
        if (!replacementState.patient_link_issued) {
          return reject(new ApiError("LINK_NOT_ISSUED", 404, {}));
        }
        replacementState.patient_link_revoked = false;
        return resolve({
          path: "/api/v1/guides/demo-key223-reissued-link",
          expires_at: "2026-09-11T18:00:00+09:00",
          demo_only: true,
        });
      }

      if (issueLink && options.method === "DELETE") {
        var revokeState = mockGuideState(visitId);
        if (!revokeState.patient_link_issued) {
          return reject(new ApiError("LINK_NOT_ISSUED", 404, {}));
        }
        revokeState.patient_link_revoked = true;
        return resolve({});
      }

      if (options.method === "POST" && /\/submit$/.test(path)) {
        var submitted = mockGuide(visitId);
        if (!submitted) return reject(mockNoGuide());
        if (submitted.status !== "STAFF_REVIEW" && submitted.status !== "APPROVAL_RETURNED") {
          return reject(new ApiError("GUIDE_NOT_IN_REVIEW", 409, {}));
        }
        submitted.status = "APPROVAL_PENDING";
        submitted.returned_reason = null;
        var submittedState = mockGuideState(visitId);
        submittedState.status = submitted.status;
        submittedState.returned_reason = null;
        return resolve(submitted);
      }

      if (options.method === "POST" && /\/approve$/.test(path)) {
        /* 서버가 역할을 판단한다(`docs/models-layout.md` — 「[승인]은 의사 계정만」).
           화면에서 버튼을 잠그는 것은 편의일 뿐이다. */
        if (!mockIsDoctor()) return reject(new ApiError("FORBIDDEN", 403, {}));
        /* 서버는 승인 결과로도 `GuideResponse` 를 통째로 준다. 수신번호는
           싣지 않는다 — 승인할 때마다 전화번호가 화면과 로그를 지난다. */
        var approved = mockGuide(visitId);
        if (!approved) return reject(mockNoGuide());
        var blocked = mockPendingBlock(approved);
        if (blocked) return reject(blocked);
        /* 계약 §6 의 어휘를 그대로 쓴다. 서버도 `GuideStatus.SCHEDULED_TO_SEND` 를
           넣는다 — **승인이 곧 발송 예약**이라 「승인됨」이라는 상태는 없다(`D1-5`). */
        approved.status = "SCHEDULED_TO_SEND";
        approved.approved_at = mockScheduledAt();
        approved.scheduled_at = mockScheduledAt();
        var approvedState = mockGuideState(visitId);
        approvedState.status = approved.status;
        approvedState.approved_at = approved.approved_at;
        approvedState.scheduled_at = approved.scheduled_at;
        approvedState.returned_reason = null;
        return resolve(approved);
      }

      if (msgs) {
        /* 목업도 저장한 것을 들고 있는다 — 안 그러면 「저장했습니다」 뒤에
           다시 읽으면 기본값으로 돌아가, 화면에서만 되는 것처럼 보인다. */
        if (options.method === "PUT") {
          MOCK_PLANS[visitId] = body;
          return resolve(mockPlan(visitId));
        }
        return resolve(mockPlan(visitId));
      }

      if (options.method === "POST" && /\/unapprove$/.test(path)) {
        if (!mockIsDoctor()) return reject(new ApiError("FORBIDDEN", 403, {}));
        var taken = mockGuide(visitId);
        if (!taken) return reject(mockNoGuide());
        /* 서버는 승인된 것만 거둔다 — 목업이 헐거우면 화면이 아무 상태에서나
           눌리게 만들어 놓고도 멀쩡해 보인다. */
        if (taken.status !== "SCHEDULED_TO_SEND") {
          return reject(new ApiError("GUIDE_NOT_SCHEDULED", 409, {}));
        }
        taken.status = "APPROVAL_PENDING";
        taken.approved_at = null;
        taken.scheduled_at = null;
        var takenState = mockGuideState(visitId);
        takenState.status = taken.status;
        takenState.approved_at = null;
        takenState.scheduled_at = null;
        return resolve(taken);
      }

      if (options.method === "POST" && /\/return$/.test(path)) {
        if (!mockIsDoctor()) return reject(new ApiError("FORBIDDEN", 403, {}));
        if (!body.reason || !String(body.reason).trim()) {
          return reject(new ApiError("REASON_REQUIRED", 422, {}));
        }
        var returned = mockGuide(visitId);
        if (!returned) return reject(mockNoGuide());
        /* 반려도 같은 문을 지난다 — 서버 `return_to_staff()` 가 `approve()` 와
           **같은 `_require_pending()`** 을 부른다. 이미 발송을 기다리는 글을
           반려로 되돌리면 승인 기록만 남고 글은 스탭에게 가 버린다. */
        var blockedReturn = mockPendingBlock(returned);
        if (blockedReturn) return reject(blockedReturn);
        returned.status = "APPROVAL_RETURNED";
        returned.returned_reason = body.reason;
        var returnedState = mockGuideState(visitId);
        returnedState.status = returned.status;
        returnedState.scheduled_at = null;
        returnedState.returned_reason = returned.returned_reason;
        return resolve(returned);
      }

      if (options.method === "PATCH") {
        if (!sec) return reject(new ApiError("NOT_FOUND", 404, {}));

        var guide = mockGuide(visitId);
        if (!guide) return reject(mockNoGuide());

        var target = guide.sections.filter(function (s) {
          return s.key === sec[2];
        })[0];
        /* 계약(`docs/api/hospital.md` §918)이 정한 이름은 `SECTION_NOT_FOUND`
           이고 서버도 그 코드를 준다. 목업만 뭉뚱그린 `NOT_FOUND` 를 주고
           있었다 — 화면이 코드로 분기하는 날 목업에서만 갈린다.

           **빈 본문 검사보다 먼저 본다.** 서버 `edit_section()` 은
           `GuideSectionKey(key)` 파싱을 doctor 권한 검사 바로 다음, `strip()`
           검사보다 앞에서 한다 — 키가 유효하지 않으면 본문을 보기도 전에
           `SECTION_NOT_FOUND` 다. 목업이 순서를 바꾸면 같은 요청(없는 섹션 +
           빈 본문)에 서버와 다른 코드를 준다. */
        if (!target) return reject(new ApiError("SECTION_NOT_FOUND", 404, {}));

        /* **빈 본문은 저장 자체가 안 된다.** 서버 `edit_section()` 은 받은 값을
           `strip()` 한 뒤 비어 있으면 `EMPTY_BODY` 422 로 막는다. 공백만 넣은
           것도 빈 것이다 — 승인된 안내문의 한 갈래가 빈 채로 환자에게 가면
           그 갈래는 없느니만 못하다. */
        var text = String(body.body === undefined || body.body === null ? "" : body.body).trim();
        if (!text) return reject(new ApiError("EMPTY_BODY", 422, {}));

        /* 🚨 응급 문장은 식약처 정보를 근거로 미리 써 둔 것이라 사람이 고칠
           자리가 아니다 — 서버가 `SECTION_LOCKED` 409 로 막는다
           (`app/services/guides.py`). */
        if (target.locked) return reject(new ApiError("SECTION_LOCKED", 409, {}));

        /* **상태와 역할을 함께 본다.** 스탭 확인·반려 상태에서는 스탭과
           의사가 고칠 수 있고, 승인 요청 뒤에는 의사만 고친다. 이미 승인해
           발송을 기다리는 글을 조용히 바꾸면 환자가 받는 것과 의사가 승인한
           것이 달라진다.

           `mockPendingBlock()` 을 쓰지 않는 이유: 서버 `edit_section()` 은
           `_require_pending()` 을 부르지 않고, 승인된 글도 `ALREADY_APPROVED`
           가 아니라 `GUIDE_NOT_PENDING` 으로 막는다 — 그리고 잠금을 상태보다
           먼저 보므로 위 `SECTION_LOCKED` 검사가 이 검사보다 앞서야 한다. */
        if (
          guide.status !== "STAFF_REVIEW" &&
          guide.status !== "APPROVAL_PENDING" &&
          guide.status !== "APPROVAL_RETURNED"
        ) {
          return reject(new ApiError("GUIDE_NOT_PENDING", 409, {}));
        }
        if (guide.status === "APPROVAL_PENDING" && !mockIsDoctor()) {
          return reject(new ApiError("FORBIDDEN", 403, {}));
        }

        /* 저장한다 — 안 해두면 다음 `GET /guide` 가 고치기 전 본문을 다시
           준다. 승인·반려처럼 `mockGuideState()` 로 부분 갱신하므로, 이미
           승인·반려 상태로 저장된 값(`status`·`scheduled_at`)은 그대로다. */
        mockGuideState(visitId).sections[target.key] = text;

        /* 서버는 고친 그 섹션 하나만 돌려준다(`SectionResponse`).

           `locked`·`warn` 은 **이 섹션의 값을 그대로** 실어야 한다. 예전처럼
           늘 `false`/`null` 로 주면 자기 데이터(`mockGuide`)와 어긋나서, 편집
           기능이 붙는 순간 **잠긴 섹션이 풀린 것처럼** 보인다. */
        return resolve({
          key: target.key,
          body: text,
          edited: true,
          locked: target.locked,
          warn: target.warn,
        });
      }

      /* `get` 이 아닌 길로 여기 닿았다는 것은 approve·return·PATCH 중 어느
         분기도 아니라는 뜻이다 — 예를 들어 `/guide/sections/{key}` 에 GET을
         보낸 경우다. 그런 라우트는 서버에 없으므로 조용히 전체 guide 를
         돌려주지 않고 404 다. */
      if (get && (!options.method || options.method === "GET")) {
          var found = mockGuide(visitId);
          return found ? resolve(found) : reject(mockNoGuide());
      }
      return reject(new ApiError("NOT_FOUND", 404, {}));
    }, 200);
  });
}

/* 목업의 역할 판정. `?case=staff` 면 스탭으로 본다. */
function mockIsDoctor() {
  return DOCTOR_CASE !== "staff";
}
