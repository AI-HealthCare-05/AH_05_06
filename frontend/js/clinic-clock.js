/* 의원 시계 — KEY-234.
 *
 * **화면에 뜨는 시각은 의원 시각이다. 보는 사람의 노트북 시각이 아니다.**
 *
 * 서버는 `2026-09-01T18:00:00+09:00` 처럼 시간대를 붙여 준다. 그것을
 * `new Date(...)` 로 감싸 `getHours()` 를 부르면 **보는 사람의 시간대**로
 * 옮겨진다 — 서울에서 보면 18:00 이지만 시간대를 다르게 맞춘 노트북에서는
 * 다른 시각이 뜬다. 같은 진료가 사람마다 다른 시각으로 보이면 「몇 시에
 * 오셨죠」에 답할 수 없다.
 *
 * 그래서 **글자에서 읽는다.** 서버가 이미 의원 시각으로 적어 보냈으므로,
 * 옮기지 않고 그대로 떼어 쓰는 것이 맞다.
 *
 * 「오늘」만은 글자로 못 읽는다 — 브라우저에게 물어야 하고, 그때
 * `Asia/Seoul` 을 함께 준다.
 */

var CLINIC_ZONE = "Asia/Seoul";

/** 「2026-09-01」 */
function clinicDay(iso) {
  var m = /^(\d{4}-\d{2}-\d{2})/.exec(String(iso == null ? "" : iso));
  return m ? m[1] : "";
}

/** 「09-01」 */
function clinicMonthDay(iso) {
  var m = /^\d{4}-(\d{2})-(\d{2})/.exec(String(iso == null ? "" : iso));
  return m ? m[1] + "-" + m[2] : "";
}

/** 「18:00」 */
function clinicTime(iso) {
  var m = /T(\d{2}):(\d{2})/.exec(String(iso == null ? "" : iso));
  return m ? m[1] + ":" + m[2] : "";
}

/** 「09-01 18:00」 */
function clinicStamp(iso) {
  var day = clinicMonthDay(iso);
  var time = clinicTime(iso);
  return day && time ? day + " " + time : day || time;
}

/** 의원의 오늘 — 「2026-09-01」. **보는 사람의 오늘이 아니다.** */
function clinicToday(at) {
  var when = at || new Date();
  /* `sv-SE` 는 `YYYY-MM-DD` 로 준다 — 자리 수를 손으로 맞추지 않아도 된다. */
  return when.toLocaleDateString("sv-SE", { timeZone: CLINIC_ZONE });
}

/** 의원 기준으로 며칠 전/후. 「최근 7일」 같은 창을 만들 때 쓴다. */
function clinicDayShift(days, at) {
  var when = at ? new Date(at.getTime()) : new Date();
  when.setDate(when.getDate() + days);
  return clinicToday(when);
}

/** 이 시각이 의원의 오늘인가. */
function isClinicToday(iso, at) {
  return !!clinicDay(iso) && clinicDay(iso) === clinicToday(at);
}
