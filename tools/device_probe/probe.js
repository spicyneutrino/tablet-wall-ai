/*
 * Tablet wall device probe.
 *
 * Standalone page: no build step, no imports, no application code. It plays a
 * burned-in frame/time fixture and writes bounded evidence to sessionStorage
 * and localStorage before suspension and across reload. A page that is killed
 * leaves an unobserved interval; this page never invents a cause for it.
 */
(function () {
  "use strict";

  const CONTRACT = JSON.parse(document.getElementById("probe-contract").textContent);
  const LIMITS = CONTRACT.limits;
  const PREFIX = "tw-device-probe:v1:";
  const params = new URLSearchParams(window.location.search);
  const runId = cleanId(params.get("run") || "default");
  const sourceParam = params.get("src") || "";
  const autoplayRequested = params.get("autoplay") === "1";
  const loopRequested = params.get("loop") === "1";
  const keys = {
    ledger: PREFIX + runId + ":ledger",
    last: PREFIX + runId + ":last",
    session: PREFIX + runId + ":session"
  };

  const video = document.getElementById("video");
  const elements = {
    pageLine: document.getElementById("page-line"),
    play: document.getElementById("play"),
    pause: document.getElementById("pause"),
    loop: document.getElementById("loop"),
    mute: document.getElementById("mute"),
    wakeLock: document.getElementById("wake-lock"),
    fullscreen: document.getElementById("fullscreen"),
    download: document.getElementById("download"),
    reset: document.getElementById("reset"),
    seek: document.getElementById("seek"),
    seekValue: document.getElementById("seek-value"),
    markerLabel: document.getElementById("marker-label"),
    markButton: document.getElementById("mark-button"),
    time: document.getElementById("readout-time"),
    ready: document.getElementById("readout-ready"),
    frames: document.getElementById("readout-frames"),
    dropped: document.getElementById("readout-dropped"),
    gap: document.getElementById("readout-gap"),
    visibility: document.getElementById("readout-visibility"),
    wake: document.getElementById("readout-wake"),
    fullscreenState: document.getElementById("readout-fullscreen"),
    sequence: document.getElementById("readout-sequence"),
    source: document.getElementById("readout-source"),
    support: document.getElementById("support-line"),
    log: document.getElementById("log")
  };

  function cleanId(value) {
    const text = String(value || "").trim().replace(/[^A-Za-z0-9._-]/g, "_").slice(0, 80);
    return text || "default";
  }

  function nowWall() {
    return Date.now();
  }

  function nowMono() {
    return performance.now();
  }

  function numberOrNull(value) {
    return typeof value === "number" && Number.isFinite(value) ? value : null;
  }

  function round(value, digits) {
    const number = typeof value === "number" ? value : Number(value);
    if (!Number.isFinite(number)) return null;
    return Number(number.toFixed(digits === undefined ? 3 : digits));
  }

  function iso(ms) {
    return new Date(ms).toISOString();
  }

  function errorInfo(error) {
    if (!error) return null;
    return {
      name: error.name || "Error",
      message: String(error.message || error),
      stack: typeof error.stack === "string" ? error.stack.slice(0, 1200) : null
    };
  }

  function uuid() {
    if (window.crypto && typeof window.crypto.randomUUID === "function") {
      return window.crypto.randomUUID();
    }
    const bytes = new Uint8Array(16);
    if (window.crypto && window.crypto.getRandomValues) window.crypto.getRandomValues(bytes);
    else for (let i = 0; i < bytes.length; i += 1) bytes[i] = Math.floor(Math.random() * 256);
    bytes[6] = (bytes[6] & 15) | 64;
    bytes[8] = (bytes[8] & 63) | 128;
    const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
    return hex.slice(0, 8) + "-" + hex.slice(8, 12) + "-" + hex.slice(12, 16) + "-" +
      hex.slice(16, 20) + "-" + hex.slice(20);
  }

  function supports(fn) {
    return typeof fn === "function";
  }

  function apiSupport() {
    return {
      requestVideoFrameCallback: supports(video.requestVideoFrameCallback),
      wakeLock: !!(navigator.wakeLock && typeof navigator.wakeLock.request === "function"),
      fullscreen: !!(document.fullscreenEnabled && supports(document.documentElement.requestFullscreen)),
      getVideoPlaybackQuality: supports(video.getVideoPlaybackQuality),
      playbackQuality: "playbackQuality" in video,
      deviceMemory: typeof navigator.deviceMemory === "number",
      screenOrientation: !!(window.screen && screen.orientation && typeof screen.orientation.type === "string")
    };
  }

  const CAPS = apiSupport();
  const codecSupport = (function () {
    const media = {
      mp4_h264_baseline: 'video/mp4; codecs="avc1.42E01E"',
      mp4_h264_main: 'video/mp4; codecs="avc1.4D401E"',
      mp4_h264_high: 'video/mp4; codecs="avc1.64001F"',
      mp4_container: "video/mp4",
      webm_vp9: 'video/webm; codecs="vp9"',
      webm_vp8: 'video/webm; codecs="vp8"'
    };
    const output = {};
    Object.keys(media).forEach(function (name) {
      let answer = "";
      try {
        answer = video.canPlayType(media[name]) || "";
      } catch (error) {
        answer = "";
      }
      output[name] = { mime: media[name], can_play_type: answer };
    });
    output.media_source = null;
    try {
      if (window.MediaSource && typeof window.MediaSource.isTypeSupported === "function") {
        output.media_source = {
          mp4_h264: window.MediaSource.isTypeSupported(media.mp4_h264_baseline),
          mp4_container: window.MediaSource.isTypeSupported(media.mp4_container)
        };
      }
    } catch (error) {
      output.media_source = { error: errorInfo(error) };
    }
    return output;
  })();

  const storageState = {
    session: { available: true, writes: 0, errors: 0, last_error: null },
    local: { available: true, writes: 0, errors: 0, last_error: null }
  };

  const state = {
    initialized: false,
    storageDisabled: false,
    instanceId: uuid(),
    runId: runId,
    sequence: 1,
    previousInstanceId: null,
    originInstanceId: null,
    startedAt: nowWall(),
    startedMono: nowMono(),
    sessionStoragePresent: false,
    persistedPageshow: false,
    previousSummary: null,
    ledger: null,
    events: [],
    samples: [],
    frameRows: [],
    gaps: [],
    markers: [],
    actions: [],
    lifecycle: [],
    playAttempts: [],
    trimmed: {
      events: 0,
      samples: 0,
      frame_callbacks: 0,
      markers: 0,
      gaps: 0,
      lifecycle: 0,
      actions: 0,
      play_attempts: 0
    },
    flushes: 0,
    lastFlush: null,
    lastCallback: null,
    gapNotice: false,
    frameCallbackPending: false,
    frameCallbackId: null,
    lastDropped: null,
    media: {
      loaded: false,
      duration: null,
      video_width: null,
      video_height: null,
      loaded_at: null
    },
    wakeLock: {
      state: CAPS.wakeLock ? "not-requested" : "unsupported",
      sentinel: null,
      requests: [],
      changes: [],
      last_error: null
    },
    fullscreen: {
      state: CAPS.fullscreen ? "not-requested" : "unsupported",
      requests: [],
      changes: [],
      last_error: null
    },
    counters: {
      frameCallbacks: 0,
      lastPresentedFrames: null,
      lastQuality: null,
      lastSampleAt: null
    }
  };

  function readJSON(storage, key, area) {
    try {
      const raw = storage.getItem(key);
      if (!raw) return { value: null, error: null };
      return { value: JSON.parse(raw), error: null };
    } catch (error) {
      const detail = errorInfo(error);
      storageState[area].last_error = detail;
      storageState[area].available = false;
      return { value: null, error: detail };
    }
  }

  function writeJSON(storage, key, value, area) {
    try {
      storage.setItem(key, JSON.stringify(value));
      storageState[area].writes += 1;
      storageState[area].available = true;
      return true;
    } catch (error) {
      storageState[area].errors += 1;
      storageState[area].available = false;
      storageState[area].last_error = errorInfo(error);
      return false;
    }
  }

  function pushBounded(array, item, limit, trimKey) {
    array.push(item);
    const overflow = array.length - limit;
    if (overflow > 0) {
      array.splice(0, overflow);
      state.trimmed[trimKey] = (state.trimmed[trimKey] || 0) + overflow;
    }
  }

  function pushCapped(array, item, limit) {
    array.push(item);
    if (array.length > limit) array.splice(0, array.length - limit);
  }

  function addLifecycle(kind, detail) {
    pushBounded(state.lifecycle, {
      kind: kind,
      detail: detail === undefined ? null : detail,
      at: nowWall(),
      mono: round(nowMono(), 3),
      current_time: round(video.currentTime),
      visibility: document.visibilityState,
      page_instance_id: state.instanceId
    }, LIMITS.lifecycle, "lifecycle");
  }

  function logAction(kind, detail) {
    pushBounded(state.actions, {
      kind: kind,
      detail: detail === undefined ? null : detail,
      at: nowWall(),
      mono: round(nowMono(), 3),
      current_time: round(video.currentTime),
      paused: video.paused,
      loop: video.loop,
      muted: video.muted,
      page_instance_id: state.instanceId
    }, LIMITS.actions, "actions");
  }

  function summarizePrior(raw) {
    if (!raw || typeof raw !== "object") return null;
    return {
      instance_id: raw.instance_id || null,
      sequence: raw.sequence || null,
      started_at: raw.started_at || null,
      last_seen_at: raw.last_seen_at || null,
      media_events: Array.isArray(raw.media_events) ? raw.media_events.slice(-LIMITS.summary_events) : [],
      samples: Array.isArray(raw.samples) ? raw.samples.slice(-LIMITS.summary_samples) : [],
      markers: Array.isArray(raw.markers) ? raw.markers.slice(-20) : [],
      counters: raw.counters || null,
      source: raw.source || null,
      trimmed: raw.trimmed || null
    };
  }

  function initLineage() {
    const ledgerRead = readJSON(localStorage, keys.ledger, "local");
    const sessionRead = readJSON(sessionStorage, keys.session, "session");
    state.sessionStoragePresent = !!sessionRead.value;

    let ledger = ledgerRead.value;
    if (!ledger || typeof ledger !== "object" || !Array.isArray(ledger.sessions)) {
      ledger = {
        schema: CONTRACT.schema,
        run_id: runId,
        created_at: state.startedAt,
        origin_instance_id: state.instanceId,
        next_sequence: 1,
        sessions: [],
        gaps: [],
        gaps_trimmed: 0
      };
    }
    if (!Array.isArray(ledger.gaps)) ledger.gaps = [];

    const previousSession = ledger.sessions.length
      ? ledger.sessions[ledger.sessions.length - 1]
      : null;
    const next = Number(ledger.next_sequence);
    state.sequence = Number.isFinite(next) && next > 0
      ? next
      : ledger.sessions.length + 1;
    state.previousInstanceId = previousSession ? previousSession.instance_id || null : null;
    state.originInstanceId = ledger.origin_instance_id || (previousSession && previousSession.instance_id) || state.instanceId;

    const lastRead = readJSON(localStorage, keys.last, "local");
    const priorRaw = (lastRead.value && lastRead.value.instance_id !== state.instanceId)
      ? lastRead.value
      : (sessionRead.value && sessionRead.value.instance_id !== state.instanceId ? sessionRead.value : null);
    if (priorRaw) state.previousSummary = summarizePrior(priorRaw);

    const priorLastSeen = priorRaw && priorRaw.last_seen_at
      ? Number(priorRaw.last_seen_at)
      : (previousSession && previousSession.last_seen_at ? Number(previousSession.last_seen_at) : null);

    if (priorLastSeen && Number.isFinite(priorLastSeen) && state.startedAt >= priorLastSeen) {
      const gap = {
        from_instance_id: (priorRaw && priorRaw.instance_id) || (previousSession && previousSession.instance_id) || null,
        to_instance_id: state.instanceId,
        from_last_seen_at: priorLastSeen,
        to_started_at: state.startedAt,
        wall_gap_ms: state.startedAt - priorLastSeen,
        observation: "unobserved",
        cause: null,
        note: "No page context was observed between these timestamps. The page does not infer reload, suspension, low-memory termination or decoder freeze."
      };
      ledger.gaps.push(gap);
      if (ledger.gaps.length > LIMITS.lineage_gaps) {
        const overflow = ledger.gaps.length - LIMITS.lineage_gaps;
        ledger.gaps.splice(0, overflow);
        ledger.gaps_trimmed = (ledger.gaps_trimmed || 0) + overflow;
      }
    }

    ledger.next_sequence = state.sequence + 1;
    ledger.sessions.push({
      instance_id: state.instanceId,
      sequence: state.sequence,
      started_at: state.startedAt,
      last_seen_at: state.startedAt,
      source_name: params.get("source_name") || null,
      user_agent: String(navigator.userAgent || "").slice(0, 200)
    });
    if (ledger.sessions.length > LIMITS.ledger_sessions) {
      ledger.sessions.splice(0, ledger.sessions.length - LIMITS.ledger_sessions);
    }
    state.ledger = ledger;
    writeJSON(localStorage, keys.ledger, ledger, "local");
    addLifecycle("probe-init", {
      sequence: state.sequence,
      previous_instance_id: state.previousInstanceId,
      session_storage_present: state.sessionStoragePresent
    });
  }

  function bufferedRanges() {
    const output = [];
    try {
      const ranges = video.buffered;
      for (let i = 0; i < ranges.length && i < 8; i += 1) {
        output.push({ start: round(ranges.start(i), 3), end: round(ranges.end(i), 3) });
      }
      return { ranges: output, count: ranges.length };
    } catch (error) {
      return { ranges: [], count: 0, error: errorInfo(error) };
    }
  }

  function seekableRanges() {
    const output = [];
    try {
      const ranges = video.seekable;
      for (let i = 0; i < ranges.length && i < 8; i += 1) {
        output.push({ start: round(ranges.start(i), 3), end: round(ranges.end(i), 3) });
      }
      return { ranges: output, count: ranges.length };
    } catch (error) {
      return { ranges: [], count: 0, error: errorInfo(error) };
    }
  }

  function playedRanges() {
    const output = [];
    try {
      const ranges = video.played;
      for (let i = 0; i < ranges.length && i < 8; i += 1) {
        output.push({ start: round(ranges.start(i), 3), end: round(ranges.end(i), 3) });
      }
      return { ranges: output, count: ranges.length };
    } catch (error) {
      return { ranges: [], count: 0, error: errorInfo(error) };
    }
  }

  function qualitySnapshot() {
    const output = {
      playback_quality: null,
      get_video_playback_quality: null,
      webkit_decoded_frames: numberOrNull(video.webkitDecodedFrameCount),
      webkit_dropped_frames: numberOrNull(video.webkitDroppedFrameCount),
      error: null
    };
    function pick(quality) {
      if (!quality || typeof quality !== "object") return null;
      return {
        creation_time: numberOrNull(quality.creationTime),
        total_video_frames: numberOrNull(quality.totalVideoFrames),
        dropped_video_frames: numberOrNull(quality.droppedVideoFrames),
        corrupted_video_frames: numberOrNull(quality.corruptedVideoFrames),
        displayed_video_frames: numberOrNull(quality.displayedVideoFrames)
      };
    }
    try {
      if (video.playbackQuality) output.playback_quality = pick(video.playbackQuality);
      if (supports(video.getVideoPlaybackQuality)) {
        output.get_video_playback_quality = pick(video.getVideoPlaybackQuality());
      }
    } catch (error) {
      output.error = errorInfo(error);
    }
    return output;
  }

  function mediaEventRow(name) {
    return {
      name: name,
      at: nowWall(),
      mono: round(nowMono(), 3),
      current_time: round(video.currentTime, 6),
      duration: numberOrNull(video.duration),
      ready_state: video.readyState,
      network_state: video.networkState,
      paused: video.paused,
      ended: video.ended,
      seeking: video.seeking,
      muted: video.muted,
      volume: round(video.volume),
      playback_rate: round(video.playbackRate),
      buffered: bufferedRanges(),
      error: video.error ? { code: video.error.code, message: String(video.error.message || "") } : null
    };
  }

  function updateMediaMetadata() {
    state.media.loaded = true;
    state.media.duration = numberOrNull(video.duration);
    state.media.video_width = video.videoWidth || null;
    state.media.video_height = video.videoHeight || null;
    state.media.loaded_at = nowWall();
    if (state.media.duration !== null) {
      elements.seek.max = String(Math.max(0.1, state.media.duration));
    }
  }

  function resetFrameBaseline() {
    state.lastCallback = null;
    state.gapNotice = false;
  }

  function recordGap(source, wallGapMs, mediaGapMs, presentedDelta) {
    pushBounded(state.gaps, {
      at: nowWall(),
      mono: round(nowMono(), 3),
      source: source,
      wall_gap_ms: round(wallGapMs, 3),
      media_gap_ms: round(mediaGapMs, 6),
      presented_delta: presentedDelta === undefined ? null : presentedDelta,
      current_time: round(video.currentTime, 6),
      ready_state: video.readyState,
      visibility: document.visibilityState,
      paused: video.paused,
      note: "Observed interval without a frame callback or sample. Cause is not recorded."
    }, LIMITS.gaps, "gaps");
  }

  function onFrame(now, metadata) {
    state.frameCallbackPending = false;
    if (!metadata || typeof metadata !== "object") return;
    const wall = nowWall();
    const previous = state.lastCallback;
    const wallGap = previous ? now - previous.mono : null;
    const mediaGap = previous ? metadata.mediaTime - previous.media_time : null;
    const presentedDelta = (previous && numberOrNull(metadata.presentedFrames) !== null &&
      numberOrNull(previous.presented_frames) !== null)
      ? metadata.presentedFrames - previous.presented_frames
      : null;
    const playing = !video.paused && !video.ended;
    const row = {
      at: wall,
      mono: round(now, 3),
      media_time: round(metadata.mediaTime, 6),
      presented_frames: numberOrNull(metadata.presentedFrames),
      expected_display_time: numberOrNull(metadata.expectedDisplayTime),
      width: numberOrNull(metadata.width),
      height: numberOrNull(metadata.height),
      processing_duration: numberOrNull(metadata.processingDuration),
      presentation_time: numberOrNull(metadata.presentationTime),
      capture_time: numberOrNull(metadata.captureTime),
      metadata: {
        mediaTime: numberOrNull(metadata.mediaTime),
        presentedFrames: numberOrNull(metadata.presentedFrames),
        expectedDisplayTime: numberOrNull(metadata.expectedDisplayTime),
        width: numberOrNull(metadata.width),
        height: numberOrNull(metadata.height),
        processingDuration: numberOrNull(metadata.processingDuration),
        presentationTime: numberOrNull(metadata.presentationTime),
        captureTime: numberOrNull(metadata.captureTime)
      },
      wall_gap_ms: wallGap === null ? null : round(wallGap, 3),
      media_gap_ms: mediaGap === null ? null : round(mediaGap, 6),
      presented_delta: presentedDelta,
      current_time: round(video.currentTime, 6),
      ready_state: video.readyState,
      paused: video.paused,
      ended: video.ended,
      visibility: document.visibilityState
    };
    pushBounded(state.frameRows, row, LIMITS.frame_callbacks, "frame_callbacks");
    state.counters.frameCallbacks += 1;
    if (row.presented_frames !== null) state.counters.lastPresentedFrames = row.presented_frames;
    if (previous && previous.playing && playing && document.visibilityState === "visible" &&
      wallGap !== null && wallGap > CONTRACT.gap_threshold_ms) {
      recordGap("callback", wallGap, mediaGap, presentedDelta);
    }
    state.gapNotice = false;
    state.lastCallback = {
      mono: now,
      media_time: metadata.mediaTime,
      presented_frames: numberOrNull(metadata.presentedFrames),
      playing: playing,
      at: wall
    };
    if (playing) scheduleFrameCallback();
  }

  function scheduleFrameCallback() {
    if (!CAPS.requestVideoFrameCallback || state.frameCallbackPending) return;
    state.frameCallbackPending = true;
    try {
      state.frameCallbackId = video.requestVideoFrameCallback(function (now, metadata) {
        state.frameCallbackId = null;
        onFrame(now, metadata);
      });
    } catch (error) {
      state.frameCallbackPending = false;
      state.frameCallbackId = null;
      addLifecycle("frame-callback-error", errorInfo(error));
    }
  }

  function restartFrameCallback() {
    if (!CAPS.requestVideoFrameCallback) return;
    if (state.frameCallbackId !== null) {
      if (typeof video.cancelVideoFrameCallback !== "function") return;
      try {
        video.cancelVideoFrameCallback(state.frameCallbackId);
      } catch (error) {
        addLifecycle("frame-callback-cancel-error", errorInfo(error));
      }
      state.frameCallbackId = null;
      state.frameCallbackPending = false;
    }
    scheduleFrameCallback();
  }

  function sample(trigger) {
    const quality = qualitySnapshot();
    const getQuality = quality.get_video_playback_quality;
    const dropped = getQuality && getQuality.dropped_video_frames !== null
      ? getQuality.dropped_video_frames
      : (quality.webkit_dropped_frames !== null ? quality.webkit_dropped_frames : null);
    let droppedDelta = null;
    if (dropped !== null && state.lastDropped !== null) droppedDelta = dropped - state.lastDropped;
    state.lastDropped = dropped;
    const row = {
      at: nowWall(),
      mono: round(nowMono(), 3),
      trigger: trigger || "interval",
      current_time: round(video.currentTime, 6),
      duration: numberOrNull(video.duration),
      ready_state: video.readyState,
      network_state: video.networkState,
      paused: video.paused,
      ended: video.ended,
      seeking: video.seeking,
      muted: video.muted,
      loop: video.loop,
      playback_rate: round(video.playbackRate),
      video_width: video.videoWidth || null,
      video_height: video.videoHeight || null,
      buffered: bufferedRanges(),
      seekable: seekableRanges(),
      played: playedRanges(),
      dropped_video_frames: dropped,
      dropped_frames_delta: droppedDelta,
      total_video_frames: getQuality ? getQuality.total_video_frames : null,
      corrupted_video_frames: getQuality ? getQuality.corrupted_video_frames : null,
      frames_presented: state.counters.lastPresentedFrames,
      frame_callbacks: state.counters.frameCallbacks,
      last_callback_media_time: state.lastCallback ? round(state.lastCallback.media_time, 6) : null,
      visibility: document.visibilityState,
      wake_lock: state.wakeLock.state,
      fullscreen: !!document.fullscreenElement,
      playback_quality: quality.playback_quality,
      get_video_playback_quality: getQuality
    };
    pushBounded(state.samples, row, LIMITS.samples, "samples");
    state.counters.lastQuality = quality;
    state.counters.lastSampleAt = row.at;

    const last = state.lastCallback;
    if (last && last.playing && !video.paused && !video.ended &&
      document.visibilityState === "visible") {
      const wallGap = nowMono() - last.mono;
      if (wallGap > CONTRACT.gap_threshold_ms && !state.gapNotice) {
        recordGap("sampler", wallGap, row.current_time - last.media_time, null);
        state.gapNotice = true;
      }
    } else if (video.paused || video.ended || document.visibilityState !== "visible") {
      state.gapNotice = false;
    }
    updateUI();
  }

  function countersSnapshot() {
    const quality = state.counters.lastQuality || {};
    const getQuality = quality.get_video_playback_quality || null;
    return {
      frame_callbacks: state.counters.frameCallbacks,
      presented_frames: state.counters.lastPresentedFrames,
      dropped_video_frames: getQuality ? getQuality.dropped_video_frames : null,
      total_video_frames: getQuality ? getQuality.total_video_frames : null,
      corrupted_video_frames: getQuality ? getQuality.corrupted_video_frames : null,
      webkit_decoded_frames: numberOrNull(video.webkitDecodedFrameCount),
      webkit_dropped_frames: numberOrNull(video.webkitDroppedFrameCount),
      playback_quality: quality.playback_quality || null,
      get_video_playback_quality: getQuality,
      callback_gap_count: state.gaps.length,
      samples: state.samples.length,
      events: state.events.length,
      last_sample_at: state.counters.lastSampleAt
    };
  }

  function viewportSnapshot() {
    const visual = window.visualViewport;
    return {
      inner_width: window.innerWidth,
      inner_height: window.innerHeight,
      outer_width: window.outerWidth,
      outer_height: window.outerHeight,
      client_width: document.documentElement.clientWidth,
      client_height: document.documentElement.clientHeight,
      screen_width: screen.width,
      screen_height: screen.height,
      avail_width: screen.availWidth,
      avail_height: screen.availHeight,
      color_depth: screen.colorDepth,
      visual_width: visual ? round(visual.width, 2) : null,
      visual_height: visual ? round(visual.height, 2) : null,
      visual_scale: visual ? round(visual.scale, 4) : null,
      visual_offset_left: visual ? round(visual.offsetLeft, 2) : null,
      visual_offset_top: visual ? round(visual.offsetTop, 2) : null
    };
  }

  function orientationSnapshot() {
    const orientation = screen.orientation;
    return {
      type: orientation && orientation.type ? orientation.type : null,
      angle: orientation && numberOrNull(orientation.angle) !== null ? orientation.angle : null,
      legacy_window_orientation: numberOrNull(window.orientation),
      portrait: window.matchMedia("(orientation: portrait)").matches,
      landscape: window.matchMedia("(orientation: landscape)").matches
    };
  }

  function displayModeSnapshot() {
    const modes = ["browser", "standalone", "minimal-ui", "fullscreen", "window-controls-overlay"];
    const output = {};
    modes.forEach(function (mode) {
      try {
        output[mode] = window.matchMedia("(display-mode: " + mode + ")").matches;
      } catch (error) {
        output[mode] = null;
      }
    });
    output.navigator_standalone = typeof navigator.standalone === "boolean"
      ? navigator.standalone
      : null;
    return output;
  }

  function wakeLockSnapshot() {
    return {
      api: CAPS.wakeLock,
      state: state.wakeLock.state,
      sentinel_active: !!state.wakeLock.sentinel,
      requests: state.wakeLock.requests.slice(-10),
      changes: state.wakeLock.changes.slice(-20),
      last_error: state.wakeLock.last_error
    };
  }

  function fullscreenSnapshot() {
    return {
      api: CAPS.fullscreen,
      enabled: !!document.fullscreenEnabled,
      active: !!document.fullscreenElement,
      element: document.fullscreenElement ? document.fullscreenElement.tagName : null,
      state: state.fullscreen.state,
      requests: state.fullscreen.requests.slice(-10),
      changes: state.fullscreen.changes.slice(-20),
      last_error: state.fullscreen.last_error
    };
  }

  function environmentSnapshot() {
    const userAgentData = navigator.userAgentData;
    return {
      user_agent: navigator.userAgent,
      app_version: navigator.appVersion,
      platform: userAgentData && userAgentData.platform ? userAgentData.platform : (navigator.platform || "unknown"),
      user_agent_data: userAgentData ? {
        brands: Array.isArray(userAgentData.brands) ? userAgentData.brands.slice(0, 8) : [],
        mobile: typeof userAgentData.mobile === "boolean" ? userAgentData.mobile : null,
        platform: userAgentData.platform || null
      } : null,
      language: navigator.language || null,
      languages: Array.isArray(navigator.languages) ? navigator.languages.slice(0, 8) : [],
      hardware_concurrency: numberOrNull(navigator.hardwareConcurrency),
      device_memory: numberOrNull(navigator.deviceMemory),
      max_touch_points: numberOrNull(navigator.maxTouchPoints),
      coarse_pointer: window.matchMedia("(pointer: coarse)").matches,
      viewport: viewportSnapshot(),
      device_pixel_ratio: round(window.devicePixelRatio, 4),
      orientation: orientationSnapshot(),
      display_mode: displayModeSnapshot(),
      visibility_state: document.visibilityState,
      codec_support: codecSupport,
      api_support: Object.assign({}, CAPS),
      wake_lock: wakeLockSnapshot(),
      fullscreen: fullscreenSnapshot(),
      secure_context: window.isSecureContext,
      time_origin_ms: round(performance.timeOrigin, 3)
    };
  }

  function sourceSnapshot() {
    const sizeValue = params.get("source_size");
    const size = sizeValue !== null && sizeValue !== "" && Number.isFinite(Number(sizeValue))
      ? Number(sizeValue)
      : null;
    return {
      src: video.currentSrc || video.getAttribute("src") || sourceParam || null,
      name: params.get("source_name") || null,
      size: size,
      sha256: params.get("source_sha256") || null,
      supplied: {
        name: params.has("source_name"),
        size: params.has("source_size"),
        hash: params.has("source_sha256")
      },
      media: state.media.loaded ? {
        duration: state.media.duration,
        video_width: state.media.video_width,
        video_height: state.media.video_height,
        loaded_at: state.media.loaded_at,
        buffered: bufferedRanges(),
        seekable: seekableRanges()
      } : null
    };
  }

  function pageSnapshot() {
    let navigation = { type: "unknown", reload: false, back_forward: false };
    try {
      const entries = performance.getEntriesByType ? performance.getEntriesByType("navigation") : [];
      if (entries && entries.length) {
        navigation = {
          type: entries[0].type || "unknown",
          reload: entries[0].type === "reload",
          back_forward: entries[0].type === "back_forward"
        };
      }
    } catch (error) {
      navigation.error = errorInfo(error);
    }
    return {
      instance_id: state.instanceId,
      run_id: state.runId,
      sequence: state.sequence,
      previous_instance_id: state.previousInstanceId,
      origin_instance_id: state.originInstanceId,
      started_at: state.startedAt,
      started_at_iso: iso(state.startedAt),
      started_monotonic_ms: round(state.startedMono, 3),
      time_origin_ms: round(performance.timeOrigin, 3),
      navigation: Object.assign(navigation, {
        persisted_pageshow: state.persistedPageshow,
        session_storage_present: state.sessionStoragePresent
      })
    };
  }

  function frameSnapshot() {
    const rows = state.frameRows.slice();
    const wallGaps = [];
    rows.forEach(function (row) {
      if (typeof row.wall_gap_ms === "number") wallGaps.push(row.wall_gap_ms);
    });
    wallGaps.sort(function (a, b) { return a - b; });
    const median = wallGaps.length
      ? wallGaps[Math.floor(wallGaps.length / 2)]
      : null;
    return {
      supported: CAPS.requestVideoFrameCallback,
      registered: state.frameCallbackPending || state.counters.frameCallbacks > 0,
      count: state.counters.frameCallbacks,
      rows: rows,
      first: rows.length ? rows[0] : null,
      last: rows.length ? rows[rows.length - 1] : null,
      gaps: state.gaps.slice(),
      gap_threshold_ms: CONTRACT.gap_threshold_ms,
      median_wall_gap_ms: median,
      max_wall_gap_ms: wallGaps.length ? wallGaps[wallGaps.length - 1] : null,
      rows_truncated: state.counters.frameCallbacks > rows.length,
      required_metadata: CONTRACT.required_frame_metadata,
      unavailable_reason: CAPS.requestVideoFrameCallback ? null : "requestVideoFrameCallback is not available"
    };
  }

  function lineageSnapshot() {
    return {
      run_id: state.runId,
      origin_instance_id: state.originInstanceId,
      sequence: state.sequence,
      previous_instance_id: state.previousInstanceId,
      sessions: state.ledger ? state.ledger.sessions.map(function (session) {
        return Object.assign({}, session);
      }) : [],
      gaps_trimmed: state.ledger ? (state.ledger.gaps_trimmed || 0) : 0,
      previous_summary: state.previousSummary,
      unexplained_gaps: state.ledger ? state.ledger.gaps.map(function (gap) {
        return Object.assign({}, gap);
      }) : [],
      note: "A gap is an interval with no observed page. Cause is not inferred: reload, bfcache restore, suspension and low-memory termination are not distinguishable from this log alone."
    };
  }

  function persistenceSnapshot() {
    return {
      keys: Object.assign({}, keys),
      limits: Object.assign({}, LIMITS),
      sample_interval_ms: CONTRACT.sample_interval_ms,
      session_storage: Object.assign({}, storageState.session),
      local_storage: Object.assign({}, storageState.local),
      trimmed: Object.assign({}, state.trimmed),
      flushes: state.flushes,
      last_flush: state.lastFlush,
      note: "Oldest rows are dropped at the contract limits; dropped counts stay in trimmed."
    };
  }

  function unavailableApis() {
    const unavailable = [];
    if (!CAPS.requestVideoFrameCallback) unavailable.push("HTMLVideoElement.requestVideoFrameCallback");
    if (!CAPS.wakeLock) unavailable.push("navigator.wakeLock");
    if (!CAPS.fullscreen) unavailable.push("Element.requestFullscreen");
    if (!CAPS.getVideoPlaybackQuality) unavailable.push("HTMLVideoElement.getVideoPlaybackQuality");
    if (!CAPS.playbackQuality) unavailable.push("HTMLVideoElement.playbackQuality");
    if (!CAPS.deviceMemory) unavailable.push("navigator.deviceMemory");
    if (!CAPS.screenOrientation) unavailable.push("screen.orientation");
    if (numberOrNull(video.webkitDecodedFrameCount) === null) unavailable.push("HTMLVideoElement.webkitDecodedFrameCount");
    if (numberOrNull(video.webkitDroppedFrameCount) === null) unavailable.push("HTMLVideoElement.webkitDroppedFrameCount");
    if (!storageState.session.available) unavailable.push("sessionStorage");
    if (!storageState.local.available) unavailable.push("localStorage");
    return unavailable;
  }

  function snapshot() {
    return {
      schema: CONTRACT.schema,
      probe_version: CONTRACT.probe_version,
      generated_at: iso(nowWall()),
      generated_wall_ms: nowWall(),
      generated_monotonic_ms: round(nowMono(), 3),
      page: pageSnapshot(),
      environment: environmentSnapshot(),
      source: sourceSnapshot(),
      play: {
        autoplay: autoplayRequested,
        attempts: state.playAttempts.slice(),
        last_outcome: state.playAttempts.length
          ? state.playAttempts[state.playAttempts.length - 1].outcome
          : "none"
      },
      counters: countersSnapshot(),
      media_events: state.events.slice(),
      samples: state.samples.slice(),
      frame_callbacks: frameSnapshot(),
      lifecycle: state.lifecycle.slice(),
      actions: state.actions.slice(),
      markers: state.markers.slice(),
      lineage: lineageSnapshot(),
      persistence: persistenceSnapshot(),
      unavailable: unavailableApis()
    };
  }

  function sessionState() {
    return {
      instance_id: state.instanceId,
      sequence: state.sequence,
      started_at: state.startedAt,
      last_seen_at: nowWall(),
      source: sourceSnapshot(),
      counters: countersSnapshot(),
      media_events: state.events.slice(),
      samples: state.samples.slice(),
      frame_callbacks: state.frameRows.slice(),
      gaps: state.gaps.slice(),
      markers: state.markers.slice(),
      actions: state.actions.slice(),
      lifecycle: state.lifecycle.slice(),
      play_attempts: state.playAttempts.slice(),
      trimmed: Object.assign({}, state.trimmed),
      user_agent: String(navigator.userAgent || "").slice(0, 200)
    };
  }

  function saveSession(trigger) {
    if (!state.initialized || state.storageDisabled) return;
    const session = sessionState();
    const sessionOk = writeJSON(sessionStorage, keys.session, session, "session");
    const summary = {
      instance_id: session.instance_id,
      sequence: session.sequence,
      started_at: session.started_at,
      last_seen_at: session.last_seen_at,
      source: session.source,
      counters: session.counters,
      media_events: session.media_events.slice(-LIMITS.summary_events),
      samples: session.samples.slice(-LIMITS.summary_samples),
      markers: session.markers.slice(-20),
      play_attempts: session.play_attempts.slice(-5),
      trimmed: session.trimmed,
      user_agent: session.user_agent
    };
    const localOk = writeJSON(localStorage, keys.last, summary, "local");
    if (state.ledger) {
      const sessions = state.ledger.sessions;
      if (sessions.length) sessions[sessions.length - 1].last_seen_at = session.last_seen_at;
      writeJSON(localStorage, keys.ledger, state.ledger, "local");
    }
    state.flushes += 1;
    state.lastFlush = {
      trigger: trigger,
      at: session.last_seen_at,
      mono: round(nowMono(), 3),
      session_ok: sessionOk,
      local_ok: localOk
    };
  }

  function finishPlay(attempt, outcome, error) {
    attempt.outcome = outcome;
    attempt.elapsed_ms = round(nowMono() - attempt.mono, 3);
    attempt.current_time = round(video.currentTime, 6);
    attempt.ready_state = video.readyState;
    attempt.paused = video.paused;
    attempt.error = error ? errorInfo(error) : null;
    attempt.finished_at = nowWall();
    addLifecycle("play-promise", {
      outcome: outcome,
      trigger: attempt.trigger,
      error: attempt.error
    });
    saveSession("play-promise");
    updateUI();
  }

  function startPlayback(trigger) {
    const name = trigger || "manual";
    const attempt = {
      attempt: state.playAttempts.length + 1,
      trigger: name,
      at: nowWall(),
      mono: round(nowMono(), 3),
      outcome: "pending",
      elapsed_ms: null,
      finished_at: null,
      current_time: round(video.currentTime, 6),
      ready_state: video.readyState,
      paused: video.paused,
      muted: video.muted,
      error: null
    };
    pushBounded(state.playAttempts, attempt, LIMITS.play_attempts, "play_attempts");
    logAction("play", { trigger: name });
    let promise = null;
    try {
      promise = video.play();
    } catch (error) {
      finishPlay(attempt, "rejected", error);
      return false;
    }
    if (promise && typeof promise.then === "function") {
      promise.then(function () {
        finishPlay(attempt, "resolved", null);
      }).catch(function (error) {
        finishPlay(attempt, "rejected", error);
      });
    } else {
      finishPlay(attempt, "resolved", null);
    }
    return true;
  }

  function pausePlayback() {
    video.pause();
    logAction("pause");
    saveSession("control");
    return video.paused;
  }

  function setLoop(value) {
    video.loop = !!value;
    logAction("loop", { value: video.loop });
    addLifecycle("loop-change", { value: video.loop });
    saveSession("control");
    updateUI();
    return video.loop;
  }

  function setMuted(value) {
    video.muted = !!value;
    logAction("mute", { value: video.muted });
    saveSession("control");
    updateUI();
    return video.muted;
  }

  function seekTo(seconds) {
    const target = Math.max(0, Number(seconds) || 0);
    const duration = numberOrNull(video.duration);
    try {
      video.currentTime = duration === null ? target : Math.min(target, Math.max(0, duration - 0.05));
    } catch (error) {
      addLifecycle("seek-error", errorInfo(error));
    }
    logAction("seek", { target: target, applied: round(video.currentTime, 3) });
    saveSession("control");
    updateUI();
    return round(video.currentTime, 3);
  }

  function mark(label) {
    const text = String(label || "").trim() || ("marker-" + (state.markers.length + 1));
    const row = {
      label: text,
      at: nowWall(),
      mono: round(nowMono(), 3),
      current_time: round(video.currentTime, 6),
      ready_state: video.readyState,
      paused: video.paused,
      visibility: document.visibilityState,
      page_instance_id: state.instanceId,
      sequence: state.sequence
    };
    pushBounded(state.markers, row, LIMITS.markers, "markers");
    logAction("marker", { label: text });
    saveSession("marker");
    updateLog();
    return row;
  }

  async function requestWakeLock() {
    if (!CAPS.wakeLock) {
      state.wakeLock.state = "unsupported";
      state.wakeLock.last_error = { name: "NotSupported", message: "navigator.wakeLock is unavailable", stack: null };
      saveSession("wake-lock");
      updateUI();
      return state.wakeLock.state;
    }
    if (state.wakeLock.sentinel) {
      try {
        await state.wakeLock.sentinel.release();
      } catch (error) {
        state.wakeLock.last_error = errorInfo(error);
      }
      state.wakeLock.sentinel = null;
      state.wakeLock.state = "released";
      pushCapped(state.wakeLock.changes, { at: nowWall(), state: "released", detail: "manual" }, 20);
      saveSession("wake-lock");
      updateUI();
      return state.wakeLock.state;
    }
    state.wakeLock.state = "requesting";
    updateUI();
    try {
      const sentinel = await navigator.wakeLock.request("screen");
      state.wakeLock.sentinel = sentinel;
      state.wakeLock.state = "active";
      pushCapped(state.wakeLock.requests, { at: nowWall(), outcome: "resolved", type: "screen" }, 10);
      sentinel.addEventListener("release", function () {
        state.wakeLock.sentinel = null;
        state.wakeLock.state = "released";
        pushCapped(state.wakeLock.changes, { at: nowWall(), state: "released", detail: "sentinel" }, 20);
        saveSession("wake-lock");
        updateUI();
      });
    } catch (error) {
      state.wakeLock.sentinel = null;
      state.wakeLock.state = "denied";
      state.wakeLock.last_error = errorInfo(error);
      pushCapped(state.wakeLock.requests, {
        at: nowWall(),
        outcome: "rejected",
        type: "screen",
        error: state.wakeLock.last_error
      }, 10);
    }
    saveSession("wake-lock");
    updateUI();
    return state.wakeLock.state;
  }

  async function toggleFullscreen() {
    if (!CAPS.fullscreen) {
      state.fullscreen.state = "unsupported";
      saveSession("fullscreen");
      updateUI();
      return state.fullscreen.state;
    }
    try {
      if (document.fullscreenElement) {
        await document.exitFullscreen();
        state.fullscreen.state = "exited";
        pushCapped(state.fullscreen.requests, { at: nowWall(), outcome: "resolved", action: "exit" }, 10);
      } else {
        await document.documentElement.requestFullscreen();
        state.fullscreen.state = "active";
        pushCapped(state.fullscreen.requests, { at: nowWall(), outcome: "resolved", action: "enter" }, 10);
      }
    } catch (error) {
      state.fullscreen.state = "error";
      state.fullscreen.last_error = errorInfo(error);
      pushCapped(state.fullscreen.requests, {
        at: nowWall(),
        outcome: "rejected",
        error: state.fullscreen.last_error
      }, 10);
    }
    saveSession("fullscreen");
    updateUI();
    return state.fullscreen.state;
  }

  function resetStoredEvidence() {
    state.storageDisabled = true;
    Object.keys(keys).forEach(function (name) {
      try { localStorage.removeItem(keys[name]); } catch (error) { /* storage unavailable */ }
      try { sessionStorage.removeItem(keys[name]); } catch (error) { /* storage unavailable */ }
    });
    window.location.reload();
  }

  function download() {
    const payload = snapshot();
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "device-probe-" + state.runId + "-" + state.sequence + "-" + state.instanceId.slice(0, 8) + ".json";
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    window.setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
    return anchor.download;
  }

  function formatEvent(row) {
    const time = new Date(row.at).toISOString().slice(11, 23);
    return time + " " + row.name + " t=" + (row.current_time === null ? "?" : row.current_time.toFixed(3)) +
      " rs=" + row.ready_state;
  }

  function updateLog() {
    const rows = state.events.slice(-8).map(formatEvent);
    const marks = state.markers.slice(-3).map(function (row) {
      const time = row.current_time === null ? "?" : row.current_time.toFixed(3);
      return new Date(row.at).toISOString().slice(11, 23) + " MARK " + row.label + " t=" + time;
    });
    const text = rows.concat(marks).join("\n");
    elements.log.textContent = text || "waiting for media";
  }

  function updateUI() {
    if (!state.initialized) return;
    const counters = countersSnapshot();
    const sample = state.samples.length ? state.samples[state.samples.length - 1] : null;
    const lastGap = state.gaps.length ? state.gaps[state.gaps.length - 1] : null;
    elements.pageLine.textContent = "run " + state.runId + " · page " + state.sequence +
      " · " + state.instanceId.slice(0, 8);
    elements.time.textContent = (sample && sample.current_time !== null ? sample.current_time.toFixed(3) : video.currentTime.toFixed(3)) + " s";
    elements.ready.textContent = String(video.readyState);
    elements.frames.textContent = String(counters.frame_callbacks);
    elements.dropped.textContent = counters.dropped_video_frames === null ? "n/a" : String(counters.dropped_video_frames);
    elements.gap.textContent = lastGap ? lastGap.wall_gap_ms.toFixed(0) + " ms" : "none";
    elements.visibility.textContent = document.visibilityState;
    elements.wake.textContent = state.wakeLock.state;
    elements.fullscreenState.textContent = document.fullscreenElement ? "active" : state.fullscreen.state;
    elements.sequence.textContent = String(state.sequence);
    elements.source.textContent = params.get("source_name") || (sourceParam ? sourceParam.split("/").pop() : "none");
    elements.seekValue.textContent = video.currentTime.toFixed(2) + " s";
    if (document.activeElement !== elements.seek) {
      elements.seek.value = String(video.currentTime);
    }
    elements.loop.textContent = "Loop: " + (video.loop ? "on" : "off");
    elements.loop.setAttribute("aria-pressed", String(video.loop));
    elements.mute.textContent = video.muted ? "Muted" : "Sound on";
    elements.mute.setAttribute("aria-pressed", String(video.muted));
    const missing = unavailableApis();
    elements.support.textContent = "API support: rVFC " + (CAPS.requestVideoFrameCallback ? "yes" : "no") +
      " · wake lock " + (CAPS.wakeLock ? "yes" : "no") +
      " · fullscreen " + (CAPS.fullscreen ? "yes" : "no") +
      " · unavailable " + missing.length;
  }

  function bindMediaEvents() {
    CONTRACT.required_media_events.forEach(function (name) {
      video.addEventListener(name, function () {
        pushBounded(state.events, mediaEventRow(name), LIMITS.events, "events");
        if (name === "playing") {
          resetFrameBaseline();
          restartFrameCallback();
        }
        if (name === "pause" || name === "ended" || name === "emptied") {
          resetFrameBaseline();
        }
        if (name === "loadedmetadata" || name === "durationchange" || name === "loadeddata") {
          updateMediaMetadata();
        }
        if (name === "error") {
          addLifecycle("media-error", video.error
            ? { code: video.error.code, message: String(video.error.message || "") }
            : null);
          saveSession("media-error");
        }
        updateLog();
        updateUI();
      }, { passive: true });
    });
    if (CAPS.requestVideoFrameCallback) {
      video.addEventListener("play", restartFrameCallback, { passive: true });
    }
  }

  function recordEnvironmentChange(kind) {
    addLifecycle(kind, {
      viewport: viewportSnapshot(),
      orientation: orientationSnapshot(),
      display_mode: displayModeSnapshot(),
      device_pixel_ratio: round(window.devicePixelRatio, 4)
    });
    saveSession(kind);
    updateUI();
  }

  function bindLifecycle() {
    window.addEventListener("resize", function () {
      recordEnvironmentChange("resize");
    });
    window.addEventListener("orientationchange", function () {
      recordEnvironmentChange("orientationchange");
    });
    if (window.screen && screen.orientation && typeof screen.orientation.addEventListener === "function") {
      screen.orientation.addEventListener("change", function () {
        recordEnvironmentChange("screen-orientation-change");
      });
    }
    window.addEventListener("pagehide", function (event) {
      addLifecycle("pagehide", { persisted: !!event.persisted });
      saveSession("pagehide");
    });
    window.addEventListener("pageshow", function (event) {
      state.persistedPageshow = !!event.persisted;
      addLifecycle("pageshow", { persisted: !!event.persisted });
      if (event.persisted) restartFrameCallback();
    });
    document.addEventListener("visibilitychange", function () {
      addLifecycle("visibilitychange", { state: document.visibilityState });
      resetFrameBaseline();
      if (document.visibilityState === "hidden") saveSession("visibilitychange");
      else if (!video.paused && !video.ended) restartFrameCallback();
      updateUI();
    });
    document.addEventListener("freeze", function () {
      addLifecycle("freeze", null);
      saveSession("freeze");
    });
    document.addEventListener("resume", function () {
      addLifecycle("resume", null);
    });
    document.addEventListener("fullscreenchange", function () {
      if (document.fullscreenElement) {
        state.fullscreen.state = "active";
      } else if (state.fullscreen.state !== "unsupported") {
        state.fullscreen.state = "exited";
      }
      const entry = { at: nowWall(), active: !!document.fullscreenElement, state: state.fullscreen.state };
      pushCapped(state.fullscreen.changes, entry, 20);
      addLifecycle("fullscreenchange", entry);
      saveSession("fullscreen");
      updateUI();
    });
  }

  function bindControls() {
    elements.play.addEventListener("click", function () { startPlayback("button"); });
    elements.pause.addEventListener("click", pausePlayback);
    elements.loop.addEventListener("click", function () { setLoop(!video.loop); });
    elements.mute.addEventListener("click", function () { setMuted(!video.muted); });
    elements.wakeLock.addEventListener("click", requestWakeLock);
    elements.fullscreen.addEventListener("click", toggleFullscreen);
    elements.download.addEventListener("click", download);
    elements.reset.addEventListener("click", resetStoredEvidence);
    elements.markButton.addEventListener("click", function () {
      mark(elements.markerLabel.value);
      elements.markerLabel.value = "";
    });
    elements.seek.addEventListener("input", function () {
      elements.seekValue.textContent = Number(elements.seek.value).toFixed(2) + " s";
    });
    elements.seek.addEventListener("change", function () {
      seekTo(Number(elements.seek.value));
    });
  }

  function applySource() {
    video.loop = loopRequested;
    video.muted = true;
    if (sourceParam) {
      video.src = sourceParam;
      video.load();
    } else {
      addLifecycle("source-missing", null);
    }
    if (autoplayRequested && sourceParam) {
      window.setTimeout(function () { startPlayback("autoplay"); }, 0);
    }
  }

  initLineage();
  state.initialized = true;
  bindMediaEvents();
  bindLifecycle();
  bindControls();
  applySource();
  sample("init");
  saveSession("init");
  updateLog();
  updateUI();
  let lastPersist = Date.now();
  window.setInterval(function () {
    sample("interval");
    const now = Date.now();
    if (now - lastPersist >= 1000) {
      lastPersist = now;
      saveSession("interval");
    }
  }, CONTRACT.sample_interval_ms);
  window.setInterval(function () {
    updateLog();
    updateUI();
  }, 1000);

  window.__deviceProbe = {
    contract: function () { return CONTRACT; },
    snapshot: snapshot,
    state: function () {
      return {
        ready: true,
        playing: !video.paused && !video.ended && video.readyState >= 2,
        paused: video.paused,
        ended: video.ended,
        currentTime: round(video.currentTime, 6),
        duration: numberOrNull(video.duration),
        readyState: video.readyState,
        networkState: video.networkState,
        frames: state.counters.frameCallbacks,
        playOutcome: state.playAttempts.length
          ? state.playAttempts[state.playAttempts.length - 1].outcome
          : "none",
        sequence: state.sequence,
        pageInstanceId: state.instanceId,
        loop: video.loop,
        muted: video.muted,
        visibility: document.visibilityState,
        error: video.error ? { code: video.error.code, message: String(video.error.message || "") } : null
      };
    },
    mark: mark,
    start: function (trigger) { return startPlayback(trigger || "api"); },
    pause: pausePlayback,
    setLoop: setLoop,
    setMuted: setMuted,
    seek: seekTo,
    requestWakeLock: requestWakeLock,
    toggleFullscreen: toggleFullscreen,
    reset: resetStoredEvidence,
    download: download
  };
  window.__deviceProbeReady = true;
})();
