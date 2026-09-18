const { test } = require("node:test");
const assert = require("node:assert");
const { read } = require("./source.js");

test("약속처방 기본 약과 현재 진료의 직접 입력 약을 구분해서 말한다", () => {
  const source = read("js/ocr-review.js");
  const start = source.indexOf("function drugsHtml(rows)");
  const end = source.indexOf("function manualDrugRowsHtml()", start);
  const drugsHtml = source.slice(start, end);

  assert.ok(start >= 0 && end > start, "약속처방 약 목록 렌더러를 찾지 못했다");
  assert.ok(drugsHtml.includes("약속처방에 기본 약이 없습니다"));
  assert.ok(drugsHtml.includes("현재 진료의 약은 아래 입력값을 확인해 주세요"));
  assert.ok(!drugsHtml.includes("이 처방에 등록된 약이 없습니다"));
});
