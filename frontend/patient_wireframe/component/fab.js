/* 드래그 가능한 FAB 컴포넌트
 *
 * 사용법:
 *   var fab = Fab({ defaultBottom: 88, defaultRight: 20 }, function onClick() { ... });
 *   document.body.appendChild(fab.el);
 *   fab.showBadge(true);
 */
function Fab(opts, onClick) {
  var bottom = opts.defaultBottom || 88;
  var right  = opts.defaultRight  || 20;

  var el = document.createElement('button');
  el.type = 'button';
  el.className = 'fab';
  el.setAttribute('aria-label', '의료 상담 챗봇 열기');
  el.innerHTML = '💬<span class="fab-badge" id="fab-badge"></span>';
  el.style.bottom = bottom + 'px';
  el.style.right  = right  + 'px';

  /* ── 드래그 ─────────────────────────────── */
  var dragging = false;
  var startX, startY, startRight, startBottom;

  function onPointerDown(e) {
    dragging = false;
    startX = e.clientX;
    startY = e.clientY;
    startRight  = parseInt(el.style.right,  10);
    startBottom = parseInt(el.style.bottom, 10);

    window.addEventListener('pointermove', onPointerMove);
    window.addEventListener('pointerup',   onPointerUp);
    el.setPointerCapture(e.pointerId);
    e.preventDefault();
  }

  function onPointerMove(e) {
    var dx = e.clientX - startX;
    var dy = e.clientY - startY;
    if (!dragging && Math.sqrt(dx * dx + dy * dy) < 6) return;
    dragging = true;
    el.classList.add('fab--dragging');

    var vw = window.innerWidth;
    var vh = window.innerHeight;
    var size = 52;
    var newRight  = Math.max(8, Math.min(vw  - size - 8, startRight  - dx));
    var newBottom = Math.max(8, Math.min(vh  - size - 8, startBottom + dy));
    el.style.right  = newRight  + 'px';
    el.style.bottom = newBottom + 'px';
  }

  function onPointerUp() {
    window.removeEventListener('pointermove', onPointerMove);
    window.removeEventListener('pointerup',   onPointerUp);
    el.classList.remove('fab--dragging');
    if (!dragging && onClick) onClick();
    dragging = false;
  }

  el.addEventListener('pointerdown', onPointerDown);

  return {
    el: el,
    showBadge: function (show) {
      var badge = el.querySelector('#fab-badge');
      if (badge) badge.classList.toggle('fab-badge--show', !!show);
    },
  };
}
