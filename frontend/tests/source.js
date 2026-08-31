/* **원문을 읽는 도구.**
 *
 * 화면을 그리는 코드는 shim 아래서 안 돌기 때문에, 어떤 것들은 원문으로 잴
 * 수밖에 없다 (「이 함수를 실제로 쓰는가」 같은 것). 그때 **주석에 적힌 말이
 * 코드로 세어지는** 함정에 여러 번 걸렸다:
 *
 *   · `document_type` 을 안 보낸다는 것을 확인하려는데 내 주석에 그 낱말이
 *     있어서 통과했다
 *   · `tab--later` 를 안 쓴다는 것을 확인하려는데 HTML 주석에 있었다
 *   · `/documents` 로 보내는 자리를 세려는데 주석의 `app/documents/api.py`
 *     가 걸렸다 — 줄이 `(` 로 시작해서 「주석 줄」로 안 걸러졌다
 *
 * 앞의 둘은 줄 첫 글자만 봐도 걸러졌지만, 셋째는 **여러 줄 주석의 가운데
 * 줄**이라 안 걸러진다. 그래서 여기서는 여러 줄 주석의 시작과 끝을 실제로
 * 따라간다.
 *
 * (이 주석 자체도 한 번 걸렸다 — 안에 주석 닫는 기호를 그대로 적었더니
 *  거기서 주석이 끝나고 파일이 깨졌다.)
 */
const fs = require("node:fs");
const path = require("node:path");

const ROOT = path.join(__dirname, "..");

function read(rel) {
  return fs.readFileSync(path.join(ROOT, rel), "utf8");
}

/** 주석과 문자열 밖의 코드만 남긴다. 주석 자리는 빈칸으로 채워 줄 수를 지킨다. */
function codeOnly(text) {
  let out = "";
  let i = 0;
  const n = text.length;

  while (i < n) {
    const two = text.slice(i, i + 2);

    if (two === "/*") {
      const end = text.indexOf("*/", i + 2);
      const stop = end === -1 ? n : end + 2;
      /* 줄바꿈은 남긴다 — 줄 번호로 짚는 검사가 어긋나지 않게 */
      out += text.slice(i, stop).replace(/[^\n]/g, " ");
      i = stop;
      continue;
    }

    if (two === "//") {
      const end = text.indexOf("\n", i);
      const stop = end === -1 ? n : end;
      out += " ".repeat(stop - i);
      i = stop;
      continue;
    }

    out += text[i];
    i += 1;
  }
  return out;
}

/** HTML 주석을 뺀다. 같은 함정이 화면 파일에도 있다. */
function markupOnly(text) {
  return text.replace(/<!--[\s\S]*?-->/g, (m) => m.replace(/[^\n]/g, " "));
}

/** CSS 규칙 하나를 통째로. `.list__head` 를 찾다가 `.list--folded .list__head`
    에 걸린 적이 있어, **줄 처음에 오는** 선택자만 본다. */
function rule(css, selector) {
  const at = css.indexOf("\n" + selector + " {");
  if (at === -1) throw new Error(`${selector} 규칙이 없다 — 검사가 헛돈다`);
  const open = css.indexOf("{", at);
  return css.slice(open, css.indexOf("}", open));
}

module.exports = { read, codeOnly, markupOnly, rule };
