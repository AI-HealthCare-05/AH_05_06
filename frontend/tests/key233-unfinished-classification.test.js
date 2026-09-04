const { test } = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const ROOT = path.join(__dirname, "..");
const REPO = path.join(ROOT, "..");

function loadFrames() {
  const context = {};
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(path.join(ROOT, "js", "frames.js"), "utf8"), context);
  return context;
}

function loadClassification() {
  return JSON.parse(
    fs.readFileSync(path.join(REPO, "docs", "qa", "KEY-233-unfinished-classification.json"), "utf8"),
  );
}

test("현재 미완성 프레임은 근거와 함께 정확히 한 번 분류된다", () => {
  const { FRAMES } = loadFrames();
  const audit = loadClassification();
  const buckets = [audit.delete_candidates, audit.wp_f_handoff, audit.follow_up];
  const classified = buckets.flat();
  const duplicate = classified.filter((id, index) => classified.indexOf(id) !== index);
  const incomplete = FRAMES.filter((frame) => frame.level !== 1).map((frame) => frame.id);

  assert.deepEqual(duplicate, [], "둘 이상의 분류에 들어간 프레임이 있다");
  assert.deepEqual(classified.slice().sort(), incomplete.slice().sort(), "미완성 프레임이 빠졌거나 완료 프레임이 섞였다");
  assert.equal(classified.length, audit.current_incomplete_count, "현재 미완성 개수 기준선이 다르다");

  for (const id of classified) {
    const frame = FRAMES.find((item) => item.id === id);
    assert.ok(frame && frame.blocker, `${id}에 분류 근거(blocker)가 없다`);
  }
});

test("WP-F 인계 목록은 안전 실패 화면 대상과 일치한다", () => {
  const { FRAMES, needsGuideScreen } = loadFrames();
  const audit = loadClassification();
  const expected = FRAMES.filter(needsGuideScreen).map((frame) => frame.id).sort();
  assert.deepEqual(audit.wp_f_handoff.slice().sort(), expected, "KEY-235 인계 대상이 화면 정본과 다르다");
});

test("원본 63건 근거가 없다는 사실을 개수로 덮어쓰지 않는다", () => {
  const audit = loadClassification();
  assert.equal(audit.legacy_claimed_count, 63);
  assert.equal(audit.legacy_source_available, false);
  assert.notEqual(audit.current_incomplete_count, audit.legacy_claimed_count);
});
