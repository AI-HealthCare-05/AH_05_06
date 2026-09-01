/* 하단 시트 (Bottom Sheet) 컴포넌트
 *
 * 사용법:
 *   var sheet = Sheet({
 *     title: 'PDF로 저장',
 *     options: [{ key: 'guide', label: '복약지도', desc: '...' }, ...],
 *     defaultSelected: ['guide', 'care'],
 *     onSave: function(selected) { ... }
 *   });
 *   document.body.appendChild(sheet.el);
 *   document.body.appendChild(sheet.backdrop);
 *   sheet.open();
 *   sheet.close();
 */
function Sheet(opts) {
  var selected = {};
  var defaults = opts.defaultSelected || opts.options.map(function (o) { return o.key; });
  (opts.options || []).forEach(function (o) {
    selected[o.key] = defaults.indexOf(o.key) >= 0;
  });

  var backdrop = document.createElement('div');
  backdrop.className = 'pdf-sheet-backdrop';
  backdrop.addEventListener('click', close);

  var el = document.createElement('div');
  el.className = 'pdf-sheet';

  var handle = document.createElement('div');
  handle.className = 'pdf-sheet__handle';

  var title = document.createElement('h2');
  title.className = 'pdf-sheet__title';
  title.textContent = opts.title || 'PDF로 저장';

  var subtitle = document.createElement('p');
  subtitle.className = 'pdf-sheet__subtitle';
  subtitle.textContent = opts.subtitle || '넣을 내용을 고르세요. 탭이 나뉘어 있어도 한 파일로 묶어요.';

  var optionsWrap = document.createElement('div');
  optionsWrap.id = 'sheet-options';

  var note = document.createElement('p');
  note.className = 'pdf-sheet__note';
  note.textContent = 'ⓘ 챗봇 대화는 담기지 않아요. 파일에 이름과 진료일이 들어가니 공유에 주의해 주세요.';

  var actions = document.createElement('div');
  actions.className = 'pdf-sheet__actions';

  var cancelBtn = document.createElement('button');
  cancelBtn.type = 'button';
  cancelBtn.className = 'btn-sheet btn-sheet--cancel';
  cancelBtn.textContent = '취소';
  cancelBtn.addEventListener('click', close);

  var saveBtn = document.createElement('button');
  saveBtn.type = 'button';
  saveBtn.className = 'btn-sheet btn-sheet--save';

  actions.appendChild(cancelBtn);
  actions.appendChild(saveBtn);

  el.appendChild(handle);
  el.appendChild(title);
  el.appendChild(subtitle);
  el.appendChild(optionsWrap);
  el.appendChild(note);
  el.appendChild(actions);

  function countSelected() {
    return Object.keys(selected).filter(function (k) { return selected[k]; }).length;
  }

  function updateSaveBtn() {
    var n = countSelected();
    saveBtn.textContent = '미리보기 (' + n + '쪽)';
    saveBtn.disabled = n === 0;
  }

  function renderOptions() {
    optionsWrap.innerHTML = '';
    (opts.options || []).forEach(function (o) {
      var div = document.createElement('div');
      div.className = 'pdf-option' + (selected[o.key] ? ' pdf-option--checked' : '');

      var check = document.createElement('span');
      check.className = 'pdf-option__check';
      check.textContent = selected[o.key] ? '✓' : '';

      var info = document.createElement('div');
      info.className = 'pdf-option__info';

      var label = document.createElement('div');
      label.className = 'pdf-option__label';
      label.textContent = o.label;

      var desc = document.createElement('div');
      desc.className = 'pdf-option__desc';
      desc.textContent = o.desc || '';

      info.appendChild(label);
      info.appendChild(desc);
      div.appendChild(check);
      div.appendChild(info);

      div.addEventListener('click', function () {
        selected[o.key] = !selected[o.key];
        renderOptions();
        updateSaveBtn();
      });
      optionsWrap.appendChild(div);
    });
  }

  renderOptions();
  updateSaveBtn();

  saveBtn.addEventListener('click', function () {
    var chosen = Object.keys(selected).filter(function (k) { return selected[k]; });
    if (opts.onSave) opts.onSave(chosen);
    close();
  });

  function open() {
    el.style.visibility = 'visible';
    backdrop.classList.add('pdf-sheet-backdrop--open');
    el.classList.add('pdf-sheet--open');
    document.body.style.overflow = 'hidden';
  }
  function close() {
    backdrop.classList.remove('pdf-sheet-backdrop--open');
    el.classList.remove('pdf-sheet--open');
    document.body.style.overflow = '';
    setTimeout(function () {
      if (!el.classList.contains('pdf-sheet--open')) {
        el.style.visibility = '';
      }
    }, 320);
  }

  return { el: el, backdrop: backdrop, open: open, close: close };
}
