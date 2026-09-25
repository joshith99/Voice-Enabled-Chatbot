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

  function languageLabel(code) {
    if (!code) {
      return "Unknown language";
    }
    var name = LANGUAGE_NAMES[code] || code;
    return name + " (" + code + ")";
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

  function addBubble(role, label, body, caption) {
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
    bodyEl.textContent = body;
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
    if (!base64) {
      return;
    }
    var url = null;
    try {
      url = URL.createObjectURL(base64ToBlob(base64, "audio/mpeg"));
      var audio = new Audio(url);
      audio.onended = function () {
        URL.revokeObjectURL(url);
      };
      audio.onerror = function () {
        URL.revokeObjectURL(url);
      };
      var playPromise = audio.play();
      if (playPromise && typeof playPromise.catch === "function") {
        playPromise.catch(function () {
          showNotice("Reply audio was blocked by the browser. Click anywhere, then try again.");
        });
      }
    } catch (err) {
      if (url) {
        URL.revokeObjectURL(url);
      }
    }
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

        var transcript = data.transcript || "(no speech detected)";
        addBubble("user", "You · " + languageLabel(data.language_code), transcript, "");

        if (data.english) {
          addBubble("interpretation", "English interpretation", data.english, "");
        }

        var caption = "";
        if (data.intent) {
          caption = "intent: " + data.intent;
          if (typeof data.confidence === "number") {
            caption += " · confidence: " + data.confidence.toFixed(2);
          }
        }
        addBubble("bot", "Therapist", data.response || "(no response)", caption);

        if (data.language_code) {
          setStatus("Heard " + languageLabel(data.language_code), null);
        }
        playBase64Audio(data.audio);
      })
      .catch(function (err) {
        typing.remove();
        addBubble("error", "Error", friendlyError(err), "");
        setStatus("Ready", "error");
      })
      .then(function () {
        setBusy(false);
      });
  }

  /* ---------- Text flow ---------- */

  function sendText(message) {
    addBubble("user", "You", message, "");

    setBusy(true);
    var typing = addTypingBubble();

    fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: message })
    })
      .then(parseJsonResponse)
      .then(function (data) {
        typing.remove();

        var caption = "";
        if (data.intent) {
          caption = "intent: " + data.intent;
          if (typeof data.confidence === "number") {
            caption += " · confidence: " + data.confidence.toFixed(2);
          }
        }
        addBubble("bot", "Therapist", data.response || "(no response)", caption);
      })
      .catch(function (err) {
        typing.remove();
        addBubble("error", "Error", friendlyError(err), "");
        setStatus("Ready", "error");
      })
      .then(function () {
        setBusy(false);
      });
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
