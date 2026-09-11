/* 어드민 — 감사 로그 (A1-6 전체 · A1-7 한 진료 건). KEY-322.
 *
 * **A1-7 은 별도 화면이 아니다.** 진료 번호를 거르개에 넣으면 그 진료 건의
 * 모든 유형이 시간순으로 온다 — 서버가 그렇게 한 벌로 답한다.
 *
 * `admin-staff.js` 와 같은 규율이다: 값을 받아 문자열을 돌려주는 순수 함수만
 * 여기 두고, DOM 은 `admin.js` 가 만진다.
 */

/* 화면에 쓰는 유형 이름. 서버는 `guide` · `otp` 처럼 영문으로 준다. */
var AUDIT_SOURCE_LABEL = {
  guide: "안내문",
  otp: "본인 확인",
  message: "문자",
  patient_usage: "환자 이용",
  staff_account: "직원 계정",
  //: 여섯째 — 의원 정보 수정 (KEY-331). 여기 적힌 예약 링크가 문자에 실린다.
  hospital: "의원 정보",
};

function auditSourceLabel(source) {
  return AUDIT_SOURCE_LABEL[source] || source;
}

/* 「누가」 칸. **환자·발송기가 한 일에는 행위자가 없다** — 빈칸으로 두지 않고
   누가 한 일인지를 말한다. 빈칸이면 「이름을 못 불러왔다」로 읽힌다. */
function auditActorLabel(row) {
  if (row.actor_name) return row.actor_name;
  if (row.source === "patient_usage" || row.source === "otp") return "환자";
  if (row.source === "message") return "발송기";
  return "—";
}

/* 시각은 **분까지**만 보인다. 초까지 보이면 줄마다 폭이 들쭉날쭉하고,
   감사 목록에서 사람이 찾는 것은 「언제쯤」이지 「몇 초」가 아니다.
   되짚어야 할 때는 `event_id` 가 그 줄을 정확히 가리킨다. */
function auditWhen(iso) {
  if (!iso) return "";
  var at = new Date(iso);
  if (isNaN(at.getTime())) return String(iso);
  var two = function (n) {
    return (n < 10 ? "0" : "") + n;
  };
  return (
    at.getFullYear() +
    "-" +
    two(at.getMonth() + 1) +
    "-" +
    two(at.getDate()) +
    " " +
    two(at.getHours()) +
    ":" +
    two(at.getMinutes())
  );
}

function auditRowHtml(row) {
  return (
    "<tr>" +
    '<td class="audit__when">' +
    esc(auditWhen(row.occurred_at)) +
    "</td>" +
    "<td>" +
    esc(auditSourceLabel(row.source)) +
    "</td>" +
    "<td>" +
    esc(auditActorLabel(row)) +
    "</td>" +
    '<td class="audit__visit">' +
    (row.visit_id == null ? "" : esc(String(row.visit_id))) +
    "</td>" +
    "<td>" +
    esc(row.summary) +
    "</td>" +
    "</tr>"
  );
}

function auditListHtml(entries) {
  if (!entries || !entries.length) {
    return '<p class="pane__lead">그 조건에 맞는 기록이 없습니다.</p>';
  }
  var rows = "";
  for (var i = 0; i < entries.length; i++) rows += auditRowHtml(entries[i]);
  return (
    '<table class="audit">' +
    "<thead><tr><th>언제</th><th>유형</th><th>누가</th><th>진료</th><th>무슨 일</th></tr></thead>" +
    "<tbody>" +
    rows +
    "</tbody>" +
    "</table>"
  );
}

/* 거르개. **행위자 목록은 A1-1 이 이미 주는 것을 쓴다**(`listStaffs`) —
   이름을 손으로 적게 하면 오타 하나로 빈 목록이 나오고, 사람은 기록이 없는
   것으로 읽는다. */
function auditFilterHtml(staffs) {
  var sources = '<option value="">유형 전체</option>';
  for (var key in AUDIT_SOURCE_LABEL) {
    if (!Object.prototype.hasOwnProperty.call(AUDIT_SOURCE_LABEL, key)) continue;
    sources += '<option value="' + esc(key) + '">' + esc(AUDIT_SOURCE_LABEL[key]) + "</option>";
  }
  var people = '<option value="">행위자 전체</option>';
  for (var i = 0; i < (staffs || []).length; i++) {
    people +=
      '<option value="' +
      esc(String(staffs[i].staff_id)) +
      '">' +
      esc(staffs[i].name + " (" + staffs[i].login_id + ")") +
      "</option>";
  }
  return (
    '<form class="audit-filter" id="audit-filter">' +
    '<label class="audit-filter__field"><span class="audit-filter__label">유형</span>' +
    '<select class="audit-filter__input" id="audit-source">' +
    sources +
    "</select></label>" +
    '<label class="audit-filter__field"><span class="audit-filter__label">행위자</span>' +
    '<select class="audit-filter__input" id="audit-actor">' +
    people +
    "</select></label>" +
    '<label class="audit-filter__field"><span class="audit-filter__label">진료 번호</span>' +
    '<input class="audit-filter__input" id="audit-visit" inputmode="numeric" placeholder="예: 1204" /></label>' +
    '<label class="audit-filter__field"><span class="audit-filter__label">이 날부터</span>' +
    '<input class="audit-filter__input" id="audit-from" type="date" /></label>' +
    '<label class="audit-filter__field"><span class="audit-filter__label">이 날까지</span>' +
    '<input class="audit-filter__input" id="audit-to" type="date" /></label>' +
    '<button class="button-primary" type="submit" id="audit-go">거르기</button>' +
    "</form>"
  );
}

/* 화면 값 → 서버 질의. **빈 칸은 아예 안 보낸다** — 빈 문자열을 보내면
   서버가 그것을 값으로 읽고 아무것도 안 맞는 목록을 준다. */
function auditQueryFrom(values) {
  var query = {};
  if (values.source) query.source = values.source;
  if (values.actor) query.actor_staff_id = values.actor;
  if (values.visit) query.visit_id = values.visit;
  /* 날짜만 고르면 그날 0시다. 「이 날까지」는 그날을 **포함**해야 하므로
     하루 끝으로 민다 — 안 그러면 그날 기록이 통째로 빠지고, 고른 사람은
     그날 아무 일도 없었다고 읽는다. */
  if (values.from) query.occurred_from = values.from + "T00:00:00";
  if (values.to) query.occurred_to = values.to + "T23:59:59";
  return query;
}

function auditLoadSaying(error) {
  return errorMessage(
    error,
    [
      { status: 403, say: "감사 기록을 볼 권한이 없습니다." },
      { code: "INVALID_CURSOR", say: "목록이 오래됐습니다. 다시 걸러 주세요." },
      { code: "INVALID_REQUEST", say: "거르개 값 중에 규칙에 안 맞는 것이 있습니다." },
    ],
    "감사 기록을 불러오지 못했습니다.",
  );
}

function listAuditLogs(query) {
  var params = new URLSearchParams();
  for (var key in query) {
    if (Object.prototype.hasOwnProperty.call(query, key) && query[key] !== "" && query[key] != null) {
      params.set(key, String(query[key]));
    }
  }
  var suffix = params.toString();
  return request("/admin/audit-logs" + (suffix ? "?" + suffix : ""));
}
