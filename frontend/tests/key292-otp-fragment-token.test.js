/* 실서버에서 환자 본인 확인 화면이 실제로 열린다 — KEY-292.
 *
 * 두 화면(`otp.html` · `otp-verify.html`)이 **목업일 때만** 조각(`#t=`)에서
 * 토큰을 읽고 아니면 `?token=` 을 봤다. 그런데 실서버에서 `MOCK` 은 항상
 * 거짓이고(`js/api.js` 는 `file:`·localhost 에서만 켠다) 보내는 쪽은 모두 조각을
 * 준다. 그래서 디벨롭·운영에서 「본인 확인 열기」가 곧장 오류 화면으로 떨어졌다.
 *
 * **소스 모양을 재지 않는다.** 「`fragment.get` 이라는 낱말이 있는가」는 갈래를
 * 거꾸로 달아도 초록이다. 인라인 IIFE 를 `vm` 에 그대로 태워 `init()` 을 돌리고
 * **어느 화면이 떴는지**와 **토큰이 어디로 실려 갔는지**를 본다. 옆 검사
 * `key205-patient-link-launch.test.js` 가 `guide.js` 에 쓰는 길과 같다.
 */
const { test } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const HTML_DIR = path.join(__dirname, "..", "patient_wireframe/html");
const TOKEN = "synthetic-key292-browser-token";
const VIEWS = ["view-loading", "view-normal", "view-normal-btn", "view-expired", "view-revoked", "view-error"];

function pageHtml(file) {
  return fs.readFileSync(path.join(HTML_DIR, file), "utf8");
}

function inlineScript(file) {
  const html = pageHtml(file);
  const open = html.indexOf("<script>");
  const close = html.indexOf("</script>", open);
  assert.ok(open >= 0 && close > open, `${file} 에서 인라인 스크립트를 못 찾았다`);
  return html.slice(open + "<script>".length, close);
}

/** 이 페이지가 **실제로 싣는** 외부 스크립트를 그 차례대로.
 *
 * 페이지가 `<script src>` 를 빠뜨리면 브라우저에서는 `ReferenceError` 로
 * 화면이 통째로 안 뜨는데, 인라인 조각만 태우던 예전 방식에서는 그것이 안
 * 보였다. 페이지에게 물어 싣는다 — 태그를 빼면 여기서 똑같이 깨진다. */
function pageScripts(file) {
  const html = pageHtml(file);
  return [...html.matchAll(/<script\s+src="([^"]+)"/g)].map((m) => {
    const href = m[1].replace(/\?.*$/, "");
    const full = path.join(__dirname, "..", href.replace(/^\//, ""));
    assert.ok(fs.existsSync(full), `${file} 이 싣는 ${href} 가 없다`);
    return fs.readFileSync(full, "utf8");
  });
}

/** 화면 대신 **눌린 흔적만** 받아 두는 문서 — 무엇이 보이는지만 알면 된다. */
function fakeDocument() {
  const nodes = new Map();
  const make = () => ({
    style: {},
    textContent: "",
    innerHTML: "",
    value: "",
    disabled: false,
    listeners: {},
    classList: { add() {}, remove() {} },
    focus() {},
    addEventListener(type, fn) {
      this.listeners[type] = fn;
    },
  });
  return {
    nodes,
    getElementById(id) {
      if (!nodes.has(id)) nodes.set(id, make());
      return nodes.get(id);
    },
    querySelectorAll() {
      return Array.from({ length: 6 }, make);
    },
    addEventListener() {},
  };
}

/** `show()` 가 하나만 남기고 `none` 으로 덮으므로, 안 덮인 것이 뜬 화면이다. */
function shownView(document) {
  return VIEWS.filter((id) => {
    const node = document.nodes.get(id);
    return node && node.style.display && node.style.display !== "none";
  });
}

/** 인라인 스크립트를 브라우저인 척하는 자리에 올려 돌린다. */
async function run(file, { search = "", hash = "", answer = () => ({ ok: false, status: 404 }) } = {}) {
  const document = fakeDocument();
  const went = [];
  const sent = [];
  const location = {
    search,
    hash,
    pathname: "/patient_wireframe/html/" + file,
    get href() {
      return this.pathname + search + hash;
    },
    set href(url) {
      went.push(url);
    },
    replace(url) {
      went.push(url);
    },
  };
  const context = vm.createContext({
    URLSearchParams, Promise, JSON, Date, Array, String, Number, RegExp,
    parseInt, encodeURIComponent, decodeURIComponent, isNaN, Math,
    setInterval: () => 0,
    clearInterval: () => {},
    setTimeout: () => 0,
    alert: () => {},
    sessionStorage: { getItem: () => null, setItem() {} },
    document,
    window: { location, clipboardData: undefined },
    location,
    fetch(url, options) {
      sent.push({
        url,
        method: (options && options.method) || "GET",
        body: options && options.body ? JSON.parse(options.body) : null,
      });
      return Promise.resolve(answer(url, options));
    },
  });

  for (const source of pageScripts(file)) vm.runInContext(source, context);
  vm.runInContext(inlineScript(file), context);
  /* `init()` 안의 await 들이 다 풀리도록 큰 틱 하나를 준다 —
     가짜 fetch 가 이미 풀린 약속을 주므로 마이크로태스크가 여기서 다 빠진다. */
  await new Promise((resolve) => setImmediate(resolve));
  await new Promise((resolve) => setImmediate(resolve));

  return { document, went, sent, node: (id) => document.nodes.get(id) };
}

/** 실서버가 주는 대답 — 세션은 없고 진료 맥락은 있다. */
function liveServer(url) {
  if (url.includes("/patient-auth/session")) return { ok: false, status: 401 };
  if (url.includes("/patient-auth/context")) {
    return {
      ok: true,
      json: () =>
        Promise.resolve({
          hospital_name: "여성의원 KEY292",
          visited_at: "2026-09-08",
          masked_phone: "010-****-5678",
        }),
    };
  }
  if (url.includes("/patient-auth/otp/issue")) {
    return { ok: true, json: () => Promise.resolve({ expires_at: "2026-09-08T12:03:00+09:00", retry_after_seconds: 60 }) };
  }
  return { ok: false, status: 404, json: () => Promise.resolve({}) };
}

test("① 실서버에서 조각 토큰을 열면 오류가 아니라 인증 화면이 뜬다", async () => {
  /* **인수조건 ①.** `?mock=0` 이니 예전 코드는 `?token=` 만 보고 빈손으로
     `view-error` 에 떨어졌다 — 지금 디벨롭에서 나는 그 증상이다. */
  const ran = await run("otp.html", { search: "?mock=0", hash: "#t=" + TOKEN, answer: liveServer });

  assert.deepStrictEqual(shownView(ran.document), ["view-normal", "view-normal-btn"],
    `조각 토큰을 읽고도 인증 화면이 안 떴다 — 뜬 것: ${shownView(ran.document).join(", ") || "없음"}`);
  assert.equal(ran.node("ctx-phone").textContent, "010-****-5678", "진료 맥락을 못 채웠다");
});

test("② 그 토큰이 실제로 서버까지 간다 — 빈 값으로 화면만 넘기지 않는다", async () => {
  const ran = await run("otp.html", { search: "?mock=0", hash: "#t=" + TOKEN, answer: liveServer });

  const context = ran.sent.find((call) => call.url.includes("/patient-auth/context"));
  assert.ok(context, "진료 맥락을 아예 안 물었다");
  assert.equal(context.body.link_token, TOKEN, "서버로 간 토큰이 주소의 그것과 다르다");
});

test("③ 토큰이 없으면 조용히 넘어가지 않고 오류 화면으로 멈춘다", async () => {
  const ran = await run("otp.html", { search: "?mock=0", hash: "", answer: liveServer });

  assert.deepStrictEqual(shownView(ran.document), ["view-error"], "토큰 없이 인증 화면을 열었다");
  assert.deepStrictEqual(ran.sent, [], "토큰도 없이 서버를 불렀다");
});

test("④ 인증번호를 받으면 토큰을 조각으로 넘긴다 — 주소창에 안 남는다", async () => {
  /* **인수조건 ③.** 이 갈래는 실서버에서 열린 적이 없어(①이 먼저 막았다)
     `?token=` 인 채로 남아 있었다. 고침이 길을 여는 순간 드러나는 자리다. */
  const ran = await run("otp.html", { search: "?mock=0", hash: "#t=" + TOKEN, answer: liveServer });

  await ran.node("btn-issue").listeners.click();
  await new Promise((resolve) => setImmediate(resolve));

  assert.equal(ran.went.length, 1, `인증번호를 받고도 안 넘어갔다 — ${JSON.stringify(ran.went)}`);
  const url = ran.went[0];
  assert.ok(url.includes("#t=" + TOKEN), `토큰을 조각으로 안 실었다 — ${url}`);
  assert.doesNotMatch(url.split("#")[0], /token=/, `토큰이 주소창(query)에 남았다 — ${url}`);
  assert.match(url, /expires_at=|retry_after=/, "비밀이 아닌 값까지 조각으로 숨겼다");
});

test("⑤ 이어받는 화면도 목업과 무관하게 조각을 먼저 읽는다", async () => {
  /* `otp-verify.html` 에 똑같은 결함이 있었다. 여기가 안 고쳐지면 앞 화면이
     토큰을 주소창에 실어 보낼 수밖에 없다 — ④가 성립하지 않는다. */
  const ran = await run("otp-verify.html", {
    search: "?expires_at=2026-09-08T12:03:00%2B09:00&retry_after=60",
    hash: "#t=" + TOKEN,
    answer: liveServer,
  });

  await ran.node("resend-btn").listeners.click();
  await new Promise((resolve) => setImmediate(resolve));

  const issue = ran.sent.find((call) => call.url.includes("/patient-auth/otp/issue"));
  assert.ok(issue, "조각에서 토큰을 못 읽어 다시 받기가 서버까지 못 갔다");
  assert.equal(issue.body.link_token, TOKEN, "다시 받기가 엉뚱한 토큰을 보냈다");
});

test("⑥ 되돌아가는 주소에도 토큰을 query 로 붙이지 않는다", async () => {
  const ran = await run("otp-verify.html", {
    search: "?expires_at=2026-09-08T12:03:00%2B09:00&retry_after=60",
    hash: "#t=" + TOKEN,
    answer: liveServer,
  });

  ran.node("back-btn").listeners.click();

  assert.equal(ran.went.length, 1, `뒤로 가기가 안 움직였다 — ${JSON.stringify(ran.went)}`);
  assert.ok(ran.went[0].includes("#t=" + TOKEN), `돌아갈 토큰을 잃었다 — ${ran.went[0]}`);
  assert.doesNotMatch(ran.went[0].split("#")[0], /token=/, `뒤로 가기가 토큰을 주소창에 남겼다 — ${ran.went[0]}`);
});

test("⑧ 둘 다 있으면 새 조각이 이긴다 — 옛 주소가 산 토큰을 덮지 않는다", async () => {
  /* `?token=` 은 **뒤호환으로만** 받는다. 순서가 뒤집히면 주소창에 남아 있던
     옛 토큰이 방금 받은 링크를 이기고, 환자는 이미 폐기된 토큰으로 인증을
     시도하다 영문 모를 오류를 본다. 되는 것이 아니라 **어느 쪽이 이기는지**가
     규칙이라 따로 잰다. */
  const ran = await run("otp.html", {
    search: "?mock=0&token=stale-key292-token-from-an-old-address",
    hash: "#t=" + TOKEN,
    answer: liveServer,
  });

  const context = ran.sent.find((call) => call.url.includes("/patient-auth/context"));
  assert.ok(context, "진료 맥락을 아예 안 물었다");
  assert.equal(context.body.link_token, TOKEN, "주소창에 남은 옛 토큰이 새 조각을 덮었다");
});

test("⑦ 저장소에 토큰을 query 로 만드는 자리가 남아 있지 않다", () => {
  /* 위 여섯은 **지나간 갈래만** 잰다. 안 지나간 자리에 같은 모양이 새로 생기는
     것은 못 막으므로, 만드는 쪽을 전수로 한 번 더 훑는다. 받는 쪽(`?token=` 을
     읽어 주는 뒤호환)은 세지 않는다 — 만드는 자리만 본다. */
  const made = [];
  for (const file of fs.readdirSync(HTML_DIR).filter((name) => name.endsWith(".html"))) {
    inlineScript(file)
      .split("\n")
      .forEach((line, index) => {
        if (/['"][^'"]*\?token=/.test(line) || /set\(\s*['"]token['"]/.test(line)) {
          made.push(`${file}:${index + 1} ${line.trim()}`);
        }
      });
  }
  assert.deepStrictEqual(made, [], `토큰을 query 로 만드는 자리가 남았다:\n${made.join("\n")}`);
});

test("⑨ 여정 어느 요청 주소에도 토큰 원문이 없다 — 유가은 님 `#255` 리뷰", () => {
  /* 🚩 **이 PR 이 그 유출을 살아 있게 만든다.**
   *
   * `checkSession` 이 `GET …/session?link_token=<원문>` 을 보내고 있었다.
   * 고치기 전에는 실서버가 이 자리에 **도달하지 못해서**(①이 먼저 막았다)
   * 안 드러났는데, 길을 여는 순간 정상 진입마다 그 요청이 나가고 **nginx
   * access log 에 원문이 남는다** — 실제 스택에서 확인했다.
   *
   *     "GET /api/v1/patient-auth/session?link_token=<원문> HTTP/1.1" 401
   *
   * `app/core/masking.py` 가 `token` 을 가려도 그것은 uvicorn 쪽이라 nginx
   * 로그를 못 막는다. 그래서 후속으로 미루지 않고 여기서 걷는다.
   *
   * **한 자리만 재지 않는다** — 화면이 부르는 자리가 늘어나도 잡히도록
   * 여정에서 나간 **모든** 요청과 이동 주소를 훑는다. */
  const seen = [];
  const collect = (ran) => {
    ran.sent.forEach((call) => seen.push({ what: "요청", url: call.url }));
    ran.went.forEach((url) => seen.push({ what: "이동", url: url }));
  };

  return (async () => {
    const first = await run("otp.html", { search: "?mock=0", hash: "#t=" + TOKEN, answer: liveServer });
    await first.node("btn-issue").listeners.click();
    await new Promise((resolve) => setImmediate(resolve));
    collect(first);

    const next = await run("otp-verify.html", {
      search: "?expires_at=2026-09-08T12:03:00%2B09:00&retry_after=60",
      hash: "#t=" + TOKEN,
      answer: liveServer,
    });
    await next.node("resend-btn").listeners.click();
    await new Promise((resolve) => setImmediate(resolve));
    collect(next);

    assert.ok(seen.length >= 4, `여정을 못 지났다 — ${seen.length}건`);

    for (const one of seen) {
      /* 조각(`#t=`)은 **서버로 안 간다** — 브라우저가 안 싣고 access log 에도
         안 남는다. 그것이 이 화면이 조각을 쓰는 까닭이라 여기서는 빼고 본다. */
      const addressed = String(one.url).split("#")[0];
      assert.ok(
        !addressed.includes(TOKEN),
        `${one.what} 주소에 토큰 원문이 실렸다 — ${addressed}`,
      );
    }

    /* 반대쪽도 잰다 — 안 싣기만 하고 안 보내면 화면이 아예 안 도는 것이다. */
    const bodies = seen.filter((one) => one.what === "요청");
    assert.ok(bodies.length >= 3, "서버를 부르는 자리가 사라졌다");
  })();
});

test("⑩ 세션 확인은 본문으로 보낸다 — 주소에 실을 자리를 아예 안 만든다", () => {
  return (async () => {
    const ran = await run("otp.html", { search: "?mock=0", hash: "#t=" + TOKEN, answer: liveServer });
    const session = ran.sent.find((call) => call.url.includes("/patient-auth/session"));

    assert.ok(session, "세션 확인을 아예 안 물었다");
    assert.equal(session.method, "POST", `주소에 실리는 방식으로 되돌아갔다 — ${session.method} ${session.url}`);
    assert.equal(session.url, "/api/v1/patient-auth/session", "주소에 무언가 붙었다");
    assert.equal(session.body && session.body.link_token, TOKEN, "본문으로 토큰을 안 보낸다");
  })();
});

/* ── 이희진 님 `#255` 리뷰 ①②③ ────────────────────────────────────────── */

test("⑪ 목업도 같은 규칙을 탄다 — 갈래를 다시 두지 않는다", () => {
  return (async () => {
    /* `isMock` 갈래를 없애면서 목업도 `?token=` 폴백을 받게 넓어졌다.
       **의도한 것이다** — 갈래를 다시 두면 「목업에서는 되는데 실서버에서는
       안 되는」 거리가 또 생기고, 그 거리가 바로 이 티켓의 버그였다.
       넓어졌다는 사실 자체를 여기 못 박아 둔다. */
    const legacy = await run("otp.html", { search: "?mock=1&token=" + TOKEN, hash: "" });
    assert.ok(
      !shownView(legacy.document).includes("view-error"),
      "목업에서 옛 주소를 열면 오류 화면으로 떨어진다 — 실서버와 규칙이 갈렸다",
    );

    /* 조각이 있으면 목업에서도 조각이 이긴다. */
    const both = await run("otp.html", { search: "?mock=1&token=old", hash: "#t=" + TOKEN });
    const next = both.went.find((url) => url.includes("otp-verify"));
    if (next) assert.ok(next.includes(TOKEN), `목업에서 옛 주소가 조각을 덮었다 — ${next}`);
  })();
});

test("⑫ 토큰 읽는 규칙은 한 벌이다 — 조각이 먼저, 옛 이름은 순서대로", () => {
  const rule = fs.readFileSync(path.join(__dirname, "..", "js", "link-token.js"), "utf8");
  const linkTokenFrom = new Function("URLSearchParams", rule + "\nreturn linkTokenFrom;")(URLSearchParams);

  assert.equal(linkTokenFrom({ search: "?token=old", hash: "#t=new" }, ["token"]), "new", "조각이 먼저가 아니다");
  assert.equal(linkTokenFrom({ search: "?token=old", hash: "" }, ["token"]), "old", "옛 주소를 안 받아 준다");
  assert.equal(linkTokenFrom({ search: "", hash: "#t=new" }, []), "new", "옛 이름이 없어도 조각은 읽어야 한다");
  assert.equal(linkTokenFrom({ search: "?t=a&visit=b", hash: "" }, ["t", "visit"]), "a", "옛 이름 차례가 틀렸다");
  assert.equal(linkTokenFrom({ search: "?visit=b", hash: "" }, ["t", "visit"]), "b", "둘째 옛 이름을 못 읽는다");
  assert.equal(linkTokenFrom({ search: "?token=x", hash: "" }, ["t"]), "", "그 화면이 안 쓰던 옛 이름까지 받아 준다");
  assert.equal(linkTokenFrom({ search: "", hash: "" }, ["token"]), "", "없는데 무언가를 준다");
  assert.equal(linkTokenFrom(undefined, ["token"]), "", "주소가 없으면 터진다");
});

test("⑬ 주석이 실제 발신자를 그대로 든다 — 틀린 주석은 엉뚱한 파일을 보게 한다", () => {
  /* 이 주석은 재발 방지용이라 근거가 틀리면 그 자체로 해롭다. 그래서 잰다 —
     `otp.html` 주소를 만드는 파일이 전부 주석에 적혀 있어야 한다. */
  const note = /\*\*토큰은 fragment 로 온다\*\*([\s\S]*?)\*\//.exec(pageHtml("otp.html"));
  assert.ok(note, "발신자를 적어 둔 주석을 못 찾았다");

  const root = path.join(__dirname, "..");
  const senders = [];
  const walk = (dir) => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        if (entry.name !== "tests" && entry.name !== "node_modules") walk(full);
      } else if (entry.name.endsWith(".js")) {
        const text = fs.readFileSync(full, "utf8");
        if (/["']\/patient_wireframe\/html\/otp\.html/.test(text)) {
          senders.push(path.relative(root, full).replace(/\\/g, "/"));
        }
      }
    }
  };
  walk(root);

  assert.ok(senders.length >= 3, `발신자를 못 찾았다 — ${JSON.stringify(senders)}`);
  for (const file of senders) {
    assert.ok(note[1].includes(file), `주석이 발신자 ${file} 를 안 든다`);
  }
});
