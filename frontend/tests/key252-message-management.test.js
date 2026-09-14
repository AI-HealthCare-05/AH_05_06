const { test } = require("node:test");
const assert = require("node:assert");
const { load } = require("./browser-shim.js");
const { read, codeOnly, markupOnly } = require("./source.js");

test("발송 예정 미리보기와 발송 이력 재발송 경로가 연결된다", () => {
  const api = codeOnly(read("js/messages-api.js"));
  const screen = codeOnly(read("js/manage.js"));

  assert.match(api, /\/visits\/.*\/guide/);
  assert.match(api, /\/messages\/history\/.*\/resend/);
  assert.match(screen, /data-preview-visit/);
  assert.match(screen, /data-resend-message/);
  assert.match(screen, /patientGuidePreviewHtml/);
  assert.match(screen, /재발송이 예약되었습니다/);
});

test("관리 화면은 공용 환자 카드 렌더러만 불러온다", () => {
  const html = markupOnly(read("manage.html"));

  assert.match(html, /\/js\/patient-guide-cards\.js/);
  assert.doesNotMatch(html, /patient_wireframe\/js\/guide\.js/);
});

test("목업에서도 미리보기와 재발송이 실제 계약 모양으로 끝난다", async () => {
  const box = load(
    "api",
    "clinic-clock",
    "message-words",
    "schedule-rules",
    "history-rules",
    "messages-api",
  );
  box.MOCK = true;

  const preview = await box.messagesApi.preview(8803);
  const resent = await box.messagesApi.resend(7001);

  assert.strictEqual(preview.status, "SCHEDULED_TO_SEND");
  assert.ok(preview.approved_at);
  assert.strictEqual(resent.guide_message_id, 9901);
  assert.strictEqual(resent.status, "SCHEDULED");
  assert.strictEqual(JSON.stringify(resent).includes("token"), false);
});

test("링크 상태는 두 배지와 세 종료 사유로만 표시한다", () => {
  const screen = codeOnly(read("js/manage.js"));

  for (const word of ["사용 중", "사용 불가", "기간 만료", "새 링크로 교체", "직접 폐기"]) {
    assert.ok(screen.includes(word), `${word} 표시가 없다`);
  }
});

test("미리보기의 늦은 응답과 모달 기본 접근성을 지킨다", () => {
  const screen = codeOnly(read("js/manage.js"));

  assert.match(screen, /requestVersion !== previewVersion/);
  assert.match(screen, /event\.key === "Escape"/);
  assert.match(screen, /document\.querySelector\(modalReturnSelector\)/);
  assert.match(screen, /returnFocus\.focus\(\)/);
});
