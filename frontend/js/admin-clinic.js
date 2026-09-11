/* 어드민 — 의원 정보 (A1-4). KEY-331.
 *
 * 이 칸이 오래 골격만이었다. **그 빈자리가 조용하지 않았다** — 소진·재진
 * 문자의 `{예약링크}` 를 채울 데가 없어서 발송 코드가 그 환자의 안내문 링크를
 * 대신 넣었고, 「재진 예약을 잡아주세요: …」를 누른 환자는 예약 화면이 아니라
 * 제 안내문을 다시 열었다.
 *
 * **그리는 함수와 부르는 함수를 나눠 둔다** — `admin-staff.js` 와 같은 규율이다.
 * 아래 `…Html` · `clinic…` 들은 값을 받아 문자열이나 값을 돌려주는 순수
 * 함수라 검사가 그대로 부를 수 있다. DOM 을 만지는 것은 `admin.js` 가 한다.
 */

/* **고칠 수 있는 칸 셋.** 서버 `EDITABLE` 과 같은 목록이다 (`admin_hospital.py`).
   의원 이름은 없다 — 배포 한 판의 정체라 시드가 정하고, 바꾸면 이미 나간
   문자의 `{의원명}` 과 앞으로 나갈 것이 갈린다. */
var CLINIC_FIELDS = [
  {
    key: "phone",
    id: "clinic-phone",
    label: "대표번호",
    hint: "환자 화면의 「문의하기」가 이 번호로 겁니다 · 예: 02-123-4567",
    placeholder: "02-123-4567",
  },
  {
    key: "address",
    id: "clinic-address",
    label: "주소",
    hint: "관리자가 제 의원을 알아보는 표시입니다 · 문자에는 안 들어갑니다",
    placeholder: "서울시 ○○구 ○○로 12, 3층",
  },
  {
    key: "booking_url",
    id: "clinic-booking-url",
    label: "예약 링크",
    hint: "소진·재진 문자의 {예약링크} 가 여는 곳 · http:// 또는 https:// 로 시작합니다",
    placeholder: "https://booking.example.com/…",
  },
];

/* **예약 링크가 비어 있으면 문자가 안 나간다.**
 *
 * 서버가 그 문자를 보내지 않고 붙든다(`BOOKING_URL_MISSING`) — 빈칸을 채워
 * 「재진 예약을 잡아주세요: 」를 보내는 것보다 낫기 때문이다. 그런데 그것을
 * 여기서 말하지 않으면, 관리자는 **보류 목록을 보고 나서야** 무엇을 안 적었는지
 * 안다. 적는 자리에서 미리 말한다. */
function clinicBookingWarning(info) {
  if (info && info.booking_url) return "";
  return "예약 링크가 비어 있습니다. 채우기 전까지 소진·재진 문자는 보내지 않고 보류됩니다.";
}

/* 화면이 보내는 몸 — **셋을 늘 함께 보낸다.**
   빈칸은 `null` 이다: 「지웠다」와 「안 보냈다」를 화면이 헷갈리지 않게
   한쪽으로 못박는다. 서버는 안 보낸 칸을 손대지 않으므로, 지우려면 이렇게
   `null` 을 실어야 한다. */
function clinicPayload(values) {
  var body = {};
  for (var i = 0; i < CLINIC_FIELDS.length; i++) {
    var key = CLINIC_FIELDS[i].key;
    var raw = values[key] == null ? "" : String(values[key]).trim();
    body[key] = raw === "" ? null : raw;
  }
  return body;
}

function clinicFieldHtml(field, info) {
  var value = info && info[field.key] != null ? info[field.key] : "";
  return (
    '<label class="clinic__field"><span class="clinic__label">' +
    esc(field.label) +
    "</span>" +
    '<input class="clinic__input" id="' +
    esc(field.id) +
    '" name="' +
    esc(field.key) +
    '" value="' +
    esc(value) +
    '" placeholder="' +
    esc(field.placeholder) +
    '" maxlength="500" />' +
    '<span class="clinic__hint">' +
    esc(field.hint) +
    "</span></label>"
  );
}

function clinicFormHtml(info) {
  var fields = "";
  for (var i = 0; i < CLINIC_FIELDS.length; i++) fields += clinicFieldHtml(CLINIC_FIELDS[i], info);

  var warning = clinicBookingWarning(info);
  return (
    '<form class="clinic" id="clinic-form">' +
    '<h2 class="clinic__title">' +
    esc((info && info.name) || "의원") +
    "</h2>" +
    /* **이름은 제목으로만 보인다.** 고칠 칸을 두지 않는 것이 「여기서는 못
       바꾼다」를 지키는 가장 확실한 방법이다 — 서버도 그 칸을 안 받는다. */
    '<p class="clinic__note">의원 이름은 여기서 바꾸지 않습니다.</p>' +
    (warning ? '<p class="clinic__warn">' + esc(warning) + "</p>" : "") +
    '<div class="clinic__fields">' +
    fields +
    "</div>" +
    '<div class="clinic__foot">' +
    '<p class="clinic__say" id="clinic-say" role="status" aria-live="polite"></p>' +
    '<button class="button-primary" type="submit" id="clinic-save">저장</button>' +
    "</div>" +
    "</form>"
  );
}

/* 서버가 준 오류 하나를 사람 말 한 줄로 — 좁은 것을 먼저 적는다. */
function clinicSaveSaying(error) {
  return errorMessage(
    error,
    [
      { code: "INVALID_REQUEST", say: "적어 주신 값 중에 규칙에 안 맞는 것이 있습니다. 번호와 예약 링크를 확인해 주세요." },
      { code: "HOSPITAL_NOT_FOUND", say: "의원 정보를 찾을 수 없습니다. 관리자에게 알려 주세요." },
      { status: 403, say: "의원 정보를 고칠 권한이 없습니다." },
    ],
    "의원 정보를 저장하지 못했습니다. 잠시 뒤 다시 시도해 주세요.",
  );
}

function clinicLoadSaying(error) {
  return errorMessage(
    error,
    [{ status: 403, say: "의원 정보를 볼 권한이 없습니다." }],
    "의원 정보를 불러오지 못했습니다.",
  );
}

function getHospital() {
  return request("/admin/hospital");
}

function updateHospital(body) {
  return request("/admin/hospital", { method: "PATCH", body: body });
}
