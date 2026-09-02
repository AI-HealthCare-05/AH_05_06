/* 안내 하단 공통 푸터
 *
 * 사용법:
 *   body.appendChild(GuideFooter({ approvedAt: '2026.08.13', onReport: fn }));
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
