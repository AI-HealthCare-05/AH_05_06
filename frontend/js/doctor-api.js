/* 의사 검토·승인 API — KEY-86
 *
 * 안내문을 읽고, 고치고, 승인하거나 스탭에게 되돌린다.
 *
 *   GET   /api/v1/visits/{visit_id}/guide                안내문 네 갈래 + ⚠ 표시
 *   PATCH /api/v1/visits/{visit_id}/guide/sections/{key}  그 항목만 고친다
 *   POST  /api/v1/visits/{visit_id}/guide/approve         승인 — 발송 예약
 *   POST  /api/v1/visits/{visit_id}/guide/return          스탭에 되돌린다 (사유 필수)
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
  approve: function (visitId, body) {
    return doctorRequest("/visits/" + encodeURIComponent(visitId) + "/guide/approve", {
      method: "POST",
      body: body || {},
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
 *   staff     스탭 계정으로 본 화면 — 승인·되돌리기가 잠긴다
 *   returned  이미 되돌린 건
 *   clean     ⚠ 가 하나도 없는 건 — 읽지 않고 승인해도 되는 상태
 */
var DOCTOR_CASE = (function () {
  var q = new URLSearchParams(location.search).get("case");
  if (q !== null) sessionStorage.setItem("mockDoctorCase", q);
  return sessionStorage.getItem("mockDoctorCase") || "";
})();

/* 목록의 두 줄이 각각 다른 안내문을 갖는다.
   하나만 돌려주면 줄을 눌러도 오른쪽이 안 바뀌어, **고르기가 고장난 것처럼**
   보인다. 실제 서버는 visit_id 로 갈라 주므로 목업도 그렇게 한다. */
var MOCK_PATIENTS = {
  8801: {
    patient: { name: "김서연", birth_date: "1990-03-14", age: 36, gender: "FEMALE", hospital_patient_no: "SYN-12345" },
    summary: "자궁내막증 · 비잔 (계속) · 84일 · 지난 방문 05-20",
  },
  8802: {
    patient: { name: "최다인", birth_date: "1997-06-02", age: 29, gender: "FEMALE", hospital_patient_no: "SYN-10982" },
    summary: "다낭성 · 야즈 (계속) · 84일 · 지난 방문 06-02",
  },
};

/* 서버 `GuideResponse` 를 그대로 흉내 낸다 — `app/dtos/guides.py`.

   섹션은 **본문 한 덩이**(`body`)다. 제목·표·목록으로 쪼갠 예전 모양은 렌더
   편의였지 계약이 아니었고, 8/27 여정에서 안내문은 고정 텍스트다(KEY-150).

   `warn` 은 **서버가 판정한다.** 「AI 가 자신 없는 곳」을 화면이 알 수 없다. */
/* 승인·반려가 남긴 상태. **진료 번호마다 하나.**

   예전에는 `mockGuide()` 가 매번 새로 만들고 승인 핸들러가 그 사본을 고쳐
   돌려줬다. 즉 **승인해도 다음 조회는 다시 「승인 요청」이었다.** 목업만 보면
   승인이 아무 일도 안 한 것처럼 보이고, 상태에 걸리는 규칙(아래
   `GUIDE_NOT_PENDING`)은 아예 잴 수가 없다 (이희진 님 `#76` 리뷰). */
var MOCK_GUIDE_STATE = {};

function mockGuideBase(visitId) {
  var warn = DOCTOR_CASE !== "clean";
  var who = MOCK_PATIENTS[visitId] || MOCK_PATIENTS[8801];
  return {
    visit_id: visitId,
    patient: who.patient,
    summary: who.summary,
    status: DOCTOR_CASE === "returned" ? "APPROVAL_RETURNED" : "APPROVAL_PENDING",
    version: 3,
    approved_at: null,
    scheduled_at: null,
    returned_reason: DOCTOR_CASE === "returned" ? "검사 결과지를 다시 올려 주세요" : null,
    sections: [
      {
        key: "medication",
        body:
          "자궁내막증으로 진료받으셨고, 통증 관리를 위한 약을 처방받으셨어요.\n\n" +
          "처방받은 약 — 비잔정 2mg · 성분 디에노게스트 · 1일 1회 · 84일분\n" +
          "빈혈 Hb 10.2 → 10.4 (목표 12) · 자궁내막종 2.8 → 2.4",
        edited: false,
        locked: false,
        warn: warn ? "AMH 결과가 아직 안 나왔습니다 — 값이 빠진 자리입니다" : null,
      },
      {
        key: "caution",
        body:
          "비잔 복용 중에는 부정출혈이 있을 수 있어요. 대부분 3개월 안에 줄어듭니다.\n" +
          "다리가 붓고 아프거나 갑자기 숨이 차면 바로 병원에 연락해 주세요.",
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
          "일주일 뒤 · 보름 뒤 확인 문자와 소진 3일 전 안내가 자동 발송됩니다.\n" +
          "「{환자명}님, 복약 {일차}일째 확인입니다. 잘 드시고 계신가요? {링크}」",
        edited: false,
        locked: false,
        warn: null,
      },
    ],
  };
}


/* 저장된 상태가 있으면 그것이 이긴다. 없으면 `DOCTOR_CASE` 가 정한 기본값이다. */
function mockGuide(visitId) {
  var guide = mockGuideBase(visitId);
  var saved = MOCK_GUIDE_STATE[visitId];
  if (saved) {
    guide.status = saved.status;
    guide.scheduled_at = saved.scheduled_at;
    guide.returned_reason = saved.returned_reason;
  }
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

function mockDoctorRequest(path, options) {
  var body = options.body || {};
  return new Promise(function (resolve, reject) {
    setTimeout(function () {
      /* **목업이 서버보다 헐거우면 경로 오류를 못 잡는다.** 예전 정규식은
         `/guide/{무엇이든}` 을 다 받아서, 화면이 없는 주소를 불러도 `?mock=1`
         에서는 멀쩡해 보였다. 서버가 실제로 가진 넷만 받는다. */
      var get = path.match(/^\/visits\/(\d+)\/guide$/);
      var sec = path.match(/^\/visits\/(\d+)\/guide\/sections\/(\w+)$/);
      var act = path.match(/^\/visits\/(\d+)\/guide\/(approve|return)$/);
      var m = get || sec || act;
      if (!m) return reject(new ApiError("NOT_FOUND", 404, {}));
      var visitId = Number(m[1]);

      if (options.method === "POST" && /\/approve$/.test(path)) {
        /* 서버가 역할을 판단한다(`docs/models-layout.md` — 「[승인]은 의사 계정만」).
           화면에서 버튼을 잠그는 것은 편의일 뿐이다. */
        if (!mockIsDoctor()) return reject(new ApiError("FORBIDDEN", 403, {}));
        /* 서버는 승인 결과로도 `GuideResponse` 를 통째로 준다. 수신번호는
           싣지 않는다 — 승인할 때마다 전화번호가 화면과 로그를 지난다. */
        var approved = mockGuide(visitId);
        var blocked = mockPendingBlock(approved);
        if (blocked) return reject(blocked);
        /* 계약 §6 의 어휘를 그대로 쓴다. 서버도 `GuideStatus.SCHEDULED_TO_SEND` 를
           넣는다 — **승인이 곧 발송 예약**이라 「승인됨」이라는 상태는 없다(`D1-5`). */
        approved.status = "SCHEDULED_TO_SEND";
        approved.scheduled_at = mockScheduledAt();
        MOCK_GUIDE_STATE[visitId] = {
          status: approved.status,
          scheduled_at: approved.scheduled_at,
          returned_reason: null,
        };
        return resolve(approved);
      }

      if (options.method === "POST" && /\/return$/.test(path)) {
        if (!mockIsDoctor()) return reject(new ApiError("FORBIDDEN", 403, {}));
        if (!body.reason || !String(body.reason).trim()) {
          return reject(new ApiError("REASON_REQUIRED", 422, {}));
        }
        var returned = mockGuide(visitId);
        /* 반려도 같은 문을 지난다 — 서버 `return_to_staff()` 가 `approve()` 와
           **같은 `_require_pending()`** 을 부른다. 이미 발송을 기다리는 글을
           반려로 되돌리면 승인 기록만 남고 글은 스탭에게 가 버린다. */
        var blockedReturn = mockPendingBlock(returned);
        if (blockedReturn) return reject(blockedReturn);
        returned.status = "APPROVAL_RETURNED";
        returned.returned_reason = body.reason;
        MOCK_GUIDE_STATE[visitId] = {
          status: returned.status,
          scheduled_at: null,
          returned_reason: returned.returned_reason,
        };
        return resolve(returned);
      }

      if (options.method === "PATCH") {
        if (!mockIsDoctor()) return reject(new ApiError("FORBIDDEN", 403, {}));
        if (!sec) return reject(new ApiError("NOT_FOUND", 404, {}));

        var guide = mockGuide(visitId);

        var target = guide.sections.filter(function (s) {
          return s.key === sec[2];
        })[0];
        if (!target) return reject(new ApiError("NOT_FOUND", 404, {}));

        /* **잠긴 섹션은 목업도 막는다.** 🚨 응급 문장은 식약처 정보를 근거로
           미리 써 둔 것이라 사람이 고칠 자리가 아니다 — 서버가
           `SECTION_LOCKED` 409 로 막는다(`app/services/guides.py`).

           목업이 서버보다 헐거우면 **화면 버그를 목업으로는 못 잡는다.**
           잠긴 섹션에 [수정]이 열리는 회귀가 나도 목업에서는 저장까지
           성공해 버린다 (이희진 님 `#76` 리뷰). */
        if (target.locked) return reject(new ApiError("SECTION_LOCKED", 409, {}));

        /* **승인 요청 상태에서만 고칠 수 있다.** 이미 승인해 발송을 기다리는
           글을 조용히 바꾸면 **환자가 받는 것과 의사가 승인한 것이 달라진다.**
           반려된 글도 스탭 손에 있어 의사가 고칠 자리가 아니다 — 서버가
           `GUIDE_NOT_PENDING` 409 로 막는다(`app/services/guides.py`).

           **순서가 서버와 같아야 한다.** `edit_section()` 은 잠금을 먼저 보므로,
           승인된 글의 잠긴 섹션은 `SECTION_LOCKED` 다. 목업이 먼저 상태를 보면
           같은 요청에 다른 코드를 돌려주고, 화면은 목업에서만 통하는 분기를
           갖게 된다.

           여기서는 `mockPendingBlock()` 을 쓰지 않는다 — 서버 `edit_section()`
           은 `_require_pending()` 을 부르지 않고, 승인된 글도 `ALREADY_APPROVED`
           가 아니라 `GUIDE_NOT_PENDING` 으로 막는다. 목업이 서버보다 헐거우면
           화면 버그를 목업으로 못 잡는다 (이희진 님 `#76` 리뷰). */
        if (guide.status !== "APPROVAL_PENDING") {
          return reject(new ApiError("GUIDE_NOT_PENDING", 409, {}));
        }

        /* 서버는 고친 그 섹션 하나만 돌려준다(`SectionResponse`).

           `locked`·`warn` 은 **이 섹션의 값을 그대로** 실어야 한다. 예전처럼
           늘 `false`/`null` 로 주면 자기 데이터(`mockGuide`)와 어긋나서, 편집
           기능이 붙는 순간 **잠긴 섹션이 풀린 것처럼** 보인다. */
        return resolve({
          key: target.key,
          body: String(body.body || ""),
          edited: true,
          locked: target.locked,
          warn: target.warn,
        });
      }

      return resolve(mockGuide(visitId));
    }, 200);
  });
}

/* 목업의 역할 판정. `?case=staff` 면 스탭으로 본다. */
function mockIsDoctor() {
  return DOCTOR_CASE !== "staff";
}
