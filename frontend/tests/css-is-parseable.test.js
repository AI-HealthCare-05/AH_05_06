/* **CSS 가 파서에게 성한가** — 중괄호 짝과 선언 모양.
 *
 * 이 검사가 있는 이유가 요점이다. 두 가지가 `blocks.css` 의 **같은 자리**에
 * 각자 규칙을 넣어 충돌했고, 합치면서 닫는 중괄호 하나가 사라졌다. 그 뒤로
 * 파서가 한 칸씩 밀려 **그 아래 규칙이 통째로 죽었다** — `.modal` 이 안 먹어서
 * 「전체 이력 보기」가 겹쳐 뜨지 않고 화면 맨 아래에 그냥 붙었다.
 *
 * 무서운 것은 **아무도 안 운다는 점**이다. CSS 는 깨진 자리를 건너뛰고 계속
 * 읽는다. 검사도 화면도 조용하고, 사람이 그 화면을 열어 봐야 안다.
 *
 * 가지 하나씩은 전부 성했다 — **합치는 순간에만** 깨졌다. 그래서 이것은
 * 사람이 눈으로 지킬 수 있는 종류가 아니다.
 */
const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

const CSS_DIR = path.join(__dirname, "..", "css");

/** 주석을 걷는다. 주석 안의 중괄호까지 세면 멀쩡한 파일이 운다. */
function withoutComments(text) {
  return text.replace(/\/\*[\s\S]*?\*\//g, "");
}

function sheets() {
  const found = fs.readdirSync(CSS_DIR).filter((name) => name.endsWith(".css"));
  assert.ok(found.length >= 3, `CSS 를 ${found.length} 개밖에 못 찾았다 — 검사가 헛돈다`);
  return found;
}

test("중괄호 짝이 맞는다 — 하나만 어긋나도 그 아래가 통째로 죽는다", () => {
  for (const name of sheets()) {
    const code = withoutComments(fs.readFileSync(path.join(CSS_DIR, name), "utf8"));

    let depth = 0;
    let line = 1;
    for (const ch of code) {
      if (ch === "\n") line += 1;
      else if (ch === "{") depth += 1;
      else if (ch === "}") {
        depth -= 1;
        assert.ok(depth >= 0, `${name}:${line} — 열지 않은 중괄호를 닫는다`);
      }
    }
    assert.equal(depth, 0, `${name} — 닫는 중괄호가 ${depth} 개 모자라다. 그 아래 규칙이 전부 안 먹는다`);
  }
});

test("규칙 밖에 떠 있는 선언이 없다", () => {
  /* `}` 를 빠뜨리면 다음 선택자가 앞 규칙 **안으로** 빨려 들어간다. 그때
     중괄호 수는 맞을 수도 있다 — 이 검사가 그 자리를 잡는다: 중괄호 밖에
     `color: …` 같은 선언 줄이 떠 있으면 어딘가 어긋난 것이다. */
  for (const name of sheets()) {
    const code = withoutComments(fs.readFileSync(path.join(CSS_DIR, name), "utf8"));

    let depth = 0;
    code.split("\n").forEach((raw, index) => {
      const text = raw.trim();
      if (depth === 0 && /^[-a-z]+\s*:[^:]/.test(text) && !text.startsWith("--")) {
        assert.fail(`${name}:${index + 1} — 규칙 밖에 선언이 떠 있다: ${text}`);
      }
      depth += (raw.match(/{/g) || []).length - (raw.match(/}/g) || []).length;
    });
  }
});

test("화면이 기대는 규칙이 실제로 있다", () => {
  /* 위 둘이 **모양**을 본다면 이것은 **있느냐**를 본다. 이름을 적어 두는
     대신, 화면이 겹쳐 뜨는 데 반드시 필요한 몇을 골라 둔다 — 이것이 없으면
     모달이 화면 아래에 그냥 붙는다. */
  const blocks = fs.readFileSync(path.join(CSS_DIR, "blocks.css"), "utf8");

  const modal = blocks.slice(blocks.indexOf("\n.modal {"), blocks.indexOf("\n.modal__card"));
  assert.match(modal, /position:\s*fixed/, "모달이 화면에 고정되지 않는다");
  assert.match(modal, /z-index:/, "모달이 다른 것 아래로 깔린다");
});
