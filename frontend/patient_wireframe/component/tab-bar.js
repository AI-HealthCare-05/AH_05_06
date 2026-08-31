/* 재사용 탭 바 컴포넌트
 *
 * 사용법:
 *   var tabs = TabBar('#tabs-container', [
 *     { key: 'status', label: '현황' },
 *     { key: 'guide',  label: '복약지도' },
 *   ], function(key) { ... });
 *   tabs.setActive('status');
 */
function TabBar(containerSelector, items, onChange) {
  var container = typeof containerSelector === 'string'
    ? document.querySelector(containerSelector)
    : containerSelector;
  if (!container) return null;

  var activeKey = items[0] && items[0].key;

  function render() {
    container.innerHTML = '';
    container.className = 'tab-bar';
    container.setAttribute('role', 'tablist');

    items.forEach(function (item) {
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'tab-bar__item' + (item.key === activeKey ? ' tab-bar__item--active' : '');
      btn.textContent = item.label;
      btn.setAttribute('role', 'tab');
      btn.setAttribute('aria-selected', item.key === activeKey ? 'true' : 'false');
      btn.setAttribute('data-key', item.key);

      btn.addEventListener('click', function () {
        if (item.key === activeKey) return;
        activeKey = item.key;
        render();
        if (onChange) onChange(item.key);
      });

      container.appendChild(btn);
    });
  }

  render();

  return {
    setActive: function (key) {
      activeKey = key;
      render();
    },
    getActive: function () { return activeKey; },
  };
}
