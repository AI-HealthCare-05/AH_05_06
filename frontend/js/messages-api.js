/* 발송 예정 · 발송 이력 — KEY-234.
 *
 *   GET /api/v1/messages/scheduled?days=7&limit=200   앞으로 나갈 것 + 안 나간 것
 *
 * **안 나간 것은 기간 밖이어도 온다.** 서버 규칙이고, 목업도 같아야 한다 —
 * 다르면 목업에서만 되는 화면이 생긴다.
 */

var messagesApi = {
  scheduled: function (days, limit) {
    if (MOCK) return mockScheduled(days, limit);
    var query =
      "?days=" +
      encodeURIComponent(days) +
      (limit ? "&limit=" + encodeURIComponent(limit) : "");
    return request("/messages/scheduled" + query);
  },

  history: function (range, limit) {
    if (MOCK) return mockHistory(range, limit);
    var query =
      "?from=" +
      encodeURIComponent(range.from) +
      "&to=" +
      encodeURIComponent(range.to) +
      (limit ? "&limit=" + encodeURIComponent(limit) : "");
    return request("/messages/history" + query);
  },

  /* **글자를 받아 온다.** `request` 는 JSON 만 읽으므로 여기만 따로 간다.
     주소에 토큰을 붙이지 않으려고 헤더로 보낸다 — 주소는 브라우저 기록과
     서버 접근 로그에 남고, 그 토큰은 환자 자료로 가는 열쇠다. */
  historyCsv: function (range) {
    if (MOCK) return Promise.resolve(mockHistoryCsv(range));
    var token = session.token();
    return fetch(API_BASE + historyCsvPath(range), {
      headers: token ? { Authorization: "Bearer " + token } : {},
      credentials: "include",
    }).then(function (res) {
      if (!res.ok) throw new ApiError("CSV_FAILED", res.status, {});
      return res.text();
    });
  },
};

/* ── 목업 ──────────────────────────────────────────────────────────────
 *
 * 와이어프레임 S2-3 의 여섯 줄을 그대로 옮긴다. 날짜는 **오늘에서 상대로**
 * 잡는다 — 고정 날짜를 박으면 그 날이 지나는 순간 창 밖으로 나가 목업이
 * 빈 화면이 된다.
 */
function mockDay(offset, hour) {
  var day = new Date();
  day.setDate(day.getDate() + offset);
  day.setHours(hour, 0, 0, 0);
  var pad = function (n) {
    return (n < 10 ? "0" : "") + n;
  };
  return (
    day.getFullYear() +
    "-" +
    pad(day.getMonth() + 1) +
    "-" +
    pad(day.getDate()) +
    "T" +
    pad(hour) +
    ":00:00+09:00"
  );
}

function mockScheduledRows() {
  return [
    {
      guide_message_id: 9001,
      visit_id: 8801,
      patient_id: 501,
      scheduled_at: mockDay(-3, 18),
      kind: "GUIDE",
      status: "FAILED",
      hold_reason: null,
      failure_code: "INVALID_PHONE",
      name: "박수빈",
      hospital_patient_no: "09871",
      gender: "FEMALE",
      birth_date: "1992-05-20",
      age: 34,
      prescription_set: "자궁내막증 · 초진",
    },
    {
      guide_message_id: 9002,
      visit_id: 8802,
      patient_id: 501,
      scheduled_at: mockDay(0, 10),
      kind: "GUIDE",
      status: "HELD",
      hold_reason: "INVALID_PHONE",
      failure_code: null,
      name: "박수빈",
      hospital_patient_no: "09871",
      gender: "FEMALE",
      birth_date: "1992-05-20",
      age: 34,
      prescription_set: "자궁내막증 · 초진",
    },
    {
      guide_message_id: 9003,
      visit_id: 8803,
      patient_id: 502,
      scheduled_at: mockDay(66, 10),
      kind: "RUN_OUT",
      status: "HELD",
      hold_reason: "NO_CREDIT",
      failure_code: null,
      name: "강예린",
      hospital_patient_no: "11902",
      gender: "FEMALE",
      birth_date: "1997-04-22",
      age: 29,
      prescription_set: "자궁내막증 · 비잔",
    },
    {
      guide_message_id: 9004,
      visit_id: 8804,
      patient_id: 503,
      scheduled_at: mockDay(0, 18),
      kind: "GUIDE",
      status: "SCHEDULED",
      hold_reason: null,
      failure_code: null,
      name: "김서연",
      hospital_patient_no: "12345",
      gender: "FEMALE",
      birth_date: "1990-01-01",
      age: 36,
      prescription_set: "자궁내막증 · 비잔",
    },
    {
      guide_message_id: 9005,
      visit_id: 8805,
      patient_id: 504,
      scheduled_at: mockDay(0, 18),
      kind: "GUIDE",
      status: "SCHEDULED",
      hold_reason: null,
      failure_code: null,
      name: "이서아",
      hospital_patient_no: "13820",
      gender: "FEMALE",
      birth_date: "1998-12-01",
      age: 27,
      prescription_set: "PCOS · 야즈 + 메트포르민",
    },
    /* **창 밖의 예정.** 기간을 7일에서 30일로 넓히면 이 줄이 나타난다 —
       목업이 규칙을 눈으로 보여 주지 못하면 화면을 눌러 봐도 모른다. */
    {
      guide_message_id: 9007,
      visit_id: 8805,
      patient_id: 504,
      scheduled_at: mockDay(20, 10),
      kind: "CHECK_D30",
      status: "SCHEDULED",
      hold_reason: null,
      failure_code: null,
      name: "이서아",
      hospital_patient_no: "13820",
      gender: "FEMALE",
      birth_date: "1998-12-01",
      age: 27,
      prescription_set: "PCOS · 야즈 + 메트포르민",
    },
    {
      guide_message_id: 9006,
      visit_id: 8803,
      patient_id: 502,
      scheduled_at: mockDay(4, 10),
      kind: "CHECK_D7",
      status: "SCHEDULED",
      hold_reason: null,
      failure_code: null,
      name: "강예린",
      hospital_patient_no: "11902",
      gender: "FEMALE",
      birth_date: "1997-04-22",
      age: 29,
      prescription_set: "자궁내막증 · 비잔",
    },
  ];
}

function mockScheduled(days, limit) {
  var rows = mockScheduledRows();
  var start = new Date();
  start.setHours(0, 0, 0, 0);
  var end = new Date(start);
  end.setDate(end.getDate() + days);
  var dayEnd = new Date(start);
  dayEnd.setDate(dayEnd.getDate() + 1);

  var within = function (row, until) {
    var at = new Date(row.scheduled_at);
    return at >= start && at < until;
  };
  var unsent = rows.filter(isUnsent);
  var scheduled = rows.filter(function (row) {
    return row.status === "SCHEDULED";
  });
  var inWindow = scheduled.filter(function (row) {
    return within(row, end);
  });
  var shown = unsent.concat(inWindow.slice(0, limit || 200));

  return Promise.resolve({
    days: days,
    timezone: "Asia/Seoul",
    counts: {
      total: rows.length,
      failed: rows.filter(function (row) {
        return row.status === "FAILED";
      }).length,
      held: rows.filter(function (row) {
        return row.status === "HELD";
      }).length,
      today: scheduled.filter(function (row) {
        return within(row, dayEnd);
      }).length,
      window: inWindow.length,
    },
    items: scheduleOrder(shown),
    truncated: inWindow.length > (limit || 200),
  });
}

/* ── 발송 이력 목업 (S2-4) ───────────────────────────────────────────────
 *
 * 원문의 세 줄을 옮긴다. 원문 견본은 고정 표시가 완료 줄에 붙어 있는데,
 * 캡션과 설계 주석이 「실패가 맨 위」라고 못박으므로 규칙 쪽을 따른다 —
 * 목업이 화면 규칙과 어긋나면 눌러 봐도 되는지 알 수 없다.
 */
function mockHistoryRows() {
  return [
    {
      guide_message_id: 7001,
      visit_id: 8803,
      patient_id: 502,
      happened_at: mockDay(0, 18),
      kind: "GUIDE",
      status: "SENT",
      failure_code: null,
      name: "강예린",
      hospital_patient_no: "11902",
      gender: "FEMALE",
      birth_date: "1997-04-22",
      age: 29,
      prescription_set: "자궁내막증 · 비잔",
      viewed: false,
      viewed_at: null,
    },
    {
      guide_message_id: 7002,
      visit_id: 8806,
      patient_id: 505,
      happened_at: mockDay(-1, 16),
      kind: "CHECK_D7",
      status: "SENT",
      failure_code: null,
      name: "서다은",
      hospital_patient_no: "10447",
      gender: "FEMALE",
      birth_date: "1995-07-19",
      age: 31,
      prescription_set: "자궁내막증 · 비잔 (계속)",
      viewed: true,
      viewed_at: mockDay(-1, 21),
    },
    {
      guide_message_id: 7003,
      visit_id: 8801,
      patient_id: 501,
      happened_at: mockDay(0, 10),
      kind: "GUIDE",
      status: "FAILED",
      failure_code: "INVALID_PHONE",
      name: "박수빈",
      hospital_patient_no: "09871",
      gender: "FEMALE",
      birth_date: "1992-05-20",
      age: 34,
      prescription_set: "자궁내막증 · 초진",
      viewed: false,
      viewed_at: null,
    },
    /* **기간 밖.** 최근 7일에서는 안 보이고 30일로 넓히면 나타난다 —
       목업이 규칙을 눈으로 보여 주지 못하면 눌러 봐도 모른다. */
    {
      guide_message_id: 7004,
      visit_id: 8807,
      patient_id: 506,
      happened_at: mockDay(-19, 11),
      kind: "RUN_OUT",
      status: "SENT",
      failure_code: null,
      name: "최다인",
      hospital_patient_no: "10982",
      gender: "FEMALE",
      birth_date: "1997-02-03",
      age: 29,
      prescription_set: "PCOS · 대사관리",
      viewed: true,
      viewed_at: mockDay(-19, 12),
    },
  ];
}

function mockHistory(range, limit) {
  var rows = mockHistoryRows().filter(function (row) {
    var day = String(row.happened_at).slice(0, 10);
    return day >= range.from && day <= range.to;
  });
  var failed = rows.filter(isFailed);
  var sent = rows.filter(function (row) {
    return row.status === "SENT";
  });
  var cap = limit || 200;

  return Promise.resolve({
    from_date: range.from,
    to_date: range.to,
    timezone: "Asia/Seoul",
    counts: {
      total: rows.length,
      failed: failed.length,
      viewed: sent.filter(function (row) {
        return row.viewed;
      }).length,
      unviewed: sent.filter(function (row) {
        return !row.viewed;
      }).length,
    },
    items: historyOrder(failed.concat(sent.slice(0, cap))),
    truncated: sent.length > cap,
  });
}

/* 쉼표·따옴표가 든 값은 감싼다. 서버는 `csv.writer` 가 해 주는 일인데,
   목업이 그냥 이으면 이름에 쉼표 하나만 들어와도 열이 밀린다 — 목업에서만
   되는 파일이 생긴다. */
function csvCell(value) {
  var text = value == null ? "" : String(value);
  if (/[",\n\r]/.test(text)) return '"' + text.replace(/"/g, '""') + '"';
  return text;
}

/* 서버가 만드는 것과 **같은 열**이어야 한다. 목업만 다른 파일이 나오면
   「받아 보니 다르더라」를 배포 뒤에 안다. */
function mockHistoryCsv(range) {
  var head = "발송일시,환자,차트번호,식별정보,세트명,종류,발송상태,실패사유,열람여부,열람일시\n";
  var rows = mockHistoryRows().filter(function (row) {
    var day = String(row.happened_at).slice(0, 10);
    return day >= range.from && day <= range.to;
  });
  return (
    "﻿" +
    head +
    historyOrder(rows)
      .map(function (row) {
        return [
          String(row.happened_at).slice(0, 16).replace("T", " "),
          row.name,
          row.hospital_patient_no,
          identityOf(row),
          row.prescription_set || "",
          MESSAGE_SAYING[row.kind] || row.kind,
          row.status === "FAILED" ? "발송 실패" : "발송 완료",
          row.failure_code ? FAILURE_SAYING[row.failure_code] || "" : "",
          isFailed(row) ? "—" : row.viewed ? "열람" : "미열람",
          row.viewed_at ? String(row.viewed_at).slice(0, 16).replace("T", " ") : "",
        ]
          .map(csvCell)
          .join(",");
      })
      .join("\n") +
    "\n"
  );
}
