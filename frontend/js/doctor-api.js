/* 의사 검토·승인 API — KEY-86
 *
 * 안내문을 읽고, 고치고, 승인하거나 스탭에게 되돌린다.
 *
 *   GET   /api/v1/visits/{visit_id}/guide            안내문 네 갈래 + ⚠ 표시
 *   PATCH /api/v1/visits/{visit_id}/guide/{section}  그 항목만 고친다
 *   POST  /api/v1/visits/{visit_id}/guide/approve    승인 — 발송 예약
 *   POST  /api/v1/visits/{visit_id}/guide/return     스탭에 되돌린다 (사유 필수)
 *
 * **이 계약은 아직 서버에 없습니다.** `KEY-76` 의 API 몫이고 문서도 없어서,
 * 화면이 필요로 하는 모양을 여기 적어 두고 `?mock=1` 로 확인합니다.
 * 붙일 때 맞춰야 할 것을 PR 본문에 적었습니다.
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
    return doctorRequest("/visits/" + encodeURIComponent(visitId) + "/guide/" + section, {
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
    patient: { name: "김서연", age: 36, gender: "여", hospital_patient_no: "12345" },
    summary: "자궁내막증 · 비잔 (계속) · 84일 · 지난 방문 05-20",
  },
  8802: {
    patient: { name: "최다인", age: 29, gender: "여", hospital_patient_no: "10982" },
    summary: "다낭성 · 야즈 (계속) · 84일 · 지난 방문 06-02",
  },
};

function mockGuide(visitId) {
  var warn = DOCTOR_CASE !== "clean";
  var who = MOCK_PATIENTS[visitId] || MOCK_PATIENTS[8801];
  return {
    visit_id: visitId,
    status: DOCTOR_CASE === "returned" ? "APPROVAL_RETURNED" : "APPROVAL_PENDING",
    version: 3,
    patient: who.patient,
    summary: who.summary,
    sections: [
      {
        key: "medication",
        label: "복약지도",
        editable: true,
        blocks: [
          { title: "오늘 진료 요약", body: "자궁내막증으로 진료받으셨고, 통증 관리를 위한 약을 처방받으셨어요." },
          {
            title: "나의 목표",
            table: {
              head: ["", "시작", "지금", "목표"],
              rows: [
                ["빈혈 Hb", "10.2", "10.4", "12"],
                ["자궁내막종", "2.8", "2.4", "─"],
                /* ⚠ 는 「확인 부탁」이다 — AI 가 스스로 자신 없는 곳,
                   지난번과 달라진 곳, 값이 빠진 곳에만 붙는다. */
                ["AMH", "곧 나와요", "─", "─"],
              ],
            },
            warn: warn ? "AMH 결과가 아직 안 나왔습니다 — 값이 빠진 자리입니다" : null,
          },
          { title: "처방받은 약", body: "비잔정 2mg · 성분 디에노게스트 · 1일 1회 · 84일분" },
          {
            title: "이 약을 왜 드시나요",
            body:
              "지난번 8점이던 생리통이 오늘 4점까지 내려왔어요. 약이 잘 듣고 있다는 뜻이에요. " +
              "다만 통증이 줄었다고 병변까지 없어진 것은 아니에요. 끊을 시기는 진료 때 함께 정해요.",
            warn: warn ? "지난 진료와 통증 점수가 달라졌습니다 (8 → 4)" : null,
          },
          { title: "다음 방문 계획", body: "3개월 뒤 재진 예정이에요." },
        ],
      },
      {
        key: "caution",
        label: "주의사항",
        editable: true,
        blocks: [
          {
            title: "흔하고 괜찮은 반응",
            body: "피가 조금씩 비치는 것이 가장 흔해요. 특히 처음 3개월에 그래요. 생리가 없어지는 것은 폐경이 아니에요.",
          },
          {
            title: "함께 드시면 안 되는 것",
            body: "세인트존스워트(성요한풀)가 든 건강기능식품이나 허브차는 약효를 떨어뜨릴 수 있어요.",
          },
          /* 🚨 는 식약처 의약품정보를 근거로 미리 써 둔 문장이다.
             약이 바뀌면 문장도 함께 바뀐다 — 사람이 고치지 않는다. */
          {
            title: "🚨 바로 병원에 연락하세요",
            locked: "비잔 · 식약처 의약품정보 기준 문장이라 고칠 수 없습니다 — 약이 바뀌면 문장도 바뀝니다",
            list: [
              "기분이 심하게 가라앉아 일상생활이 어려울 때",
              "스스로를 해치고 싶은 생각이 들 때",
              "생리가 아닌데 출혈이 많아 어지럽거나 힘이 빠질 때",
            ],
          },
        ],
      },
      {
        key: "life",
        label: "생활지도",
        editable: true,
        blocks: [
          {
            title: "이번 4주 챌린지",
            list: ["밤 11시 전에 잠들기 · 주 5일", "칼슘 음식 챙겨 먹기 · 주 5일", "주 3회 30분 걷기 · 주 3회"],
          },
          { title: "수면", body: "밤 10시~새벽 2시 사이에 잠들어 있는 것이 좋아요. 자기 전 2시간은 휴대폰을 보지 않으시면 더 좋아요." },
          { title: "뼈 건강", body: "우유 · 요거트 · 치즈 · 두부 · 녹색 잎채소를 매일 챙겨 드세요." },
          { title: "운동", body: "걷기 · 계단 오르기처럼 뼈에 체중이 실리는 운동이 특히 좋아요." },
        ],
      },
    ],
    /* 문자 설정은 스탭이 S1-14 에서 맞춰 놓은 것을 원장이 보고 필요하면 고친다.
       같은 화면을 두 역할이 보는 것이지 값이 두 자리에 있는 것이 아니다. */
    messages: {
      schedule: [
        { key: "d7", label: "일주일 뒤", on: true, fixed: true, when: "08-20 (목) 예정" },
        { key: "d15", label: "보름 뒤", on: true, when: "08-28 (금) 예정" },
        { key: "d30", label: "한 달 뒤", on: false, when: "꺼짐 · 켜면 09-12 (토)" },
        { key: "refill", label: "소진 3일 전", on: true, when: "11-02 (월) 예정 · 소진 11-05" },
      ],
      send_at: "오전 10:00",
      template_name: "일주일 뒤 확인 · 기본 템플릿",
      body: "{환자명}님, 복약 {일차}일째 확인입니다. 잘 드시고 계신가요? {링크}",
      preview: who.patient.name + "님, 복약 7일째 확인입니다. 잘 드시고 계신가요? mg.kr/a3F9x2",
      preview_meta: "010-5678-1234 · 08-20 (목) 10:00 · 발신 064-000-0000 · 76바이트 · 단문(SMS)",
    },
    approve_preview: { send_at: "오늘 18:00", to: who.patient.name + " 님" },
  };
}

function mockDoctorRequest(path, options) {
  var body = options.body || {};
  return new Promise(function (resolve, reject) {
    setTimeout(function () {
      var m = path.match(/^\/visits\/(\d+)\/guide(?:\/(\w+))?$/);
      if (!m) return reject(new ApiError("NOT_FOUND", 404, {}));
      var visitId = Number(m[1]);

      if (options.method === "POST" && /\/approve$/.test(path)) {
        /* 서버가 역할을 판단한다(`docs/models-layout.md` — 「[승인]은 의사 계정만」).
           화면에서 버튼을 잠그는 것은 편의일 뿐이다. */
        if (!mockIsDoctor()) return reject(new ApiError("FORBIDDEN", 403, {}));
        var target = MOCK_PATIENTS[visitId] || MOCK_PATIENTS[8801];
        return resolve({ status: "APPROVED", send_at: "오늘 18:00", to: target.patient.name + " 님" });
      }

      if (options.method === "POST" && /\/return$/.test(path)) {
        if (!mockIsDoctor()) return reject(new ApiError("FORBIDDEN", 403, {}));
        if (!body.reason || !String(body.reason).trim()) {
          return reject(new ApiError("REASON_REQUIRED", 422, {}));
        }
        return resolve({ status: "APPROVAL_RETURNED", reason: body.reason });
      }

      if (options.method === "PATCH") {
        if (!mockIsDoctor()) return reject(new ApiError("FORBIDDEN", 403, {}));
        return resolve({ section: m[2], version: 4 });
      }

      return resolve(mockGuide(visitId));
    }, 200);
  });
}

/* 목업의 역할 판정. `?case=staff` 면 스탭으로 본다. */
function mockIsDoctor() {
  return DOCTOR_CASE !== "staff";
}
