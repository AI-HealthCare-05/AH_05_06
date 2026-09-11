/* 절의 **차례를 바꾸는 화면** — KEY-317.
 *
 * 화면이 지키는 것은 하나다: **만들 수 있는 차례는 전부 서버가 받아 주는
 * 차례다.** 옮길 수 있는 절끼리 자리를 맞바꾸므로 안전 절이 앉은 자리는
 * 건드려지지 않는다.
 *
 * 무엇이 옮겨질 수 있는지는 **서버가 절마다 `movable` 로 말해 준다.** 화면이
 * 스스로 판정하면 정책이 바뀌는 날 한쪽만 고쳐지고, 화면은 옮길 수 있다고
 * 그리는데 서버가 422 를 내는 자리가 생긴다.
 */
const { test } = require("node:test");
const assert = require("node:assert/strict");
const { load } = require("./browser-shim");
const { read, bareCode } = require("./source");

/** 계약 차례 그대로의 다섯 절. 안전 둘은 `movable: false` 다. */
function sections() {
  return [
    { key: "medication", movable: true },
    { key: "caution", movable: false },
    { key: "emergency", movable: false },
    { key: "life", movable: true },
    { key: "messages", movable: true },
  ];
}

function box() {
  /* `esc` 는 `api.js` 에 있다 — 화면이 싣는 차례 그대로 함께 싣는다. */
  return load("api", "guide-view");
}

test("옮길 수 있는 절끼리 자리를 맞바꾼다 — 안전 절은 제자리다", () => {
  const view = box();

  const back = view.guideOrderMoved(sections(), "medication", 1);

  assert.deepEqual(back, ["life", "caution", "emergency", "medication", "messages"]);
  assert.equal(back[1], "caution", "주의사항이 자리를 떴다");
  assert.equal(back[2], "emergency", "응급이 주의사항에서 떨어졌다");
});

test("앞으로 옮길 때도 안전 절을 건너뛴다", () => {
  const view = box();

  assert.deepEqual(view.guideOrderMoved(sections(), "life", -1), [
    "life",
    "caution",
    "emergency",
    "medication",
    "messages",
  ]);
});

test("안전 절은 아예 못 옮긴다 — 단추가 만들어 낼 차례가 없다", () => {
  const view = box();

  assert.equal(view.guideOrderMoved(sections(), "caution", 1), null);
  assert.equal(view.guideOrderMoved(sections(), "emergency", -1), null);
});

test("끝에서 더 밀면 아무 차례도 안 나온다", () => {
  const view = box();

  assert.equal(view.guideOrderMoved(sections(), "medication", -1), null);
  assert.equal(view.guideOrderMoved(sections(), "messages", 1), null);
});

test("화면이 만들어 내는 차례는 언제나 **온전한 한 벌**이다", () => {
  /* 하나라도 빠지거나 겹치면 서버가 422 를 낸다 — 눌렀는데 안 되는 단추가 된다. */
  const view = box();
  const all = sections().map((s) => s.key);

  for (const key of all) {
    for (const step of [-1, 1]) {
      const moved = view.guideOrderMoved(sections(), key, step);
      if (!moved) continue;
      assert.deepEqual([...moved].sort(), [...all].sort(), `${key} ${step} 에서 절이 빠지거나 겹쳤다`);
    }
  }
});

test("단추가 **저장할 차례를 그대로** 들고 있다", () => {
  /* 누른 뒤에 다시 셈하면 그 사이 다시 그려진 화면과 어긋난다. 스탭 화면은
     한 판에 패널을 둘 띄워 「지금 어느 탭인가」가 하나로 답해지지도 않는다. */
  const view = box();

  const html = view.guideMoveHtml(sections(), "medication", true);

  assert.match(html, /data-move="life,caution,emergency,medication,messages"/);
  assert.match(html, /disabled/, "맨 앞인데 [◀] 가 안 잠겼다");
});

test("옮길 수 없는 절을 고르면 단추가 아예 안 선다", () => {
  const view = box();

  assert.equal(view.guideMoveHtml(sections(), "caution", true), "");
});

test("고칠 수 없는 사람에게는 단추를 안 준다", () => {
  /* 승인 뒤·남의 차례에는 서버가 막는다. 화면이 먼저 안 그린다. */
  const view = box();

  assert.equal(view.guideMoveHtml(sections(), "medication", false), "");
});

test("화면은 안전 절 목록을 제 안에 안 적는다", () => {
  /* 서버가 절마다 `movable` 을 준다. 화면에도 적어 두면 정책이 바뀌는 날
     한쪽만 고쳐진다 — 이 저장소가 「목업이 자기 자신을 정본으로 삼는다」로
     여러 번 겪은 자리다. */
  const code = bareCode(read("js/guide-view.js"));

  assert.ok(/\.movable/.test(code), "서버가 준 movable 을 안 읽는다");
  assert.ok(
    !/SAFETY|안전 절 목록은[\s\S]{0,40}=/.test(code) && !/"caution".*"emergency"/.test(code),
    "화면이 안전 절 이름을 제 안에 들고 있다"
  );
});

test("목업도 차례를 저장하고 다시 준다", async () => {
  /* 목업이 이 자리를 모르면 `?mock=1` 로 화면을 검수할 수 없다 — 눌러도
     「불러오지 못했습니다」만 나온다. */
  const api = load("api", "doctor-api");
  const wanted = ["life", "caution", "emergency", "medication", "messages"];

  const saved = await api.doctorApi.reorderSections(8801, { order: wanted });
  const again = await api.doctorApi.guide(8801);

  /* 글자로 견준다 — 목업은 제 realm 의 `Array` 를 돌려줘서 `deepEqual` 이
     「모양은 같은데 같은 것이 아니다」로 떨어진다. */
  assert.equal(saved.sections.map((s) => s.key).join(","), wanted.join(","));
  assert.equal(
    again.sections.map((s) => s.key).join(","),
    wanted.join(","),
    "다시 불러오니 차례가 돌아갔다"
  );
});

test("목업도 안전 절을 옮기는 요청을 서버와 같은 코드로 막는다", async () => {
  /* 목업이 헐거우면 `?mock=1` 에서는 되는데 실서버에서만 422 가 난다. */
  const api = load("api", "doctor-api");

  await assert.rejects(
    api.doctorApi.reorderSections(8801, {
      order: ["medication", "life", "caution", "emergency", "messages"],
    }),
    (error) => error.status === 422 && error.code === "SECTION_ORDER_INVALID"
  );
});

test("목업도 빠뜨린 절을 막는다", async () => {
  const api = load("api", "doctor-api");

  await assert.rejects(
    api.doctorApi.reorderSections(8801, { order: ["medication", "caution", "emergency", "life"] }),
    (error) => error.status === 422
  );
});
