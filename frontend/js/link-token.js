/* 환자 링크 토큰을 주소에서 읽는 **한 곳** — KEY-292.
 *
 * 규칙은 하나다: **조각(`#t=`)을 먼저 본다.**
 *
 * 조각은 서버 요청에 안 실리고 nginx access log 에도 안 남는다. 그래서
 * AGENTS.md 「환자 링크 토큰을 코드·화면·로그·커밋에 남기지 않는다」를 지키는
 * 자리가 바로 여기다. 질의문자열(`?token=`·`?t=`)은 **받아만 준다** — 그 모양을
 * 만드는 코드는 저장소에 더 없지만, 이미 나간 옛 주소가 아직 살아 있을 수 있다.
 *
 * 🚩 **네 화면이 같은 줄을 각자 베껴 갖고 있었다** (이희진 님 `#255` ③).
 *
 *     frontend/patient_wireframe/html/otp.html
 *     frontend/patient_wireframe/html/otp-verify.html
 *     frontend/js/checkin.js
 *     frontend/patient_wireframe/js/guide.js
 *
 * KEY-267 이 `checkin.js` 를 조각 우선으로 옮겼을 때 나머지 셋이 안 따라왔고,
 * 그래서 실서버에서 본인 확인 화면이 토큰을 못 읽었다 — **KEY-292 가 고치려던
 * 버그 자체가 이 중복이었다.** 한 벌로 둔다.
 *
 * 목업인지는 **안 본다.** 목업일 때만 조각을 읽던 것이 바로 그 버그였고,
 * 갈래를 다시 두면 「목업에서는 되는데 실서버에서는 안 되는」 거리가 또 생긴다.
 */

/** 주소에서 링크 토큰을 읽는다. 없으면 빈 글자.
 *
 * @param {{search: string, hash: string}} where  보통 `window.location`.
 * @param {string[]} [legacyQueryKeys]  옛 주소가 쓰던 질의 이름. 순서대로 본다.
 *   화면마다 다르다 — 본인 확인은 `?token=`, 체크인·안내는 `?t=`(안내는 `?visit=`
 *   까지). **여기서 합치지 않는다**: 한 화면이 다른 화면의 옛 이름까지 받아 주면
 *   그 화면이 만든 적 없는 주소를 열어 주게 된다.
 */
function linkTokenFrom(where, legacyQueryKeys) {
  var at = where || {};
  var fragment = new URLSearchParams(String(at.hash || "").replace(/^#/, ""));
  var fromFragment = fragment.get("t");
  if (fromFragment) return fromFragment;

  var query = new URLSearchParams(String(at.search || ""));
  var keys = legacyQueryKeys || [];
  for (var i = 0; i < keys.length; i++) {
    var found = query.get(keys[i]);
    if (found) return found;
  }
  return "";
}
