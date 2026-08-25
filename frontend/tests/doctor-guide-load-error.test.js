/* 안내문을 못 불러왔을 때 **무엇 때문인지** 말하는가 — KEY-126.
 *
 * `#106` 이 남긴 제한사항이다. 예전에는 무엇이 오든 한 문장이었다.
 *
 *     안내문을 불러오지 못했습니다. 잠시 뒤 다시 시도해 주세요.
 *
 * 그런데 `404 GUIDE_NOT_FOUND` 는 **기다린다고 생기지 않는다.** 아직 아무도
 * 안 만든 것이다. 그 화면에서 원장님은 없는 것을 기다리며 새로고침을 반복한다.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const { load } = require("./browser-shim.js");

function box() {
  return load("api", "session", "patients-api", "shell", "doctor-api", "doctor");
}

test("없는 안내문과 잠깐의 장애가 **다른 말**을 듣는다", () => {
  const { guideLoadSaying } = box();

  const missing = guideLoadSaying({ status: 404, code: "GUIDE_NOT_FOUND" });
  const flaky = guideLoadSaying({ status: 500 });

  assert.notStrictEqual(missing, flaky, "둘이 같으면 원장님이 없는 것을 기다린다");
  assert.doesNotMatch(missing, /잠시 뒤/, "없는 것은 기다린다고 생기지 않는다");
  assert.match(flaky, /잠시 뒤/, "잠깐의 장애는 다시 눌러 볼 만하다");
});

test("없는 안내문은 **지금 무슨 상태인지**를 말한다", () => {
  const { guideLoadSaying } = box();
  const said = guideLoadSaying({ status: 404, code: "GUIDE_NOT_FOUND" });

  assert.match(said, /아직|없습니다/, "상태를 안 말한다");
});

test("의사 화면에 없는 버튼을 가리키지 않는다", () => {
  /* 이 화면이 할 수 있는 것은 승인·되돌리기뿐이다. 안내문을 만드는 길이
     없는데 「만드세요」라고 하면, 찾다가 못 찾는다. */
  const { guideLoadSaying } = box();
  const said = guideLoadSaying({ status: 404, code: "GUIDE_NOT_FOUND" });

  assert.doesNotMatch(said, /만드세요|생성해|눌러/, `없는 버튼을 가리킨다: ${said}`);
});

test("권한 문제는 권한 문제라고 말한다", () => {
  const { guideLoadSaying } = box();

  assert.match(guideLoadSaying({ status: 403 }), /의사 계정/);
});

test("오류가 아예 없어도 말이 나온다", () => {
  /* `catch` 는 `undefined` 로도 불린다. 그때 빈 화면이 되면 안 된다. */
  const { guideLoadSaying } = box();

  for (const nothing of [null, undefined, {}]) {
    const said = guideLoadSaying(nothing);
    assert.ok(said && said.length > 0, `${JSON.stringify(nothing)} 에 할 말이 없다`);
  }
});

test("화면이 그 함수를 실제로 쓴다 — 오류를 삼키지 않는다", () => {
  /* 규칙만 맞고 `catch(function () {...})` 가 인자를 안 받으면 아무 소용이 없다.
     예전 코드가 정확히 그랬다. */
  const source = fs.readFileSync(path.join(__dirname, "..", "js", "doctor.js"), "utf8");

  /* **정의가 아니라 호출부**를 찾는다. `indexOf` 로 이름만 찾으면 파일 맨 위의
     `function guideLoadSaying(error)` 가 먼저 걸려서, 검사가 자기 자신을 재고
     통과한다 — 처음에 그렇게 썼다가 걸렸다. */
  const at = source.indexOf("guideLoadSaying(error);");
  assert.notStrictEqual(at, -1, "화면이 사유를 가려 쓰지 않는다");

  const opened = source.lastIndexOf(".catch(", at);
  assert.notStrictEqual(opened, -1, "호출부 앞에 catch 가 없다");
  assert.match(
    source.slice(opened, at),
    /\.catch\(function \(error\)/,
    "catch 가 오류를 안 받으면 사유를 알 수 없다",
  );
});

test("문장을 고르는 방식은 **공용 헬퍼**가 갖는다", () => {
  /* `detail.js` 의 `messageFor()` 와 같은 모양을 각자 적고 있었다 —
     기본 문구를 바꿀 때 세 곳을 따로 고쳐야 했다 (이희진 님 `#121` 리뷰). */
  const source = fs.readFileSync(path.join(__dirname, "..", "js", "doctor.js"), "utf8");
  const detail = fs.readFileSync(path.join(__dirname, "..", "js", "detail.js"), "utf8");

  assert.match(source, /errorMessage\(error, GUIDE_LOAD_SAYINGS/, "doctor 가 공용 헬퍼를 안 쓴다");
  assert.match(detail, /errorMessage\(error, SAVE_SAYINGS/, "detail 이 공용 헬퍼를 안 쓴다");
});

test("환자가 바뀐 것만 소리로 알린다 — 탭 클릭에는 안 나간다", () => {
  const source = fs.readFileSync(path.join(__dirname, "..", "js", "doctor.js"), "utf8");
  const tabHandler = source.slice(source.indexOf("var tab = target.closest"), source.indexOf("var tab = target.closest") + 300);

  assert.doesNotMatch(tabHandler, /sayPanel\(/, "탭을 누를 때도 소리가 나간다");
  /* 호출 안에 괄호가 중첩돼 있어 `[^)]*` 로는 못 잡는다 — 문구 자리를 먼저
     찾고 그 앞을 짧게 되돌아본다. */
  const said = source.indexOf("안내문을 불러왔습니다");
  assert.notStrictEqual(said, -1, "환자 전환을 안 알린다");
  assert.match(source.slice(Math.max(0, said - 120), said), /sayPanel\(/, "그 문구가 알림으로 안 나간다");
});
