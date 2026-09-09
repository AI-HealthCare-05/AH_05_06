/* **8월 31일 사진이 지금 표와 어긋나지 않는다** — KEY-218 인수조건 ④.
 *
 * 티켓은 「화면 ID와 기능 구현 상태가 `docs/구현현황.md` 및 와이어프레임 정본과
 * 일치한다」를 요구한다. 정본 ↔ `frames.js` 대조는 `key234-frame-manifest.test.js`
 * 가 이미 한다. **남은 한 변이 이것이다** — 문서 ↔ 표.
 *
 * 두 표를 나란히 두면 한쪽만 고쳐진다. 그래서 문서는 **그날의 사진**으로 두고,
 * 여기서는 그 사진이 지금 표와 **어긋나지 않는가**만 잰다:
 *
 *   ① 문서가 적은 화면 번호가 전부 표에 있다 — 없는 번호를 말하지 않는다
 *   ② 문서가 스스로 사진임을 밝히고, 살아 있는 표를 가리킨다
 *
 * ①이 없으면 화면 번호가 바뀌었을 때 문서만 옛 번호를 들고 남는다. Sprint 4 를
 * 왜 그렇게 짰는지 되짚는 사람이 없는 화면을 찾게 된다.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { read } = require("./source.js");

const ROOT = path.join(__dirname, "..");
const DOC = "docs/구현현황.md";

function manifestIds() {
  const context = { console };
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(path.join(ROOT, "js", "frames.js"), "utf8"), context);
  return new Set(context.FRAMES.map((frame) => frame.id));
}

/** 문서 **표의 첫 칸**에 오는 화면 번호만 본다.
 *
 * 본문 아무 데나 나오는 `P1` 같은 글자까지 세면, 문단에서 묶어 부르는 이름
 * (`P2` · `D1`)이 전부 「없는 번호」로 잡혀 검사가 늘 운다. 재려는 것은
 * **표가 가리키는 화면**이다. */
function docIds() {
  const found = new Set();
  for (const line of read("../" + DOC).split("\n")) {
    const match = /^\|\s*([A-Z]\d?-\d+)\s*\|/.exec(line);
    if (match) found.add(match[1]);
  }
  return found;
}

test("**문서가 없는 화면 번호를 말하지 않는다** — 번호가 바뀌면 문서만 옛것을 든다", () => {
  const manifest = manifestIds();
  const doc = docIds();

  assert.ok(doc.size >= 30, `문서 표에서 화면 번호를 ${doc.size}개밖에 못 찾았다 — 검사가 헛돈다`);

  const missing = [...doc].filter((id) => !manifest.has(id)).sort();
  assert.deepEqual(missing, [], `문서가 표에 없는 화면을 말한다 — ${missing.join(" · ")}`);
});

test("**문서가 스스로 사진임을 밝히고 살아 있는 표를 가리킨다**", () => {
  /* 이것이 없으면 다음 사람이 이 문서를 지금 상태로 읽는다. 실제로 이 문서는
     9일 지난 뒤에도 「전체 62개 중 31개 구현」이라고 적혀 있었다. */
  const doc = read("../" + DOC);

  assert.match(doc, /스냅샷/, "언제 찍은 사진인지 안 밝힌다");
  assert.ok(doc.includes("frontend/js/frames.js"), "지금 상태를 어디서 보는지 안 가리킨다");
  assert.ok(doc.includes("map.html"), "화면 지도를 안 가리킨다");
});
