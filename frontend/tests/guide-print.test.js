const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const read = rel => fs.readFileSync(path.join(__dirname, '..', rel), 'utf8');
const source = read('patient_wireframe/js/guide.js');

function selectionHarness() {
  const state = { data: { life: { axes: { 수면: {}, 운동: {}, 통증: {} } } }, lifeAxis: '운동', lifeExpanded: false };
  let result;
  const context = {
    state, PDF_OPTIONS: [{ key: 'guide', label: '복약지도' }, { key: 'care', label: '주의사항' }, { key: 'life', label: '생활관리' }],
    renderGuide: () => 'approved-guide', renderCare: () => 'approved-care',
    renderLife: () => ({ axis: state.lifeAxis, children: [], appendChild(n) { this.children.push(n); }, querySelector() { return state.lifeAxis; } }),
    GuidePdf: { preview(d, sections) { result = sections; } }, sayGuide() {},
  };
  vm.createContext(context);
  vm.runInContext(source.slice(source.indexOf('  function printSections('), source.indexOf("  if (typeof Sheet === 'function'")), context);
  return { state, run: chosen => { result = undefined; context.printSections(chosen); return result; } };
}

test('7개 선택 조합은 선택한 승인 항목만 출력한다', () => {
  const h = selectionHarness();
  const keys = ['guide', 'care', 'life'];
  for (let mask = 1; mask < 8; mask++) {
    const chosen = keys.filter((_, i) => mask & (1 << i));
    assert.equal(h.run(chosen).length, chosen.length);
  }
  assert.equal(h.run(['guide'])[0].content, 'approved-guide');
  assert.equal(h.run(['care'])[0].content, 'approved-care');
});

test('생활관리 전체 하위 축을 포함하며 화면 상태를 유지한다', () => {
  const h = selectionHarness();
  const content = h.run(['life'])[0].content;
  assert.equal(content.axis, '수면');
  assert.deepEqual(content.children, ['운동', '통증']);
  assert.equal(h.state.lifeAxis, '운동');
  assert.equal(h.state.lifeExpanded, false);
});

test('선택 0건 및 조회 데이터 없음은 인쇄하지 않는다', () => {
  const h = selectionHarness();
  assert.equal(h.run([]), undefined);
  h.state.data = null;
  assert.equal(h.run(['guide']), undefined);
});

test('실환경도 선택창을 사용하고 조회 중에는 버튼을 비활성화한다', () => {
  const pdf = source.slice(source.indexOf('  /* ── PDF 시트'));
  assert.doesNotMatch(pdf, /if \(GUIDE_MOCK\)|alert\('PDF/);
  assert.match(pdf, /state\.data = null;[\s\S]*pdf-btn'\)\.disabled = true/);
  assert.match(pdf, /state\.data = d;[\s\S]*pdf-btn'\)\.disabled = false/);
  assert.doesNotMatch(pdf, /key:'stat'/);
});

test('PDF 모듈은 앱 URL·토큰을 복사하거나 인쇄창을 호출하지 않는다', () => {
  const print = read('patient_wireframe/component/guide-pdf.js');
  assert.doesNotMatch(print, /location\.|TOKEN|innerHTML|fetch\(|localStorage|sessionStorage/);
  assert.match(print, /revokeObjectURL/);
  assert.doesNotMatch(print, /\.print\(/);
  assert.match(print, /drawImage\(image/);
  assert.match(print, /img.src = imageData/);
  assert.match(print, /pagehide/);
});

test('선택 버튼은 키보드로 조작 가능하며 항목 수를 페이지 수로 오인하지 않는다', () => {
  const sheet = read('patient_wireframe/component/sheet.js');
  assert.match(sheet, /createElement\('button'\)/);
  assert.match(sheet, /aria-pressed/);
  assert.match(sheet, /개 항목/);
  assert.match(sheet, /if \(!chosen.length\) return/);
});

test('PDF 버튼은 초기·로딩·만료/오류에서 숨기고 정상 조회 후에만 표시한다', () => {
  const html = read('guide.html');
  assert.match(html, /id="pdf-btn" hidden disabled style="display:none"/);
  const loading = source.slice(source.indexOf('  function loadGuide()'));
  assert.match(loading.slice(0, loading.indexOf('return fetchGuide')), /pdf-btn'\)\.hidden = true/);
  assert.match(loading.slice(loading.indexOf('.then'), loading.indexOf('.catch')), /state\.data = d;[\s\S]*pdf-btn'\)\.hidden = false/);
  const error = source.slice(source.indexOf('  function renderLoadError'), source.indexOf('  function loadGuide'));
  assert.match(error, /state\.data = null/);
  assert.match(error, /pdf-btn'\)\.hidden = true/);
});

test('선택 시트 제목과 실행 버튼에는 인쇄 문구를 쓰지 않는다', () => {
  const sheet = source.slice(source.indexOf('var pdfSheet = Sheet('), source.indexOf('document.body.appendChild(pdfSheet.backdrop)'));
  assert.match(sheet, /title: 'PDF 저장'/);
  assert.match(sheet, /saveLabel: 'PDF 저장'/);
  assert.doesNotMatch(sheet, /인쇄/);
});

function pdfHarness() {
  const context = { window: { addEventListener() {} } };
  vm.createContext(context);
  vm.runInContext(read('patient_wireframe/component/guide-pdf.js'), context);
  return context.GuidePdf;
}

test('긴 한글·줄바꿈·공백·긴 영문은 내용 손실 없이 줄바꿈한다', () => {
  const pdf = pdfHarness();
  for (const text of ['긴한글문장'.repeat(100), 'abc'.repeat(200), '공백 있는 문장 '.repeat(100)]) {
    const lines = pdf.wrapLines(text, s => Array.from(s).length * 16, 100);
    assert.equal(lines.join(''), text);
    assert.ok(lines.every(line => Array.from(line).length * 16 <= 100));
  }
  assert.equal(pdf.wrapLines('가\n\n나', s => s.length, 100).join('\n'), '가\n\n나');
});

test('긴 본문은 여러 페이지에 나눠 담고 모든 줄이 A4 본문 영역 안에 있다', () => {
  const pdf = pdfHarness();
  const text = '복약안내 내용 확인 '.repeat(1500);
  const pages = pdf.layout([{ style: 'body', text }], s => Array.from(s).length * 16);
  assert.ok(pages.length > 1);
  assert.equal(pages.flat().map(line => line.text).join(''), text);
  assert.ok(pages.flat().every(line => line.x >= 60 && line.y <= 1050));
});

test('과도하게 긴 본문은 잘라 저장하지 않고 명시적으로 실패한다', () => {
  const pdf = pdfHarness();
  assert.throws(() => pdf.layout([{ style: 'body', text: '가'.repeat(100000) }], s => s.length * 16), /PDF_TOO_LONG/);
});

test('섹션 제목과 바로 뒤 소제목·본문은 페이지 경계에서 함께 넘긴다', () => {
  const pdf = pdfHarness();
  const pages = pdf.layout([
    { style: 'body', text: Array(31).fill('내용').join('\n') },
    { style: 'section', text: '생활관리' },
    { style: 'heading', text: '이번 챌린지' },
    { style: 'body', text: '생활관리 내용' }
  ], s => s.length * 16);
  const sectionPage = pages.findIndex(page => page.some(line => line.text === '생활관리'));
  const bodyPage = pages.findIndex(page => page.some(line => line.text === '생활관리 내용'));
  assert.equal(sectionPage, bodyPage);
});

function previewHarness(withLibrary = true) {
  let document;
  class Node {
    constructor(tag) { this.tag = tag; this.nodeType = 1; this.children = []; this.style = {}; this.attrs = {}; this.events = {}; this.textContent = ''; this.inert = false; this.isConnected = true; this.classList = { toggle: () => true }; }
    appendChild(node) { this.children.push(node); node.parent = this; return node; }
    setAttribute(key, value) { this.attrs[key] = value; }
    removeAttribute(key) { delete this.attrs[key]; }
    hasAttribute(key) { return key in this.attrs; }
    addEventListener(key, fn) { this.events[key] = fn; }
    remove() { this.parent.children = this.parent.children.filter(n => n !== this); this.isConnected = false; }
    focus() { document.activeElement = this; }
    matches() { return false; }
    getContext() { return { scale() {}, measureText: text => ({ width: text.length * 16 }), fillRect() {}, fillText() {} }; }
    toDataURL() { return 'data:image/jpeg;base64,synthetic'; }
  }
  const body = new Node('body');
  body.style.overflow = 'auto';
  const app = body.appendChild(new Node('app'));
  const existingInert = body.appendChild(new Node('old'));
  existingInert.inert = true;
  const pdfButton = app.appendChild(new Node('button'));
  document = { body, activeElement: pdfButton, fonts: { ready: Promise.resolve() }, createElement: tag => new Node(tag), getElementById: () => pdfButton };
  const revoked = [];
  const context = { document, window: { addEventListener() {}, getComputedStyle: () => ({ fontFamily: 'sans-serif' }) },
    URL: { createObjectURL: () => 'blob:synthetic', revokeObjectURL: url => revoked.push(url) }, Blob, setTimeout };
  if (withLibrary) context.PDFLib = { PDFDocument: { async create() { return { setTitle() {}, setCreator() {}, async embedJpg() { return {}; }, addPage() { return { drawImage() {} }; }, async save() { return new Uint8Array([1, 2]); } }; } } };
  vm.createContext(context);
  vm.runInContext(read('patient_wireframe/component/guide-pdf.js'), context);
  const content = new Node('p');
  content.textContent = '승인된 합성 안내';
  return { pdf: context.GuidePdf, body, app, existingInert, pdfButton, document, revoked, sections: [{ label: '복약지도', content }] };
}

test('PDF 생성 성공·크게 보기·닫기에서 URL/배경/스크롤/포커스를 정리한다', async () => {
  const h = previewHarness();
  assert.equal(await h.pdf.preview({ clinic: '합성 의원' }, h.sections), true);
  const dialog = h.body.children.at(-1);
  assert.equal(h.app.inert, true);
  assert.equal(h.body.style.overflow, 'hidden');
  const [heading, close, zoom, download] = dialog.children[0].children;
  assert.equal(download.href, 'blob:synthetic');
  zoom.events.click();
  assert.equal(zoom.textContent, '화면 맞춤');
  assert.equal(await h.pdf.preview({}, h.sections), false);
  close.events.click();
  assert.equal(h.app.inert, false);
  assert.equal(h.existingInert.inert, true);
  assert.equal(h.body.style.overflow, 'auto');
  assert.equal(h.document.activeElement, h.pdfButton);
  assert.deepEqual(h.revoked, ['blob:synthetic']);
});

test('생성 실패 후 닫고 재시도할 수 있으며 다운로드는 활성화하지 않는다', async () => {
  const h = previewHarness(false);
  assert.equal(await h.pdf.preview({}, h.sections), false);
  const dialog = h.body.children.at(-1);
  assert.equal(dialog.children[1].attrs.role, 'alert');
  assert.equal(dialog.children[0].children.at(-1).hasAttribute('href'), false);
  dialog.children[0].children[1].events.click();
  assert.equal(h.app.inert, false);
  assert.equal(await h.pdf.preview({}, h.sections), false);
  h.body.children.at(-1).children[0].children[1].events.click();
});

test('미리보기는 기존 환자 UI 토큰·44px 터치 영역·모바일 확대를 사용한다', () => {
  const css = read('patient_wireframe/css/chat.css');
  const preview = css.slice(css.indexOf('.pdf-preview {'));
  assert.match(preview, /var\(--p-dark\)/);
  assert.match(preview, /var\(--font\)/);
  assert.match(preview, /min-height: 44px/);
  assert.match(preview, /pdf-preview--zoom/);
  assert.match(read('patient_wireframe/component/sheet.js'), /renderOptions\(o.key\)/);
});
