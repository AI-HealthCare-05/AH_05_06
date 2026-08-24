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
  /* 이 진료의 판독 작업이 무엇인지 묻는다.

     **계약에 이 자리가 비어 있다.** `#32`(KEY-60)에는 `POST /documents/{id}/ocr`
     로 만들고 `GET /ocr/jobs/{id}` 로 보는 길만 있고, 「이 진료의 작업」을 찾는
     길이 없다. 화면은 왼쪽에서 고른 진료로 시작하므로 반드시 필요하다.

     서버가 붙을 때는 진료 응답이 `ocr_job_id` 를 들고 오는 편이 낫다 —
     왕복이 하나 줄고, 「작업이 아직 없다」도 같은 응답으로 말할 수 있다.

     이 자리를 채우는 것은 **KEY-133** 이다 — 「`visit_id` 로 접근 가능한 OCR
     작업을 조회하는 공식 계약」이 그 일감의 범위이고, 아래 임시 호출을 실제
     계약으로 교체하는 것까지 적혀 있다. 그때까지 목업이 진료 번호로 만든다.

     처음에는 KEY-109 로 적어 뒀는데 그건 「이전 값 유지·이번 미시행」의 뜻을
     정하는 일감이다. 성격이 다른 계약을 한 일감에 쌓으면 어느 것이 끝나야
     무엇이 풀리는지 알 수 없게 된다. */
  jobForVisit: function (visitId) {
    if (MOCK) return mockJobForVisit(visitId);
    return request("/visits/" + visitId + "/ocr-job");
  },

  job: function (jobId) {
    return ocrRequest("/ocr/jobs/" + encodeURIComponent(jobId));
  },
  result: function (jobId) {
    return ocrRequest("/ocr/jobs/" + encodeURIComponent(jobId) + "/result");
  },
  fields: function (jobId) {
    return ocrRequest("/ocr/jobs/" + encodeURIComponent(jobId) + "/fields");
  },

  /* KEY-63. base_version 은 「내가 보고 있던 판」이다 — 서버가 그 사이
     달라졌으면 409 로 막는다. 접수대는 한 컴퓨터를 여럿이 쓰기 때문에
     이 확인이 없으면 나중에 저장한 사람이 앞사람 수정을 조용히 지운다.
     계약: PATCH /api/v1/ocr/fields/{id} — #32 */
  updateField: function (fieldId, body) {
    return ocrRequest("/ocr/fields/" + encodeURIComponent(fieldId), { method: "PATCH", body: body });
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
 *   conflict    옆자리가 먼저 고침   — 409 VERSION_CONFLICT (KEY-63)
 *   confirmed   이미 확정된 항목     — 409 OCR_FIELD_CONFIRMED (KEY-63)
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

/* `?case=processing` 은 되물을 때마다 진행률이 오르고 결국 끝난다.
   화면이 「끝나면 저절로 바뀝니다」라고 말하므로, 목업도 실제로 끝나야
   그 약속을 눈으로 확인할 수 있다 (`#40` 리뷰). */
var mockPolls = 0;

function mockJob(jobId) {
  var id = jobId || "ocr_synthetic_501";
  if (MOCK_CASE === "processing") {
    mockPolls += 1;
    if (mockPolls <= 3) {
      return {
        ocr_job_id: id,
        status: "PROCESSING",
        progress: 25 * mockPolls,
        started_at: "2026-08-13T10:33:00+09:00",
      };
    }
  }
  if (MOCK_CASE === "failed") {
    return {
      ocr_job_id: id,
      status: "FAILED",
      progress: 100,
      started_at: "2026-08-13T10:33:00+09:00",
      completed_at: "2026-08-13T10:33:40+09:00",
      failure_code: "OCR_ENGINE_TIMEOUT",
    };
  }
  return {
    ocr_job_id: id,
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
    fields: (function () {
      if (MOCK_CASE === "clean") return mockCleanFields();
      var fields = mockFields();
      /* 확정된 항목은 고칠 수 없다(#32). 그 상태를 눌러 볼 수 있어야
         화면이 409 를 제대로 말하는지 확인할 수 있다. */
      if (MOCK_CASE === "confirmed") {
        /* 확정을 **정상 상태 하나에만** 걸면 「확정인데 못 읽은 항목」과
           「확정인데 후보가 여럿인 항목」을 못 본다. `#40` 리뷰에서 걸린 것이
           정확히 그 둘이라, 세 모양을 다 만들어 둔다. */
        var confirmIds = [9106, 9103, 9102, 9105]; // 정상 · 못 읽음 · 후보 여럿 · 별도 보고
        fields.forEach(function (field) {
          if (confirmIds.indexOf(field.ocr_field_id) === -1) return;
          field.is_confirmed = true;
          field.confirmed_by = 902;
          field.confirmed_at = "2026-08-13T10:40:00+09:00";
        });
      }
      return fields;
    })(),
  };
}

/* 저장을 붙이면서 목업도 상태를 갖게 됐다. 매번 새로 만들면
   저장한 값이 다음 조회에서 사라져 「저장이 되긴 했나」를 볼 수 없다. */
var mockStore = null;

function mockState() {
  if (!mockStore) mockStore = mockResult();
  return mockStore;
}

/* 내보낼 때는 반드시 복사한다. 그냥 넘기면 화면이 목업의 속을 그대로 쥐게 되어,
   옆자리가 고친 값이 저장도 하기 전에 화면에 나타난다 — 서버라면 있을 수 없는 일이다. */
function mockCopy(value) {
  return JSON.parse(JSON.stringify(value));
}

function mockFieldById(id) {
  var fields = mockState().fields;
  for (var i = 0; i < fields.length; i++) {
    if (fields[i].ocr_field_id === id) return fields[i];
  }
  return null;
}

/* ?case=conflict — 옆자리에서 같은 항목을 먼저 고친 상황을 만든다.
   결과를 한 번 내준 뒤 서버 쪽 판만 올려 둔다. 그러면 이 화면이 들고 있는
   base_version 이 낡아서, 저장할 때 409 VERSION_CONFLICT 가 난다.
   동시 수정은 말로만 설명하면 안 되고 눌러 봐야 하는 화면이라 넣었다. */
function mockGhostEdit() {
  var field = mockFieldById(9104);
  if (!field || field._ghosted) return;
  field._ghosted = true;
  field.corrected_value = "24";
  field.value = "24";
  field.version = 2;
  field.modified_by = 902;
  field.modified_at = "2026-08-13T10:41:00+09:00";
}

function mockPatch(fieldId, body) {
  var field = mockFieldById(fieldId);
  if (!field) return new ApiError("NOT_FOUND", 404, {});
  if (field.is_confirmed) return new ApiError("OCR_FIELD_CONFIRMED", 409, {});
  if (field.version !== body.base_version) return new ApiError("VERSION_CONFLICT", 409, {});

  /* 사람이 보낼 수 있는 상태는 둘뿐이다 — 「이번엔 안 했다」와 그 되돌리기.
     `UNREADABLE` · `PENDING_REPORT` 은 기계가 판정한 것이라 사람이 덮어쓰면
     「못 읽었다」가 사라진다 (`docs/api/hospital.md` §4 — 판독 항목의 상태 어휘). */
  if (body.field_status !== undefined) {
    if (["NOT_PERFORMED", "READ"].indexOf(body.field_status) === -1) {
      return new ApiError("INVALID_FIELD_STATUS", 400, {});
    }
    /* 「안 했다」면서 값을 함께 적는 것은 앞뒤가 맞지 않는다. */
    if (body.corrected_value !== undefined || body.candidate_id !== undefined) {
      return new ApiError("INVALID_REQUEST", 400, {});
    }
    field.field_status = body.field_status;
    field.version += 1;
    field.modified_by = 101;
    field.modified_at = "2026-08-13T10:42:00+09:00";
    return field;
  }

  /* **보낼 값이 없으면 거절한다.** 서버의 `require_one_value_source`
     (`app/ocr/schemas.py`)가 「수정값 또는 후보를 선택해 주세요」로 막는 자리다.

     목업만 이것이 없어서, 값 없는 요청이 오면 `String(undefined)` 가 **문자열
     `"undefined"` 를 필드 값으로 저장**했다. `mockFieldById()` 가 저장소의 원본
     참조를 주므로 재조회해도 남는다 — 검사값 화면에서 가장 나쁜 종류의 실패다
     (이희진 님 `#81` 리뷰).

     진짜 서버로는 `JSON.stringify` 가 `undefined` 키를 버려 `422` 로 거절되는데,
     목업만 조용히 삼켰다. **틀리는 방식이 다르면 목업으로 잡을 수 없다.** */
  if (
    (body.corrected_value === undefined || body.corrected_value === null) &&
    (body.candidate_id === undefined || body.candidate_id === null) &&
    !body.confirm
  ) {
    return new ApiError("INVALID_REQUEST", 400, {});
  }

  /* **값이 왔을 때만 값을 건드린다.** 서버가 그렇게 한다
     (`app/ocr/service.py` — `if request.corrected_value is not None or
     selected_candidate is not None`). 예전에는 `else` 가 무조건 돌아서,
     값 없는 요청이 오면 `String(undefined)` 가 값 자리에 앉았다. */
  var changed = false;
  if (body.candidate_id !== undefined && body.candidate_id !== null) {
    var picked = null;
    field.candidates.forEach(function (item) {
      item.is_selected = item.ocr_field_candidate_id === body.candidate_id;
      if (item.is_selected) picked = item;
    });
    if (!picked) return new ApiError("INVALID_CANDIDATE", 400, {});
    field.corrected_value = picked.value;
    changed = true;
  } else if (body.corrected_value !== undefined && body.corrected_value !== null) {
    field.corrected_value = String(body.corrected_value).trim();
    changed = true;
  }

  if (changed) {
    field.value = field.corrected_value;
    field.modified_by = 101;
    field.modified_at = "2026-08-13T10:42:00+09:00";
  }
  field.version += 1;
  if (body.confirm) {
    field.is_confirmed = true;
    field.confirmed_by = 101;
    /* 값을 안 바꾸고 확정만 하면 `modified_at` 은 예전 값(또는 없음)이다.
       서버는 확정 시각을 따로 찍는다 — `confirmed_at = changed_at`. */
    field.confirmed_at = "2026-08-13T10:42:00+09:00";
  }
  return field;
}

/* 진료마다 다른 작업 번호를 준다. 고정값을 쓰면 어느 환자를 골라도 같은
   판독 결과가 나온다 — 실제로 그랬다(`#40` 리뷰). */
function mockJobForVisit(visitId) {
  return new Promise(function (resolve, reject) {
    setTimeout(function () {
      if (!visitId) return reject(new ApiError("NOT_FOUND", 404, {}));
      resolve({ ocr_job_id: "ocr_synthetic_" + visitId });
    }, 80);
  });
}

function mockOcrRequest(path, options) {
  var body = (options && options.body) || {};
  return new Promise(function (resolve, reject) {
    setTimeout(function () {
      var patch = path.match(/^\/ocr\/fields\/(\d+)$/);
      if (patch) {
        var out = mockPatch(Number(patch[1]), body);
        return out instanceof ApiError ? reject(out) : resolve(mockCopy(out));
      }

      /* `/ocr/jobs/{id}` · `.../result` · `.../fields` 셋 다 여기서 id 를 얻는다. */
      var onJob = path.match(/^\/ocr\/jobs\/([^/]+)/);
      var job = mockJob(onJob && onJob[1]);
      if (/\/(result|fields)$/.test(path)) {
        if (job.status !== "COMPLETED") {
          /* #32 계약 그대로. 화면은 이 코드를 보고 「아직」과 「실패」를 가른다. */
          return reject(new ApiError("OCR_RESULT_NOT_READY", 409, {}));
        }
        var state = mockState();
        if (/\/fields$/.test(path)) return resolve(mockCopy(state.fields));
        var first = !state._served;
        state._served = true;
        if (first && MOCK_CASE === "conflict") setTimeout(mockGhostEdit, 0);
        return resolve(mockCopy(state));
      }
      return resolve(job);
    }, 200);
  });
}
