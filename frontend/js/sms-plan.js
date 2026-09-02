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

/* ── 켜고 끄기 ─────────────────────────────────────────────────────────
 *
 * 회차를 켜고 끄는 것은 규칙이 하나뿐이다 — **일주일 뒤는 못 끈다.**
 * 그 규칙을 화면 여러 곳에 흩어 두면 한쪽만 고쳐진다.
 */
function smsRoundOf(key) {
  for (var i = 0; i < SMS_ROUNDS.length; i++) {
    if (SMS_ROUNDS[i].key === key) return SMS_ROUNDS[i];
  }
  return null;
}

function smsRoundOn(plan, key) {
  var r = smsRoundOf(key);
  if (!r) return false;
  return r.fixed || ((plan && plan.on) || {})[key] === true;
}

/** 켜고 끈 뒤의 `on`. **원래 것을 고치지 않고 새로 만든다** — 화면이 다시
    그릴 때 무엇이 바뀌었는지 알 수 있어야 한다. */
function smsToggled(plan, key) {
  var r = smsRoundOf(key);
  var on = {};
  var src = (plan && plan.on) || {};
  for (var k in src) {
    if (Object.prototype.hasOwnProperty.call(src, k)) on[k] = src[k];
  }
  /* 고정 회차는 눌러도 그대로다. 끄는 시늉을 하면 껐다고 믿는다. */
  if (r && !r.fixed) on[key] = !on[key];
  return on;
}

/** 못 끄는 회차를 눌렀을 때 할 말. 아무 반응 없으면 「고장」으로 읽힌다. */
function smsFixedSaying(key) {
  var r = smsRoundOf(key);
  return r && r.fixed
    ? "일주일 뒤 확인은 끌 수 없습니다 — 복약 첫 주가 가장 잘 끊기는 구간입니다"
    : "";
}

/* ── 글에 끼워 넣기 ────────────────────────────────────────────────────
 *
 * 「+ 링크」·「+ 변수」가 커서 자리에 토큰을 넣는다. 끝에 붙이면 문장 가운데
 * 넣고 싶을 때 잘라 붙여야 한다.
 */
function smsInsert(text, token, at) {
  var s = String(text || "");
  var i = typeof at === "number" && at >= 0 && at <= s.length ? at : s.length;
  return s.slice(0, i) + token + s.slice(i);
}

/* ── 시각 ──────────────────────────────────────────────────────────────
 *
 * 와이어프레임은 「오전 10:00」이다. 진료 시간 안에서만 고르게 둔다 —
 * 새벽에 문자가 가면 그것 자체가 불편이다.
 */
var SMS_TIMES = [
  { key: "09:00", label: "오전 9:00" },
  { key: "10:00", label: "오전 10:00" },
  { key: "11:00", label: "오전 11:00" },
  { key: "14:00", label: "오후 2:00" },
  { key: "18:00", label: "오후 6:00" },
];

function smsTimeLabel(key) {
  for (var i = 0; i < SMS_TIMES.length; i++) {
    if (SMS_TIMES[i].key === key) return SMS_TIMES[i].label;
  }
  return SMS_TIMES[1].label;
}

/** 소진 며칠 전. **1일 아래로도, 처방일수 위로도 안 간다** — 0이면 소진
    당일이라 임박이 아니고, 처방일수보다 크면 처방 전에 보내는 셈이 된다. */
function smsClampBefore(value, courseDays) {
  var n = parseInt(String(value), 10);
  if (isNaN(n)) return 3;
  var max = parseInt(String(courseDays), 10);
  if (!max || isNaN(max)) max = 30;
  return Math.max(1, Math.min(n, max));
}

/* ── 서버와 주고받는 모양 (와이어프레임 S1-14) ────────────────────────
 *
 * 화면은 `d7` · `d15` · `d30` · `runOut` 으로 부르고, 서버는 `CHECK_D7` …
 * `RUN_OUT` 으로 부른다. 이름을 한쪽에 맞추지 않는 이유는, 화면 키가 회차
 * 목록(`SMS_ROUNDS`)의 키이고 서버 값은 표의 열거값이기 때문이다 — 한쪽이
 * 바뀔 때 다른 쪽이 끌려가면 안 된다. 여기 한 곳에서만 옮긴다.
 */
var SMS_KIND = { d7: "CHECK_D7", d15: "CHECK_D15", d30: "CHECK_D30", runOut: "RUN_OUT" };

function smsKeyOfKind(kind) {
  for (var key in SMS_KIND) {
    if (Object.prototype.hasOwnProperty.call(SMS_KIND, key) && SMS_KIND[key] === kind) return key;
  }
  return null;
}

/** `10` → `"10:00"`. 서버는 시각을 숫자로 담는다 — 분은 고를 자리가 없다. */
function smsHourText(hour) {
  var n = parseInt(String(hour), 10);
  if (isNaN(n) || n < 0 || n > 23) return "10:00";
  return (n < 10 ? "0" : "") + n + ":00";
}

/** 서버가 준 설정을 화면 상태로. 모르는 회차는 버린다 — 화면에 그릴 자리가 없다. */
function smsPlanFromServer(plan) {
  var out = { at: smsHourText(plan && plan.check_hour), on: {}, texts: {}, runOutBefore: 3 };
  var rounds = (plan && plan.rounds) || [];

  for (var i = 0; i < rounds.length; i++) {
    var row = rounds[i];
    var key = smsKeyOfKind(row.kind);
    if (!key) continue;

    /* **소진 임박은 회차가 아니다.** `on` 에 섞으면 왼쪽 회차 목록에 「소진」이
       한 줄 더 생긴다 — 그건 아래 따로 있는 칸이다. */
    if (key === "runOut") {
      out.runOutOn = row.enabled !== false;
      if (row.days_before !== null && row.days_before !== undefined) out.runOutBefore = row.days_before;
    } else if (key !== "d7") {
      /* d7 은 늘 켜져 있다 — `on` 에 담지 않는 것이 화면의 규칙이다(`smsRoundOn`) */
      out.on[key] = row.enabled !== false;
    }

    if (row.body) out.texts[key] = row.body;
  }
  return out;
}

/** 화면 상태를 서버가 받는 모양으로. **한 판을 통째로 보낸다** — 회차 하나씩
    보내면 중간에 끊겼을 때 반쪽 상태가 남는다. */
function smsPlanToServer(state) {
  var st = state || {};
  var texts = st.texts || {};
  var rounds = [];

  for (var i = 0; i < SMS_ROUNDS.length; i++) {
    var r = SMS_ROUNDS[i];
    rounds.push({
      kind: SMS_KIND[r.key],
      enabled: smsRoundOn({ on: st.on || {} }, r.key),
      /* 기본 문구 그대로면 안 보낸다 — 보내면 「이 환자만 적용」이 아닌데도
         고친 것으로 담기고, 나중에 기본 문구가 바뀌어도 안 따라온다. */
      body: texts[r.key] !== undefined && texts[r.key] !== smsDefaultText(r.key) ? texts[r.key] : null,
      days_before: null,
    });
  }

  rounds.push({
    kind: SMS_KIND.runOut,
    enabled: st.runOutOn !== false,
    body: texts.runOut !== undefined ? texts.runOut : null,
    days_before: st.runOutBefore === undefined ? 3 : st.runOutBefore,
  });

  return { check_hour: parseInt(String(st.at || "10:00").slice(0, 2), 10), rounds: rounds };
}
