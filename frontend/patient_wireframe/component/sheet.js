/* 하단 시트 (Bottom Sheet) 컴포넌트
 *
 * 사용법:
 *   var sheet = Sheet({
 *     title: 'PDF 저장 · 범위 고르기',
 *     options: [{ key: 'guide', label: '복약지도' }, ...],
 *     onSave: function(selected) { ... }
 *   });
 *   document.body.appendChild(sheet.el);
 *   document.body.appendChild(sheet.backdrop);
 *   sheet.open();
 *   sheet.close();
 */
function Sheet(opts) {
  var selected = {};
  (opts.options || []).forEach(function (o) { selected[o.key] = true; });

  var backdrop = document.createElement('div');
  backdrop.className = 'pdf-sheet-backdrop';
  backdrop.addEventListener('click', close);

  var el = document.createElement('div');
  el.className = 'pdf-sheet';
  el.innerHTML =
    '<div class="pdf-sheet__handle"></div>' +
    '<h2 class="pdf-sheet__title">' + (opts.title || '') + '</h2>' +
    '<div id="sheet-options"></div>' +
    '<div class="pdf-sheet__actions">' +
      '<button type="button" class="btn-sheet btn-sheet--cancel" id="sheet-cancel">취소</button>' +
      '<button type="button" class="btn-sheet btn-sheet--save"   id="sheet-save">PDF 저장</button>' +
    '</div>';

  function renderOptions() {
    var wrap = el.querySelector('#sheet-options');
    wrap.innerHTML = '';
    (opts.options || []).forEach(function (o) {
      var div = document.createElement('div');
      div.className = 'pdf-option' + (selected[o.key] ? ' pdf-option--checked' : '');
      div.innerHTML =
        '<span class="pdf-option__check">' + (selected[o.key] ? '✓' : '') + '</span>' +
        '<span class="pdf-option__label">' + o.label + '</span>';
      div.addEventListener('click', function () {
        selected[o.key] = !selected[o.key];
        renderOptions();
      });
      wrap.appendChild(div);
    });
  }
  renderOptions();

  el.querySelector('#sheet-cancel').addEventListener('click', close);
  el.querySelector('#sheet-save').addEventListener('click', function () {
    var chosen = Object.keys(selected).filter(function (k) { return selected[k]; });
    if (opts.onSave) opts.onSave(chosen);
    close();
  });

  function open() {
    backdrop.classList.add('pdf-sheet-backdrop--open');
    el.classList.add('pdf-sheet--open');
    document.body.style.overflow = 'hidden';
  }
  function close() {
    backdrop.classList.remove('pdf-sheet-backdrop--open');
    el.classList.remove('pdf-sheet--open');
    document.body.style.overflow = '';
  }

  return { el: el, backdrop: backdrop, open: open, close: close };
}
