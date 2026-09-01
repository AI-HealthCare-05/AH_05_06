/* 복약 응답을 사람 말로 — KEY-151 · 와이어프레임 P6 · S2-2.
 *
 * **화면 둘이 같은 낱말을 쓴다.** 환자가 확인 링크에서 고르는 말(`checkin.js`)과
 * 의료진이 이력에서 읽는 말(`manage.js`)이 같아야 한다 — 환자가 「먹고 있는데
 * 불편해요」를 골랐는데 의원 화면에 다른 문장이 뜨면, 그 둘이 같은 답인지
 * 알 수 없다.
 *
 * `checkin.js` 의 IIFE 안에 있던 것을 꺼냈다. 거기 두면 환자 화면 파일을
 * 통째로 실어야 닿는다 — `roleLabel` 을 `session.js` 로, 문자 어휘를
 * `message-words.js` 로 옮긴 것과 같은 까닭이다.
 */
var CHECKIN_SAYING = {
  taking: "잘 먹고 있어요",
  uncomfortable: "먹고 있는데 불편해요",
  missing: "가끔 놓쳐요",
  stopped_side_effect: "불편해서 중단했어요",
  stopped_improved: "증상이 좋아져서 그만뒀어요",
};

/** 모르는 답은 **적지 않는다** — 코드를 그대로 보이면 사람 말이 아니다. */
function checkinSaying(answer) {
  return CHECKIN_SAYING[answer] || "";
}
