/* KEY-370: 브라우저에서 승인 안내를 페이지 이미지로 렌더링한다.
 * 미리보기와 PDF에 같은 이미지를 사용한다. 서버 요청/영구 저장 없음. */
var GuidePdf = (function () {
  var WIDTH = 794, HEIGHT = 1123, MARGIN = 60, BOTTOM = 1050;
  var active = null;
  var FONT = 'sans-serif';
  var STYLES = {
    title: { size: 28, line: 42, bold: true, color: '#A63C79', gap: 14 },
    section: { size: 23, line: 36, bold: true, color: '#A63C79', gap: 16 },
    heading: { size: 18, line: 29, bold: true, color: '#30272C', gap: 10 },
    body: { size: 16, line: 27, bold: false, color: '#30272C', gap: 10 },
    meta: { size: 14, line: 23, bold: false, color: '#6C5963', gap: 18 }
  };

  function wrapLines(value, measure, width) {
    var result = [];
    String(value || '').replace(/\r\n?/g, '\n').split('\n').forEach(function (paragraph) {
      var line = '';
      Array.from(paragraph).forEach(function (char) {
        if (line && measure(line + char) > width) {
          result.push(line);
          line = char;
        } else line += char;
      });
      result.push(line);
    });
    return result;
  }

  // 화면 렌더러의 평문만 수집. 인터랙션/접힘/탭 상태는 가져오지 않는다.
  function extractBlocks(root) {
    var blocks = [];
    function walk(node) {
      if (node.nodeType !== 1 && node.nodeType !== 11) return;
      if (node.nodeType === 1 && node.matches('button, .axis-tabs, .tab-title, .care-fade, .life-fade')) return;
      var style = node.nodeType === 1 && node.matches('.card__section-title, .drug-row__name, .danger-title') ? 'heading' : 'body';
      if (node.nodeType === 1 && node.matches('.challenge-row, .axis-chal-row')) {
        blocks.push({ style: 'body', text: Array.from(node.children).map(function (n) { return n.textContent; }).join(' · ') });
      } else if (!node.children.length) {
        var value = node.textContent.trim();
        if (value) blocks.push({ style: style, text: value });
      } else Array.from(node.children).forEach(walk);
    }
    walk(root);
    return blocks;
  }

  function layout(blocks, measure) {
    var pages = [[]], y = MARGIN;
    function nextPage() {
      if (pages.length >= 30) throw new Error('PDF_TOO_LONG'); // 누락/잘림 대신 명시적으로 실패
      pages.push([]);
      y = MARGIN;
    }
    blocks.forEach(function (block, index) {
      var style = STYLES[block.style] || STYLES.body;
      var lines = wrapLines(block.text, function (text) { return measure(text, style); }, WIDTH - 2 * MARGIN);
      // 소제목 뒤에 최소 두 줄을 둘 수 있도록 다음 페이지로 함께 넘긴다.
      var keep = 0;
      if (block.style === 'heading' || block.style === 'section') {
        keep = style.gap;
        for (var next = index + 1; next < blocks.length; next++) {
          var following = STYLES[blocks[next].style] || STYLES.body;
          if (blocks[next].style === 'heading') keep += following.line + following.gap;
          else { keep += following.line * 2; break; }
        }
      }
      if (y + style.line * Math.min(lines.length, 2) + keep > BOTTOM) nextPage();
      lines.forEach(function (line) {
        if (y + style.line > BOTTOM) nextPage();
        pages[pages.length - 1].push({ text: line, x: MARGIN, y: y + style.size, style: style });
        y += style.line;
      });
      y += style.gap;
    });
    return pages;
  }

  function close() {
    if (!active) return;
    var old = active;
    active = null;
    old.dialog.remove();
    old.background.forEach(function (item) { item.node.inert = item.inert; });
    document.body.style.overflow = old.overflow;
    if (old.url) URL.revokeObjectURL(old.url);
    if (old.focus && old.focus.isConnected) old.focus.focus();
  }

  async function preview(data, sections) {
    if (!data || !sections.length || active) return false;
    var dialog = document.createElement('div');
    dialog.className = 'pdf-preview';
    dialog.setAttribute('role', 'dialog');
    dialog.setAttribute('aria-modal', 'true');
    dialog.setAttribute('aria-label', 'PDF 미리보기');
    var bar = document.createElement('div');
    bar.className = 'pdf-preview__bar';
    var heading = document.createElement('strong');
    heading.textContent = 'PDF 미리보기';
    var cancel = document.createElement('button');
    cancel.type = 'button';
    cancel.textContent = '닫기';
    cancel.addEventListener('click', close);
    var zoom = document.createElement('button');
    zoom.type = 'button';
    zoom.textContent = '크게 보기';
    zoom.setAttribute('aria-pressed', 'false');
    zoom.addEventListener('click', function () {
      var enlarged = dialog.classList.toggle('pdf-preview--zoom');
      zoom.textContent = enlarged ? '화면 맞춤' : '크게 보기';
      zoom.setAttribute('aria-pressed', enlarged ? 'true' : 'false');
    });
    var download = document.createElement('a');
    download.className = 'pdf-preview__download';
    download.textContent = 'PDF 다운로드';
    download.setAttribute('aria-disabled', 'true');
    bar.appendChild(heading);
    bar.appendChild(cancel);
    bar.appendChild(zoom);
    bar.appendChild(download);
    var status = document.createElement('p');
    status.className = 'pdf-preview__status';
    status.setAttribute('role', 'status');
    status.textContent = 'PDF를 만들고 있어요…';
    var pagesRoot = document.createElement('div');
    pagesRoot.className = 'pdf-preview__pages';
    dialog.appendChild(bar);
    dialog.appendChild(status);
    dialog.appendChild(pagesRoot);
    var current = { dialog: dialog, url: null, overflow: document.body.style.overflow, focus: document.getElementById('pdf-btn') || document.activeElement,
      background: Array.from(document.body.children).map(function (node) { return { node: node, inert: node.inert }; }) };
    active = current;
    current.background.forEach(function (item) { item.node.inert = true; });
    document.body.appendChild(dialog);
    document.body.style.overflow = 'hidden';
    cancel.focus();
    dialog.addEventListener('keydown', function (event) {
      if (event.key === 'Escape') { event.preventDefault(); close(); }
      if (event.key === 'Tab') {
        var last = download.hasAttribute('href') ? download : zoom;
        if (event.shiftKey && document.activeElement === cancel) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); cancel.focus(); }
      }
    });
    try {
      if (typeof PDFLib === 'undefined') throw new Error('PDF_LIBRARY_MISSING');
      if (document.fonts && document.fonts.ready) await document.fonts.ready;
      if (active !== current) return false;
      FONT = window.getComputedStyle(document.body).fontFamily || 'sans-serif';
      var canvas = document.createElement('canvas');
      canvas.width = WIDTH * 2;
      canvas.height = HEIGHT * 2;
      var ctx = canvas.getContext('2d');
      if (!ctx) throw new Error('CANVAS_UNAVAILABLE');
      ctx.scale(2, 2);
      function setFont(style) { ctx.font = (style.bold ? 'bold ' : '') + style.size + 'px ' + FONT; }
      var blocks = [
        { style: 'title', text: '진료 안내문' },
        { style: 'meta', text: [data.clinic, data.patient ? data.patient + ' 님' : '', data.visit ? data.visit + ' 진료' : ''].filter(Boolean).join(' · ') }
      ];
      sections.forEach(function (section) {
        blocks.push({ style: 'section', text: section.label });
        blocks = blocks.concat(extractBlocks(section.content));
      });
      var pages = layout(blocks, function (text, style) { setFont(style); return ctx.measureText(text).width; });
      var pdf = await PDFLib.PDFDocument.create();
      pdf.setTitle('진료 안내문');
      pdf.setCreator('CareOn');
      for (var i = 0; i < pages.length; i++) {
        if (active !== current) { canvas.width = 0; return false; }
        ctx.fillStyle = '#ffffff';
        ctx.fillRect(0, 0, WIDTH, HEIGHT);
        pages[i].forEach(function (line) {
          setFont(line.style);
          ctx.fillStyle = line.style.color;
          ctx.fillText(line.text, line.x, line.y);
        });
        setFont(STYLES.meta);
        ctx.fillStyle = '#777078';
        ctx.textAlign = 'center';
        ctx.fillText((i + 1) + ' / ' + pages.length, WIDTH / 2, HEIGHT - 35);
        ctx.textAlign = 'left';
        var imageData = canvas.toDataURL('image/jpeg', .95);
        var image = await pdf.embedJpg(imageData);
        if (active !== current) { canvas.width = 0; return false; }
        pdf.addPage([595.28, 841.89]).drawImage(image, { x: 0, y: 0, width: 595.28, height: 841.89 });
        var img = document.createElement('img');
        img.src = imageData;
        img.alt = '진료 안내문 ' + (i + 1) + ' / ' + pages.length + '페이지';
        img.className = 'pdf-preview__page';
        pagesRoot.appendChild(img);
        await new Promise(function (resolve) { setTimeout(resolve, 0); });
      }
      canvas.width = 0;
      var bytes = await pdf.save();
      if (active !== current) return false;
      current.url = URL.createObjectURL(new Blob([bytes], { type: 'application/pdf' }));
      download.href = current.url;
      download.download = 'careon-guide.pdf'; // 파일명에는 환자 식별정보를 넣지 않는다.
      download.removeAttribute('aria-disabled');
      status.textContent = pages.length + '페이지 · 내용을 확인한 뒤 PDF 다운로드를 눌러 주세요. 개인정보가 포함되어 있으니 공유에 주의해 주세요.';
      download.addEventListener('click', function () {
        status.textContent = '저장 위치는 브라우저에 따라 달라요. 모바일에서는 파일 앱 또는 다운로드 목록을 확인해 주세요.';
      });
      // 이미지 PDF에서 읽을 수 없는 사용자를 위한 동일 본문 제공.
      var accessible = document.createElement('div');
      accessible.className = 'sr-only';
      accessible.textContent = blocks.map(function (block) { return block.text; }).join('\n');
      pagesRoot.appendChild(accessible);
      return true;
    } catch (error) {
      if (canvas) canvas.width = 0;
      if (active !== current) return false;
      pagesRoot.textContent = '';
      status.setAttribute('role', 'alert');
      status.textContent = error.message === 'PDF_TOO_LONG'
        ? '안내문이 너무 길어요. 닫은 뒤 항목을 나누어 저장해 주세요.'
        : 'PDF를 만들지 못했어요. 닫은 뒤 다시 시도해 주세요.';
      return false;
    }
  }
  window.addEventListener('pagehide', close);
  return { preview: preview, wrapLines: wrapLines, layout: layout, extractBlocks: extractBlocks };
})();
