/* KEY-322 — **늦게 도착한 응답이 화면을 차지하지 못한다.**
 *
 * 「안내문」으로 거른 직후 「문자」로 다시 거르면 요청이 둘 뜬다. 응답이 오는
 * 순서는 요청한 순서가 아니라서, 안내문 것이 늦게 오면 거르개는 문자인데
 * 목록은 안내문이 된다. 다음 쪽 커서도 그 응답 것으로 덮인다.
 * 「더 보기」가 도는 중에 거르개를 바꾸면 옛 조건의 줄이 새 목록에 **붙는다**
 * (한금준 님 `#287` 리뷰).
 *
 * ── 왜 원문 대조가 아니라 돌려 보는가 ────────────────────────────────
 * 이 세 가지는 **타이밍**이다. 「가드가 코드에 있는가」를 재면 가드가 엉뚱한
 * 값을 견줘도 통과한다. 옛 응답을 실제로 늦게 흘려 보내야 드러난다
 * (`key281-chat-abort-on-real-path.test.js` 가 같은 까닭으로 같은 모양이다).
 *
 * 그래서 공용 껍데기(`browser-shim`)를 안 쓴다. 그쪽 `getElementById` 는 늘
 * `null` 이라 `admin.js` 의 IIFE 가 첫 줄에서 되돌아 나오고, `innerHTML` 에
 * 값을 넣으면 던진다 — 이 파일이 재려는 것이 바로 그 `innerHTML` 이다.
 *
 * ── 여기서 흉내내지 않는 것 ─────────────────────────────────────────
 * `esc` 와 `errorMessage` 는 **흉내다.** 이 검사가 가리는 것은 「어느 응답이
 * 화면을 차지하는가」지 글자를 어떻게 다듬는가가 아니다. 문구와 이스케이프는
 * `key322-admin-audit.test.js` 의 「빈 결과와 못 불러온 것은 다른 말이다」와
 * 「요약에 든 HTML 이 그대로 그려지지 않는다」가 이미 잡고 있다.
 */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const JS = path.join(__dirname, "..", "js");

function read(name) {
  return fs.readFileSync(path.join(JS, name), "utf8");
}

/** 다음 마이크로태스크까지 기다린다 — `.then` 사슬이 다 풀리게. */
const tick = () => new Promise(setImmediate);

/* ── 아주 작은 문서 ───────────────────────────────────────────────── */

/* `innerHTML` 을 **문자열로** 들고 있는 칸. `admin.js` 가 화면을 그리는 길이
   전부 `innerHTML` 이라 이만큼이면 무엇이 그려졌는지 그대로 읽을 수 있다. */
function makeDocument() {
  const ids = new Map();

  /* `innerHTML` 을 갈아끼우면 **그 안에 있던 것은 사라진다.** 그것을 안
     흉내내면, 새로 그린 「더 보기」를 눌렀을 때 지워졌어야 할 옛 단추의
     리스너까지 같이 불려 검사가 거짓 요청을 세게 된다. */
  function release(html) {
    const found = String(html).match(/id="([^"]+)"/g) || [];
    for (const chunk of found) ids.delete(chunk.slice(4, -1));
  }

  class Fake {
    constructor(id) {
      this.id = id;
      this.html = "";
      this.value = "";
      this.disabled = false;
      this.style = {};
      this.listeners = {};
    }
    get innerHTML() {
      return this.html;
    }
    set innerHTML(next) {
      release(this.html);
      this.html = String(next);
    }
    get outerHTML() {
      return this.html;
    }
    set outerHTML(next) {
      release(this.html);
      this.html = String(next);
    }
    addEventListener(name, fn) {
      (this.listeners[name] = this.listeners[name] || []).push(fn);
    }
    fire(name, event) {
      for (const fn of (this.listeners[name] || []).slice()) fn(event || {});
    }
    /* `admin.js` 가 찾는 것은 이어 붙일 `tbody` 하나뿐이다. 표가 없으면
       `null` — 그 갈래(앞 쪽이 비어 통째로 다시 그린다)도 살아 있어야 한다. */
    querySelector(selector) {
      if (selector !== "tbody" || this.html.indexOf("<tbody") === -1) return null;
      const owner = this;
      return {
        insertAdjacentHTML(where, chunk) {
          assert.equal(where, "beforeend");
          const at = owner.html.lastIndexOf("</tbody>");
          owner.html = owner.html.slice(0, at) + chunk + owner.html.slice(at);
        },
      };
    }
    setAttribute() {}
    getAttribute() {
      return null;
    }
    focus() {}
  }

  return {
    ids,
    document: {
      getElementById(id) {
        if (!ids.has(id)) ids.set(id, new Fake(id));
        return ids.get(id);
      },
      createElement: () => new Fake(),
      addEventListener() {},
      body: new Fake("body"),
    },
  };
}

/* ── 전체 로그 화면을 세우고, 응답을 손에 쥔다 ───────────────────────── */

function auditScreen() {
  const { ids, document } = makeDocument();
  const asks = [];

  const context = vm.createContext({
    console,
    Date,
    JSON,
    Math,
    Number,
    Object,
    Promise,
    String,
    URLSearchParams,
    isNaN,
    setTimeout,
    document,
    window: { addEventListener() {}, removeEventListener() {} },
    location: { search: "", replace() {} },
    esc: (text) => String(text == null ? "" : text),
    errorMessage: () => "못 불러왔습니다",
    request: () => Promise.reject(new Error("검사에서 실제 요청이 나갔다")),
    session: { clear() {} },
    wireFold() {},
    /* **끝내 답하지 않는다.** 신원이 채워지면 상단 탭을 잠그는 뒷부분이
       도는데, 이 검사가 재는 것과 무관하고 `landingFor` 같은 것을 더 흉내내야
       한다. 화면 골격은 그 전에 이미 선다. */
    requireSession: () => new Promise(() => {}),
    listStaffs: () => Promise.resolve({ staffs: [] }),
  });

  vm.runInContext(read("frames.js"), context, { filename: "frames.js" });
  vm.runInContext(read("admin-audit.js"), context, { filename: "admin-audit.js" });
  vm.runInContext(read("admin-staff.js"), context, { filename: "admin-staff.js" });

  /* 진짜 `listAuditLogs` 를 실은 **뒤에** 손에 쥔 것으로 바꾼다 — 그래야 줄을
     그리는 `auditRowHtml` 들은 실물 그대로 남는다. */
  context.listAuditLogs = (query) => {
    let settle;
    let fail;
    const answer = new Promise((resolve, reject) => {
      settle = resolve;
      fail = reject;
    });
    asks.push({
      query,
      reply: (entries, cursor) =>
        settle({ entries, has_more: cursor != null, next_cursor: cursor == null ? null : cursor }),
      refuse: (error) => fail(error || new Error("끊겼습니다")),
    });
    return answer;
  };

  vm.runInContext(read("admin.js"), context, { filename: "admin.js" });

  /* 좌측 목록에서 「전체 로그」를 누른다 — 화면이 실제로 그리로 가는 길이다. */
  ids.get("admin-menu").fire("click", {
    target: { closest: () => ({ getAttribute: () => "log" }) },
  });

  const pick = (id) => document.getElementById(id);

  /* **단추가 실제로 걸려 있는지부터 본다.** 이 문서는 묻는 id 를 만들어 주므로,
     화면이 그것을 안 그렸어도 `fire` 는 조용히 아무 일도 안 하고 끝난다 —
     검사가 초록불로 지나간다. */
  const press = (id, name, event) => {
    const el = pick(id);
    assert.ok((el.listeners[name] || []).length, `화면이 ${id} 를 안 걸었다`);
    el.fire(name, event);
  };

  const submit = (source) => {
    pick("audit-source").value = source;
    press("audit-filter", "submit", { preventDefault() {} });
  };
  const more = () => press("audit-more-go", "click", {});
  const shown = () => pick("audit-list").html;
  const under = () => pick("audit-more").html;

  return { ids, asks, submit, more, shown, under };
}

function line(source, summary) {
  return {
    event_id: source + ":1",
    occurred_at: "2026-09-10T10:00:00",
    source: source,
    actor_staff_id: null,
    actor_name: null,
    visit_id: null,
    summary: summary,
  };
}

/* ── ① 늦게 온 성공 ───────────────────────────────────────────────── */

test("거르개를 바꾼 뒤 늦게 온 옛 응답이 목록을 차지하지 않는다", async () => {
  const s = auditScreen();
  await tick();

  const first = s.asks[0]; /* 화면에 들어오며 낸 것 */
  s.submit("guide");
  const guide = s.asks[s.asks.length - 1];
  s.submit("message");
  const message = s.asks[s.asks.length - 1];

  assert.equal(message.query.source, "message", "두 번째 검색이 안 나갔다");

  /* 늦게 온다 — 문자가 먼저 앉고, 안내문이 뒤따른다. */
  message.reply([line("message", "문자를 보냈다")], null);
  await tick();
  guide.reply([line("guide", "안내문을 고쳤다")], null);
  first.reply([line("otp", "첫 화면 것")], null);
  await tick();

  assert.match(s.shown(), /문자를 보냈다/, "지금 거르개의 줄이 사라졌다");
  assert.doesNotMatch(s.shown(), /안내문을 고쳤다/, `늦은 옛 응답이 목록을 덮었다 —\n${s.shown()}`);
  assert.doesNotMatch(s.shown(), /첫 화면 것/, `더 늦은 첫 응답이 목록을 덮었다 —\n${s.shown()}`);
});

/* ── ② 늦게 온 커서 ───────────────────────────────────────────────── */

test("늦게 온 옛 응답이 다음 쪽 커서를 덮지 않는다", async () => {
  const s = auditScreen();
  await tick();

  s.submit("guide");
  const guide = s.asks[s.asks.length - 1];
  s.submit("message");
  const message = s.asks[s.asks.length - 1];

  message.reply([line("message", "문자를 보냈다")], "cursor-message");
  await tick();
  guide.reply([line("guide", "안내문을 고쳤다")], "cursor-guide");
  await tick();

  s.more();
  const next = s.asks[s.asks.length - 1];
  assert.equal(next.query.cursor, "cursor-message", "「더 보기」가 지난 검색의 커서를 이어 보냈다");
  assert.equal(next.query.source, "message", "「더 보기」가 지난 검색의 조건을 이어 보냈다");
});

/* ── ③ 늦게 온 실패 ───────────────────────────────────────────────── */

test("늦게 온 옛 실패가 지금 목록 위에 오류를 적지 않는다", async () => {
  const s = auditScreen();
  await tick();

  s.submit("guide");
  const guide = s.asks[s.asks.length - 1];
  s.submit("message");
  const message = s.asks[s.asks.length - 1];

  message.reply([line("message", "문자를 보냈다")], "cursor-message");
  await tick();
  guide.refuse(new Error("끊겼습니다"));
  await tick();

  assert.match(s.shown(), /문자를 보냈다/, `늦은 옛 실패가 멀쩡한 목록을 지웠다 —\n${s.shown()}`);
  assert.doesNotMatch(s.shown(), /못 불러왔습니다/, "늦은 옛 실패가 목록 자리에 오류를 적었다");
  assert.match(s.under(), /더 보기/, `늦은 옛 실패가 「더 보기」를 「다시 시도」로 바꿨다 —\n${s.under()}`);
  assert.doesNotMatch(s.under(), /다시 시도/, "늦은 옛 실패가 지금 검색의 단추를 갈아치웠다");
});

/* ── ④ 「더 보기」가 도는 중에 거르개를 바꾼다 ────────────────────────── */

test("「더 보기」가 도는 중에 거르개를 바꾸면 옛 줄이 새 목록에 안 붙는다", async () => {
  const s = auditScreen();
  await tick();

  s.submit("guide");
  s.asks[s.asks.length - 1].reply([line("guide", "안내문 첫 줄")], "cursor-guide");
  await tick();
  assert.match(s.shown(), /안내문 첫 줄/, "첫 쪽이 안 그려졌다");

  s.more();
  const append = s.asks[s.asks.length - 1];
  assert.equal(append.query.cursor, "cursor-guide", "이어 보기가 커서를 안 실었다");

  /* 이어 보기가 도는 중에 거르개를 바꾼다. */
  s.submit("message");
  const message = s.asks[s.asks.length - 1];
  message.reply([line("message", "문자 한 줄")], null);
  await tick();

  /* 이제야 옛 이어 보기가 돌아온다 — 붙을 곳이 없다. */
  append.reply([line("guide", "안내문 둘째 줄")], null);
  await tick();

  assert.match(s.shown(), /문자 한 줄/, "지금 거르개의 줄이 사라졌다");
  assert.doesNotMatch(s.shown(), /안내문 둘째 줄/, `옛 이어 보기가 새 목록에 붙었다 —\n${s.shown()}`);
});

/* ── ⑤ 늦은 것을 버리느라 제 것까지 버리지 않는다 ────────────────────── */

/* **여기 안 걸리는 돌연변이가 하나 있다** — 검색이 아니라 *요청*마다 번호를
   올려도 다섯이 다 통과한다. 오늘은 같은 검색의 요청이 둘 뜨지 못하기
   때문이다: `loadAudit` 이 떠나기 전에 「더 보기」 자리를 비우고(`more.innerHTML
   = ""`), 누른 단추는 그 자리에서 잠긴다. 그래서 이어 보기는 늘 혼자다.

   그런데도 **검색 단위로 매긴다.** 그 둘을 걷어 이어 보기가 겹칠 수 있게 되면,
   요청 단위 번호는 먼저 떠난 쪽의 한 쪽을 소리 없이 버린다 — 감사 목록에서
   줄이 사라지는 것이 제일 나쁘다. 지금 안 걸리는 것을 알고 고른 모양이다. */

test("한 검색만 있을 때는 이어 보기가 그대로 붙는다", async () => {
  const s = auditScreen();
  await tick();

  s.submit("guide");
  s.asks[s.asks.length - 1].reply([line("guide", "첫 줄")], "cursor-1");
  await tick();

  s.more();
  s.asks[s.asks.length - 1].reply([line("guide", "둘째 줄")], null);
  await tick();

  assert.match(s.shown(), /첫 줄/, "앞 쪽이 사라졌다");
  assert.match(s.shown(), /둘째 줄/, "이어 붙이기가 통째로 막혔다");
  assert.equal(s.under(), "", "더 없는데 「더 보기」가 남았다");
});
