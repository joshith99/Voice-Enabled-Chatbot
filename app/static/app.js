(function () {
  "use strict";

  var chatEl = document.getElementById("chat");
  var micBtn = document.getElementById("micBtn");
  var micText = document.getElementById("micText");
  var textForm = document.getElementById("textForm");
  var textInput = document.getElementById("textInput");
  var sendBtn = document.getElementById("sendBtn");
  var statusEl = document.getElementById("status");
  var statusText = document.getElementById("statusText");
  var noticeEl = document.getElementById("notice");
  var newChatBtn = document.getElementById("newChatBtn");

  var HISTORY_KEY = "myra.history.v1";
  var HISTORY_LIMIT = 20;
  var greetingHTML = chatEl.innerHTML;

  var LANGUAGE_NAMES = {
    "en-IN": "English",
    "hi-IN": "Hindi",
    "te-IN": "Telugu",
    "ta-IN": "Tamil",
    "kn-IN": "Kannada",
    "pa-IN": "Punjabi",
    "bn-IN": "Bengali",
    "gu-IN": "Gujarati",
    "ml-IN": "Malayalam",
    "mr-IN": "Marathi",
    "od-IN": "Odia",
    "ur-IN": "Urdu"
  };

  var recorder = null;
  var chunks = [];
  var activeStream = null;
  var isRecording = false;
  var isBusy = false;
  var mimeType = pickMimeType();
  var micAvailable = !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia && window.MediaRecorder);
  var history = loadHistory();

  function pickMimeType() {
    if (!window.MediaRecorder || !window.MediaRecorder.isTypeSupported) {
      return "";
    }
    if (MediaRecorder.isTypeSupported("audio/webm;codecs=opus")) {
      return "audio/webm;codecs=opus";
    }
    if (MediaRecorder.isTypeSupported("audio/webm")) {
      return "audio/webm";
    }
    return "";
  }

  function languageName(code) {
    if (!code) {
      return "Unknown";
    }
    return LANGUAGE_NAMES[code] || code;
  }

  function scrollToBottom() {
    chatEl.scrollTop = chatEl.scrollHeight;
  }

  function setStatus(text, mode) {
    statusText.textContent = text;
    statusEl.classList.remove("busy", "error");
    if (mode) {
      statusEl.classList.add(mode);
    }
  }

  function showNotice(message) {
    noticeEl.textContent = message;
    noticeEl.classList.remove("hidden");
  }

  function renderRich(text) {
    var escaped = text
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
    return escaped.replace(/\*([^*]+)\*/g, "<em>$1</em>");
  }

  function addBubble(role, label, body, caption, rich) {
    var bubble = document.createElement("div");
    bubble.className = "bubble " + role;

    if (label) {
      var labelEl = document.createElement("div");
      labelEl.className = "bubble-label";
      labelEl.textContent = label;
      bubble.appendChild(labelEl);
    }

    var bodyEl = document.createElement("div");
    bodyEl.className = "bubble-body";
    if (rich) {
      bodyEl.innerHTML = renderRich(body);
    } else {
      bodyEl.textContent = body;
    }
    bubble.appendChild(bodyEl);

    if (caption) {
      var captionEl = document.createElement("div");
      captionEl.className = "bubble-caption";
      captionEl.textContent = caption;
      bubble.appendChild(captionEl);
    }

    chatEl.appendChild(bubble);
    scrollToBottom();
    return bubble;
  }

  function addTypingBubble() {
    return addBubble("bot", "Therapist", "thinking...", "");
  }

  function renderHistoryBubble(message) {
    if (message.role === "user") {
      addBubble("user", "You", message.content, "");
    } else {
      addBubble("bot", "Therapist", message.content, "", true);
    }
  }

  function setControlsDisabled(disabled) {
    micBtn.disabled = disabled || !micAvailable;
    sendBtn.disabled = disabled;
    textInput.disabled = disabled;
  }

  function setBusy(busy) {
    isBusy = busy;
    setControlsDisabled(busy);
    if (busy) {
      setStatus("thinking...", "busy");
    } else {
      setStatus("Ready", null);
    }
  }

  function base64ToBlob(base64, type) {
    var binary = atob(base64);
    var bytes = new Uint8Array(binary.length);
    for (var i = 0; i < binary.length; i++) {
      bytes[i] = binary.charCodeAt(i);
    }
    return new Blob([bytes], { type: type || "audio/mpeg" });
  }

  function playBase64Audio(base64) {
    return new Promise(function (resolve) {
      if (!base64) {
        resolve();
        return;
      }
      var url = null;
      try {
        url = URL.createObjectURL(base64ToBlob(base64, "audio/mpeg"));
        var audio = new Audio(url);
        var finish = function () {
          if (url) {
            URL.revokeObjectURL(url);
            url = null;
          }
          resolve();
        };
        audio.onended = finish;
        audio.onerror = finish;
        var playPromise = audio.play();
        if (playPromise && typeof playPromise.catch === "function") {
          playPromise.catch(function () {
            showNotice("Reply audio was blocked by the browser. Click anywhere, then try again.");
            finish();
          });
        }
      } catch (err) {
        if (url) {
          URL.revokeObjectURL(url);
        }
        resolve();
      }
    });
  }

  function friendlyError(err) {
    if (!err) {
      return "Something went sideways. Try again?";
    }
    return "My brain short-circuited: " + err.message + " — try again.";
  }

  function parseJsonResponse(response) {
    return response.json().catch(function () {
      throw new Error("Server returned an unreadable response (HTTP " + response.status + ").");
    }).then(function (data) {
      if (!response.ok) {
        throw new Error(data && data.error ? data.error : "Server error (HTTP " + response.status + ").");
      }
      return data;
    });
  }

  /* ---------- History persistence ---------- */

  function loadHistory() {
    try {
      var raw = localStorage.getItem(HISTORY_KEY);
      if (!raw) {
        return [];
      }
      var parsed = JSON.parse(raw);
      if (!Array.isArray(parsed)) {
        return [];
      }
      return parsed.filter(function (message) {
        return message &&
          (message.role === "user" || message.role === "assistant") &&
          typeof message.content === "string";
      }).slice(-HISTORY_LIMIT);
    } catch (err) {
      return [];
    }
  }

  function saveHistory() {
    try {
      localStorage.setItem(HISTORY_KEY, JSON.stringify(history));
    } catch (err) {
      /* storage unavailable — keep in-memory history only */
    }
  }

  function clearHistory() {
    history = [];
    try {
      localStorage.removeItem(HISTORY_KEY);
    } catch (err) {
      /* ignore */
    }
  }

  function rememberTurn(userText, assistantText) {
    history.push({ role: "user", content: userText });
    history.push({ role: "assistant", content: assistantText });
    if (history.length > HISTORY_LIMIT) {
      history = history.slice(history.length - HISTORY_LIMIT);
    }
    saveHistory();
  }

  /* ---------- SSE parsing ---------- */

  function extractFrames(buffer) {
    var frames = [];
    var idx = buffer.indexOf("\n\n");
    while (idx !== -1) {
      frames.push(buffer.slice(0, idx));
      buffer = buffer.slice(idx + 2);
      idx = buffer.indexOf("\n\n");
    }
    return { frames: frames, rest: buffer };
  }

  function parseFrame(frame) {
    var eventName = "message";
    var dataLines = [];
    frame.split("\n").forEach(function (line) {
      if (!line) {
        return;
      }
      if (line.indexOf("event:") === 0) {
        eventName = line.slice(6).trim();
      } else if (line.indexOf("data:") === 0) {
        var value = line.slice(5);
        if (value.charAt(0) === " ") {
          value = value.slice(1);
        }
        dataLines.push(value);
      }
    });
    if (!dataLines.length) {
      return null;
    }
    var raw = dataLines.join("\n");
    if (raw === "[DONE]") {
      return { event: "done", data: {} };
    }
    var data;
    try {
      data = JSON.parse(raw);
    } catch (err) {
      return null;
    }
    return { event: eventName, data: data };
  }

  /* ---------- Chat streaming ---------- */

  function streamChat(message, userLabel) {
    addBubble("user", userLabel || "You", message, "");
    setBusy(true);

    var bot = addBubble("bot", "Therapist", "", "");
    var bodyEl = bot.querySelector(".bubble-body");
    var captionEl = null;
    var full = "";
    var gotError = false;
    var audioQueue = Promise.resolve();

    function queueAudio(base64) {
      audioQueue = audioQueue.then(function () {
        return playBase64Audio(base64);
      });
    }

    function setCaption(text) {
      if (!captionEl) {
        captionEl = document.createElement("div");
        captionEl.className = "bubble-caption";
        bot.appendChild(captionEl);
      }
      captionEl.textContent = text;
    }

    function dispatch(eventName, data) {
      if (eventName === "meta") {
        var topic = data.topic || "unknown";
        var confidence = typeof data.confidence === "number" ? data.confidence.toFixed(2) : data.confidence;
        setCaption("topic: " + topic + " · confidence: " + confidence);
      } else if (eventName === "token") {
        if (typeof data.text === "string") {
          full += data.text;
          bodyEl.innerHTML = renderRich(full);
          scrollToBottom();
        }
      } else if (eventName === "audio") {
        if (data.b64) {
          queueAudio(data.b64);
        }
      } else if (eventName === "error") {
        gotError = true;
        addBubble("error", "Error", data.message || "The reply stream failed.", "");
      }
    }

    fetch("/api/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: message, history: history })
    })
      .then(function (response) {
        if (!response.ok) {
          throw new Error("Server error (HTTP " + response.status + ").");
        }
        if (!response.body || !response.body.getReader) {
          throw new Error("Streaming is not supported in this browser.");
        }

        var reader = response.body.getReader();
        var decoder = new TextDecoder();
        var buffer = "";

        function consume(frames) {
          frames.forEach(function (frame) {
            var parsed = parseFrame(frame);
            if (parsed) {
              dispatch(parsed.event, parsed.data);
            }
          });
        }

        function pump() {
          return reader.read().then(function (result) {
            if (result.done) {
              buffer += decoder.decode();
              buffer = buffer.replace(/\r/g, "");
              consume(extractFrames(buffer).frames);
              return;
            }
            buffer += decoder.decode(result.value, { stream: true });
            buffer = buffer.replace(/\r/g, "");
            var split = extractFrames(buffer);
            buffer = split.rest;
            consume(split.frames);
            return pump();
          });
        }

        return pump();
      })
      .catch(function (err) {
        if (!gotError) {
          addBubble("error", "Error", friendlyError(err), "");
        }
      })
      .then(function () {
        return audioQueue;
      })
      .then(function () {
        setBusy(false);
        if (gotError) {
          setStatus("Ready", "error");
        } else if (full.trim()) {
          rememberTurn(message, full);
        }
      });
  }

  /* ---------- Voice flow ---------- */

  function startRecording() {
    if (isBusy || isRecording || !micAvailable) {
      return;
    }

    navigator.mediaDevices.getUserMedia({ audio: true }).then(function (stream) {
      activeStream = stream;
      chunks = [];

      var options = mimeType ? { mimeType: mimeType } : undefined;
      try {
        recorder = new MediaRecorder(stream, options);
      } catch (err) {
        recorder = new MediaRecorder(stream);
      }

      recorder.ondataavailable = function (event) {
        if (event.data && event.data.size > 0) {
          chunks.push(event.data);
        }
      };

      recorder.onerror = function (event) {
        cleanupStream();
        isRecording = false;
        micBtn.classList.remove("recording");
        micText.textContent = "Talk";
        setStatus("Ready", null);
        addBubble("error", "Error", friendlyError(event.error), "");
      };

      recorder.onstop = function () {
        var type = recorder.mimeType || mimeType || "audio/webm";
        var blob = new Blob(chunks, { type: type });
        chunks = [];
        cleanupStream();
        isRecording = false;
        micBtn.classList.remove("recording");
        micText.textContent = "Talk";

        if (!blob || blob.size <= 0) {
          setStatus("Ready", null);
          addBubble("error", "Error", "I didn't catch any audio. Hold the mic a moment longer and try again.", "");
          return;
        }

        sendAudio(blob);
      };

      recorder.start();
      isRecording = true;
      micBtn.classList.add("recording");
      micText.textContent = "Stop";
      setStatus("listening...", "busy");
    }).catch(function (err) {
      var denied = err && (err.name === "NotAllowedError" || err.name === "SecurityError");
      micAvailable = false;
      micBtn.disabled = true;
      showNotice(
        denied
          ? "Microphone permission was denied. Use Chrome or Edge over HTTPS (or localhost), and allow mic access. The text box below still works."
          : "Could not access the microphone. Use Chrome or Edge over HTTPS (or localhost). The text box below still works."
      );
      setStatus("Mic unavailable", "error");
    });
  }

  function stopRecording() {
    if (recorder && isRecording && recorder.state !== "inactive") {
      recorder.stop();
    }
  }

  function cleanupStream() {
    if (activeStream) {
      activeStream.getTracks().forEach(function (track) {
        track.stop();
      });
      activeStream = null;
    }
  }

  function sendAudio(blob) {
    var formData = new FormData();
    formData.append("audio", blob, "recording.webm");

    setBusy(true);
    var typing = addTypingBubble();

    fetch("/api/transcribe", {
      method: "POST",
      body: formData
    })
      .then(parseJsonResponse)
      .then(function (data) {
        typing.remove();

        var transcript = (data.transcript || "").trim();
        if (!transcript) {
          setBusy(false);
          setStatus("Ready", "error");
          addBubble("error", "Error", "I couldn't make out any words. Try again?", "");
          return;
        }

        var label = "You";
        if (data.language_code) {
          label = "You · " + languageName(data.language_code);
        }
        streamChat(transcript, label);
      })
      .catch(function (err) {
        typing.remove();
        setBusy(false);
        setStatus("Ready", "error");
        addBubble("error", "Error", friendlyError(err), "");
      });
  }

  /* ---------- Text flow ---------- */

  function sendText(message) {
    streamChat(message, "You");
  }

  /* ---------- Wiring ---------- */

  micBtn.addEventListener("click", function () {
    if (isRecording) {
      stopRecording();
    } else {
      startRecording();
    }
  });

  textForm.addEventListener("submit", function (event) {
    event.preventDefault();
    var message = textInput.value.trim();
    if (!message || isBusy) {
      return;
    }
    textInput.value = "";
    sendText(message);
  });

  newChatBtn.addEventListener("click", function () {
    if (history.length && !window.confirm("Start a new chat? This clears the conversation.")) {
      return;
    }
    clearHistory();
    chatEl.innerHTML = greetingHTML;
    scrollToBottom();
    setStatus("Ready", null);
  });

  window.addEventListener("storage", function (event) {
    if (event.key !== HISTORY_KEY) {
      return;
    }
    history = loadHistory();
    chatEl.innerHTML = greetingHTML;
    history.forEach(renderHistoryBubble);
    scrollToBottom();
  });

  if (history.length) {
    history.forEach(renderHistoryBubble);
  }

  if (!micAvailable) {
    micBtn.disabled = true;
    micBtn.title = "Voice input unavailable";
    showNotice(
      "Voice input needs Chrome or Edge over HTTPS (or localhost). The text box below still works."
    );
    setStatus("Text mode", "error");
  } else {
    setStatus("Ready", null);
  }
})();
