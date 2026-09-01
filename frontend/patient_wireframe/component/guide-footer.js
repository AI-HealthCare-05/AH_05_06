/* 안내 하단 공통 푸터
 *
 * 사용법:
 *   body.appendChild(GuideFooter({ generatedAt: '2026.08.13 10:44', onReport: fn }));
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

  var gen = document.createElement('span');
  gen.className = 'guide-footer__meta';
  gen.textContent = '생성 · ' + (opts && opts.generatedAt ? opts.generatedAt : '');
  wrap.appendChild(gen);

  var reportBtn = document.createElement('button');
  reportBtn.type = 'button';
  reportBtn.className = 'guide-footer__report';
  reportBtn.textContent = '오류 신고';
  reportBtn.addEventListener('click', function () {
    if (opts && opts.onReport) opts.onReport();
  });
  wrap.appendChild(reportBtn);

  return wrap;
}
