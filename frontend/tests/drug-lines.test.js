/* 처방약 내역 — 판독 화면(S1-6) — 2heej 님 `#176` 리뷰.

   원문 요청:
       처방약1  28일  일 1회 같은시간
       처방약2  28일  아침 식후
       처방약3  10일  필요 시 복용

   **가장 크게 재는 것은 「며칠인가」다.** 이 숫자가 안내문에 그대로 나가고
   소진 예정일과 문자 발송일이 여기서 갈린다. 「필요시」 약에 84일을 붙이면
   「진통제를 84일간 드세요」가 되고, 소진 예정일도 진통제 기준으로 하나 더
   생긴다. 그래서 **모르면 셈하지 않는다.**
*/
const { test } = require("node:test");
const assert = require("node:assert");
const { load } = require("./browser-shim.js");
const { read, codeOnly, markupOnly } = require("./source.js");

function rules() {
  return load("api", "drug-lines");
}

function a_set(over) {
  return Object.assign({ days_mode: "DAYS", days_per_pack: null, drugs: [] }, over || {});
}

test("**일수로 세는 처방은 총투가 그대로 일수다**", () => {
  const { drugLines } = rules();
  const set = a_set({ drugs: [{ name: "비잔정 2mg", frequency: "1일 1회", note: "매일 같은 시간" }] });

  const lines = drugLines(set, "84");
  assert.equal(lines.length, 1);
  assert.equal(lines[0].name, "비잔정 2mg");
  assert.equal(lines[0].days, 84);
  assert.equal(lines[0].saying, "1일 1회 · 매일 같은 시간");
});

test("**통으로 세는 처방은 한 통 일수를 곱한다** — 「3」이 3일이 아니라 84일이다", () => {
  const { drugLines } = rules();
  const set = a_set({
    days_mode: "PACK",
    days_per_pack: 28,
    drugs: [{ name: "야즈정", frequency: "1일 1회" }],
  });

  assert.equal(drugLines(set, "3")[0].days, 84);
});

test("**한 통이 며칠인지 모르면 셈하지 않는다** — 지어낸 날짜로 문자가 나간다", () => {
  const { drugLines } = rules();
  const set = a_set({ days_mode: "PACK", days_per_pack: null, drugs: [{ name: "야즈정" }] });

  assert.equal(drugLines(set, "3")[0].days, null, "통 일수가 없는데 셈했다");
});

test("**총투를 못 읽었으면 셈하지 않는다**", () => {
  const { drugLines } = rules();
  const set = a_set({ drugs: [{ name: "비잔정 2mg" }] });

  for (const written of [null, "", "0", "-3", "몰라"]) {
    assert.equal(drugLines(set, written)[0].days, null, `「${written}」로 셈했다`);
  }
});

test("**「필요시」 약에는 기간을 안 붙인다** — 「진통제를 84일간 드세요」가 된다", () => {
  const { drugLines } = rules();
  const set = a_set({
    drugs: [
      { name: "비잔정 2mg", frequency: "1일 1회" },
      { name: "진통제", frequency: "필요시" },
    ],
  });

  const lines = drugLines(set, "84");
  assert.equal(lines[0].days, 84);
  assert.equal(lines[1].days, null, "필요시 약에 기간이 붙었다");
});

test("**띄어쓰기가 달라도 「필요시」다** — EMR 마다 다르게 적는다", () => {
  const { drugLines } = rules();
  for (const frequency of ["필요시", "필요 시", "필요시 복용", "필요 시 복용"]) {
    const set = a_set({ drugs: [{ name: "진통제", frequency: frequency }] });
    assert.equal(drugLines(set, "84")[0].days, null, `「${frequency}」에 기간이 붙었다`);
  }
});

test("**빈 칸은 자리를 차지하지 않는다** — 가운뎃점만 남으면 빠진 것처럼 보인다", () => {
  const { drugLines } = rules();
  const set = a_set({
    drugs: [
      { name: "약1", frequency: "1일 1회", note: null },
      { name: "약2", frequency: null, note: "아침 식후" },
      { name: "약3", frequency: null, note: null },
    ],
  });

  const lines = drugLines(set, "28");
  assert.equal(lines[0].saying, "1일 1회");
  assert.equal(lines[1].saying, "아침 식후");
  assert.equal(lines[2].saying, "");
});

test("**차례는 설정이 정한 그대로다** — 이름순으로 세우지 않는다", () => {
  const { drugLines } = rules();
  const set = a_set({ drugs: [{ name: "하약" }, { name: "가약" }] });

  assert.deepEqual(
    drugLines(set, "28").map((one) => one.name),
    ["하약", "가약"],
  );
});

test("**약이 없으면 빈 목록이다** — `null` 이 아니다", () => {
  const { drugLines } = rules();
  assert.deepEqual(drugLines(a_set(), "28"), []);
  assert.deepEqual(drugLines(null, "28"), []);
});

test("**고르기 전에는 아무것도 안 그린다** — 빈 목록이 「약 없는 처방」으로 읽힌다", () => {
  const code = codeOnly(read("js/ocr-review.js"));
  const at = code.indexOf("function drugsHtml");
  assert.notEqual(at, -1, "그리는 자리가 없다");
  assert.match(code.slice(at, at + 200), /if \(!pickedSet\) return ""/);
});

test("**못 셈한 일수는 비워 둔다** — 「0일」을 적으면 값으로 읽힌다", () => {
  const code = codeOnly(read("js/ocr-review.js"));
  const at = code.indexOf("function drugsHtml");
  const body = code.slice(at, code.indexOf("function renderFields"));
  assert.match(body, /line\.days === null/, "못 셈한 자리를 안 가른다");
  assert.doesNotMatch(body, /"0일"|'0일'/, "0일을 적는다");
});

test("**비었으면 어디서 채우는지 적는다**", () => {
  const code = codeOnly(read("js/ocr-review.js"));
  const at = code.indexOf("function drugsHtml");
  const body = code.slice(at, code.indexOf("function renderFields"));
  assert.match(body, /설정/, "채우는 자리를 안 알려 준다");
});

test("**판독 화면이 규칙 파일을 싣는다**", () => {
  assert.ok(markupOnly(read("ocr-review.html")).indexOf("drug-lines.js") !== -1);
});
