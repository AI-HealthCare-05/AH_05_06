/* **문자 설정** — 와이어프레임 S1-14.
 *
 * 확인 문자 회차 · 소진 임박 · 재진 안내를 한 자리에 모은다. 스탭이 S2-1 에서
 * 이탈 환자를 발견하면 곧바로 조치할 수 있게 하려는 것이다.
 *
 * **여기 있는 것은 규칙뿐이다.** 저장할 자리가 서버에 아직 없다 —
 * `GuideResponse` 에 문자 설정이 없고, 회차·문구를 담는 표도 없다
 * (`check_in` 은 환자의 D+7 응답이지 회차가 아니다). 화면은 그 사실을
 * 감추지 않는다.
 */

/* 회차 — 와이어프레임의 세 가지. **일주일 뒤는 끌 수 없다.**
 *
 * 「필요하면 켜세요」로 두면 아무도 안 켠다. 복약 첫 주가 가장 잘 끊기는
 * 구간이라, 그 한 번은 어느 처방에서도 고정이다 (D2-3 도 「(고정)」이라 적는다). */
var SMS_ROUNDS = [
  { key: "d7", label: "일주일 뒤", days: 7, fixed: true },
  { key: "d15", label: "보름 뒤", days: 15, fixed: false },
  { key: "d30", label: "한 달 뒤", days: 30, fixed: false },
];

/* 날짜 셈은 **숫자로 뜯어 숫자로** 한다.
   `new Date("2026-08-13")` 은 UTC 자정이라 시간대에 따라 하루 밀린다 —
   이 함정에 이미 걸렸다 (`ocr-groups.js` 의 `runOutDate` 와 같은 이유). */
function smsDateAfter(startIso, days) {
  var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(startIso || ""));
  var n = parseInt(String(days), 10);
  if (!m || isNaN(n)) return "";

  var d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  d.setDate(d.getDate() + n);

  var mm = String(d.getMonth() + 1);
  var dd = String(d.getDate());
  return d.getFullYear() + "-" + (mm.length < 2 ? "0" + mm : mm) + "-" + (dd.length < 2 ? "0" + dd : dd);
}

var SMS_WEEKDAY = ["일", "월", "화", "수", "목", "금", "토"];

/** 「08-20 (목)」 — 와이어프레임의 표기. 요일이 붙는 이유는 스탭이 주말을
    피해 잡는지 눈으로 보기 위해서다. */
function smsWhen(iso) {
  var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(iso || ""));
  if (!m) return "";
  var d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  return m[2] + "-" + m[3] + " (" + SMS_WEEKDAY[d.getDay()] + ")";
}

/** 소진 임박 — 소진 예정일에서 N일 **앞**이다. 뒤로 세면 약이 떨어진 뒤에 간다. */
function smsRunOutNotice(runOutIso, daysBefore) {
  var n = parseInt(String(daysBefore), 10);
  if (!n || n <= 0) return "";
  return smsDateAfter(runOutIso, -n);
}

/* ── 문자 길이 ──────────────────────────────────────────────────────────
 *
 * 한국 문자는 **EUC-KR 바이트**로 센다 — 한글 2바이트, 영숫자 1바이트.
 * 90바이트까지가 단문(SMS)이고 넘으면 장문(LMS)이다. 통신사 과금이 그
 * 경계에서 갈리므로, 스탭이 한 글자 더 넣기 전에 보여야 한다.
 *
 * **와이어프레임의 숫자와는 다르다.** 원문은 같은 문구에 78·76 바이트라
 * 적는데, 그 문자열은 EUC-KR 로 66·65 이고 UTF-8 로 91·86 이라 어느
 * 쪽과도 안 맞는다. 예시로 적어 둔 값으로 보인다 — 맞지 않는 숫자를
 * 따라가느라 규칙을 비틀지 않는다. 팀에 알린다.
 *
 * `TextEncoder` 로는 EUC-KR 을 못 센다(UTF-8 만 된다). 글자 범위로 센다 —
 * 한글·한자·전각은 2바이트, 나머지는 1바이트다.
 */
var SMS_SHORT_MAX = 90;

function smsBytes(text) {
  var s = String(text || "");
  var n = 0;
  for (var i = 0; i < s.length; i++) {
    var c = s.charCodeAt(i);
    /* ASCII 와 반각은 1바이트 */
    n += c < 0x80 || (c >= 0xff61 && c <= 0xff9f) ? 1 : 2;
  }
  return n;
}

/** 단문인가 장문인가. 경계에서 값이 바뀌므로 화면이 미리 말해 준다. */
function smsKind(text) {
  var n = smsBytes(text);
  return {
    bytes: n,
    long: n > SMS_SHORT_MAX,
    label: n > SMS_SHORT_MAX ? "장문(LMS)" : "단문(SMS)",
  };
}

/* ── 변수 ───────────────────────────────────────────────────────────────
 *
 * 미리보기는 **변수가 치환된 실제 발송본**이다. 치환 전 글을 보여 주면
 * 스탭은 「{환자명}」이 그대로 나가는지 알 수 없고, 바이트 수도 실제와 다르다.
 */
var SMS_VARS = [
  { token: "{환자명}", label: "환자명" },
  { token: "{일차}", label: "일차" },
  { token: "{의원명}", label: "의원명" },
  { token: "{링크}", label: "링크" },
  { token: "{예약링크}", label: "예약링크" },
];

/** **`{링크}` 는 지울 수 없다** — 그것이 없으면 환자가 안내문을 열 길이 없다. */
function smsHasLink(text) {
  return String(text || "").indexOf("{링크}") !== -1;
}

function smsLinkMissingSaying(text) {
  return smsHasLink(text) ? "" : "{링크}가 빠졌습니다 — 없으면 환자가 안내문을 열 수 없습니다";
}

/** 치환한다. 모르는 변수는 **그대로 둔다** — 지우면 빠진 줄 모르고 나간다. */
function smsFill(text, values) {
  var out = String(text || "");
  var v = values || {};
  for (var i = 0; i < SMS_VARS.length; i++) {
    var token = SMS_VARS[i].token;
    var key = token.slice(1, -1);
    if (v[key] === undefined || v[key] === null) continue;
    out = out.split(token).join(String(v[key]));
  }
  return out;
}
