/* FAB 컴포넌트
 *
 * 사용법:
 *   var fab = Fab({ defaultBottom: 88, defaultRight: 20 }, function onClick() { ... });
 *   document.body.appendChild(fab.el);
 *   fab.showBadge(true);
 */
function Fab(opts, onClick) {
  var safeBottom = parseInt(getComputedStyle(document.documentElement).getPropertyValue('--sab') || '0', 10) ||
    (CSS && CSS.supports && CSS.supports('padding-bottom', 'env(safe-area-inset-bottom)')
      ? (function () { var d = document.createElement('div'); d.style.paddingBottom = 'env(safe-area-inset-bottom)'; document.body.appendChild(d); var v = parseInt(getComputedStyle(d).paddingBottom, 10) || 0; document.body.removeChild(d); return v; }())
      : 0);
  var bottom = (opts.defaultBottom || 88) + safeBottom;
  var right  = opts.defaultRight  || 20;

  var el = document.createElement('button');
  el.type = 'button';
  el.className = 'fab';
  el.setAttribute('aria-label', '의료 상담 챗봇 열기');
  el.innerHTML = '<img src="/patient_wireframe/assets/chat_bot.png" alt="" class="fab__icon" aria-hidden="true"><span class="fab-badge" id="fab-badge"></span>';
  el.style.bottom = bottom + 'px';
  el.style.right  = right  + 'px';

  el.addEventListener('click', function () {
    if (onClick) onClick();
  });

  return {
    el: el,
    showBadge: function (show) {
      var badge = el.querySelector('#fab-badge');
      if (badge) badge.classList.toggle('fab-badge--show', !!show);
    },
  };
}
