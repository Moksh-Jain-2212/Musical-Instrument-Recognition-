"use strict";
const $ = (id) => document.getElementById(id);
const audio = $("audio");
const colors = ["#c4f06a", "#70d6c3", "#b5a0ee", "#edb878", "#8cb9ee", "#e7a2ba", "#c6ce91"];
let selectedFile = null, objectURL = null, result = null, controller = null, busy = false;
let config = null, frame = null, lastActiveKey = "", rowElements = [], tableRows = [];

function time(seconds, precise = false) {
  if (!Number.isFinite(seconds)) seconds = 0;
  if (precise) seconds = Math.round(seconds * 10) / 10;
  const minutes = Math.floor(seconds / 60);
  const rest = seconds - minutes * 60;
  return `${String(minutes).padStart(2, "0")}:${precise ? rest.toFixed(1).padStart(4, "0") : String(Math.floor(rest)).padStart(2, "0")}`;
}
function element(tag, text, className) {
  const el = document.createElement(tag);
  if (text !== undefined) el.textContent = text;
  if (className) el.className = className;
  return el;
}
function error(message) { $("error").textContent = message; $("error").hidden = !message; }
function resetResults() {
  result = null; lastActiveKey = ""; rowElements = []; tableRows = [];
  $("raw-details").hidden = true; $("raw-windows").replaceChildren();
  $("instrument-summary").hidden = true; $("results").hidden = true; $("details").hidden = true; $("empty").hidden = false;
  $("active-instruments").replaceChildren(element("span", "Your detected instruments will appear here.", "muted"));
}
function setBusy(value) {
  busy = value;
  $("analyze").disabled = value || !selectedFile || !config?.token_configured || !config?.ffmpeg_available;
  $("clear").disabled = value; $("file").disabled = value; $("threshold").disabled = value;
  $("fallback").disabled = value;
  $("dropzone").setAttribute("aria-disabled", String(value));
  $("progress-area").hidden = !value;
}
function selectFile(file) {
  if (busy || !file) return;
  if (file.size === 0) return error("This file is empty. Choose an audio recording.");
  if (file.size > (config?.max_upload_mb || 100) * 1024 * 1024) return error("This file exceeds the upload size limit.");
  error(""); resetResults(); audio.pause();
  if (objectURL) URL.revokeObjectURL(objectURL);
  selectedFile = file; objectURL = URL.createObjectURL(file); audio.src = objectURL;
  $("file-info").hidden = false; $("file-name").textContent = file.name;
  $("file-meta").textContent = `${(file.size / 1024 / 1024).toFixed(2)} MB`;
  $("player-hint").textContent = "Ready to listen. Analyze to reveal the timeline.";
  setBusy(false);
}
$("file").addEventListener("change", (event) => selectFile(event.target.files[0]));
$("dropzone").addEventListener("keydown", (event) => {
  if (!busy && (event.key === "Enter" || event.key === " ")) { event.preventDefault(); $("file").click(); }
});
for (const name of ["dragenter", "dragover"]) $("dropzone").addEventListener(name, (e) => { e.preventDefault(); if (!busy) $("dropzone").classList.add("dragging"); });
for (const name of ["dragleave", "drop"]) $("dropzone").addEventListener(name, (e) => { e.preventDefault(); $("dropzone").classList.remove("dragging"); });
$("dropzone").addEventListener("drop", (e) => selectFile(e.dataTransfer.files[0]));
$("clear").addEventListener("click", () => {
  audio.pause(); audio.removeAttribute("src"); audio.load();
  if (objectURL) URL.revokeObjectURL(objectURL);
  objectURL = null; selectedFile = null; $("file").value = ""; $("file-info").hidden = true;
  $("player-hint").textContent = "Choose a file to listen and explore.";
  resetResults(); error(""); setBusy(false); updatePlayback();
});
$("threshold").addEventListener("input", () => { $("threshold-value").textContent = `${$("threshold").value}%`; });
$("cancel").addEventListener("click", () => controller?.abort());
$("analyze").addEventListener("click", async () => {
  if (busy || !selectedFile) return;
  error(""); resetResults(); setBusy(true); $("progress").removeAttribute("value");
  $("progress-text").textContent = "Uploading and preparing your audio…";
  controller = new AbortController();
  const form = new FormData(); form.append("file", selectedFile);
  try {
    const threshold = Math.min(80, Math.max(5, Number($("threshold").value) || 20)) / 100;
    const fallback = config.provider === "yamnet" && $("fallback").checked;
    const response = await fetch(`/api/analyze/stream?threshold=${threshold}&fallback=${fallback}`, { method: "POST", body: form, signal: controller.signal });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(typeof body.detail === "string" ? body.detail : `Request failed (HTTP ${response.status}).`);
    }
    const reader = response.body.getReader(), decoder = new TextDecoder();
    let buffer = "", receivedResult = false;
    const handle = (line) => {
      if (!line.trim()) return;
      const event = JSON.parse(line);
      if (event.type === "error") throw new Error(event.message);
      if (event.type === "progress") {
        if (event.total) {
          $("progress").value = event.completed / event.total * 100;
          $("progress-text").textContent = `Analyzed ${event.completed} of ${event.total} chunks${event.completed < event.total ? " · listening…" : ""}`;
        } else {
          $("progress").removeAttribute("value");
          $("progress-text").textContent = {
            decoding: "Decoding your audio…",
            uploading_to_gemini: "Uploading the complete audio to Gemini…",
            preparing_gemini_audio: "Gemini is preparing the recording…",
            analyzing_instruments: "Gemini is estimating instrument timestamps…",
          }[event.stage] || "Processing your audio…";
        }
      }
      if (event.type === "result") { result = event.result; receivedResult = true; renderResults(); }
    };
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n"); buffer = lines.pop();
      for (const line of lines) handle(line);
    }
    buffer += decoder.decode(); handle(buffer);
    if (!receivedResult) throw new Error("The connection ended before analysis finished. Please try again.");
  } catch (e) {
    controller.abort();
    error(e.name === "AbortError" ? "Analysis canceled." : e.message);
  } finally { controller = null; setBusy(false); }
});

function noDetectionMessage(entry) {
  return (entry?.message ? displayMessage(entry.message) : null) || "No specific musical instrument was confidently detected in this interval.";
}
function emptyResultMessage() {
  if (result.failed_chunks === result.windows.length) return "Analysis failed. See the errors below.";
  return [...new Set(result.windows.filter((w) => w.status === "ok" && !w.instruments.length).map(noDetectionMessage))].join(" ");
}
function occurrenceTime(seconds) {
  return time(seconds, seconds % 1 !== 0).replace(/^0(?=\d:)/, "");
}
function displayMessage(message) {
  return message.replace(/\b\d+(?:\.\d+)?% fallback/g, "fallback").replace(/\b\d+(?:\.\d+)?%/g, "selected");
}

function renderResults() {
  $("empty").hidden = true; $("results").hidden = false; $("details").hidden = false;
  $("resolution").textContent = result.chunk_duration ? `${result.chunk_duration} SECOND RESOLUTION` : "ESTIMATED TIMESTAMPS";
  $("result-summary").textContent = `${Object.keys(result.instrument_tracks).length} instruments · ${time(result.duration, true)}`;
  $("player-hint").textContent = "Your track, mapped. Play or select a moment to explore.";
  if (result.windows.some((w) => w.fallback_used)) $("player-hint").textContent += " A lower detection threshold was used for some intervals.";
  const axis = $("axis"); axis.replaceChildren();
  for (let i = 0; i <= 5; i++) {
    const label = element("span", time(result.duration * i / 5, result.duration < 5));
    label.style.left = `${i * 20}%`; axis.append(label);
  }
  $("tracks").replaceChildren(); rowElements = [];
  Object.entries(result.instrument_tracks).sort(([a], [b]) => a.localeCompare(b)).forEach(([name, segments], index) => {
    const row = element("div", undefined, "track-row"); row.style.setProperty("--track-color", colors[index % colors.length]);
    const label = element("div", undefined, "track-name"); label.append(element("span", undefined, "dot"), document.createTextNode(name));
    const lane = element("div", undefined, "track-lane");
    for (const segment of segments) {
      const bar = element("button", undefined, "segment");
      const description = `${name} · ${occurrenceTime(segment.start)}–${occurrenceTime(segment.end)}`;
      bar.title = description; bar.setAttribute("aria-label", description);
      bar.setAttribute("data-tooltip", `${occurrenceTime(segment.start)}–${occurrenceTime(segment.end)}`);
      bar.style.left = `${segment.start / result.duration * 100}%`;
      bar.style.width = `${(segment.end - segment.start) / result.duration * 100}%`;
      bar.addEventListener("click", () => { audio.currentTime = segment.start; updatePlayback(); });
      lane.append(bar);
    }
    row.append(label, lane); $("tracks").append(row); rowElements.push({ name, row });
  });
  if (!rowElements.length) $("tracks").append(element("p", emptyResultMessage(), "muted"));
  $("instrument-summary").hidden = true;
  $("raw-details").hidden = true;
  $("warnings").replaceChildren(...result.warnings.map((message) => element("p", displayMessage(message))));
  const failures = [...new Set(result.windows.filter((w) => w.error).map((w) => w.error))];
  for (const message of failures) $("warnings").append(element("p", displayMessage(message)));
  $("table-body").replaceChildren(); tableRows = [];
  const names = Object.keys(result.instrument_tracks).sort((a, b) => a.localeCompare(b));
  const occurrences = names.flatMap((name, index) => result.instrument_tracks[name].map((segment) => ({
    ...segment, name, color: colors[index % colors.length],
  }))).sort((a, b) => a.start - b.start || a.end - b.end || a.name.localeCompare(b.name));
  for (const entry of occurrences) {
    const row = element("li", undefined, "occurrence");
    row.style.setProperty("--track-color", entry.color);
    const button = element("button", undefined, "occurrence-button");
    const name = element("span", undefined, "occurrence-name");
    name.append(element("span", undefined, "dot"), document.createTextNode(entry.name));
    const range = `${occurrenceTime(entry.start)}–${occurrenceTime(entry.end)}`;
    button.setAttribute("aria-label", `${entry.name}, ${range}. Seek to this moment.`);
    button.append(name, element("span", range, "occurrence-time"), element("span", "↗", "occurrence-arrow"));
    button.addEventListener("click", () => { audio.currentTime = entry.start; updatePlayback(); });
    row.append(button); $("table-body").append(row); tableRows.push({ entry, row });
  }
  if (!occurrences.length) $("table-body").append(element("li", emptyResultMessage(), "log-empty"));
  lastActiveKey = ""; updatePlayback();
}

function updatePlayback() {
  const current = audio.currentTime || 0;
  const duration = result?.duration || (Number.isFinite(audio.duration) ? audio.duration : 0);
  $("clock").textContent = `${time(current, true)} / ${time(duration, true)}`;
  if (!result) return;
  const fraction = Math.min(1, Math.max(0, current / result.duration));
  $("playhead").style.left = `calc(var(--label-width) + (100% - var(--label-width)) * ${fraction})`;
  // Provider-normalized windows determine current instruments; merged rows summarize them.
  const window = result.windows.find((w) => current >= w.start && current < w.end);
  const key = window ? `${window.start}:${window.status}` : "ended";
  if (key !== lastActiveKey) {
    lastActiveKey = key;
    const events = window?.instruments || [];
    $("active-instruments").replaceChildren(...events.map((e) => element("span", e.name, "instrument-chip")));
    if (!events.length) $("active-instruments").append(element("span", !window ? "End of audio." : window.status === "failed" ? "This interval could not be analyzed." : noDetectionMessage(window), "muted"));
    if (window?.fallback_used) $("active-instruments").append(element("span", "Closer listening applied", "muted"));
    for (const { name, row } of rowElements) row.classList.toggle("active", events.some((e) => e.name === name));
    for (const { entry, row } of tableRows) row.classList.toggle("current", current >= entry.start && current < entry.end);
  }
}
function animate() { updatePlayback(); if (!audio.paused && !audio.ended) frame = requestAnimationFrame(animate); }
audio.addEventListener("play", () => { cancelAnimationFrame(frame); animate(); });
for (const event of ["timeupdate", "seeked", "loadedmetadata", "ended", "pause"]) audio.addEventListener(event, updatePlayback);
audio.addEventListener("error", () => { if (selectedFile) $("player-hint").textContent = "Your browser cannot play this format. Analysis may still work; convert to MP3 or WAV for synchronized playback."; });
window.addEventListener("beforeunload", () => { if (objectURL) URL.revokeObjectURL(objectURL); controller?.abort(); });
$("download").addEventListener("click", () => {
  if (!result) return;
  const url = URL.createObjectURL(new Blob([JSON.stringify(result, null, 2)], { type: "application/json" }));
  const link = element("a"); link.href = url; link.download = "instrument-timeline-analysis.json"; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
(async () => {
  try {
    const response = await fetch("/health"); if (!response.ok) throw new Error("Health check failed");
    config = await response.json();
    $("connection").textContent = config.status === "ready" ? "● API configured" : "○ Setup needed";
    $("connection").classList.toggle("ready", config.status === "ready");
    $("setup").hidden = config.token_configured;
    if (!config.token_configured) $("setup").textContent = `Set ${config.required_credential} in .env and restart the server. See README.md for API key setup.`;
    const gemini = config.provider === "gemini";
    $("fallback-setting").hidden = gemini;
    $("fallback").checked = !gemini && config.instrument_fallback_enabled === true;
    $("supported-list").replaceChildren(...config.supported_instruments.map((name) => element("li", name)));
    $("supported-count").textContent = `(${config.supported_instruments.length})`;
    $("supported-note").textContent = gemini
      ? "Gemini results use these instrument names and families. Recognition is an estimate and can miss or confuse instruments."
      : "These names come from YAMNet's supported instrument labels. Combined names such as Marimba / Xylophone cannot be distinguished by this model.";
    $("supported-instruments").hidden = false;
    $("provider-label").textContent = gemini ? `Powered by ${config.model}` : "Powered by hosted YAMNet";
    $("privacy-copy").textContent = gemini
      ? "The complete recording is sent to Google Gemini. Local files are deleted after analysis; temporary Google upload deletion is requested."
      : "Audio chunks are sent to a community Hugging Face Space. Local copies are deleted after analysis; the host may cache uploads.";
    $("provider-limitation").textContent = gemini
      ? "Gemini estimates instruments and timing semantically; similar or quiet instruments can be missed or confused."
      : "YAMNet exposes only its top 5 predictions per chunk; broad labels can displace instruments.";
    $("max-size").textContent = config.max_upload_mb;
    $("resolution").textContent = config.chunk_duration ? `${config.chunk_duration} SECOND RESOLUTION` : "ESTIMATED TIMESTAMPS";
    $("threshold").value = Math.min(80, Math.max(5, Math.round((config.confidence_threshold ?? 0.2) * 100)));
    $("threshold-value").textContent = `${$("threshold").value}%`;
    if (!config.ffmpeg_available) error("FFmpeg is unavailable. Install it or set FFMPEG_PATH, then restart.");
    setBusy(false);
  } catch { error("Cannot reach the server. Start FastAPI and reload this page."); $("connection").textContent = "○ Offline"; }
})();
