/* S1-5 진료기록 업로드 — KEY-53
 *
 * 한 버튼으로 여러 장을 받고, 무엇이 찍혔는지는 프로그램이 가려낸다.
 * 종류별로 나눠 올리게 하면 스탭이 매번 어느 칸인지 고민한다.
 *
 * KEY-56: uploadOne 을 실제 서버 호출로 교체했다.
 *   POST /api/v1/front-desk/visits/{visit_id}/documents  (multipart)
 *   완료 후 ocr-review.html 로 이동 — KEY-62 TODO 처리.
 */

function human(bytes) {
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return Math.round(bytes / 1024) + " KB";
  return (bytes / 1024 / 1024).toFixed(1) + " MB";
}

/* **종류는 화면이 정하지 않는다.**

   전에는 파일명 정규식으로 어림잡고(`guessKind`) 사람이 고르개로 고치게 했다.
   와이어프레임 설계 주석은 그 반대를 말한다 — 「진료기록을 종류별로 나눠 올리게
   하면 스탭이 매번 어느 칸인지 고민한다. **한 버튼으로 받고 무엇이 찍혔는지는
   프로그램이 가려낸다**」.

   그리고 파일명으로 맞히는 것은 못 맞힌다. 「스크린샷 2026-08-14.png」에는
   단서가 없다. 못 맞힌 값이 고르개에 남으면 사람이 그것을 고치는 수고가 다시
   생기고, 안 고치면 버튼이 잠긴 채로 남았다.

   서버는 `document_type` 을 **선택값**으로 받고 없으면 EMR 로 둔다
   (`app/documents/api.py:36` · `service.py:43`). 판독이 실제 종류를 가려낸다. */

/* 미리보기를 못 만들었을 때 자리를 채우는 그림. 이모지를 쓰지 않는다 —
   기기마다 다르게 그려지고 색을 못 맞춘다 (tokens.css: 「장식용 이모지」). */
var FILE_PIC = {
  pdf:
    '<svg class="file__pic" viewBox="0 0 20 20" aria-hidden="true" focusable="false">' +
    '<path d="M5 2.5h6l4 4v11h-10z" fill="none" stroke="currentColor" stroke-width="1.3"' +
    ' stroke-linejoin="round"/><path d="M11 2.5v4h4" fill="none" stroke="currentColor"' +
    ' stroke-width="1.3" stroke-linejoin="round"/></svg>',
  image:
    '<svg class="file__pic" viewBox="0 0 20 20" aria-hidden="true" focusable="false">' +
    '<rect x="3" y="4.5" width="14" height="11" rx="1.5" fill="none" stroke="currentColor"' +
    ' stroke-width="1.3"/><circle cx="7.5" cy="8.5" r="1.2" fill="none" stroke="currentColor"' +
    ' stroke-width="1.3"/><path d="M4.5 13.5l3.5-3.5 2.5 2.5 2-1.7 3 3.2" fill="none"' +
    ' stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>',
};

/* **판독으로 돌아가는 길** — 와이어프레임에 없는 추가다.
 *
 * 판독 확인 도중에 「기본정보」를 눌러 돌아오면 판독 화면으로 갈 길이 없었다.
 * 단계 줄의 「진료기록」은 이 업로드 칸으로 오고, 판독 확인은 그 다음 화면이라
 * 단계 줄에 자리가 없다. 막다른 곳이다.
 *
 * 업로드가 끝나고 판독이 돌기 시작하면 이 진료 건에는 **판독 작업이 있다.**
 * 그때만 길을 낸다 — 없는데 버튼을 두면 눌러도 아무 일이 없다.
 */
function readingLink(job) {
  if (!job || !job.ocr_job_id) {
    return { show: false, label: "", say: "", tone: "" };
  }
  if (job.status === "PROCESSING") {
    return {
      show: true,
      label: "판독 결과 확인",
      say: "판독 중입니다" + (typeof job.progress === "number" ? " · " + job.progress + "%" : ""),
      tone: "wait",
    };
  }
  if (job.status === "FAILED") {
    /* 실패해도 길은 연다 — 판독 화면이 왜 실패했는지와 다시 하는 길을 갖는다.
       여기서 막으면 스탭이 실패 사유를 볼 데가 없다. */
    return { show: true, label: "판독 결과 확인", say: "판독이 실패했습니다", tone: "warn" };
  }
  return { show: true, label: "판독 결과 확인", say: "판독이 끝났습니다", tone: "done" };
}

function filePic(mimeType) {
  return mimeType === "application/pdf" ? FILE_PIC.pdf : FILE_PIC.image;
}

(function () {
  /* **자기 칸이 없는 페이지에서는 아무것도 하지 않는다.**
     이 파일은 `patients.html` 에만 실린다. 뿌리가 없으면 조용히 돌아간다 —
     위 순수 규칙은 그대로 남아서 다른 파일도, 검사도 부를 수 있다 (KEY-158). */
  if (!document.getElementById("drop")) return;

  var drop = document.getElementById("drop");
  var input = document.getElementById("file");
  var list = document.getElementById("files");
  var next = document.getElementById("next");
  var later = document.getElementById("later");

  /* 크기 제한 · 받는 형식 · 보내는 주소는 `js/upload-core.js` 가 갖는다 —
     판독 확인 화면에서도 그 자리에서 올릴 수 있어야 해서, 두 벌이면 한쪽만
     고쳐지고 어디서 올렸느냐에 따라 되고 안 되고가 갈린다 (WP-S③ 공용 모듈). */
  var files = [];
  var seq = 0;

  function render() {
    var done = files.filter(function (f) {
      return f.state === "done";
    });
    /* 실패와 거부를 가른다.
       실패 — 올리다 끊긴 것. 다시 시도하면 될 수 있다.
       거부 — 형식이나 크기가 안 맞는 것. 다시 시도해도 똑같이 안 된다.
       둘을 같게 다루면 눌러도 아무 일이 안 일어나는 버튼을 계속 누르게 된다. */
    var stuck = files.filter(function (f) {
      return f.state === "failed" || f.state === "rejected";
    });

    var head = "";
    if (files.length) {
      head = '<div class="files__count">' + done.length + "장 업로드됨";
      if (stuck.length) head += " · <span style='color:var(--danger)'>" + stuck.length + "장 안 올라감</span>";
      head += "</div>";
    }

    list.innerHTML =
      head +
      files
        .map(function (f) {
          var meta;
          if (f.state === "uploading") {
            meta =
              '<div class="file__meta">올리는 중 ' +
              f.progress +
              '%</div><div class="bar"><div class="bar__fill" style="width:' +
              f.progress +
              '%"></div></div>';
          } else if (f.state === "failed" || f.state === "rejected") {
            meta = '<div class="file__meta file__meta--failed">' + f.error + "</div>";
          } else {
            meta = '<div class="file__meta">' + human(f.size) + "</div>";
          }

          var right = "";
          if (f.state === "failed") {
            right = '<button class="file__act" type="button" data-retry="' + f.id + '">다시 시도</button>';
          }
          /* rejected 에는 다시 시도를 붙이지 않는다 — 지우고 다른 파일을 올려야 한다 */

          return (
            '<div class="file' +
            (f.state === "failed" || f.state === "rejected" ? " file--failed" : "") +
            '">' +
            '<div class="file__thumb">' +
            (f.thumb ? '<img src="' + f.thumb + '" alt="">' : filePic(f.type)) +
            "</div>" +
            '<div class="file__body"><div class="file__name">' +
            f.name +
            "</div>" +
            meta +
            "</div>" +
            right +
            '<button class="file__act file__act--danger" type="button" data-remove="' +
            f.id +
            '" aria-label="' +
            f.name +
            ' 지우기">지우기</button>' +
            "</div>"
          );
        })
        .join("");

    /* **한 장이라도 올렸으면 다음으로 간다.**

       전에는 「EMR 과거기록이 한 장 이상」을 요구했는데, 그 판정이 파일명
       정규식이었다. 「스크린샷 2026-08-14.png」는 EMR 인지 알 길이 없어
       기본값으로 통과했고, 파일명에 「검사」가 든 EMR 은 잠긴 채로 남았다 —
       사람이 고르개로 고쳐야만 풀렸다.

       못 맞히는 값으로 길을 막지 않는다. 진짜 판정은 판독이 한다 — 필수 항목이
       안 나오면 그때 「확인 필요」로 선다(`ai_worker/tasks/ocr_task.py`). */
    next.disabled = !done.length;
    next.title = done.length ? "" : "진료기록을 한 장 이상 올려 주세요";
  }

  /* 실제 업로드 — POST /api/v1/front-desk/visits/{visit_id}/documents
     request() 는 Content-Type: application/json 을 고정으로 붙이므로
     multipart 에는 fetch() 를 직접 쓴다. 브라우저가 boundary 를 포함한
     Content-Type 을 자동으로 설정한다. */
  function uploadOne(item) {
    if (!visit) {
      item.state = "failed";
      item.error = "진료 건을 먼저 선택해 주세요.";
      render();
      return;
    }

    item.state = "uploading";
    item.progress = 0;
    render();

    postDocument(visit.visit_id, item.file)
      .then(function (data) {
        item.state = "done";
        item.ocr_job_id = data.ocr_job_id;
        render();
      })
      .catch(function (err) {
        item.state = "failed";
        item.error = err.message || "업로드하지 못했습니다. 다시 시도해 주세요.";
        render();
      });
  }


  function add(fileList) {
    var incoming = Array.prototype.slice.call(fileList);
    var room = roomFor(files.length);
    if (incoming.length > room) {
      incoming = incoming.slice(0, room);
      alert("한 번에 " + UPLOAD_MAX_FILES + "장까지 올릴 수 있습니다.");
    }

    incoming.forEach(function (file) {
      var item = {
        id: "f" + ++seq,
        name: file.name,
        size: file.size,
        type: file.type,
        file: file, // uploadOne 이 FormData 에 실을 실제 File 객체
        state: "uploading",
        progress: 0,
        thumb: null,
      };
      var bad = rejectFile(file, human);
      files.push(item);

      if (bad) {
        item.state = "rejected";
        item.error = bad;
        return render();
      }
      if (/^image\//.test(file.type)) item.thumb = URL.createObjectURL(file);
      uploadOne(item);
    });
    render();
  }

  document.getElementById("pick").addEventListener("click", function () {
    input.click();
  });

  input.addEventListener("change", function () {
    add(this.files);
    this.value = ""; // 같은 파일을 다시 골라도 change 가 나게 한다
  });

  /* 끌어다 놓기 — 창 전체 방어까지 `js/upload-core.js` 가 붙인다 */
  wireDrop(drop, add);

  list.addEventListener("click", function (event) {
    var retry = event.target.closest("[data-retry]");
    var remove = event.target.closest("[data-remove]");
    if (retry) {
      var again = files.find(function (f) {
        return f.id === retry.dataset.retry;
      });
      if (again) uploadOne(again);
      return;
    }
    if (remove) {
      files = files.filter(function (f) {
        if (f.id !== remove.dataset.remove) return true;
        if (f.thumb) URL.revokeObjectURL(f.thumb); // 미리보기를 놓아준다
        return false;
      });
      render();
    }
  });

  /* 두 버튼이 갈 곳은 아직 없다.
     없는 주소로 보내면 404 가 뜨고, 스탭은 그것을 「내가 뭘 잘못했나」로 읽는다 —
     그래서 여기 세워 두고 무슨 일이 일어났는지만 말한다.
     왼쪽 목록은 늘 있으니 다음 환자로 가는 길이 막히지도 않는다. */
  function say(text) {
    document.getElementById("say").textContent = text;
  }

  /* 여기서 그만둬도 환자는 남는다. 「작성 중 · 진료기록 없음」으로 목록에 있다. */
  later.addEventListener("click", function () {
    say("나중에 올려도 됩니다 — 목록에 「작성 중 · 진료기록 없음」으로 남아 있습니다.");
  });

  next.addEventListener("click", function () {
    /* KEY-56: ocr-review.html 이 완성됐으므로 바로 이동한다 (KEY-62 TODO 처리).
       shell.js 가 현재 진료 건을 자동 선택하고 visit:selected 를 발생시키면
       ocr-review.js 가 jobForVisit 으로 OCR 결과를 불러온다. */
    location.href = "/ocr-review.html";
  });

  /* 지금 고른 진료 건. **업로드가 붙는 자리는 visit_id 다.**
     화면에 보이는 것은 hospital_patient_no(차트번호)이고 둘은 다르다.

     차트번호로 걸어 두면 같은 환자의 **지난 진료에 이번 기록이 붙는다.**
     화면 위에 누구의 기록인지 늘 붙어 있어야 하는 이유와 같은 이야기다. */
  var visit = null;

  /* 화면 위의 「누구의 기록인가」 줄은 환자 카드가 갖는다(KEY-50 detail.js) —
     기본정보 탭과 진료기록 탭이 같은 머리를 쓰기 때문이다. 여기서는 어느
     진료 건에 붙이는지만 들고 있으면 된다. */
  function showVisit(next) {
    if (!next) return;
    visit = next;
    askReading();
  }

  /* 이 진료 건에 판독 작업이 있는지 묻고, 있으면 돌아가는 길을 낸다.
     없으면 조용히 지운다 — 앞 환자의 길이 남아 있으면 남의 판독으로 간다. */
  function askReading() {
    var box = document.getElementById("reading");
    if (!box || !visit || !visit.visit_id) return;
    var asked = visit.visit_id;

    box.hidden = true;
    ocrApi
      .jobForVisit(asked)
      .then(function (job) {
        /* 답이 오는 사이 다른 환자를 골랐으면 버린다 */
        if (!visit || visit.visit_id !== asked) return;
        drawReading(readingLink(job));
      })
      .catch(function () {
        /* 판독 작업이 없으면 404 다. 그건 오류가 아니라 「아직 안 올렸다」다. */
        if (!visit || visit.visit_id !== asked) return;
        drawReading(readingLink(null));
      });
  }

  function drawReading(link) {
    var box = document.getElementById("reading");
    if (!box) return;
    box.hidden = !link.show;
    if (!link.show) return;

    var say = document.getElementById("reading-say");
    var go = document.getElementById("reading-go");
    if (say) {
      say.textContent = link.say;
      say.className = "note note--" + link.tone;
    }
    if (go) go.textContent = link.label;
  }

  document.addEventListener("session:ready", function () {
    showVisit(selectedVisit());
  });

  /* 다른 환자를 고르면 올리던 것을 따라가면 안 된다.
     KEY-35 가 목록을 실제 API 와 이으면 이 자리가 그대로 쓰인다. */
  document.addEventListener("visit:selected", function (event) {
    if (visit && event.detail.visit_id === visit.visit_id) return;
    files.forEach(function (f) {
      if (f.thumb) URL.revokeObjectURL(f.thumb);
    });
    files = [];
    /* 앞 환자에게 한 말도 같이 지운다 — 남겨 두면 새 환자 이름 아래에 붙어서
       이 사람 것을 올렸다는 뜻으로 읽힌다. 파일을 비우는 것과 같은 이유다. */
    say("");
    showVisit(event.detail);
    render();
  });

  document.addEventListener("click", function (event) {
    var go = event.target.closest && event.target.closest("#reading-go");
    if (!go || !visit || !visit.visit_id) return;
    location.href = "/ocr-review.html?visit=" + encodeURIComponent(visit.visit_id);
  });

  render();
})();
