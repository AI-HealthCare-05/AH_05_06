/* **종류는 화면이 정하지 않는다** — 업로드 뒤 고르개를 없앤 것.
 *
 * 전에는 올린 파일마다 「과거기록 · 소견 · 검사지」를 고르는 칸이 붙었다.
 * 값은 파일명 정규식(`guessKind`)이 어림잡았고 사람이 고칠 수 있었다.
 *
 * 와이어프레임 설계 주석은 그 반대를 말한다 —
 * 「진료기록을 종류별로 나눠 올리게 하면 스탭이 매번 어느 칸인지 고민한다.
 *  **한 버튼으로 받고 무엇이 찍혔는지는 프로그램이 가려낸다**」.
 *
 * 그리고 파일명으로는 못 맞힌다. 「스크린샷 2026-08-14.png」에는 단서가 없다.
 * 더 나쁜 것은 그 값이 **다음 단계를 잠갔다**는 점이다 — 파일명에 「검사」가 든
 * EMR 을 올리면 「업로드 후 안내문 생성」이 잠긴 채로 남았고, 고르개를 고쳐야만
 * 풀렸다.
 *
 * 서버는 `document_type` 을 선택값으로 받고 없으면 EMR 로 둔다
 * (`app/documents/api.py:36` · `service.py:43`). 판독이 실제 종류를 가려낸다.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const { load } = require("./browser-shim.js");

const ROOT = path.join(__dirname, "..");

function read(rel) {
  return fs.readFileSync(path.join(ROOT, rel), "utf8");
}

/* **주석을 뺀 코드 줄만 돌려준다.** 설명 문단에 `document_type` 같은 낱말이
   적혀 있으면, 글자로 찾는 검사가 제 주석을 물고 실패하거나 통과한다. */
function codeOnly(source) {
  return source
    .split("\n")
    .filter((line) => {
      const t = line.trim();
      return t && !t.startsWith("/*") && !t.startsWith("*") && !t.startsWith("//");
    })
    .join("\n");
}

test("**화면이 종류를 어림잡지 않는다**", () => {
  const source = codeOnly(read("js/upload.js"));

  assert.ok(!source.includes("function guessKind"), "파일명으로 종류를 어림잡는다");
  assert.ok(!/var KINDS\s*=/.test(source), "고르개 목록이 남아 있다");
  assert.ok(!/KIND_TO_TYPE/.test(source), "화면 종류를 서버 값으로 옮기는 표가 남아 있다");
});

test("**고르개를 그리지 않는다**", () => {
  const source = codeOnly(read("js/upload.js"));

  assert.ok(!source.includes('class="file__kind"'), "파일마다 종류 고르개를 그린다");
  assert.ok(!source.includes('data-kind='), "고르개를 듣는 자리가 남아 있다");
});

test("**서버에 종류를 보내지 않는다** — 서버가 EMR 로 두고 판독이 가려낸다", () => {
  const source = codeOnly(read("js/upload.js"));
  const at = source.indexOf("new FormData()");
  assert.notEqual(at, -1, "업로드가 FormData 를 안 쓴다 — 검사가 헛돈다");

  const body = source.slice(at, at + 500);
  assert.ok(!body.includes("document_type"), "화면이 종류를 정해 보낸다");
  assert.ok(body.includes('form.append("files"'), "파일을 안 싣는다 — 검사가 헛돈다");
});

test("**다음 단계가 종류로 잠기지 않는다** — 못 맞히는 값으로 길을 막지 않는다", () => {
  const source = read("js/upload.js");
  const at = source.indexOf("next.disabled =");
  assert.notEqual(at, -1, "다음 단추 잠금이 없다 — 검사가 헛돈다");

  const line = source.slice(source.lastIndexOf("\n", at), source.indexOf("\n", at));
  assert.ok(
    !/kind|emr/i.test(line),
    `종류로 다음 단계를 잠근다 — 파일명을 잘못 읽으면 영영 안 열린다: 「${line.trim()}」`,
  );
  assert.ok(/done\.length/.test(line), "올린 것이 있는지로 재지 않는다");
});

test("파일 그림도 이모지가 아니다", () => {
  const source = codeOnly(read("js/upload.js"));
  assert.ok(!source.includes("📄"), "PDF 이모지가 남아 있다");
  assert.ok(!source.includes("🖼"), "그림 이모지가 남아 있다");

  const { filePic } = load("api", "session", "patients-api", "shell", "upload");
  assert.match(filePic("application/pdf"), /<svg class="file__pic"/, "PDF 그림이 없다");
  assert.match(filePic("image/png"), /<svg class="file__pic"/, "이미지 그림이 없다");
  assert.notStrictEqual(
    filePic("application/pdf"),
    filePic("image/png"),
    "PDF 와 이미지가 같은 그림이다 — 갈라 보이지 않는다",
  );
  assert.match(filePic("image/png"), /aria-hidden="true"/, "그림을 낭독기가 읽는다");
});

test("설명 카드 셋은 그대로 있다 — 무엇을 올려야 하는지는 여전히 말해 준다", () => {
  /* 고르개를 없앤 것이지 안내를 없앤 것이 아니다. 어떤 화면을 찍어 와야 하는지는
     여전히 화면이 말해야 한다 — 그것까지 사라지면 스탭이 무엇을 올릴지 모른다. */
  const html = read("patients.html");
  for (const kind of ["EMR 과거기록", "소견 · 메모", "검사 결과지"]) {
    assert.ok(html.includes(kind), `설명 카드가 사라졌다: ${kind}`);
  }
  assert.ok(
    html.includes("자동으로 분류합니다"),
    "자동 분류한다는 안내가 없다 — 고르개가 없는 이유가 안 보인다",
  );
});
