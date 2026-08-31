/* **5단계 줄** — 환자 카드의 다섯 칸을 어느 화면에서든 같은 모양으로 그린다.
 *
 * 같은 다섯 단계가 두 화면에 **다른 물건으로** 있었다.
 *
 *     patients.html    <button class="tab" role="tab">   눌러서 옮겨 다닌다
 *     ocr-review.html  <li class="step">                 그림일 뿐, 안 눌린다
 *
 * 그래서 판독 화면에서 「기본정보」를 눌러도 아무 일이 없었고, 앞 화면으로
 * 돌아가려면 왼쪽 목록에서 그 환자를 다시 골라야 했다. 머리말 모양도 두 화면이
 * 달라서 화면을 옮길 때마다 다른 화면처럼 보였다.
 *
 * 구조 진단 §5.1 이 적어 둔 그 자리다 — 「같은 5단계를 한 화면은 `<li>`, 다른
 * 화면은 `<button role="tab">` 으로 만들었다」.
 *
 * 여기 있는 것은 순수 함수다. 화면 요소를 찾지 않으므로 검사가 닿는다.
 */

/* 다섯 단계와 그것이 사는 곳. 순서가 곧 진행 순서다. */
var VISIT_STEPS = [
  { key: "basic", label: "기본정보", page: "/patients.html" },
  { key: "record", label: "진료기록", page: "/patients.html" },
  { key: "guide", label: "안내문", page: "/patients.html" },
  { key: "final", label: "최종 확인", page: "/patients.html" },
  { key: "status", label: "현황", page: "/patients.html" },
];

/* 지금 어디에 서 있는가에 따라 앞 단계는 ✓, 지금은 ●, 아직은 ○.
   와이어프레임 S1-6 의 「✓기본정보 ●진료기록 ○안내문 ○최종 확인 ○현황」 이다. */
function stepMark(stepKey, currentKey) {
  var here = -1;
  var mine = -1;
  for (var i = 0; i < VISIT_STEPS.length; i++) {
    if (VISIT_STEPS[i].key === currentKey) here = i;
    if (VISIT_STEPS[i].key === stepKey) mine = i;
  }
  if (mine === here) return "●";
  return mine < here ? "✓" : "○";
}

/* 그 단계로 가는 주소. **지금 서 있는 칸이면 `null`** — 제자리로 오는 링크가
   가장 나쁘다(눌렀는데 아무 일도 안 일어난 것처럼 보인다).

   같은 화면 안의 탭이면 주소를 만들지 않고 `null` 을 준다 — 그때는 부르는 쪽이
   `showTab` 으로 옮긴다. 화면을 새로 받으면 고르던 값이 사라진다. */
function stepHref(stepKey, currentKey, currentPage, visitId) {
  if (stepKey === currentKey) return null;

  var step = null;
  for (var i = 0; i < VISIT_STEPS.length; i++) {
    if (VISIT_STEPS[i].key === stepKey) step = VISIT_STEPS[i];
  }
  if (!step) return null;
  if (step.page === currentPage) return null; // 같은 화면 안 — 탭으로 옮긴다

  return step.page + "?visit=" + encodeURIComponent(visitId) + "&tab=" + encodeURIComponent(stepKey);
}

/* 주소에서 「어느 진료의 어느 칸을 열까」를 읽는다. */
function stepFromSearch(search) {
  var visit = /[?&]visit=([^&]+)/.exec(search || "");
  var tab = /[?&]tab=([^&]+)/.exec(search || "");
  var key = tab ? decodeURIComponent(tab[1]) : "";

  var known = false;
  for (var i = 0; i < VISIT_STEPS.length; i++) {
    if (VISIT_STEPS[i].key === key) known = true;
  }
  return {
    visitId: visit ? Number(decodeURIComponent(visit[1])) : null,
    tab: known ? key : null,
  };
}

/* 다섯 칸을 그린다. `currentKey` 칸만 채워지고 나머지는 누를 수 있다. */
function stepsHtml(currentKey, currentPage, visitId) {
  return VISIT_STEPS.map(function (step) {
    var here = step.key === currentKey;
    var href = stepHref(step.key, currentKey, currentPage, visitId);
    return (
      '<button class="tab" type="button" role="tab" data-tab="' +
      esc(step.key) +
      '" aria-selected="' +
      (here ? "true" : "false") +
      '"' +
      (href ? ' data-href="' + esc(href) + '"' : "") +
      '><span class="tab__mark" aria-hidden="true">' +
      stepMark(step.key, currentKey) +
      "</span>" +
      esc(step.label) +
      "</button>"
    );
  }).join("");
}
