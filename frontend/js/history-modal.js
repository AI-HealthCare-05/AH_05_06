/* 환자 이력 모달 — 와이어프레임 S2-2 「★ 신설」. KEY-234.
 *
 * 원문 캡션: 「S2-1 위에 뜬다 · 스탭 · 의사 공통」.
 *
 * **담지 않는 것이 이 화면의 요점 절반이다.** 원문 주석이 층을 못박는다 —
 * 관리에 필요한 만큼(발송 · 열람 · 응답)은 여기서 스탭 · 의사 모두에게,
 * 감사 수준(누가 열어봤나 · 토큰 · 버전 이력)은 어드민 A1-7 로 관리자에게만.
 *
 * 규칙만 둔다. 그리는 일은 `manage.js` 가 한다.
 */

/* 복약 응답을 사람 말로. **환자 화면과 같은 말이어야 한다** —
   `js/checkin-words.js` 것을 쓰고 여기서 다시 적지 않는다. */
function answerSaying(answer) {
  return checkinSaying(answer);
}

/* 「2026-05-20 진료 · 비잔 (계속) · 84일」 */
function courseSaying(block) {
  if (!block) return "";
  var parts = [dayOf(block.visited_at) + " 진료"];
  if (block.prescription_set) parts.push(block.prescription_set);
  if (block.course_days) parts.push(block.course_days + "일");
  return parts.join(" · ");
}

/* 「진료 안내문 — 발송 05-20 18:00 · 열람 05-27 (4장 중 2장)」
 *
 * **한동안 장수를 못 적었다.** 열람 이벤트에 어느 장인지가 안 남아서였다.
 * 이제 환자 화면이 탭을 넘길 때마다 그 장을 알린다(KEY-256).
 *
 * 분수를 적는 까닭: 다 읽은 환자와 첫 장만 열고 닫은 환자는 다음 진료 때 물을
 * 것이 다르다. 「안내문 보셨어요?」에 둘 다 「네」라고 답한다.
 *
 * **분모를 화면이 정하지 않는다.** 서버가 함께 준다 — 장이 늘거나 줄 때
 * 이 화면과 현황 화면이 따로 놀면 어느 쪽이 맞는지 알 수 없다.
 */
function guideSaying(block) {
  if (!block) return "";
  if (!block.guide_sent_at) return "진료 안내문 — 아직 발송되지 않았습니다";
  var said = "진료 안내문 — 발송 " + stamp(block.guide_sent_at);
  if (!block.guide_viewed_at) return said + " · 미열람";
  return said + " · 열람 " + dayShort(block.guide_viewed_at) + pagesSaying(block);
}

/** 「 (4장 중 2장)」 — 앞에 빈칸이 붙는다.
 *
 * **모르면 안 적는다.** 장수를 안 주는 서버(옛 판)나 장이 하나도 안 적힌
 * 열람이면 빈 글자다 — 「4장 중 0장」은 「안 읽었다」로 읽히는데, 실제로는
 * 열긴 열었고 어느 장인지만 모르는 것이다. 둘은 다르다. */
function pagesSaying(block) {
  var total = Number(block && block.guide_pages_total) || 0;
  var read = Number(block && block.guide_pages_read) || 0;
  if (!total || !read) return "";
  return " (" + total + "장 중 " + read + "장)";
}

/* 「확인 문자 — 일주일 뒤 05-27 미열람 · 보름 뒤 06-04 미열람」
   「확인 문자 — 일주일 뒤 02-21 응답 「잘 먹고 있어요」」 */
function checksSaying(block) {
  var rows = (block && block.checks) || [];
  if (!rows.length) return "";
  return (
    "확인 문자 — " +
    rows
      .map(function (row) {
        var head = roundSaying(row.kind) + " " + dayShort(row.at);
        if (!row.sent) return head + " 발송 예정";
        if (row.answer)
          return head + " 응답 「" + answerSaying(row.answer) + "」";
        return head + (row.viewed_at ? " 열람" : " 미열람");
      })
      .join(" · ")
  );
}

/* 「소진 08-12 · 재진 예약 없음」
 **모르면 적지 않는다** — 처방일수가 없으면 소진일도 없다. */
function courseEndSaying(block) {
  if (!block) return "";
  var parts = [];
  if (block.runs_out_on) parts.push("소진 " + dayShort(block.runs_out_on));
  if (!block.revisited) parts.push("재진 예약 없음");
  return parts.join(" · ");
}

/* 아래 한 줄 — 원문 「지난 안내문 4건 중 3건」.
   다 보이면 「몇 건 중 몇 건」이라 하지 않는다. */
function historyCountSaying(body) {
  if (!body) return "";
  var shown = (body.visits || []).length;
  var total = body.total || 0;
  if (!total) return "지난 진료 없음";
  return shown >= total
    ? "지난 진료 " + total + "건"
    : "지난 진료 " + total + "건 중 " + shown + "건";
}

/* 회차 이름에서 「확인」을 덜어낸다 — 앞머리가 이미 「확인 문자 —」라
   「확인 문자 — 일주일 뒤 확인 05-27」이 된다. **낱말을 새로 짓지 않고**
   `message-words.js` 것에서 덜어내는 이유는, 회차 이름이 바뀌면 여기도
   따라가야 하기 때문이다. */
function roundSaying(kind) {
  var said = MESSAGE_SAYING[kind] || kind || "";
  return said.replace(/\s*확인$/, "");
}

function dayOf(iso) {
  var m = /^(\d{4}-\d{2}-\d{2})/.exec(String(iso || ""));
  return m ? m[1] : "";
}

function dayShort(iso) {
  var m = /^\d{4}-(\d{2})-(\d{2})/.exec(String(iso || ""));
  return m ? m[1] + "-" + m[2] : "";
}

function stamp(iso) {
  var m = /^\d{4}-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(String(iso || ""));
  return m ? m[1] + "-" + m[2] + " " + m[3] + ":" + m[4] : "";
}
