const { test } = require("node:test");
const assert = require("node:assert");
const { read, codeOnly } = require("./source.js");

test("[구현중]과 [임시] 표기는 공통 스타일 한 곳에서 관리한다", () => {
  const css = read("css/tokens.css");

  assert.match(css, /\.implementation-badge\s*\{/);
  assert.match(css, /\.implementation-badge--in-progress\s*\{/);
  assert.match(css, /\.implementation-badge--temporary\s*\{/);
});

test("D+7은 숨기지 않고 시연 범위만 각주로 밝힌다", () => {
  const patients = read("patients.html");
  const guide = codeOnly(read("js/guide-view.js"));
  const status = codeOnly(read("js/status-view.js"));

  assert.match(patients, /이번 시연은 예약 상태까지 보여드립니다/);
  assert.match(guide, /이번 시연은 예약 상태까지 보여드립니다/);
  assert.match(status, /이번 시연은 확인 문자 예약 상태까지 보여드립니다/);
  assert.doesNotMatch(patients, /소진 임박 안내는 자동 발송됩니다/);
  assert.doesNotMatch(guide, /소진 임박 안내는 자동 발송됩니다/);
});

test("D+7 기본값은 고정이라고 표시하지 않는다", () => {
  const settings = codeOnly(read("js/settings.js"));

  assert.doesNotMatch(settings, /일주일 뒤[^\n]{0,80}\(고정\)/);
  assert.match(settings, /일주일 뒤[^\n]{0,120}기본 켜짐 · 환자별 문자 설정에서 변경/);
});

test("준비 중 기능과 시연 문서는 같은 어휘를 쓴다", () => {
  const manage = read("manage.html");
  const readme = read("../README.md");
  const demo = read("../docs/local-demo-accounts.md");

  assert.match(manage, />\[구현중\]</);
  for (const document of [readme, demo]) {
    assert.match(document, /`\[구현중\]`/);
    assert.match(document, /`\[임시\]`/);
  }
});
