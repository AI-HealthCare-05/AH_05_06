/* **상단바 탭이 실제로 어딘가로 가는가.**
 *
 * 다섯 화면이 다 「현황 · 관리 · 설정」을 이고 있는데, 그중 갈 곳이 있는 것은
 * `<button>` 으로 박혀 있어서 **눌러도 아무 일이 없었다**. 모양은 살아 있는
 * 탭이라 눌러 보기 전에는 모른다 — 「설정 링크 활성화해 줘」로 들어왔다.
 *
 * 탭은 셋 중 하나여야 한다.
 *
 *   · `<a href>` — 가는 자리. 그 파일이 실제로 있어야 한다
 *   · `aria-current="page"` — 여기. 갈 곳이 없는 게 맞다
 *   · `tab--later` + `aria-disabled` — 아직 없는 자리. 눌리는 척하지 않는다
 *
 * 넷째는 없다. 손이 붙은 `<button>` 이 필요해지면 그때 여기를 고치면서
 * 「무엇이 그 손을 다는가」를 같이 적으면 된다.
 *
 * 스크립트가 `id` 로 찾아 바꾸는 탭(`to-work`·`to-settings`)도 마크업에서는
 * 이 규칙을 지킨다. 서버가 늦거나 죽어도 골격은 서 있어야 하기 때문이다.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const { markupOnly, codeOnly } = require("./source.js");

const ROOT = path.join(__dirname, "..");

function pages() {
  return fs
    .readdirSync(ROOT)
    .filter((f) => f.endsWith(".html"))
    .filter(
      (f) =>
        markupOnly(fs.readFileSync(path.join(ROOT, f), "utf8")).indexOf(
          "topbar__nav",
        ) !== -1,
    );
}

/* 여는 꺾쇠부터 닫는 꺾쇠까지 — 탭 하나가 이고 있는 속성 전부 */
function tabsOf(markup) {
  const out = [];
  let at = 0;
  for (;;) {
    const hit = markup.indexOf("topbar__tab", at);
    if (hit === -1) return out;
    const open = markup.lastIndexOf("<", hit);
    const close = markup.indexOf(">", hit);
    out.push(markup.slice(open, close + 1));
    at = close;
  }
}

test("상단바 탭은 가거나 · 여기이거나 · 아직 없다고 말한다", () => {
  const seen = pages();
  assert.ok(
    seen.length >= 5,
    `상단바를 인 화면이 ${seen.length}개뿐이다 — 찾는 방법이 틀렸다`,
  );

  for (const page of seen) {
    const markup = markupOnly(fs.readFileSync(path.join(ROOT, page), "utf8"));
    const tabs = tabsOf(markup);
    assert.ok(tabs.length >= 3, `${page} 의 탭이 ${tabs.length}개다`);

    for (const tab of tabs) {
      const goes = /href="([^"]+)"/.exec(tab);
      const here = tab.indexOf('aria-current="page"') !== -1;
      const later = tab.indexOf("tab--later") !== -1;

      assert.ok(
        goes || here || later,
        `${page}: 눌러도 아무 일 없는 탭이 있다 — ${tab}`,
      );

      if (goes) {
        const file = path.join(ROOT, goes[1].replace(/^\//, ""));
        assert.ok(
          fs.existsSync(file),
          `${page}: ${goes[1]} 로 보내는데 그 화면이 없다`,
        );
        assert.ok(
          !here && !later,
          `${page}: 가는 탭이 여기·나중과 겹친다 — ${tab}`,
        );
      }
      if (later) {
        assert.ok(
          tab.indexOf('aria-disabled="true"') !== -1,
          `${page}: ${tab} — 화면낭독기는 못 듣는다`,
        );
      }
    }
  }
});

test("설정은 D2 · 관리는 S2 — 있는 것만 연다", () => {
  for (const page of pages()) {
    const markup = markupOnly(fs.readFileSync(path.join(ROOT, page), "utf8"));
    const asText = markup.slice(
      markup.indexOf("topbar__nav"),
      markup.indexOf("</nav>"),
    );

    /* 설정 화면은 있다 — 여기이거나 가거나 둘 중 하나여야 한다 */
    const settingsIsDead =
      /<button[^>]*topbar__tab(?![^>]*tab--later)(?![^>]*aria-current)[^>]*>\s*설정/.test(
        asText,
      );
    assert.ok(
      !settingsIsDead,
      `${page}: 설정 화면(/settings.html)이 있는데 탭이 죽어 있다`,
    );

    /* 관리(S2)는 아직 화면이 없다. 생기면 이 검사가 먼저 틀린다 */
    if (asText.indexOf("관리") !== -1) {
      assert.ok(
        !fs.existsSync(path.join(ROOT, "manage.html")),
        `${page}: S2 화면이 생겼다 — 관리 탭을 tab--later 에서 풀어야 한다`,
      );
    }
  }
});

test("어드민만 가진 계정은 설정을 열 수 없다", () => {
  const code = fs.readFileSync(path.join(ROOT, "js/session.js"), "utf8");
  const fn = new Function(code + "\nreturn opensSettings;")();

  assert.equal(fn(["staff"]), true);
  assert.equal(fn(["doctor"]), true);
  assert.equal(fn(["admin", "staff"]), true);
  assert.equal(fn(["admin"]), false, "목록 부르는 첫 걸음부터 403 을 받는다");
  assert.equal(fn([]), false);
  assert.equal(fn(), false, "역할이 아직 안 온 순간에도 답해야 한다");
});

/* **상단바 오른쪽의 역할도 사람 말이어야 한다.**
 *
 * `roleLabel` 한 줄이 화면 셋에 흩어져 있는데 어드민만 어긋나 있었다 —
 * 거기만 `roles.join(" · ")` 라서 「의사」가 아니라 `doctor` 로 떴다.
 * 눈으로 봐야 드러나는 부류라 여기서 잰다.
 *
 * 자리를 세지 않고 **`who-roles` 를 채우는 자리 전부**를 본다. 화면이
 * 늘어나도 검사를 고칠 일이 없고, 새 화면이 또 어긋나면 바로 운다.
 */
test("역할은 어느 화면에서나 사람 말로 뜬다", () => {
  const dir = path.join(ROOT, "js");
  const fills = [];

  for (const file of fs.readdirSync(dir).filter((f) => f.endsWith(".js"))) {
    const code = codeOnly(fs.readFileSync(path.join(dir, file), "utf8")).split(
      "\n",
    );
    code.forEach((line, i) => {
      if (line.indexOf("who-roles") === -1) return;
      /* 한 줄에 붙이기도 하고(`getElementById(…).textContent = …`), 변수로
         받아 두었다 몇 줄 뒤에 붙이기도 한다. **그 변수에 붙이는 줄만 본다** —
         창을 넓게 잡았더니 바로 옆의 이름(`name.textContent`) 줄이 걸렸다. */
      let put = line.indexOf(".textContent") !== -1 ? line : null;
      if (!put) {
        const held = /(?:var|const|let)\s+([A-Za-z_$][\w$]*)\s*=/.exec(line);
        assert.ok(
          held,
          `${file}: who-roles 를 찾아만 놓고 받지도 채우지도 않는다`,
        );
        put = code
          .slice(i + 1, i + 6)
          .find((l) => l.indexOf(held[1] + ".textContent") !== -1);
      }
      assert.ok(put, `${file}: who-roles 를 찾아만 놓고 안 채운다`);

      fills.push(file);
      assert.ok(
        put.indexOf("roleLabel") !== -1,
        `${file}: 역할을 그대로 붙인다 — 「의사」가 아니라 doctor 로 뜬다\n  ${put.trim()}`,
      );
    });
  }

  assert.ok(
    fills.length >= 3,
    `역할을 채우는 자리가 ${fills.length}곳뿐이다 — 찾는 방법이 틀렸다`,
  );
});

test("roleLabel 은 아는 역할만 옮기고 모르는 것은 그대로 둔다", () => {
  const code = fs.readFileSync(path.join(ROOT, "js/session.js"), "utf8");
  const fn = new Function(code + "\nreturn roleLabel;")();

  assert.equal(fn(["doctor"]), "의사");
  assert.equal(fn(["staff"]), "스탭");
  assert.equal(fn(["admin"]), "관리자");
  assert.equal(fn(["doctor", "admin"]), "의사 · 관리자");
  assert.equal(fn(["새역할"]), "새역할", "모르는 역할을 지우면 화면이 빈다");
  assert.equal(fn([]), "");
  assert.equal(fn(), "", "역할이 아직 안 온 순간에도 답해야 한다");
});
