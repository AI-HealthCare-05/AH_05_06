/* 판독(OCR) 결과 조회 API — KEY-62
 *
 * 계약은 KEY-60 (PR #32) 의 응답 모양을 그대로 따른다.
 *   GET /api/v1/ocr/jobs/{ocr_job_id}          → 상태·진행률
 *   GET /api/v1/ocr/jobs/{ocr_job_id}/result   → 원문 + 구조화 필드 + 후보
 *
 * 이 화면(S1-7·S1-8)은 읽기만 한다. 값을 고치고 저장하는
 * PATCH /ocr/fields/{id} 는 KEY-63 이 붙인다.
 *
 * #32 가 아직 리뷰 중이라 ?mock=1 로 화면을 확인한다. 서버가 붙으면
 * 아래 「목업」 아래를 통째로 지우면 된다 — 응답 필드 이름을 #32 의
 * OcrResultResponse · OcrFieldResponse · OcrCandidateResponse 와
 * 한 글자도 다르지 않게 맞춰 두었기 때문이다.
 *
 * 서버가 준비되면 정리해야 할 것 — PR 본문에 적었다.
 *   ① 저신뢰 판정. 임계값은 KEY-60 서버 설정이 갖기로 했는데(#31 리뷰)
 *      지금 응답에는 confidence 만 있고 판정도 임계값도 없다.
 *      화면이 임의로 정하면 안 되는 값이라 result.low_confidence_threshold
 *      를 먼저 보고, 없을 때만 아래 상수로 물러난다.
 *   ② 원문 줄 ↔ 필드 연결. 「수치 옆 출처를 누르면 해당 진료기록으로
 *      이동한다」를 지키려면 필드가 어느 문서 몇 번째 줄에서 왔는지
 *      알아야 한다. 지금 계약에 그 값이 없어 목업에 source_line 을 얹었다.
 */

/* 서버가 판정을 안 줄 때만 쓰는 임시값. 서버가 주기 시작하면 지운다. */
var LOW_CONFIDENCE_FALLBACK = 0.75;

function ocrRequest(path, options) {
  options = options || {};
  if (MOCK) return mockOcrRequest(path, options);
  return request(path, options);
}

var ocrApi = {
  job: function (jobId) {
    return ocrRequest("/ocr/jobs/" + encodeURIComponent(jobId));
  },
  result: function (jobId) {
    return ocrRequest("/ocr/jobs/" + encodeURIComponent(jobId) + "/result");
  },
};

/* 필드 하나가 넷 중 어느 상태인지. 화면 전체가 이 함수 하나로 갈린다.
 *
 *   missing    못 읽었다        — 추측해서 채우지 않는다. 점선 + ? 로 비워 둔다
 *   candidates 같은 항목이 둘   — 검사일이 최근인 쪽을 쓰고 고를 수 있게 한다
 *   low        읽었지만 흔들린다 — 사람이 한 번 봐야 한다
 *   ok         그대로 쓴다
 *
 * 순서가 뜻을 만든다. 못 읽은 값에는 신뢰도가 없으므로 missing 이 먼저고,
 * 후보가 둘이면 그 자체가 「골라 달라」는 뜻이라 low 보다 앞에 온다.
 */
function fieldState(field, threshold) {
  if (field.value === null || field.value === undefined) return "missing";
  if (field.candidates && field.candidates.length > 1) return "candidates";
  if (field.confidence !== null && field.confidence !== undefined && field.confidence < threshold) return "low";
  return "ok";
}

/* ── 목업 ──────────────────────────────────────────────────────
 * 와이어프레임 S1-7·S1-8 의 김서연(차트 12345 · 1990-01-01)을 그대로 옮겼다.
 * 2026-08-13 진료 · 자궁내막증 · 비잔 2mg 84일 · 소진 예정 11-05.
 *
 * 네 상태가 한 화면에 다 있어야 이 티켓을 눈으로 검수할 수 있다.
 *   자궁내막종  후보 둘 (검사지1 08-05 2.4 / EMR 05-20 2.8)
 *   CA-125     못 읽음
 *   CA19-9     저신뢰 — 원문에서 CA-125 와 한 줄에 붙어 있다
 *   AMH        별도 보고 검사 — 값이 아니라 「추후 보고 예정」이 온다
 *
 * ?case= 로 예외를 본다.
 *   processing  아직 판독 중        — 409 OCR_RESULT_NOT_READY
 *   failed      판독이 실패로 끝남  — 직접 입력으로 넘어가야 한다
 *   clean       다 읽혔을 때        — 강조가 하나도 없는 화면
 */
var MOCK_CASE = (function () {
  var q = new URLSearchParams(location.search).get("case");
  if (q !== null) sessionStorage.setItem("mockOcrCase", q);
  return sessionStorage.getItem("mockOcrCase") || "";
})();

var MOCK_RAW = {
  emr: [
    "2026-05-20  산부인과  박연",
    "진단 : 자궁내막증 (N80.9)",
    "자궁내막종  수 치 : 2.8 cm  / 참고치 : -",
    "내막 두께   수 치 : 0.5 cm  / 참고치 : 0.4-1.4",
    "AST/ALT     수 치 : 24 / 34 U/L  / 참고치 : 0-40",
    "비고 : 우울증 병력 있음. 임신 계획 상담함.",
  ],
  rx: ["2026-08-13  처방", "비잔정 2mg  1일 1회  총투 84", "※ 계속 처방"],
  lab1: [
    "검체채취일 2026-08-05",
    "Cytology (LBC) : NILM",
    "HPV DNA : Positive (type ?)",
    "SCC Ag : 1.2 ng/mL",
    "CA-125 : 48 U/mL   CA19-9 : 21 U/mL",
    "AMH : 추후 보고 예정   E2 : 62 pg/mL",
    "Hb : 10.2 g/dL   CRP : 0.4 mg/L",
  ],
  lab2: ["검체채취일 2026-08-05", "자궁내막종 : 2.4 cm", "내막 두께 : 판독 불가"],
};

var MOCK_DOCUMENTS = [
  { document_id: 8801, document_type: "EMR", label: "EMR 기록", key: "emr" },
  { document_id: 8802, document_type: "PRESCRIPTION", label: "처방전", key: "rx" },
  { document_id: 8803, document_type: "LAB_RESULT", label: "검사지1", key: "lab1" },
  { document_id: 8804, document_type: "LAB_RESULT", label: "검사지2", key: "lab2" },
];

function mockField(id, type, value, confidence, extra) {
  var field = {
    ocr_field_id: id,
    field_type: type,
    extracted_value: value,
    corrected_value: null,
    value: value,
    confidence: confidence,
    version: 1,
    is_confirmed: false,
    modified_by: null,
    modified_at: null,
    confirmed_by: null,
    confirmed_at: null,
    candidates: [],
  };
  for (var key in extra) field[key] = extra[key];
  return field;
}

function mockFields() {
  return [
    mockField(9101, "혈색소", "10.2", 0.97, { unit: "g/dL", document_id: 8803, source_line: 6, source_date: "2026-08-05" }),
    mockField(9102, "자궁내막종", "2.4", 0.94, {
      unit: "cm",
      document_id: 8804,
      source_line: 1,
      source_date: "2026-08-05",
      /* 검사일이 최근인 쪽이 rank 1 이고 is_selected 다.
         정렬을 화면에서 다시 하지 않는다 — 서버가 정한 순서를 그대로 믿는다. */
      candidates: [
        {
          ocr_field_candidate_id: 71,
          value: "2.4",
          confidence: 0.94,
          rank: 1,
          source_date: "2026-08-05",
          is_selected: true,
          document_id: 8804,
          source_line: 1,
        },
        {
          ocr_field_candidate_id: 72,
          value: "2.8",
          confidence: 0.91,
          rank: 2,
          source_date: "2026-05-20",
          is_selected: false,
          document_id: 8801,
          source_line: 2,
        },
      ],
    }),
    /* 못 읽은 항목도 행은 남는다 — #31 에서 계약으로 정한 것이다.
       행이 없으면 화면은 이 항목이 있어야 한다는 사실 자체를 모른다. */
    mockField(9103, "CA-125", null, null, { unit: "U/mL", document_id: 8803, source_line: 4 }),
    mockField(9104, "CA19-9", "21", 0.62, { unit: "U/mL", document_id: 8803, source_line: 4, source_date: "2026-08-05" }),
    /* 값이 아니라 상태가 오는 항목. 「못 읽음」과 다르다 —
       검사는 했고 결과가 아직 안 나온 것이라 다시 판독해도 값이 없다. */
    mockField(9105, "AMH", "추후 보고 예정", 0.96, {
      unit: "",
      document_id: 8803,
      source_line: 5,
      source_date: "2026-08-05",
      pending_report: true,
    }),
    mockField(9106, "내막 두께", "0.5", 0.95, { unit: "cm", document_id: 8801, source_line: 3, source_date: "2026-05-20" }),
    mockField(9107, "간수치 AST/ALT", "24 / 34", 0.93, {
      unit: "U/L",
      document_id: 8801,
      source_line: 4,
      source_date: "2026-05-20",
    }),
  ];
}

function mockCleanFields() {
  return mockFields()
    .filter(function (field) {
      return field.field_type !== "AMH";
    })
    .map(function (field) {
      field.candidates = [];
      if (field.value === null) field.value = field.extracted_value = "48";
      field.confidence = 0.96;
      return field;
    });
}

function mockJob() {
  if (MOCK_CASE === "processing") {
    return { ocr_job_id: "ocr_synthetic_501", status: "PROCESSING", progress: 40, started_at: "2026-08-13T10:33:00+09:00" };
  }
  if (MOCK_CASE === "failed") {
    return {
      ocr_job_id: "ocr_synthetic_501",
      status: "FAILED",
      progress: 100,
      started_at: "2026-08-13T10:33:00+09:00",
      completed_at: "2026-08-13T10:33:40+09:00",
      failure_code: "OCR_ENGINE_TIMEOUT",
    };
  }
  return {
    ocr_job_id: "ocr_synthetic_501",
    status: "COMPLETED",
    progress: 100,
    started_at: "2026-08-13T10:33:00+09:00",
    completed_at: "2026-08-13T10:33:52+09:00",
    failure_code: null,
  };
}

function mockResult() {
  return {
    ocr_result_id: 5101,
    ocr_job_id: "ocr_synthetic_501",
    model_name: "synthetic-ocr",
    model_version: "mock",
    version: 1,
    confirmed_by: null,
    confirmed_at: null,
    /* 서버가 이 값을 주기로 한 자리(#31 리뷰). 목업이 먼저 채워 둔다. */
    low_confidence_threshold: 0.75,
    documents: MOCK_DOCUMENTS.map(function (doc) {
      return {
        document_id: doc.document_id,
        document_type: doc.document_type,
        label: doc.label,
        raw_text: MOCK_RAW[doc.key].join("\n"),
        raw_text_purged_at: null,
      };
    }),
    fields: MOCK_CASE === "clean" ? mockCleanFields() : mockFields(),
  };
}

function mockOcrRequest(path) {
  return new Promise(function (resolve, reject) {
    setTimeout(function () {
      var job = mockJob();
      if (/\/result$/.test(path)) {
        if (job.status !== "COMPLETED") {
          /* #32 계약 그대로. 화면은 이 코드를 보고 「아직」과 「실패」를 가른다. */
          return reject(new ApiError("OCR_RESULT_NOT_READY", 409, {}));
        }
        return resolve(mockResult());
      }
      return resolve(job);
    }, 200);
  });
}
