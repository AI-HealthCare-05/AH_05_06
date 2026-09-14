const { test } = require('node:test');
const assert = require('node:assert/strict');
const { load } = require('./browser-shim.js');

test('재발송 결과는 서버 상태를 표시하고 새 예약으로 단정하지 않는다', () => {
  const box = load('api', 'message-words', 'history-rules');
  for (const [status, label] of Object.entries({
    SCHEDULED: '예정', SENT: '발송 완료', FAILED: '발송 실패',
    HELD: '보류', CANCELED: '꺼짐', UNKNOWN: '상태 확인 필요',
  })) {
    const html = box.messageResendResultHtml({ guide_message_id: 123, status });
    assert.ok(html.includes('메시지 123 · ' + label), status);
    assert.ok(html.includes('기존 재발송 결과'));
    assert.doesNotMatch(html, /새 메시지|재발송이 예약되었습니다|발송 대기/);
  }
});

test('재발송 결과는 응답 값을 HTML로 실행하지 않는다', () => {
  const box = load('api', 'message-words', 'history-rules');
  const html = box.messageResendResultHtml({ guide_message_id: '<img src=x>', status: '<script>' });
  assert.doesNotMatch(html, /<img|<script>/);
  assert.ok(html.includes('상태 확인 필요'));
});
