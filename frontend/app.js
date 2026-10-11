/* ==========================================================================
   LingoSync AI — front end
   Vanilla JS, no build step. Everything lives inside this IIFE so nothing
   leaks onto `window` except what the browser itself defines.
   ========================================================================== */
(() => {
  "use strict";

  /* ------------------------------------------------------------------ *
   *  Constants / defaults
   * ------------------------------------------------------------------ */

  const STORAGE_KEY = "lingosync:settings";
  const TARGET_CHUNK_SAMPLES = 1600; // 100ms @ 16kHz
  const TARGET_SAMPLE_RATE = 16000;

  const DEFAULT_SETTINGS = {
    sourceLang: "auto",
    targetLang: "en",
    v: 2,
    engine: "pocket_tts",
    clone: true,
    consent: false,
    micId: "",
    outputId: "",
    volume: 100,
    muted: false,
    echoCancellation: true,
    noiseSuppression: true,
    autoGainControl: true,
  };

  const STATUS_LABELS = {
    idle: "Idle",
    loading: "Loading…",
    listening: "Listening",
    speech: "Hearing speech",
    transcribing: "Transcribing…",
    translating: "Translating…",
    synthesizing: "Synthesizing voice…",
    error: "Error",
  };

  /* ------------------------------------------------------------------ *
   *  App namespace — all mutable state lives here instead of on window.
   * ------------------------------------------------------------------ */

  const App = {
    ws: null,
    wsReconnectAttempts: 0,
    wsReconnectTimer: null,

    engines: new Map(), // id -> engine descriptor from `hello`
    languages: [], // from `hello`

    settings: loadSettings(),

    // Audio capture state
    audioContext: null,
    mediaStream: null,
    sourceNode: null,
    workletNode: null,
    scriptNode: null,
    silentGain: null,
    resampler: null, // used only for the ScriptProcessor fallback path
    isListening: false,

    // Playback state
    // Streamed TTS parts are decoded into a Web Audio graph and scheduled back to back
    // (gapless), then routed into the hidden <audio> element so setSinkId still picks the earphones.
    playCtx: null,
    playDest: null,
    playHead: 0, // AudioContext time at which the next part starts
    decodeChain: Promise.resolve(), // keeps parts in arrival order while decoding
    playingCount: new Map(), // id -> number of scheduled parts still playing
    // TTS can run slower than real time, so each new utterance waits this long before playing.
    // It grows when a sentence still stalls mid-way and shrinks slowly while playback is smooth.
    prebuffer: 0.6,
    lag: 2.5, // seconds the English runs behind the speaker (see schedulePart)
    lastScheduledId: null,
    segmentAudio: new Map(), // id -> [AudioBuffer] in part order

    // Transcript state
    segmentCards: new Map(), // id -> DOM element
  };

  /* ------------------------------------------------------------------ *
   *  DOM references
   * ------------------------------------------------------------------ */

  const el = {};

  function cacheDom() {
    el.connState = document.getElementById("connState");
    el.connStateText = document.getElementById("connStateText");
    el.pipelineStatus = document.getElementById("pipelineStatus");
    el.pipelineStatusText = document.getElementById("pipelineStatusText");
    el.levelBar = document.getElementById("levelBar");
    el.speechIndicator = document.getElementById("speechIndicator");

    el.startStopBtn = document.getElementById("startStopBtn");
    el.startStopIcon = document.getElementById("startStopIcon");
    el.startStopLabel = document.getElementById("startStopLabel");
    el.warmBtn = document.getElementById("warmBtn");
    el.warmHint = document.getElementById("warmHint");
    el.flushBtn = document.getElementById("flushBtn");
    el.clearBtn = document.getElementById("clearBtn");

    el.sourceLangSelect = document.getElementById("sourceLangSelect");
    el.targetLangSelect = document.getElementById("targetLangSelect");
    el.engineSelect = document.getElementById("engineSelect");
    el.micSelect = document.getElementById("micSelect");
    el.outputSelect = document.getElementById("outputSelect");
    el.outputDeviceField = document.getElementById("outputDeviceField");

    el.volumeSlider = document.getElementById("volumeSlider");
    el.muteBtn = document.getElementById("muteBtn");
    el.muteIcon = document.getElementById("muteIcon");

    el.echoCancelToggle = document.getElementById("echoCancelToggle");
    el.noiseSuppressToggle = document.getElementById("noiseSuppressToggle");
    el.autoGainToggle = document.getElementById("autoGainToggle");

    el.consentCheckbox = document.getElementById("consentCheckbox");
    el.cloneToggle = document.getElementById("cloneToggle");
    el.consentHint = document.getElementById("consentHint");
    el.voiceStatus = document.getElementById("voiceStatus");
    el.speakerPanel = document.getElementById("speakerPanel");
    el.usageMeter = document.getElementById("usageMeter");
    el.resetVoiceBtn = document.getElementById("resetVoiceBtn");

    el.transcriptFeed = document.getElementById("transcriptFeed");
    el.transcriptEmpty = document.getElementById("transcriptEmpty");

    el.toastContainer = document.getElementById("toastContainer");
    el.playbackAudio = document.getElementById("playbackAudio");
  }

  /* ------------------------------------------------------------------ *
   *  Settings persistence (wrapped in try/catch — private mode etc.)
   * ------------------------------------------------------------------ */

  function loadSettings() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return { ...DEFAULT_SETTINGS };
      const parsed = JSON.parse(raw);
      // v2 made Pocket TTS the default (continuous speech); move old saved defaults over once.
      if (!parsed.v || parsed.v < 2) {
        if (parsed.engine === "chatterbox_turbo") delete parsed.engine;
        parsed.v = 2;
      }
      return { ...DEFAULT_SETTINGS, ...parsed };
    } catch (err) {
      return { ...DEFAULT_SETTINGS };
    }
  }

  function saveSettings() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(App.settings));
    } catch (err) {
      /* ignore quota / privacy-mode errors */
    }
  }

  /* ------------------------------------------------------------------ *
   *  WebSocket connection with auto-reconnect + exponential backoff
   * ------------------------------------------------------------------ */

  function wsUrl() {
    if (window.LINGOSYNC_WS) return window.LINGOSYNC_WS; // cloud: interpreter runs on a separate GPU endpoint
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    return `${proto}//${location.host}/ws`;
  }

  // Cloud: the server runs on a paid GPU that starts when the page connects. Connect only while the user is
  // listening, close soon after Stop / in a background tab, and never reconnect in a loop (2026-09-27: open tabs
  // and reconnect loops kept GPUs running).
  const CLOUD = !!window.LINGOSYNC_WS;
  const CLOUD_CLOSE_AFTER_STOP_MS = 15000;           // owner's rule: 15 s unused -> switch off
  const CLOUD_HIDDEN_STOP_MS = 120000;
  const CLOUD_MAX_RECONNECTS = 5;
  App.wantConnection = !CLOUD;

  function cloudConnect() {
    App.wantConnection = true;
    clearTimeout(App.cloudCloseTimer);
    if (!App.ws || App.ws.readyState > WebSocket.OPEN) {
      App.wsReconnectAttempts = 0;
      connectWebSocket();
      showToast("Starting the translator… the first start takes about a minute.");
    }
  }

  function cloudRelease(delayMs) {
    clearTimeout(App.cloudCloseTimer);
    App.cloudCloseTimer = setTimeout(() => {
      if (App.isListening) return;
      App.wantConnection = false;
      clearTimeout(App.wsReconnectTimer);
      App.wsReconnectTimer = null;
      if (App.ws) try { App.ws.close(); } catch (e) { /* already closed */ }
      setConnState("idle");
    }, delayMs);
  }

  function connectWebSocket() {
    if (!App.wantConnection) return;
    setConnState("connecting");
    let socket;
    try {
      socket = new WebSocket(wsUrl());
    } catch (err) {
      scheduleReconnect();
      return;
    }
    App.ws = socket;

    socket.addEventListener("open", () => {
      App.wsReconnectAttempts = 0;
      setConnState("open");
      sendConfig();
    });

    socket.addEventListener("message", onServerMessage);

    socket.addEventListener("close", () => {
      if (App.ws !== socket) return;                 // an older socket we already replaced
      closeUsageSession();
      setConnState(App.wantConnection ? "closed" : "idle");
      scheduleReconnect();
    });

    socket.addEventListener("error", () => {
      // onclose fires right after in browsers; nothing else to do here.
    });
  }

  function scheduleReconnect() {
    if (App.wsReconnectTimer || !App.wantConnection) return;
    if (CLOUD && App.wsReconnectAttempts >= CLOUD_MAX_RECONNECTS) {
      App.wantConnection = false;
      if (App.isListening) stopCapture({ notifyServer: false });
      setConnState("idle");
      showToast("Connection to the translator was lost. Press Start to try again.");
      return;
    }
    setConnState("reconnecting");
    const attempt = App.wsReconnectAttempts++;
    const delay = Math.min(10000, 500 * Math.pow(1.6, attempt)) + Math.random() * 300;
    App.wsReconnectTimer = setTimeout(() => {
      App.wsReconnectTimer = null;
      connectWebSocket();
    }, delay);
  }

  function setConnState(state) {
    el.connState.dataset.state = state;
    const labels = {
      open: "Connected",
      connecting: "Connecting…",
      reconnecting: "Reconnecting…",
      closed: "Disconnected",
      idle: CLOUD ? "Off (press Start)" : "Disconnected",
    };
    el.connStateText.textContent = labels[state] || state;
  }

  function wsSend(payload) {
    if (App.ws && App.ws.readyState === WebSocket.OPEN) {
      // Plain objects are control messages: they must go as JSON text (an object would be sent
      // as "[object Object]" and ignored, which silently broke Start/Reset voice before).
      const isBinary = payload instanceof ArrayBuffer || ArrayBuffer.isView(payload);
      App.ws.send(typeof payload === "string" || isBinary ? payload : JSON.stringify(payload));
      return true;
    }
    return false;
  }

  function sendConfig() {
    const msg = {
      type: "config",
      source_lang: App.settings.sourceLang,
      target_lang: App.settings.targetLang,
      engine: App.settings.engine,
      clone: !!App.settings.clone,
      consent: !!App.settings.consent,
      client_id: App.clientId,       // anonymous id for the usage record (billing by time)
    };
    wsSend(JSON.stringify(msg));
  }

  /* ------------------------------------------------------------------ *
   *  Server -> client message handling
   * ------------------------------------------------------------------ */

  function onServerMessage(event) {
    if (typeof event.data !== "string") return; // server only sends JSON text
    let msg;
    try {
      msg = JSON.parse(event.data);
    } catch (err) {
      return;
    }

    switch (msg.type) {
      case "hello":
        handleHello(msg);
        break;
      case "status":
        handleStatus(msg);
        break;
      case "level":
        handleServerLevel(msg);
        break;
      case "segment":
        handleSegment(msg);
        break;
      case "audio":
        handleAudio(msg);
        break;
      case "voice":
        handleVoice(msg);
        break;
      case "usage":
        handleUsage(msg);
        break;
      case "error":
        showToast(msg.message || "Unknown error");
        break;
      default:
        break;
    }
  }

  function handleHello(msg) {
    // Cloud server paces the English itself (phrase by phrase, in small streamed parts): play parts as they
    // arrive instead of adding the interpreter lag below, which grew to 8 s on streamed parts (2026-09-27).
    App.serverPacing = !!msg.server_pacing;
    App.engines = new Map((msg.engines || []).map((e) => [e.id, e]));
    App.languages = msg.languages || [];

    populateSelect(
      el.sourceLangSelect,
      App.languages.map((l) => ({ value: l.code, label: l.name }))
    );
    populateSelect(
      el.targetLangSelect,
      App.languages
        .filter((l) => l.code !== "auto")
        .map((l) => ({ value: l.code, label: l.name }))
    );
    populateSelect(
      el.engineSelect,
      (msg.engines || []).map((e) => ({ value: e.id, label: e.label }))
    );

    // Restore persisted selections when still valid, else keep server-implied defaults.
    setSelectValueIfPresent(el.sourceLangSelect, App.settings.sourceLang);
    setSelectValueIfPresent(el.engineSelect, App.settings.engine);
    applyEngineTargetRestrictions();
    setSelectValueIfPresent(el.targetLangSelect, App.settings.targetLang);

    // Keep settings in sync with whatever actually ended up selected.
    App.settings.sourceLang = el.sourceLangSelect.value || App.settings.sourceLang;
    App.settings.engine = el.engineSelect.value || App.settings.engine;
    App.settings.targetLang = el.targetLangSelect.value || App.settings.targetLang;
    saveSettings();
    updateCloneAvailability();
    sendConfig();
  }

  function populateSelect(selectEl, items) {
    selectEl.innerHTML = "";
    for (const item of items) {
      const opt = document.createElement("option");
      opt.value = item.value;
      opt.textContent = item.label;
      selectEl.appendChild(opt);
    }
  }

  function setSelectValueIfPresent(selectEl, value) {
    const has = Array.from(selectEl.options).some((o) => o.value === value);
    if (has) selectEl.value = value;
  }

  function applyEngineTargetRestrictions() {
    const engine = App.engines.get(el.engineSelect.value);
    const restrictedTargets = engine && Array.isArray(engine.targets) ? engine.targets : [];
    const hasRestriction = restrictedTargets.length > 0;

    let selectedStillValid = false;
    for (const opt of el.targetLangSelect.options) {
      const allowed = !hasRestriction || restrictedTargets.includes(opt.value);
      opt.disabled = !allowed;
      if (allowed && opt.value === el.targetLangSelect.value) selectedStillValid = true;
    }
    if (!selectedStillValid) {
      const firstEnabled = Array.from(el.targetLangSelect.options).find((o) => !o.disabled);
      if (firstEnabled) el.targetLangSelect.value = firstEnabled.value;
    }
  }

  function handleStatus(msg) {
    const state = msg.state || "idle";
    el.pipelineStatus.dataset.state = state;
    const label = STATUS_LABELS[state] || state;
    el.pipelineStatusText.textContent = label;
    el.pipelineStatus.title = msg.detail || label;
  }

  function handleServerLevel(msg) {
    setLevelBar(clamp01(msg.rms));
    const speaking = !!msg.speech;
    el.speechIndicator.dataset.speech = String(speaking);
  }

  function handleSegment(msg) {
    const card = getOrCreateCard(msg.id);
    if (msg.speaker !== undefined && msg.speaker !== null) {
      const spk = String(msg.speaker);
      ensureSpeaker(spk);
      App.segmentSpeaker.set(msg.id, spk);
      const chip = card.querySelector(".card-speaker");
      chip.hidden = false;
      chip.dataset.speaker = spk;
      chip.textContent = speakerName(spk);
      chip.style.setProperty("--spk", speakerColor(spk));
      if (msg.target_text === null || msg.target_text === undefined) markSpeaker(spk, "speaking");
    }

    // Partial updates (e.g. translation arriving before TTS) leave source fields null.
    if (msg.source_lang) card.querySelector(".lang-badge").textContent = languageBadgeText(msg.source_lang);
    if (msg.source_text !== null && msg.source_text !== undefined) {
      card.querySelector(".card-source-text").textContent = msg.source_text;
    }

    const targetEl = card.querySelector(".card-target-text");
    const native = msg.skipped === "same_language";
    card.classList.toggle("is-native", native);
    if (native) {
      // Spoken in the listener's own language: show it once, nothing is played.
      targetEl.textContent = "No translation needed";
    } else if (msg.target_text === null || msg.target_text === undefined) {
      targetEl.innerHTML = '<span class="shimmer" aria-hidden="true"></span><span class="sr-only">Translating…</span>';
    } else {
      targetEl.textContent = msg.target_text;
    }

    renderLatencyChips(card, msg.timings || {});

    el.transcriptEmpty.style.display = "none";
    scrollTranscriptToBottom();
  }

  function languageBadgeText(code) {
    if (!code) return "?";
    const match = App.languages.find((l) => l.code === code);
    return match ? match.name : code.toUpperCase();
  }

  function renderLatencyChips(card, timings) {
    const container = card.querySelector(".latency-chips");
    container.innerHTML = "";
    const spec = [
      ["asr_ms", "ASR"],
      ["mt_ms", "MT"],
      ["tts_ms", "TTS"],
    ];
    for (const [key, label] of spec) {
      const value = timings[key];
      if (typeof value !== "number") continue;
      const chip = document.createElement("span");
      chip.className = "chip";
      chip.textContent = `${label} ${Math.round(value)}ms`;
      container.appendChild(chip);
    }
  }

  function getOrCreateCard(id) {
    let card = App.segmentCards.get(id);
    if (card) return card;

    card = document.createElement("article");
    card.className = "transcript-card";
    card.dataset.id = String(id);
    card.innerHTML = `
      <div class="card-top-row">
        <span class="card-speaker" hidden></span>
        <span class="lang-badge">?</span>
        <span class="card-time"></span>
      </div>
      <div class="card-source-text"></div>
      <div class="card-target-text"></div>
      <div class="card-bottom-row">
        <div class="latency-chips"></div>
        <button type="button" class="btn btn-secondary play-again-btn" disabled>Play again</button>
      </div>
    `;
    card.querySelector(".card-time").textContent = new Date().toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
    });
    card.querySelector(".play-again-btn").addEventListener("click", () => replaySegment(id));

    el.transcriptFeed.appendChild(card);
    App.segmentCards.set(id, card);
    return card;
  }

  function scrollTranscriptToBottom() {
    el.transcriptFeed.scrollTop = el.transcriptFeed.scrollHeight;
  }

  function handleAudio(msg) {
    if (msg.final) {
      const card = App.segmentCards.get(msg.id);
      const btn = card && card.querySelector(".play-again-btn");
      if (btn) btn.disabled = false;
      return;
    }
    if (!msg.wav_base64) return;
    const ctx = ensurePlaybackGraph();
    // When the speaker finished this stretch, on the audio clock (server sends its age).
    const sourceEnd = typeof msg.age === "number" ? ctx.currentTime - msg.age : null;
    const bytes = base64ToBytes(msg.wav_base64);
    App.decodeChain = App.decodeChain
      .then(() => ctx.decodeAudioData(bytes.buffer))
      .then((buffer) => {
        if (!App.segmentAudio.has(msg.id)) App.segmentAudio.set(msg.id, []);
        App.segmentAudio.get(msg.id)[msg.part || 0] = buffer;
        schedulePart(msg.id, buffer, { live: true, sourceEnd });
      })
      .catch((err) => console.warn("[LingoSync] audio decode failed", err));
  }

  /* ------------------------------------------------------------------ *
   *  Speakers: who is talking, their names (editable, remembered here),
   *  and their own cloned voice. Labels come from the server (Soniox).
   * ------------------------------------------------------------------ */
  const SPEAKER_NAMES_KEY = "lingosync.speakerNames";
  const SPEAKER_COLORS = ["var(--card-cyan)", "var(--card-pink)", "var(--card-green)", "var(--card-violet)",
                          "var(--card-orange)", "var(--card-blue)"];
  App.segmentSpeaker = new Map();   // card id -> speaker label
  App.speakers = new Map();         // speaker label -> { chip, voice }
  App.speakerNames = (() => {
    try { return JSON.parse(localStorage.getItem(SPEAKER_NAMES_KEY) || "{}"); } catch (e) { return {}; }
  })();

  function speakerName(spk) {
    return App.speakerNames[spk] || `Speaker ${spk}`;
  }

  function speakerColor(spk) {
    const n = parseInt(spk, 10);
    return SPEAKER_COLORS[(Number.isNaN(n) ? 0 : n - 1 + SPEAKER_COLORS.length) % SPEAKER_COLORS.length];
  }

  function ensureSpeaker(spk) {
    let s = App.speakers.get(spk);
    if (s) return s;
    const chip = document.createElement("div");
    chip.className = "speaker-chip";
    chip.dataset.speaker = spk;
    chip.style.setProperty("--spk", speakerColor(spk));
    chip.innerHTML = `<span class="speaker-dot"></span><button type="button" class="speaker-name" title="Click to rename"></button><span class="speaker-voice"></span>`;
    chip.querySelector(".speaker-name").addEventListener("click", () => renameSpeaker(spk));
    s = { chip, voice: null };
    App.speakers.set(spk, s);
    if (el.speakerPanel) {
      el.speakerPanel.hidden = false;
      el.speakerPanel.appendChild(chip);
    }
    renderSpeaker(spk);
    return s;
  }

  function renderSpeaker(spk) {
    const s = App.speakers.get(spk);
    if (!s) return;
    s.chip.querySelector(".speaker-name").textContent = speakerName(spk);
    const v = s.voice;
    const voiceEl = s.chip.querySelector(".speaker-voice");
    if (v && v.state === "locked") voiceEl.textContent = "own voice ✓";
    else if (v && v.seconds) voiceEl.textContent = `voice ${Math.floor(v.seconds)}/${v.needed}s`;
    else voiceEl.textContent = "default voice";
    s.chip.classList.toggle("is-locked", !!(v && v.state === "locked"));
    document.querySelectorAll(`.card-speaker[data-speaker="${CSS.escape(spk)}"]`).forEach((c) => {
      c.textContent = speakerName(spk);
    });
  }

  function renameSpeaker(spk) {
    const s = App.speakers.get(spk);
    if (!s) return;
    const btn = s.chip.querySelector(".speaker-name");
    const input = document.createElement("input");
    input.className = "speaker-name-input";
    input.value = speakerName(spk);
    input.maxLength = 30;
    btn.replaceWith(input);
    input.focus();
    input.select();
    let done = false;
    const finish = (save) => {
      if (done) return;
      done = true;
      const name = input.value.trim();
      if (save) {
        if (name) App.speakerNames[spk] = name; else delete App.speakerNames[spk];
        try { localStorage.setItem(SPEAKER_NAMES_KEY, JSON.stringify(App.speakerNames)); } catch (e) { /* private mode */ }
      }
      input.replaceWith(btn);
      renderSpeaker(spk);
    };
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") finish(true);
      if (e.key === "Escape") finish(false);
    });
    input.addEventListener("blur", () => finish(true));
  }

  function markSpeaker(spk, mode) {
    // mode "speaking": their Italian is coming in; "playing": their English is being played
    const s = App.speakers.get(spk);
    if (!s) return;
    App.speakers.forEach((o) => o.chip.classList.remove(`is-${mode}`));
    s.chip.classList.add(`is-${mode}`);
    clearTimeout(s[`${mode}Timer`]);
    s[`${mode}Timer`] = setTimeout(() => s.chip.classList.remove(`is-${mode}`), 3000);
  }

  /* Usage meter: time the translator (a paid GPU) has been on, this session and in total on this device. */
  const USAGE_KEY = "lingosync.usageSeconds";
  const CLIENT_KEY = "lingosync.clientId";
  App.clientId = (() => {
    try {
      let id = localStorage.getItem(CLIENT_KEY);
      if (!id) { id = (crypto.randomUUID && crypto.randomUUID()) || String(Math.random()).slice(2); localStorage.setItem(CLIENT_KEY, id); }
      return id;
    } catch (e) { return "anonymous"; }
  })();
  App.usageSaved = (() => { try { return Number(localStorage.getItem(USAGE_KEY)) || 0; } catch (e) { return 0; } })();
  App.usageSession = 0;

  function fmtDuration(s) {
    s = Math.round(s);
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
    return h ? `${h}h ${String(m).padStart(2, "0")}m` : `${m}:${String(sec).padStart(2, "0")}`;
  }

  function handleUsage(msg) {
    App.usageSession = msg.session_s || 0;
    App.usageRate = msg.rate_per_hour || 0;
    renderUsage();
  }

  function renderUsage() {
    if (!el.usageMeter) return;
    const total = App.usageSaved + App.usageSession;
    const cost = (total / 3600) * (App.usageRate || 0);
    el.usageMeter.hidden = false;
    el.usageMeter.textContent = `On ${fmtDuration(App.usageSession)} this session · ${fmtDuration(total)} total · ` +
      `$${cost.toFixed(2)} at $${(App.usageRate || 0).toFixed(2)}/h`;
  }

  function closeUsageSession() {
    if (!App.usageSession) return;
    App.usageSaved += App.usageSession;
    App.usageSession = 0;
    try { localStorage.setItem(USAGE_KEY, String(Math.round(App.usageSaved))); } catch (e) { /* private mode */ }
    renderUsage();
  }

  function handleVoice(msg) {
    if (msg.speaker !== undefined && msg.speaker !== null) {
      // several people: each has their own voice, shown on their chip in the speaker panel
      const spk = String(msg.speaker);
      ensureSpeaker(spk).voice = msg;
      renderSpeaker(spk);
      if (el.voiceStatus) el.voiceStatus.textContent = "Voices follow each speaker (click a name to rename)";
      return;
    }
    if (!el.voiceStatus) return;
    const locked = msg.state === "locked";
    if (locked) {
      el.voiceStatus.textContent = `Voice locked (${msg.seconds}s captured)`;
    } else if (!msg.seconds) {
      el.voiceStatus.textContent = "Voice: not captured yet";
    } else {
      el.voiceStatus.textContent = `Capturing voice… ${msg.seconds}s of ${msg.needed}s`;
    }
    el.voiceStatus.classList.toggle("is-locked", locked);
  }

  /* ------------------------------------------------------------------ *
   *  Playback — Web Audio graph, parts scheduled back to back
   * ------------------------------------------------------------------ */

  function base64ToBytes(base64) {
    const byteChars = atob(base64);
    const bytes = new Uint8Array(byteChars.length);
    for (let i = 0; i < byteChars.length; i++) bytes[i] = byteChars.charCodeAt(i);
    return bytes;
  }

  function ensurePlaybackGraph() {
    if (!App.playCtx) {
      const Ctx = window.AudioContext || window.webkitAudioContext;
      App.playCtx = new Ctx();
      // Parts connect to App.playDest (a gain node, so volume/mute work on every route).
      App.playDest = App.playCtx.createGain();
      if (supportsSetSinkId()) {
        // Desktop Chrome: route through the hidden <audio> so the earphone picker (setSinkId) applies.
        const streamDest = App.playCtx.createMediaStreamDestination();
        App.playDest.connect(streamDest);
        el.playbackAudio.srcObject = streamDest.stream;
      } else {
        // Phones (iOS Safari has no setSinkId): play directly; the OS routes to connected earphones.
        App.playDest.connect(App.playCtx.destination);
      }
      applyVolumeAndMute();
      App.playCtx.onstatechange = () => reportPlayback("context", { state: App.playCtx.state });
      // Watchdog: Chrome can pause the output (Bluetooth reconnect, device switch, tab audio
      // policy). A paused output looks like the translation "got stuck", so revive it.
      setInterval(() => {
        const busy = App.isListening || App.playHead > App.playCtx.currentTime;
        if (!busy) return;
        if (App.playCtx.state === "suspended") {
          App.playCtx.resume().catch(() => {});
          reportPlayback("revived", { what: "audio context" });
        }
        if (supportsSetSinkId() && el.playbackAudio.paused) {
          el.playbackAudio.play().catch(() => {});
          reportPlayback("revived", { what: "output element" });
        }
      }, 2000);
    }
    // Both need a user gesture the first time; startCapture/replay provide one.
    if (App.playCtx.state === "suspended") App.playCtx.resume().catch(() => {});
    if (supportsSetSinkId() && el.playbackAudio.paused) el.playbackAudio.play().catch(() => {});
    return App.playCtx;
  }

  const PREBUFFER_MIN = 0.5;
  const PREBUFFER_MAX = 3.0;
  // Interpreter lag: the English runs this many seconds behind the speaker, used as a buffer so
  // uneven processing never breaks the flow. Grows when something arrives late, eases back slowly.
  const LAG_MIN = 1.5;
  const LAG_MAX = 8.0;

  function schedulePart(id, buffer, { live = false, sourceEnd = null } = {}) {
    const ctx = App.playCtx;
    const src = ctx.createBufferSource();
    src.buffer = buffer;
    src.connect(App.playDest);
    const now = ctx.currentTime;
    const newUtterance = id !== App.lastScheduledId;
    let startAt;
    if (live && App.serverPacing) {
      startAt = Math.max(now + 0.05, App.playHead);
    } else if (live && newUtterance && sourceEnd !== null) {
      // Each stretch starts a fixed lag after the speaker finished it, so the English keeps a
      // steady rhythm behind the speaker instead of stopping and starting with processing time.
      const slot = sourceEnd + App.lag;
      const earliest = now + 0.05;
      if (earliest > slot && earliest > App.playHead) {
        const late = earliest - slot;
        App.lag = Math.min(LAG_MAX, App.lag + late + 0.5);
        reportPlayback("late", { id, seconds: +late.toFixed(2), lag: +App.lag.toFixed(2) });
      } else if (slot - earliest > 2.5) {
        App.lag = Math.max(LAG_MIN, App.lag - 0.1);
      }
      startAt = Math.max(earliest, App.playHead, slot);
    } else if (live && newUtterance) {
      // Older server without "age": hold the first part back so later parts arrive in time.
      startAt = Math.max(now + App.prebuffer, App.playHead);
      App.prebuffer = Math.max(PREBUFFER_MIN, App.prebuffer - 0.1);
    } else {
      if (live && now > App.playHead) {
        // The previous part ran out before this one arrived: an audible gap. Buffer more next time.
        const gap = now - App.playHead;
        App.prebuffer = Math.min(PREBUFFER_MAX, App.prebuffer + gap + 0.2);
        App.lag = Math.min(LAG_MAX, App.lag + gap + 0.3);
        reportPlayback("stall", { id, seconds: +gap.toFixed(2), lag: +App.lag.toFixed(2) });
      }
      // A small lead keeps a part from starting in the past while the graph wakes up.
      startAt = Math.max(now + 0.03, App.playHead);
    }
    if (live) App.lastScheduledId = id; // replays do not count as a new live utterance
    src.start(startAt);
    App.playHead = startAt + buffer.duration;

    App.playingCount.set(id, (App.playingCount.get(id) || 0) + 1);
    const delayMs = Math.max(0, (startAt - ctx.currentTime) * 1000);
    setTimeout(() => {
      setCardPlaying(id, true);
      const spk = App.segmentSpeaker.get(id);
      if (spk !== undefined) markSpeaker(spk, "playing");
    }, delayMs);
    src.onended = () => {
      const left = (App.playingCount.get(id) || 1) - 1;
      App.playingCount.set(id, left);
      if (left <= 0) setCardPlaying(id, false);
    };
  }

  function reportPlayback(event, details) {
    wsSend({ type: "playback", event, ...details });
  }

  function replaySegment(id) {
    const parts = App.segmentAudio.get(id);
    if (!parts || !parts.length) return;
    ensurePlaybackGraph();
    // Queued after whatever is already scheduled; never interrupts live playback.
    parts.forEach((buffer) => buffer && schedulePart(id, buffer));
  }

  function setCardPlaying(id, isPlaying) {
    const card = App.segmentCards.get(id);
    if (card) card.classList.toggle("is-playing", isPlaying);
  }

  function applyVolumeAndMute() {
    const volume = App.settings.muted ? 0 : clamp01(App.settings.volume / 100);
    if (App.playDest) App.playDest.gain.value = volume; // the <audio> element stays at full volume
    el.muteIcon.textContent = App.settings.muted ? "🔇" : "🔊";
    el.muteBtn.setAttribute("aria-pressed", String(!!App.settings.muted));
  }

  /* ------------------------------------------------------------------ *
   *  Level meter (local, immediate) + speech indicator (server-driven)
   * ------------------------------------------------------------------ */

  function setLevelBar(rms) {
    // Simple perceptual boost so quiet speech is still visible.
    const pct = Math.min(100, Math.round(Math.sqrt(clamp01(rms)) * 100));
    el.levelBar.style.width = `${pct}%`;
  }

  function clamp01(n) {
    if (typeof n !== "number" || Number.isNaN(n)) return 0;
    return Math.max(0, Math.min(1, n));
  }

  /* ------------------------------------------------------------------ *
   *  Microphone capture pipeline
   *
   *  We resample whatever native sample rate the AudioContext gives us
   *  (commonly 44100/48000 Hz) down to 16000 Hz mono Int16 PCM using a
   *  small linear-interpolation resampler, batching output into ~100ms
   *  (1600-sample) chunks that get sent as binary WebSocket frames.
   *
   *  Preferred path: AudioWorklet (runs off the main thread). The worklet
   *  module is created from an inline string via a Blob URL so this stays
   *  a single-file, no-build-step app.
   *
   *  Fallback path: ScriptProcessorNode (deprecated but universally
   *  supported), doing the same resampling on the main thread.
   * ------------------------------------------------------------------ */

  const WORKLET_SOURCE = `
    class PCMDownsamplerProcessor extends AudioWorkletProcessor {
      constructor() {
        super();
        this._outRate = ${TARGET_SAMPLE_RATE};
        this._ratio = sampleRate / this._outRate;
        this._carry = new Float32Array(0);
        this._readPos = 0;
        this._outBuffer = [];
        this._chunkSize = ${TARGET_CHUNK_SAMPLES};
        this._rmsSumSq = 0;
        this._rmsCount = 0;
      }

      process(inputs) {
        const input = inputs[0];
        const channelData = input && input[0];
        if (!channelData || channelData.length === 0) return true;

        // Track RMS over the raw (pre-resample) samples for the level meter.
        for (let i = 0; i < channelData.length; i++) {
          this._rmsSumSq += channelData[i] * channelData[i];
        }
        this._rmsCount += channelData.length;

        // Append incoming samples to the carry buffer.
        const merged = new Float32Array(this._carry.length + channelData.length);
        merged.set(this._carry, 0);
        merged.set(channelData, this._carry.length);
        this._carry = merged;

        // Linear-interpolation resample, consuming as far as the carry buffer allows.
        while (true) {
          const i0 = Math.floor(this._readPos);
          const i1 = i0 + 1;
          if (i1 >= this._carry.length) break;
          const frac = this._readPos - i0;
          const sample = this._carry[i0] * (1 - frac) + this._carry[i1] * frac;
          const clamped = Math.max(-1, Math.min(1, sample));
          this._outBuffer.push(clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff);
          this._readPos += this._ratio;

          if (this._outBuffer.length >= this._chunkSize) {
            const int16 = new Int16Array(this._outBuffer.splice(0, this._chunkSize));
            const rms = this._rmsCount > 0 ? Math.sqrt(this._rmsSumSq / this._rmsCount) : 0;
            this._rmsSumSq = 0;
            this._rmsCount = 0;
            this.port.postMessage({ pcm: int16.buffer, rms }, [int16.buffer]);
          }
        }

        // Trim the fully-consumed prefix so the carry buffer doesn't grow forever.
        const consumedWhole = Math.floor(this._readPos);
        if (consumedWhole > 0) {
          this._carry = this._carry.slice(consumedWhole);
          this._readPos -= consumedWhole;
        }

        return true;
      }
    }
    registerProcessor('pcm-downsampler', PCMDownsamplerProcessor);
  `;

  // Mirrors the worklet's resampling logic, for the ScriptProcessorNode fallback
  // which runs on the main thread and can call straight into app code.
  class MainThreadResampler {
    constructor(inRate, outRate, chunkSize) {
      this.ratio = inRate / outRate;
      this.chunkSize = chunkSize;
      this.carry = new Float32Array(0);
      this.readPos = 0;
      this.outBuffer = [];
    }

    // Returns { chunks: Int16Array[], rms: number } for the samples pushed in.
    push(channelData) {
      let sumSq = 0;
      for (let i = 0; i < channelData.length; i++) sumSq += channelData[i] * channelData[i];
      const rms = channelData.length > 0 ? Math.sqrt(sumSq / channelData.length) : 0;

      const merged = new Float32Array(this.carry.length + channelData.length);
      merged.set(this.carry, 0);
      merged.set(channelData, this.carry.length);
      this.carry = merged;

      const chunks = [];
      while (true) {
        const i0 = Math.floor(this.readPos);
        const i1 = i0 + 1;
        if (i1 >= this.carry.length) break;
        const frac = this.readPos - i0;
        const sample = this.carry[i0] * (1 - frac) + this.carry[i1] * frac;
        const clamped = Math.max(-1, Math.min(1, sample));
        this.outBuffer.push(clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff);
        this.readPos += this.ratio;

        if (this.outBuffer.length >= this.chunkSize) {
          chunks.push(new Int16Array(this.outBuffer.splice(0, this.chunkSize)));
        }
      }

      const consumedWhole = Math.floor(this.readPos);
      if (consumedWhole > 0) {
        this.carry = this.carry.slice(consumedWhole);
        this.readPos -= consumedWhole;
      }

      return { chunks, rms };
    }
  }

  async function startCapture() {
    if (App.isListening) return;
    ensurePlaybackGraph(); // unlock audio output while we still have the click gesture
    if (CLOUD) cloudConnect();

    const constraints = {
      audio: {
        echoCancellation: App.settings.echoCancellation,
        noiseSuppression: App.settings.noiseSuppression,
        autoGainControl: App.settings.autoGainControl,
        channelCount: 1,
      },
    };
    if (App.settings.micId) constraints.audio.deviceId = { exact: App.settings.micId };

    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia(constraints);
    } catch (err) {
      showToast(`Could not access microphone: ${err.message || err}`);
      return;
    }

    App.mediaStream = stream;
    const AudioContextCtor = window.AudioContext || window.webkitAudioContext;
    App.audioContext = new AudioContextCtor();
    App.sourceNode = App.audioContext.createMediaStreamSource(stream);

    // Silent sink: keeps the processing graph active without looping mic audio to speakers.
    App.silentGain = App.audioContext.createGain();
    App.silentGain.gain.value = 0;

    const usedWorklet = await tryStartWorklet();
    if (!usedWorklet) startScriptProcessorFallback();

    App.isListening = true;
    updateStartStopUI();
    refreshDeviceLabelsAfterPermission();
  }

  async function tryStartWorklet() {
    if (!App.audioContext.audioWorklet) return false;
    try {
      const blob = new Blob([WORKLET_SOURCE], { type: "application/javascript" });
      const url = URL.createObjectURL(blob);
      try {
        await App.audioContext.audioWorklet.addModule(url);
      } finally {
        URL.revokeObjectURL(url);
      }
      App.workletNode = new AudioWorkletNode(App.audioContext, "pcm-downsampler", {
        numberOfInputs: 1,
        numberOfOutputs: 1,
        channelCount: 1,
        channelCountMode: "explicit",
      });
      App.workletNode.port.onmessage = (event) => {
        const { pcm, rms } = event.data;
        setLevelBar(rms);
        if (App.isListening) wsSend(pcm);
      };
      App.sourceNode.connect(App.workletNode);
      App.workletNode.connect(App.silentGain);
      App.silentGain.connect(App.audioContext.destination);
      return true;
    } catch (err) {
      return false;
    }
  }

  function startScriptProcessorFallback() {
    const ctor = App.audioContext.createScriptProcessor
      ? "createScriptProcessor"
      : "createJavaScriptNode"; // ancient Safari/WebKit name
    if (!App.audioContext[ctor]) {
      showToast("This browser cannot capture microphone audio (no AudioWorklet or ScriptProcessor support).");
      return;
    }
    App.resampler = new MainThreadResampler(App.audioContext.sampleRate, TARGET_SAMPLE_RATE, TARGET_CHUNK_SAMPLES);
    App.scriptNode = App.audioContext[ctor](4096, 1, 1);
    App.scriptNode.onaudioprocess = (event) => {
      const input = event.inputBuffer.getChannelData(0);
      const { chunks, rms } = App.resampler.push(input);
      setLevelBar(rms);
      if (App.isListening) {
        for (const chunk of chunks) wsSend(chunk.buffer);
      }
    };
    App.sourceNode.connect(App.scriptNode);
    App.scriptNode.connect(App.silentGain);
    App.silentGain.connect(App.audioContext.destination);
  }

  function stopCapture({ notifyServer = true } = {}) {
    if (!App.isListening && !App.mediaStream) return;
    App.isListening = false;
    if (CLOUD) cloudRelease(CLOUD_CLOSE_AFTER_STOP_MS);

    if (notifyServer) wsSend(JSON.stringify({ type: "stop" }));

    if (App.workletNode) {
      try {
        App.workletNode.port.onmessage = null;
        App.workletNode.disconnect();
      } catch (err) {
        /* noop */
      }
      App.workletNode = null;
    }
    if (App.scriptNode) {
      try {
        App.scriptNode.onaudioprocess = null;
        App.scriptNode.disconnect();
      } catch (err) {
        /* noop */
      }
      App.scriptNode = null;
    }
    if (App.silentGain) {
      try {
        App.silentGain.disconnect();
      } catch (err) {
        /* noop */
      }
      App.silentGain = null;
    }
    if (App.sourceNode) {
      try {
        App.sourceNode.disconnect();
      } catch (err) {
        /* noop */
      }
      App.sourceNode = null;
    }
    if (App.mediaStream) {
      App.mediaStream.getTracks().forEach((track) => track.stop());
      App.mediaStream = null;
    }
    if (App.audioContext) {
      App.audioContext.close().catch(() => {});
      App.audioContext = null;
    }
    App.resampler = null;

    setLevelBar(0);
    el.speechIndicator.dataset.speech = "false";
    updateStartStopUI();
  }

  function updateStartStopUI() {
    el.startStopBtn.setAttribute("aria-pressed", String(App.isListening));
    el.startStopIcon.textContent = App.isListening ? "■" : "▶";
    el.startStopLabel.textContent = App.isListening ? "Stop listening" : "Start listening";
    el.flushBtn.disabled = !App.isListening;
  }

  /* ------------------------------------------------------------------ *
   *  Device pickers (microphone input + audio output via setSinkId)
   * ------------------------------------------------------------------ */

  function supportsSetSinkId() {
    return typeof el.playbackAudio.setSinkId === "function";
  }

  async function refreshDeviceList() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.enumerateDevices) return;
    let devices;
    try {
      devices = await navigator.mediaDevices.enumerateDevices();
    } catch (err) {
      return;
    }

    const mics = devices.filter((d) => d.kind === "audioinput");
    populateSelect(
      el.micSelect,
      mics.map((d, i) => ({ value: d.deviceId, label: d.label || `Microphone ${i + 1}` }))
    );
    setSelectValueIfPresent(el.micSelect, App.settings.micId);
    if (!el.micSelect.value && mics[0]) el.micSelect.value = mics[0].deviceId;

    if (supportsSetSinkId()) {
      el.outputDeviceField.style.display = "";
      const outputs = devices.filter((d) => d.kind === "audiooutput");
      populateSelect(
        el.outputSelect,
        outputs.map((d, i) => ({ value: d.deviceId, label: d.label || `Speaker ${i + 1}` }))
      );
      setSelectValueIfPresent(el.outputSelect, App.settings.outputId);
      if (!el.outputSelect.value && outputs[0]) el.outputSelect.value = outputs[0].deviceId;
    } else {
      el.outputDeviceField.style.display = "none";
    }
  }

  function refreshDeviceLabelsAfterPermission() {
    // Device labels are blank until permission is granted; refresh once we have it.
    refreshDeviceList();
  }

  /* ------------------------------------------------------------------ *
   *  Consent / voice cloning gating
   * ------------------------------------------------------------------ */

  function updateCloneAvailability() {
    const engine = App.engines.get(el.engineSelect.value);
    const engineSupportsClone = !engine || engine.clones !== false;
    const canClone = App.settings.consent && engineSupportsClone;

    el.cloneToggle.disabled = !canClone;
    if (!canClone) {
      App.settings.clone = false;
      el.cloneToggle.checked = false;
    } else {
      el.cloneToggle.checked = !!App.settings.clone;
    }

    if (!App.settings.consent) {
      el.consentHint.textContent =
        "Voices are cloned only with the speaker's permission. Check the consent box above to enable voice cloning.";
    } else if (!engineSupportsClone) {
      el.consentHint.textContent = "The selected engine does not support voice cloning.";
    } else {
      el.consentHint.textContent = "Voice cloning is enabled with consent. Turn it off any time.";
    }
  }

  /* ------------------------------------------------------------------ *
   *  Toasts
   * ------------------------------------------------------------------ */

  function showToast(message) {
    const toast = document.createElement("div");
    toast.className = "toast";
    toast.setAttribute("role", "alert");

    const text = document.createElement("span");
    text.textContent = message;

    const closeBtn = document.createElement("button");
    closeBtn.type = "button";
    closeBtn.setAttribute("aria-label", "Dismiss");
    closeBtn.textContent = "✕";

    const remove = () => {
      if (toast.parentNode) toast.parentNode.removeChild(toast);
    };
    closeBtn.addEventListener("click", remove);

    toast.appendChild(text);
    toast.appendChild(closeBtn);
    el.toastContainer.appendChild(toast);
    setTimeout(remove, 6000);
  }

  /* ------------------------------------------------------------------ *
   *  Wire up UI event listeners
   * ------------------------------------------------------------------ */

  /* "Get ready": asks the server to start the GPU early (held at most ~75 s). One request per press, never
   * retried or sent automatically; the server enforces all limits. */
  function warmUp() {
    if (!CLOUD || App.isListening) return;
    el.warmBtn.disabled = true;
    fetch(`/warm?client=${encodeURIComponent(App.clientId)}`, { method: "POST" })
      .then((r) => r.json())
      .then((res) => {
        if (res.state === "warming" || res.state === "already") {
          el.warmBtn.dataset.state = "warming";
          let left = res.seconds || 75;
          el.warmHint.textContent = "Warming up the translator. Press Start when people begin talking.";
          clearInterval(App.warmTimer);
          App.warmTimer = setInterval(() => {
            left -= 1;
            if (left <= 0 || App.isListening) {
              clearInterval(App.warmTimer);
              el.warmBtn.dataset.state = "";
              el.warmBtn.disabled = false;
              el.warmHint.textContent = App.isListening ? "" : "Warm-up ended. Start may take about 30 s.";
            }
          }, 1000);
        } else {
          el.warmBtn.disabled = false;
          el.warmHint.textContent = res.state === "limited" ? `Warm-up not available: ${res.detail}.`
            : "Warm-up is switched off.";
        }
      })
      .catch(() => {
        el.warmBtn.disabled = false;
        el.warmHint.textContent = "Could not reach the server.";
      });
  }

  function bindEvents() {
    if (CLOUD) {
      el.warmBtn.hidden = false;
      el.warmBtn.addEventListener("click", warmUp);
    }
    el.startStopBtn.addEventListener("click", () => {
      if (App.isListening) {
        stopCapture();
      } else {
        // A fresh press of Start begins a new conversation: capture the next speaker's voice anew.
        // (Reconnects and mic switches call startCapture directly and keep the locked voice.)
        startCapture().then(() => {
          if (App.isListening) wsSend({ type: "reset_voice" });
        });
      }
    });

    el.flushBtn.addEventListener("click", () => {
      wsSend(JSON.stringify({ type: "flush" }));
    });

    el.clearBtn.addEventListener("click", clearTranscript);

    el.resetVoiceBtn.addEventListener("click", () => {
      wsSend({ type: "reset_voice" });
    });

    el.sourceLangSelect.addEventListener("change", () => {
      App.settings.sourceLang = el.sourceLangSelect.value;
      saveSettings();
      sendConfig();
    });

    el.targetLangSelect.addEventListener("change", () => {
      App.settings.targetLang = el.targetLangSelect.value;
      saveSettings();
      sendConfig();
    });

    el.engineSelect.addEventListener("change", () => {
      App.settings.engine = el.engineSelect.value;
      applyEngineTargetRestrictions();
      App.settings.targetLang = el.targetLangSelect.value;
      updateCloneAvailability();
      saveSettings();
      sendConfig();
    });

    el.micSelect.addEventListener("change", async () => {
      App.settings.micId = el.micSelect.value;
      saveSettings();
      if (App.isListening) {
        stopCapture({ notifyServer: false });
        await startCapture();
      }
    });

    el.outputSelect.addEventListener("change", async () => {
      App.settings.outputId = el.outputSelect.value;
      saveSettings();
      if (supportsSetSinkId()) {
        try {
          await el.playbackAudio.setSinkId(App.settings.outputId);
        } catch (err) {
          showToast(`Could not switch audio output: ${err.message || err}`);
        }
      }
    });

    el.volumeSlider.addEventListener("input", () => {
      App.settings.volume = Number(el.volumeSlider.value);
      if (App.settings.volume > 0) App.settings.muted = false;
      applyVolumeAndMute();
      saveSettings();
    });

    el.muteBtn.addEventListener("click", () => {
      App.settings.muted = !App.settings.muted;
      applyVolumeAndMute();
      saveSettings();
    });

    el.echoCancelToggle.addEventListener("change", () => {
      App.settings.echoCancellation = el.echoCancelToggle.checked;
      saveSettings();
    });
    el.noiseSuppressToggle.addEventListener("change", () => {
      App.settings.noiseSuppression = el.noiseSuppressToggle.checked;
      saveSettings();
    });
    el.autoGainToggle.addEventListener("change", () => {
      App.settings.autoGainControl = el.autoGainToggle.checked;
      saveSettings();
    });

    el.consentCheckbox.addEventListener("change", () => {
      App.settings.consent = el.consentCheckbox.checked;
      updateCloneAvailability();
      saveSettings();
      sendConfig();
    });

    el.cloneToggle.addEventListener("change", () => {
      App.settings.clone = el.cloneToggle.checked;
      saveSettings();
      sendConfig();
    });

    if (navigator.mediaDevices && navigator.mediaDevices.addEventListener) {
      navigator.mediaDevices.addEventListener("devicechange", refreshDeviceList);
    }

    window.addEventListener("beforeunload", () => {
      if (App.isListening) stopCapture();
    });
  }

  function clearTranscript() {
    App.segmentAudio.clear();
    App.playingCount.clear();
    App.segmentCards.clear();
    el.transcriptFeed.innerHTML = "";
    el.transcriptEmpty.style.display = "";
  }

  /* ------------------------------------------------------------------ *
   *  Apply persisted settings to the initial DOM state
   * ------------------------------------------------------------------ */

  function applyInitialSettingsToDom() {
    el.consentCheckbox.checked = !!App.settings.consent;
    el.echoCancelToggle.checked = !!App.settings.echoCancellation;
    el.noiseSuppressToggle.checked = !!App.settings.noiseSuppression;
    el.autoGainToggle.checked = !!App.settings.autoGainControl;
    el.volumeSlider.value = String(App.settings.volume);
    updateCloneAvailability();
    applyVolumeAndMute();

    if (!supportsSetSinkId()) {
      el.outputDeviceField.style.display = "none";
    }
  }

  /* ------------------------------------------------------------------ *
   *  Boot
   * ------------------------------------------------------------------ */

  function init() {
    cacheDom();
    applyInitialSettingsToDom();
    bindEvents();
    setConnState("connecting");
    el.pipelineStatus.dataset.state = "idle";
    el.pipelineStatusText.textContent = STATUS_LABELS.idle;
    refreshDeviceList();
    if (CLOUD) {
      setConnState("idle");                           // no GPU until the user presses Start
      document.addEventListener("visibilitychange", () => {
        clearTimeout(App.hiddenTimer);
        if (document.hidden) {
          App.hiddenTimer = setTimeout(() => {
            if (App.isListening) stopCapture();
            cloudRelease(0);
          }, CLOUD_HIDDEN_STOP_MS);
        }
      });
    } else {
      connectWebSocket();
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
