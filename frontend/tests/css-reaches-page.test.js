/* **화면이 쓰는 클래스가 그 화면이 싣는 CSS 에 있는가.**
 *
 * 같은 뿌리로 세 번 걸렸다.
 *
 *   · `.box` 계열이 `patients.css`·`detail.css` 에만 있어서, 판독 확인 화면의
 *     블록이 테두리 없이 떴다
 *   · `.tabs`·`.tab` 이 `detail.css` 에만 있어서, 단계 줄이 아무 모양 없이 떴다
 *     (「판독 화면으로 넘어가면 상단 레이아웃이 예전 것으로 바뀐다」)
 *   · `.button-ghost--sm` 이 `detail.css` 에만 있어서, 작은 버튼을 붙였는데
 *     큰 버튼이 떴다
 *
 * 셋 다 화면에서 눈으로 봐야 드러났다. 마크업은 옳고 CSS 도 옳은데 **닿지
 * 않는** 것이라, 어느 파일 하나만 봐서는 안 보인다. 여기서 잰다.
 *
 * 완벽하지는 않다 — 클래스를 스크립트가 붙이는 것까지는 못 본다. 화면 파일에
 * 적힌 것만 본다. 그것만으로도 위 셋은 다 잡힌다.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const { markupOnly, codeOnly } = require("./source.js");

const ROOT = path.join(__dirname, "..");

/* 이 파일들이 정의하지 않아도 되는 것 — 브라우저나 다른 데서 온다 */
const NOT_OURS = new Set(["sr-only", "grow"]);

/* **모양이 없는 표시용 이름.** 규칙이 없는 것이 맞다 — 자바스크립트가 잡거나
   사람이 읽으라고 붙인 이름이다. 여기 적어 두면 「빠뜨린 것」과 갈린다.
   새 이름을 무심코 여기 넣지 말 것: 모양이 있어야 하는데 없는 것이 이 검사가
   잡으려는 것이다. */
const MARKERS = new Set([
  "view", // 골격이 번갈아 세우는 칸. 감추는 것은 `hidden` 이 한다
  "step", // 옛 단계 줄(doctor.html). 모양은 `.step--done`·`.step--now` 가 갖는다
]);

function pages() {
  return fs.readdirSync(ROOT).filter((name) => name.endsWith(".html"));
}

function classesIn(html) {
  const out = new Set();
  /* **스크립트 안은 안 본다.** 거기 있는 `class="…"` 는 이어 붙이는 문자열이라
     `.frames__badge--` + level 처럼 반쪽만 잡힌다 — 처음에 그렇게 잡음이 났다. */
  const markup = markupOnly(html).replace(/<script[\s\S]*?<\/script>/g, "");
  for (const m of markup.matchAll(/class="([^"]+)"/g)) {
    for (const one of m[1].split(/\s+/)) {
      if (one && !NOT_OURS.has(one)) out.add(one);
    }
  }
  return out;
}

function cssFilesOf(html) {
  return [...html.matchAll(/href="\/(css\/[a-z-]+\.css)"/g)].map((m) => m[1]);
}

function definedIn(files) {
  const out = new Set();
  for (const rel of files) {
    /* **주석을 걷어낸다.** 안 걷으면 내가 「`.button-primary--sm` 이
       upload.css 에 있었다」고 적어 둔 설명글 때문에 그 이름이 「정의됐다」로
       세어졌다 — 규칙을 실제로 지워도 검사가 안 물었다. 이 함정에 이 파일까지
       포함해 다섯 번째로 걸렸다 (`tests/source.js` 가 그래서 있다). */
    const css = codeOnly(fs.readFileSync(path.join(ROOT, rel), "utf8"));
    /* 선택자에 나오는 클래스 이름을 전부 긁는다. 어느 규칙의 어느 자리든
       그 이름이 쓰였으면 「닿는다」로 본다 — 여기서 재는 것은 **파일이
       실렸는가**이지 규칙이 이기는가가 아니다. */
    for (const m of css.matchAll(/\.([a-zA-Z][\w-]*)/g)) out.add(m[1]);
  }
  return out;
}

test("**화면이 쓰는 클래스가 그 화면이 싣는 CSS 에 닿는다**", () => {
  const missing = [];

  for (const page of pages()) {
    const html = fs.readFileSync(path.join(ROOT, page), "utf8");
    const files = cssFilesOf(html);
    if (!files.length) continue; // CSS 를 안 싣는 화면은 잴 것이 없다

    const have = definedIn(files);
    for (const name of classesIn(html)) {
      if (!have.has(name) && !MARKERS.has(name)) missing.push(`${page}: .${name}`);
    }
  }

  assert.deepEqual(
    missing,
    [],
    "화면에 썼는데 그 화면이 싣는 CSS 어디에도 없다 — 모양 없이 뜬다:\n  " + missing.join("\n  "),
  );
});

test("**공용 어휘가 한 곳에만 있다** — 두 벌이면 한쪽만 고쳐진다", () => {
  /* 바탕 버튼이 `doctor.css` 와 `upload.css` 양쪽에 있었고, `doctor.css`
     안에서도 두 번이었다. 같은 이름을 두 파일이 정의하면 어느 쪽이 이기는지가
     화면마다 달라진다.

     두 가지를 가린다.
       · **같이 실리는 파일끼리만** 본다. `guide.css` 의 `.tab` 은 환자 화면
         것이고 `blocks.css` 와 한 화면에 실리지 않는다 — 이름은 같아도
         부딪히지 않는다.
       · **바탕 정의만** 센다. `@media` 안의 덮어쓰기(들여쓴 `.facts {`)나
         `.button-primary:disabled` 같은 갈래는 더하는 것이지 겨루는 것이
         아니다. 줄 처음에 오고 뒤에 ` {` 만 오는 것을 바탕으로 본다. */
  const defines = (file, sel) => {
    const css = fs.readFileSync(path.join(ROOT, "css", file), "utf8");
    return css.split("\n").some((line) => line === sel + " {");
  };

  /* 어느 화면이 어느 파일들을 같이 싣는가 */
  const together = pages().map((page) =>
    cssFilesOf(fs.readFileSync(path.join(ROOT, page), "utf8")).map((rel) => rel.replace("css/", "")),
  );

  const shared = [
    ".box", ".box__head", ".box__title", ".facts", ".cols2",
    ".tabs", ".tab", ".button-ghost", ".button-primary",
    ".blank", ".warnline", ".vtabs",
  ];

  const clash = [];
  for (const sel of shared) {
    for (const files of together) {
      const owners = files.filter((f) => defines(f, sel));
      if (owners.length > 1) clash.push(`${sel} → ${owners.join(", ")}`);
    }
  }

  assert.deepEqual([...new Set(clash)], [], "한 화면에 실리는 두 파일이 같은 것을 정의한다");
});
