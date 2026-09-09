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
const { read, loadFrames } = require("./source.js");

const DOC = "docs/구현현황.md";

function manifestIds() {
  return new Set(loadFrames().FRAMES.map((frame) => frame.id));
}

/** 문서 **표의 첫 칸**에 오는 화면 번호만 본다.
 *
 * 본문 아무 데나 나오는 `P1` 같은 글자까지 세면, 문단에서 묶어 부르는 이름
 * (`P2` · `D1`)이 전부 「없는 번호」로 잡혀 검사가 늘 운다. 재려는 것은
 * **표가 가리키는 화면**이다.
 *
 * 🚩 붙임표를 **강요하면 안 된다.** 처음엔 `-\d+` 를 못 박았는데, 그러면
 * 매니페스트에 실재하는 `P9`(문서의 `| P9 | 오류 신고 |` 행)가 아예 안 들어와
 * 그 행은 오타를 내도 안 울었다 (2heej 님 리뷰 ①). 줄 앞이 `|` 로 앵커돼
 * 있으니 붙임표를 선택으로 두어도 문단의 그룹명은 안 걸린다. */
function docIds() {
  const found = new Set();
  for (const line of read("../" + DOC).split("\n")) {
    const match = /^\|\s*([A-Z]\d?(?:-\d+)?)\s*\|/.exec(line);
    if (match) found.add(match[1]);
  }
  return found;
}

test("**문서가 없는 화면 번호를 말하지 않는다** — 번호가 바뀌면 문서만 옛것을 든다", () => {
  const manifest = manifestIds();
  const doc = docIds();

  /* 정규식이 헛도는지 보는 가드다. **절대 수를 박으면 문서 정리에 걸린다** —
     이 문서는 `S1-6~S1-9` 처럼 여러 화면을 한 행에 묶는 습관이 있어서, 묶을
     때마다 단일 id 행이 줄어든다 (2heej 님 리뷰 ②). 매니페스트에 대한 몫으로
     잰다 — 표가 무엇을 담든 「절반쯤은 단일 행이다」는 유지된다. */
  assert.ok(
    doc.size >= manifest.size / 3,
    `문서 표에서 화면 번호를 ${doc.size}개밖에 못 찾았다 (매니페스트 ${manifest.size}) — 검사가 헛돈다`,
  );

  const missing = [...doc].filter((id) => !manifest.has(id)).sort();
  assert.deepEqual(missing, [], `문서가 표에 없는 화면을 말한다 — ${missing.join(" · ")}`);
});

test("**문서가 스스로 사진임을 밝히고 살아 있는 표를 가리킨다**", () => {
  /* 이것이 없으면 다음 사람이 이 문서를 지금 상태로 읽는다. 실제로 이 문서는
     9일 지난 뒤에도 「전체 62개 중 31개 구현」이라고 적혀 있었다.

     🚩 처음엔 `/스냅샷/` 하나로 봤는데, 그 낱말은 **이 PR 전에도 3번째 줄에
     있었다** — KEY-218 안내 블록을 통째로 지워도 통과했다 (2heej 님 리뷰 ④,
     제가 리뷰에 관찰로만 적어 둔 것과 같은 자리다). 이 PR 이 넣은 블록을
     가리키는 표시로 잰다. */
  const doc = read("../" + DOC);

  assert.match(doc, /⏸ \*\*이 문서는 그날의 사진이다/, "이 PR 이 넣은 안내 블록이 없다");
  assert.match(doc, /KEY-218/, "어느 일감이 이 블록을 세웠는지 안 밝힌다");
  assert.match(doc, /스냅샷/, "언제 찍은 사진인지 안 밝힌다");
  assert.ok(doc.includes("frontend/js/frames.js"), "지금 상태를 어디서 보는지 안 가리킨다");
  assert.ok(doc.includes("map.html"), "화면 지도를 안 가리킨다");
});
