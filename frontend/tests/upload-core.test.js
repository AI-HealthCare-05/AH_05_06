/* **진료기록 올리기 — 알맹이.** `js/upload-core.js`
 *
 * 올리는 자리가 둘이다: 진료기록 탭(S1-5)과 판독 확인 화면(S1-6) 왼쪽 판.
 * 두 화면이 각자 올리는 코드를 가지면 크기 제한이나 보내는 주소가 갈라지고,
 * 한쪽만 고쳐져 **어디서 올렸느냐에 따라 되고 안 되고가 달라진다.**
 */
const { test } = require("node:test");
const assert = require("node:assert");
const { load } = require("./browser-shim.js");
const { read, codeOnly } = require("./source.js");

function box() {
  return load("api", "session", "upload-core");
}

function file(type, size) {
  return { type: type, size: size, name: "x" };
}

const MB = 1024 * 1024;

/* ── 받을 수 있는가 ─────────────────────────────────────────────────── */

test("**너무 큰 파일은 올리기 전에 막는다** — 20MB 를 보내고 실패를 보는 것보다 낫다", () => {
  const { rejectFile } = box();

  assert.equal(rejectFile(file("image/jpeg", 5 * MB)), null, "5MB 를 막았다");
  assert.equal(rejectFile(file("image/jpeg", 20 * MB)), null, "딱 20MB 는 된다");
  assert.match(rejectFile(file("image/jpeg", 21 * MB)), /너무 큽니다/, "21MB 가 통과했다");
});

test("**이미지와 PDF 만 받는다** — 다른 것은 판독기가 못 읽는다", () => {
  const { rejectFile } = box();

  assert.equal(rejectFile(file("image/png", 1 * MB)), null);
  assert.equal(rejectFile(file("image/heic", 1 * MB)), null, "아이폰 사진이 막혔다");
  assert.equal(rejectFile(file("application/pdf", 1 * MB)), null);

  assert.match(rejectFile(file("text/plain", 100)), /이미지나 PDF/, "글 파일이 통과했다");
  assert.match(rejectFile(file("application/zip", 100)), /이미지나 PDF/, "압축 파일이 통과했다");
  assert.match(rejectFile(file("", 100)), /이미지나 PDF/, "형식을 모르는 것이 통과했다");
});

test("**왜 안 되는지 말한다** — 「올릴 수 없습니다」만으로는 무엇을 고칠지 모른다", () => {
  const { rejectFile } = box();

  const big = rejectFile(file("image/jpeg", 30 * MB), (n) => Math.round(n / MB) + "MB");
  assert.match(big, /20MB/, "얼마까지 되는지 안 알려 준다");
});

test("파일이 없으면 넘어지지 않는다", () => {
  const { rejectFile } = box();
  assert.match(rejectFile(null), /파일이 없습니다/);
});

/* ── 몇 장까지 ──────────────────────────────────────────────────────── */

test("**한 번에 10장까지** — 넘치면 자르되 조용히 버리지 않는다", () => {
  const { roomFor, UPLOAD_MAX_FILES } = box();

  assert.equal(UPLOAD_MAX_FILES, 10);
  assert.equal(roomFor(0), 10, "아무것도 안 올렸는데 자리가 없다");
  assert.equal(roomFor(7), 3);
  assert.equal(roomFor(10), 0, "가득 찼는데 더 받는다");
  assert.equal(roomFor(99), 0, "음수가 나오면 slice 가 뒤에서 자른다");
  assert.equal(roomFor(null), 10);
});

/* ── 두 화면이 같은 것을 쓴다 ───────────────────────────────────────── */

test("**두 화면이 같은 알맹이를 쓴다** — 두 벌이면 한쪽만 고쳐진다", () => {
  /* 올리는 자리는 **판독 화면 하나**다. 전에는 진료기록 탭에도 업로드 판이
     있어서 둘이었고, 한쪽만 고쳐지는 위험이 있었다. 그래서 이 검사가 있었다.
     이제 한 곳이지만, 공용 알맹이를 쓰는지는 계속 본다 — 자기 것을 다시 짜기
     시작하면 제한과 셈이 갈린다. */
  assert.ok(read("ocr-review.html").includes("/js/upload-core.js"), "판독 화면이 공용 알맹이를 안 싣는다");
  assert.ok(
    !read("patients.html").includes("/js/upload.js"),
    "환자 화면에 업로드 판이 돌아왔다 — 같은 칸에 두 화면이 된다",
  );

  /* 제한을 **각자 정하는** 자리가 남으면 안 된다.
     처음엔 `1024 * 1024` 를 찾았는데, 바이트를 KB 로 세는 `human()` 이 걸렸다 —
     크기를 다루는 것과 **한계를 정하는 것**은 다르다. 한계를 정하는 이름만 본다. */
  for (const js of ["js/ocr-review.js"]) {
    const code = codeOnly(read(js));
    const owns = code.match(/\bvar\s+(MAX_BYTES|MAX_FILES|ACCEPT)\b/g) || [];
    assert.deepEqual(owns, [], `${js} 가 제한을 따로 정한다 (${owns.join(", ")}) — 공용과 갈라진다`);
  }
});

test("**보내는 주소가 한 곳이다**", () => {
  const code = codeOnly(read("js/upload-core.js"));
  assert.ok(code.includes('"/front-desk/visits/"'), "보내는 자리가 없다 — 검사가 헛돈다");

  /* 서버가 EMR 로 두고 판독이 가려낸다 — 화면이 종류를 정하지 않는다 */
  assert.ok(!code.includes("document_type"), "화면이 종류를 정해 보낸다");
});

test("**창 전체에 놓아도 화면이 안 날아간다** — 빗나가면 브라우저가 그 파일로 덮는다", () => {
  const code = codeOnly(read("js/upload-core.js"));
  assert.ok(code.includes("guardWindowDrop"), "창 전체 방어가 없다");
  assert.ok(code.includes("preventDefault"), "기본 동작을 안 막는다");

  /* 두 화면이 각자 붙이면 같은 방어가 두 번 걸린다 — 한 번만 걸리게 */
  assert.ok(code.includes("dropGuardOn"), "여러 번 붙는 것을 안 막는다");
});
