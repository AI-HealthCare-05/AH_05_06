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

/** 「9월 1일 18:00」 — 사람에게 읽어 주는 모양. 못 읽으면 빈 글자.
 *
 * `clinicStamp` 와 같은 값을 다른 옷으로 낸다. 표·목록은 짧은 `09-01 18:00`
 * 이 맞고, 한 줄로 말해 주는 자리(「9월 1일 18:00 까지」)는 이쪽이 맞다.
 *
 * `doctor.js` 의 `whenText` 가 같은 일을 하고 있었다 — 그 파일 안에 있어서
 * 다른 화면이 못 썼고, `patient-link-view.js` 가 제 손으로 `Date` 를 만들다
 * 시간대 버그를 다시 넣었다(`#250` 리뷰 ①). 여기 한 벌만 둔다.
 */
function clinicWhenText(iso) {
  var m = /^\d{4}-(\d{2})-(\d{2})T(\d{2}:\d{2})/.exec(String(iso == null ? "" : iso));
  return m ? Number(m[1]) + "월 " + Number(m[2]) + "일 " + m[3] : "";
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
