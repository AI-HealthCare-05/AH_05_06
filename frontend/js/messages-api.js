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
