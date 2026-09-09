/* 환자 화면이 **소리로도 쓸 만한가** — KEY-129.
 *
 * 오늘 KEY-126 에서 판독·의사 화면의 같은 병을 고쳤다. 환자 화면에도 그대로
 * 있었다 — `#guide-body` 가 통째로 라이브 리전이라 **탭을 옮길 때마다 안내문
 * 전체가 다시 낭독**된다. 브라우저에서 셌더니 탭 3 번에 6 번이었다.
 *
 * 완료 조건 「필수 입력·오류·중복 제출·완료 상태가 구분됨」은 눈으로는 이미
 * 되어 있었다. 안 되어 있던 것은 **귀로 구분되는가** 쪽이다.
 *
 * 그리는 것은 여기서 재지 않는다 — 이 저장소의 관례다.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");

const ROOT = path.join(__dirname, "..");

function read(rel) {
  return fs.readFileSync(path.join(ROOT, rel), "utf8");
}

/* ── 안내 화면 ─────────────────────────────────────────────────────────── */

test("안내 본문은 라이브 리전이 아니다 — 탭마다 통째로 읽히면 안 된다", () => {
  const html = read("guide.html");
  const at = html.indexOf('id="guide-body"');
  assert.notStrictEqual(at, -1, "본문을 못 찾았다 — 검사가 헛돈다");

  const tag = html.slice(html.lastIndexOf("<", at), html.indexOf(">", at) + 1);
  assert.doesNotMatch(tag, /aria-live/, `본문이 아직 라이브 리전이다: ${tag}`);
});

test("대신 **바뀐 것만** 알리는 자리가 있다", () => {
  const html = read("guide.html");

  assert.match(html, /id="guide-say"[^>]*role="status"/, "알릴 자리가 없다");
  assert.match(html, /id="guide-say"[^>]*aria-live="polite"/);
  assert.match(html, /class="sr-only"[^>]*id="guide-say"/, "눈에 보이면 화면이 지저분해진다");
});

test("탭을 옮기면 **탭 이름만** 나간다 — 본문이 아니라", () => {
  /* 재는 자리를 옮겼다 — 전에는 `js/guide.js` 를 봤는데 그 파일은 **아무 화면도
     안 싣는 고아**였다. 초록불이 사용자에게 가지 않는 코드를 지키고 있었다
     (KEY-281). 지금은 `guide.html` 이 실제로 싣는 파일을 본다. */
  const js = read("patient_wireframe/js/guide.js");
  const at = js.indexOf("b.addEventListener('click'");
  assert.notStrictEqual(at, -1, "탭 처리기를 못 찾았다 — 검사가 헛돈다");

  const handler = js.slice(at, js.indexOf("});", at));
  assert.match(handler, /sayGuide\(key\)/, "탭 이름을 안 알린다");
});

test("안내를 못 열면 그 사실을 알린다", () => {
  /* 화면에만 뜨면 못 보는 사람은 계속 기다린다. */
  const js = read("patient_wireframe/js/guide.js");
  const at = js.indexOf("guide-load-error__title");
  assert.notStrictEqual(at, -1, "오류 상자를 못 찾았다 — 검사가 헛돈다");

  assert.match(js.slice(at, at + 400), /sayGuide\(/, "오류를 소리로 안 알린다");
});

test("화면 ID 주석이 실제 탭과 맞는다", () => {
  /* 「세 탭」이라고 적혀 있었는데 KEY-95 가 둘을 더해 다섯이었다. */
  const html = read("guide.html");
  const js = read("patient_wireframe/js/guide.js");

  const at = js.indexOf("var TABS = [");
  assert.notStrictEqual(at, -1, "탭 목록을 못 찾았다 — 검사가 헛돈다");
  const tabs = (js.slice(at, js.indexOf("]", at)).match(/'/g) || []).length / 2;
  assert.strictEqual(tabs, 4, `탭 수가 바뀌었다: ${tabs} — 주석도 함께 고친다`);
  assert.match(html.slice(0, 2000), /네 탭/, "주석이 실제 탭 수와 다르다");
});

/* ── D+7 입력 화면 ─────────────────────────────────────────────────────── */

test("저장 실패는 **바로** 알린다", () => {
  /* `polite` 면 읽던 것이 끝날 때까지 기다린다. 저장이 안 됐다는 것은
     기다렸다 알릴 일이 아니다 — 그 사이에 창을 닫는다. */
  const html = read("checkin.html");
  const at = html.indexOf('id="error"');
  assert.notStrictEqual(at, -1);

  const tag = html.slice(html.lastIndexOf("<", at), html.indexOf(">", at) + 1);
  assert.match(tag, /role="alert"/, `오류가 소리로 안 난다: ${tag}`);
  assert.match(tag, /aria-live="assertive"/, "급한 것을 느긋하게 알린다");
});

test("완료 화면이 초점을 받을 수 있다", () => {
  const html = read("checkin.html");
  const at = html.indexOf('id="state"');
  assert.notStrictEqual(at, -1);

  const tag = html.slice(html.lastIndexOf("<", at), html.indexOf(">", at) + 1);
  assert.match(tag, /tabindex="-1"/, "초점을 옮기는데 받을 수가 없다");
  assert.match(tag, /role="status"/);
});

test("완료로 바뀔 때 초점을 실제로 옮긴다", () => {
  /* 폼이 통째로 사라진다. 저장 버튼에 있던 커서가 body 로 떨어지면
     「저장됐어요」를 못 듣는다. */
  const js = read("js/checkin.js");
  const at = js.indexOf("function showOnly(");
  assert.notStrictEqual(at, -1);

  assert.match(js.slice(at, js.indexOf("\n  }", at)), /focus\(\)/, "초점을 안 옮긴다");
});

test("소프트 키보드가 올라와도 저장 버튼이 안 밀린다", () => {
  /* `100vh` 는 키보드만큼 줄지 않는다. 메모 칸에 커서를 두면 저장 버튼이
     키보드 아래로 밀려 안 보인다. */
  const css = read("css/checkin.css");
  const block = css.slice(css.indexOf(".sheet {"), css.indexOf("}", css.indexOf(".sheet {")));

  /* **주석을 걷어내고 잰다.** 처음엔 블록을 통째로 `indexOf` 했는데, 바로
     위 주석에 `100vh` 가 `100dvh` 보다 먼저 나와서 **주석의 순서를 재고
     있었다.** 선언을 뒤집는 돌연변이가 그대로 통과했다. */
  const declarations = block.replace(/\/\*[\s\S]*?\*\//g, "");
  const order = (declarations.match(/min-height:\s*100d?vh/g) || []).map((d) => (d.includes("dvh") ? "dvh" : "vh"));

  assert.deepStrictEqual(order, ["vh", "dvh"], `폴백이 먼저, dvh 가 뒤여야 덮인다: ${order}`);
});

test("**사람에게 뜬 것은 소리로도 난다** — 오류 신고 오버레이", () => {
  /* 전에는 `js/guide.js` 의 `notice()` 배너를 재고 있었다. 그 파일은 **아무
     화면도 안 싣는 고아**였고, 지금 실리는 화면에는 그 배너 자체가 없다 —
     문의·PDF·오류 신고가 배너 대신 오버레이·시트로 바뀌었다.
     그래서 지키려던 것(뜬 것은 소리로도 난다)을 **실제로 실리는 자리**에서
     다시 잰다 (KEY-281 이 남긴 처분).

     탭 이동과 열기 실패는 위 두 검사가 `sayGuide` 로 지킨다. 남은 자리가
     오류 신고 오버레이인데, 보내기 결과가 화면에만 뜨면 못 보는 사람은
     보냈는지 아닌지 모른 채 기다린다. */
  const js = read("patient_wireframe/js/guide.js");
  const at = js.indexOf("var submitStatus");
  assert.notStrictEqual(at, -1, "보내기 결과를 적는 자리를 못 찾았다 — 검사가 헛돈다");

  const block = js.slice(at, at + 300);
  assert.match(block, /setAttribute\('aria-live', 'polite'\)/, "보내기 결과가 화면에만 뜬다");
});
