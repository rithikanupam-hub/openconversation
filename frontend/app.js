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
    engine: "chatterbox_turbo",
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
    prebuffer: 1.0,
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
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    return `${proto}//${location.host}/ws`;
  }

  function connectWebSocket() {
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
      setConnState("closed");
      scheduleReconnect();
    });

    socket.addEventListener("error", () => {
      // onclose fires right after in browsers; nothing else to do here.
    });
  }

  function scheduleReconnect() {
    if (App.wsReconnectTimer) return;
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
    };
    el.connStateText.textContent = labels[state] || state;
  }

  function wsSend(payload) {
    if (App.ws && App.ws.readyState === WebSocket.OPEN) {
      App.ws.send(payload);
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
      case "error":
        showToast(msg.message || "Unknown error");
        break;
      default:
        break;
    }
  }

  function handleHello(msg) {
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
    const bytes = base64ToBytes(msg.wav_base64);
    App.decodeChain = App.decodeChain
      .then(() => ctx.decodeAudioData(bytes.buffer))
      .then((buffer) => {
        if (!App.segmentAudio.has(msg.id)) App.segmentAudio.set(msg.id, []);
        App.segmentAudio.get(msg.id)[msg.part || 0] = buffer;
        schedulePart(msg.id, buffer, { live: true });
      })
      .catch((err) => console.warn("[LingoSync] audio decode failed", err));
  }

  function handleVoice(msg) {
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
    }
    // Both need a user gesture the first time; startCapture/replay provide one.
    if (App.playCtx.state === "suspended") App.playCtx.resume().catch(() => {});
    if (supportsSetSinkId() && el.playbackAudio.paused) el.playbackAudio.play().catch(() => {});
    return App.playCtx;
  }

  const PREBUFFER_MIN = 0.5;
  const PREBUFFER_MAX = 3.0;

  function schedulePart(id, buffer, { live = false } = {}) {
    const ctx = App.playCtx;
    const src = ctx.createBufferSource();
    src.buffer = buffer;
    src.connect(App.playDest);
    const now = ctx.currentTime;
    const newUtterance = id !== App.lastScheduledId;
    let startAt;
    if (live && newUtterance) {
      // Hold the first part back so later parts arrive before they are needed.
      startAt = Math.max(now + App.prebuffer, App.playHead);
      App.prebuffer = Math.max(PREBUFFER_MIN, App.prebuffer - 0.1);
    } else {
      if (live && now > App.playHead) {
        // The previous part ran out before this one arrived: an audible gap. Buffer more next time.
        App.prebuffer = Math.min(PREBUFFER_MAX, App.prebuffer + (now - App.playHead) + 0.2);
      }
      // A small lead keeps a part from starting in the past while the graph wakes up.
      startAt = Math.max(now + 0.03, App.playHead);
    }
    if (live) App.lastScheduledId = id; // replays do not count as a new live utterance
    src.start(startAt);
    App.playHead = startAt + buffer.duration;

    App.playingCount.set(id, (App.playingCount.get(id) || 0) + 1);
    const delayMs = Math.max(0, (startAt - ctx.currentTime) * 1000);
    setTimeout(() => setCardPlaying(id, true), delayMs);
    src.onended = () => {
      const left = (App.playingCount.get(id) || 1) - 1;
      App.playingCount.set(id, left);
      if (left <= 0) setCardPlaying(id, false);
    };
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

  function bindEvents() {
    el.startStopBtn.addEventListener("click", () => {
      if (App.isListening) {
        stopCapture();
      } else {
        startCapture();
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
    connectWebSocket();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
