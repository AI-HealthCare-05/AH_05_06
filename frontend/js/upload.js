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

/* 서버가 판독으로 가려내기 전, 화면에서 미리 어림잡는다.
   맞히려는 것이 아니라 고르는 수고를 줄이려는 것이다 — 사람이 고칠 수 있다. */
function guessKind(name) {
  if (/lab|검사|결과지|result/i.test(name)) return "lab";
  if (/note|소견|메모|초음파/i.test(name)) return "note";
  return "emr";
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

  /* 명세에 제약이 없어 여기서 정한다 — PR 에 적어 서버와 맞춘다.
     화면 검증은 편의일 뿐이고 최종 판정은 서버가 한다(KEY-9 와 같은 원칙). */
  var MAX_BYTES = 20 * 1024 * 1024;
  var MAX_FILES = 10;
  var ACCEPT = /^(image\/|application\/pdf$)/;

  /* 자동 분류 결과. 프로그램이 틀릴 수 있으므로 사람이 고칠 수 있어야 한다. */
  var KINDS = [
    { key: "emr", label: "과거기록" },
    { key: "note", label: "소견" },
    { key: "lab", label: "검사지" },
  ];

  var files = [];
  var seq = 0;


  function reject(file) {
    if (!ACCEPT.test(file.type)) return "이미지나 PDF만 올릴 수 있습니다.";
    if (file.size > MAX_BYTES) return "파일이 너무 큽니다 (" + human(MAX_BYTES) + " 까지).";
    return null;
  }

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
          if (f.state === "done") {
            right =
              '<select class="file__kind" data-kind="' +
              f.id +
              '" aria-label="' +
              f.name +
              ' 종류">' +
              KINDS.map(function (k) {
                return '<option value="' + k.key + '"' + (k.key === f.kind ? " selected" : "") + ">" + k.label + "</option>";
              }).join("") +
              "</select>";
          } else if (f.state === "failed") {
            right = '<button class="file__act" type="button" data-retry="' + f.id + '">다시 시도</button>';
          }
          /* rejected 에는 다시 시도를 붙이지 않는다 — 지우고 다른 파일을 올려야 한다 */

          return (
            '<div class="file' +
            (f.state === "failed" || f.state === "rejected" ? " file--failed" : "") +
            '">' +
            '<div class="file__thumb">' +
            (f.thumb ? '<img src="' + f.thumb + '" alt="">' : f.type === "application/pdf" ? "📄" : "🖼") +
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

    /* EMR 과거기록이 「안내문 생성 필수」다. 한 장도 없으면 다음으로 못 간다 —
       화면에 필수라고 적어 놓고 통과시키면 다음 단계에서 막힌다. */
    var hasEmr = done.some(function (f) {
      return f.kind === "emr";
    });
    next.disabled = !hasEmr;
    next.title = hasEmr ? "" : "EMR 과거기록을 한 장 이상 올려 주세요";
  }

  /* 화면 kind → 서버 OcrDocumentType 매핑 (KEY-56) */
  var KIND_TO_TYPE = { emr: "EMR", note: "EMR", lab: "LAB_RESULT" };

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

    var form = new FormData();
    form.append("files", item.file);
    var docType = KIND_TO_TYPE[item.kind];
    if (docType) form.append("document_type", docType);

    var headers = { Accept: "application/json" };
    var token = session.token();
    if (token) headers["Authorization"] = "Bearer " + token;

    fetch(API_BASE + "/front-desk/visits/" + visit.visit_id + "/documents", {
      method: "POST",
      headers: headers,
      credentials: "include",
      body: form,
    })
      .then(function (res) {
        return res.json().then(function (data) {
          if (!res.ok) throw new Error(data.message || "업로드 실패");
          return data;
        });
      })
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
    var room = MAX_FILES - files.length;
    if (incoming.length > room) {
      incoming = incoming.slice(0, Math.max(0, room));
      alert("한 번에 " + MAX_FILES + "장까지 올릴 수 있습니다.");
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
        kind: guessKind(file.name),
      };
      var bad = reject(file);
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

  /* 끌어다 놓기 — 창 전체에서 기본 동작(파일 열기)을 막지 않으면
     빗나가게 놓았을 때 브라우저가 그 파일로 화면을 덮어 버린다. */
  ["dragenter", "dragover", "dragleave", "drop"].forEach(function (name) {
    window.addEventListener(name, function (event) {
      event.preventDefault();
    });
  });

  drop.addEventListener("dragenter", function () {
    drop.classList.add("is-over");
  });
  drop.addEventListener("dragover", function () {
    drop.classList.add("is-over");
  });
  drop.addEventListener("dragleave", function (event) {
    if (!drop.contains(event.relatedTarget)) drop.classList.remove("is-over");
  });
  drop.addEventListener("drop", function (event) {
    drop.classList.remove("is-over");
    if (event.dataTransfer && event.dataTransfer.files.length) add(event.dataTransfer.files);
  });

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

  list.addEventListener("change", function (event) {
    var picker = event.target.closest("[data-kind]");
    if (!picker) return;
    var item = files.find(function (f) {
      return f.id === picker.dataset.kind;
    });
    if (item) item.kind = picker.value;
    render();
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
    /* **어느 진료인지 실어 보낸다.**

       예전에는 `/ocr-review.html` 로 맨몸으로 갔다. 주석은 「shell.js 가 현재
       진료 건을 자동 선택한다」고 적어 두었는데, 그런 보장이 없다 — 새 화면의
       `shell.js` 는 **목록의 맨 위 줄**을 고른다. 그래서 올린 사람과 다른
       환자의 판독 화면이 열렸다.

       게다가 올리고 나면 그 진료의 분류가 바뀐다(진료기록 없음 → 판독 확인).
       고른 칩이 옛 분류면 그 줄은 목록에서 아예 걸러진다 — 맨 위 줄이 남의
       것일 수밖에 없다.

       `?visit=` 은 `shell.js` 의 `entry` 가 받아서 그 줄을 고르고, 꺼져 있으면
       그 칩까지 켠다. 의사 화면의 진행 단계가 쓰는 길과 같은 것이다. */
    if (!visit || !visit.visit_id) return;
    location.href = "/ocr-review.html?visit=" + encodeURIComponent(visit.visit_id);
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

  render();
})();
