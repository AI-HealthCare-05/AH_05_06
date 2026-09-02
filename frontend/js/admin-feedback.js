(function () {
  if (!document.getElementById('feedback-rows')) return;

  var state = { page: 1, pageSize: 20, total: 0 };
  var labels = {
    HELPFUL: '도움됨', UNHELPFUL: '도움 안 됨', WRONG: '안내와 다름',
    HARD_TO_UNDERSTAND: '이해하기 어려움', UNSAFE: '부적절한 의료 안내', OTHER: '기타',
  };

  function filters() {
    return {
      page: state.page,
      pageSize: state.pageSize,
      target: document.getElementById('target-filter').value,
      category: document.getElementById('category-filter').value,
    };
  }

  function renderRows(items) {
    document.getElementById('feedback-rows').innerHTML = items.map(function (item) {
      return '<tr data-feedback-id="' + item.feedback_id + '">' +
        '<td>' + esc(new Date(item.created_at).toLocaleString('ko-KR')) + '</td>' +
        '<td>#' + item.visit_id + '</td>' +
        '<td>' + (item.target === 'CHATBOT_RESPONSE' ? '챗봇 답변' : '안내 내용') + '</td>' +
        '<td>' + esc(labels[item.category] || item.category) + '</td>' +
        '<td>' + (item.has_details ? '내용 있음' : '—') + '</td></tr>';
    }).join('');
  }

  function loadFeedback() {
    var status = document.getElementById('feedback-state');
    var wrap = document.getElementById('feedback-table-wrap');
    status.hidden = false;
    status.textContent = '불러오는 중…';
    wrap.hidden = true;
    return listPatientFeedback(filters()).then(function (data) {
      state.total = data.total;
      renderRows(data.items);
      status.textContent = data.items.length ? '' : '접수된 피드백이 없습니다.';
      status.hidden = data.items.length > 0;
      wrap.hidden = data.items.length === 0;
      var lastPage = Math.max(1, Math.ceil(data.total / state.pageSize));
      document.getElementById('page-label').textContent = state.page + ' / ' + lastPage;
      document.getElementById('page-prev').disabled = state.page <= 1;
      document.getElementById('page-next').disabled = state.page >= lastPage;
    }).catch(function () {
      status.hidden = false;
      status.setAttribute('role', 'alert');
      status.textContent = '피드백을 불러오지 못했습니다. 잠시 뒤 다시 시도해 주세요.';
    });
  }

  document.getElementById('feedback-filters').addEventListener('submit', function (event) {
    event.preventDefault(); state.page = 1; loadFeedback();
  });
  document.getElementById('page-prev').addEventListener('click', function () { state.page -= 1; loadFeedback(); });
  document.getElementById('page-next').addEventListener('click', function () { state.page += 1; loadFeedback(); });
  document.getElementById('logout').addEventListener('click', function () { session.logout(); });

  requireSession().then(function (me) {
    if ((me.roles || []).indexOf('admin') === -1) {
      location.replace(landingFor(me.roles));
      return;
    }
    loadFeedback();
  }).catch(function () {});
})();
