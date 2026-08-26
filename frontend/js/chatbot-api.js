/* KEY-95 챗봇 UI가 사용하는 스트림 어댑터.
 *
 * KEY-96은 실제 모델을 한 번 호출하는 최소 JSON 응답 API를 사용한다. 서버가
 * 완성한 답변 한 건을 UI의 기존 스트림 어댑터에 한 조각으로 전달한다. SSE는
 * 이번 일감에서 새로 동결하지 않는다. 목업은 P6 화면 검증용 합성 승인 안내만 사용한다.
 */

var CHATBOT_MOCK = (function () {
  try {
    return new URLSearchParams(window.location.search).get("mock") === "1";
  } catch (e) {
    return false;
  }
})();

function ChatbotUiError(code) {
  this.name = "ChatbotUiError";
  this.code = code;
}
ChatbotUiError.prototype = Object.create(Error.prototype);

function mockChatbotResult(question) {
  if (/숨|다리.*붓|가슴.*아/.test(question)) {
    return {
      answer: "지금 바로 병원에 연락해 주세요. 한쪽 다리가 붓고 숨이 차는 것은 즉시 확인이 필요한 신호예요.",
      evidence: "주의사항 · 바로 병원에 연락하세요",
      source: "담당 의료진이 승인한 진료 안내",
      limitation: "화면에서 응급 여부를 진단할 수 없어요.",
      urgent: true,
    };
  }
  if (/출혈|끊/.test(question)) {
    return {
      answer: "출혈은 복용 초기에 흔한 반응이에요. 다만 약을 끊을지 여부는 담당 의료진과 상의해 주세요.",
      evidence: "주의사항 · 흔하고 괜찮은 반응",
      source: "담당 의료진이 승인한 진료 안내",
      limitation: "진단이나 처방 변경은 안내할 수 없어요.",
      urgent: false,
    };
  }
  return {
    answer: "안내에 없는 내용은 답해 드릴 수 없어요. 병원에 문의해 주세요.",
    evidence: "승인 안내에서 근거를 찾지 못함",
    source: "담당 의료진이 승인한 진료 안내",
    limitation: "승인된 안내에 근거가 없는 내용은 답하지 않아요.",
    urgent: false,
  };
}

function streamMockResult(result, observer) {
  var chunks = result.answer.match(/.{1,9}/g) || [result.answer];
  return new Promise(function (resolve) {
    function emit(index) {
      if (index >= chunks.length) {
        if (observer.onComplete) observer.onComplete(result);
        resolve(result);
        return;
      }
      if (observer.onDelta) observer.onDelta(chunks[index]);
      setTimeout(function () {
        emit(index + 1);
      }, 35);
    }
    emit(0);
  });
}

function streamChatbotAnswer(request, observer) {
  observer = observer || {};
  if (CHATBOT_MOCK) {
    var query = new URLSearchParams(window.location.search);
    if (query.get("chat") === "error") {
      return Promise.reject(new ChatbotUiError("CHATBOT_STREAM_FAILED"));
    }
    return streamMockResult(mockChatbotResult(String(request.question || "")), observer);
  }
  if (typeof window.chatbotStreamTransport === "function") {
    return window.chatbotStreamTransport(request, observer);
  }
  return Promise.reject(new ChatbotUiError("CHATBOT_API_NOT_READY"));
}

function apiChatbotStreamTransport(request, observer) {
  observer = observer || {};
  return fetch("/api/v1/chatbot/responses", {
    method: "POST",
    credentials: "include",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify({ link_token: request.link_token, question: request.question }),
  }).then(function (response) {
    return response
      .json()
      .catch(function () {
        return {};
      })
      .then(function (result) {
        if (!response.ok) throw new ChatbotUiError(result.code || "CHATBOT_STREAM_FAILED");
        if (observer.onDelta) observer.onDelta(result.answer || "");
        if (observer.onComplete) observer.onComplete(result);
        return result;
      });
  });
}

if (!CHATBOT_MOCK && typeof window.chatbotStreamTransport !== "function") {
  window.chatbotStreamTransport = apiChatbotStreamTransport;
}

function chatbotErrorMessage(code) {
  return code === "CHATBOT_API_NOT_READY"
    ? "챗봇 연결을 준비하고 있어요. 잠시 뒤 다시 시도해 주세요."
    : "답변을 불러오지 못했어요. 잠시 뒤 다시 시도해 주세요.";
}
