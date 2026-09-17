/* 안내 하단 공통 푸터
 *
 * 사용법:
 *   body.appendChild(GuideFooter({
 *     approvedAt: '2026.08.13',
 *     onHelpful: fn,   // 👍 — 즉시 HELPFUL로 제출
 *     onUnhelpful: fn, // 👎 — UNHELPFUL 기본 선택으로 오류 신고 오버레이를 연다
 *     onReport: fn,    // '오류 신고' — 기본 선택 없이 오버레이를 연다
 *   }));
 */
function GuideFooter(opts) {
  var wrap = document.createElement('div');
  wrap.className = 'guide-footer';

  var note = document.createElement('span');
  note.className = 'guide-footer__note';
  note.textContent = 'ⓘ 이 안내는 담당 의료진이 확인한 내용입니다';
  wrap.appendChild(note);

  var source = document.createElement('span');
  source.className = 'guide-footer__meta';
  source.textContent = '출처 · 식약처 의약품정보';
  wrap.appendChild(source);

  if (opts && opts.approvedAt) {
    var approved = document.createElement('span');
    approved.className = 'guide-footer__meta';
    approved.textContent = '승인 · ' + opts.approvedAt;
    wrap.appendChild(approved);
  }

  /* 「이 안내가 도움이 되었나요?」 — KEY-361. 오류 신고보다 먼저, 눈에 띄게 둔다 —
     대부분의 환자는 문제가 없고, 그 경우엔 한 번의 탭으로 끝나야 한다. */
  if (opts && (typeof opts.onHelpful === 'function' || typeof opts.onUnhelpful === 'function')) {
    var helpfulRow = document.createElement('div');
    helpfulRow.className = 'guide-footer__helpful';

    var helpfulLabel = document.createElement('span');
    helpfulLabel.className = 'guide-footer__helpful-label';
    helpfulLabel.textContent = '이 안내가 도움이 되었나요?';
    helpfulRow.appendChild(helpfulLabel);

    var thumbs = document.createElement('div');
    thumbs.className = 'guide-footer__thumbs';

    var upBtn = document.createElement('button');
    upBtn.type = 'button';
    upBtn.className = 'guide-footer__thumb';
    upBtn.setAttribute('aria-label', '도움이 됐어요');
    upBtn.textContent = '👍';
    if (typeof opts.onHelpful === 'function') upBtn.addEventListener('click', opts.onHelpful);
    thumbs.appendChild(upBtn);

    var downBtn = document.createElement('button');
    downBtn.type = 'button';
    downBtn.className = 'guide-footer__thumb';
    downBtn.setAttribute('aria-label', '도움이 안 됐어요');
    downBtn.textContent = '👎';
    if (typeof opts.onUnhelpful === 'function') downBtn.addEventListener('click', opts.onUnhelpful);
    thumbs.appendChild(downBtn);

    helpfulRow.appendChild(thumbs);

    var helpfulStatus = document.createElement('span');
    helpfulStatus.className = 'guide-footer__helpful-status';
    helpfulStatus.setAttribute('role', 'status');
    helpfulStatus.setAttribute('aria-live', 'polite');
    helpfulStatus.setAttribute('data-feedback-status', '');
    helpfulRow.appendChild(helpfulStatus);
    wrap.appendChild(helpfulRow);
  }

  /* P9가 연결되기 전 실제 화면에 동작하지 않는 조작 요소를 두지 않는다. */
  if (opts && typeof opts.onReport === 'function') {
    var reportBtn = document.createElement('button');
    reportBtn.type = 'button';
    reportBtn.className = 'guide-footer__report';
    reportBtn.textContent = '오류 신고';
    reportBtn.addEventListener('click', opts.onReport);
    wrap.appendChild(reportBtn);
  }

  return wrap;
}
