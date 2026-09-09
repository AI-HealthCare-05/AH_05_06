/* 환자 관리 표의 쪽 나눔 규칙 — KEY-303.
 *
 * `manage.js` 는 그리는 일만 한다. 규칙은 `schedule-rules.js` · `history-rules.js`
 * 와 나란히 여기 둔다 — 그래야 화면 없이 검사가 부를 수 있다.
 */

/** 쪽 나눔 — 몇 쪽 중 몇 쪽인가, 앞뒤로 갈 수 있나 (KEY-303).
 *
 * **커서가 아니라 자리(offset)로 센다.** 커서는 앞으로만 가서 「이전」이 안 되고
 * 쪽 번호도 못 붙인다.
 *
 * `total` 은 **지금 고른 조각의** 총수다. 「전체」의 총수로 세면 조각을 눌렀을
 * 때 있지도 않은 쪽이 생긴다.
 */
function rosterPaging(total, offset, limit, serverHasNext) {
  limit = limit > 0 ? Math.floor(limit) : 1;
  total = total > 0 ? Math.floor(total) : 0;
  offset = offset > 0 ? Math.floor(offset) : 0;

  var pages = Math.max(1, Math.ceil(total / limit));
  /* 자리가 총수를 넘으면(마지막 쪽에서 조각을 좁혔을 때) 마지막 쪽으로 본다 */
  var page = Math.min(pages, Math.floor(offset / limit) + 1);

  return {
    page: page,
    pages: pages,
    total: total,
    hasPrev: offset > 0,
    /* **서버가 「더 없다」고 하면 그 말을 따른다.** 총수와 실제 줄이 어긋날 수
       있는 자리가 있으면(조각의 셈이 검색어를 모르는 등) 총수로만 세다가 「다음」
       에 빈 표를 준다. 둘 다 그렇다고 할 때만 앞으로 간다 (이희진 님 #270 리뷰). */
    hasNext: offset + limit < total && serverHasNext !== false,
    prevOffset: Math.max(0, offset - limit),
    nextOffset: offset + limit,
    from: total ? Math.min(total, offset + 1) : 0,
    to: Math.min(total, offset + limit),
  };
}

/** 「101명 중 1–40 · 1/3쪽」. 한 쪽에 다 들어가면 쪽 이야기를 안 한다. */
function rosterPagingSaying(paging) {
  if (!paging || !paging.total) return "";
  var span = paging.from === paging.to ? String(paging.from) : paging.from + "\u2013" + paging.to;
  var head = paging.total + "명 중 " + span;
  return paging.pages > 1 ? head + " \u00b7 " + paging.page + "/" + paging.pages + "쪽" : head;
}
