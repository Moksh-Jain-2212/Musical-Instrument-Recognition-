"use strict";
const $ = (id) => document.getElementById(id);
const audio = $("audio");
const colors = ["#92aa70", "#d3ad71", "#84aaa7", "#b9a3c4", "#cf9a88", "#98abd0", "#a9b677"];
let selectedFile = null, objectURL = null, result = null, controller = null, busy = false;
let config = null, frame = null, lastActiveKey = "", rowElements = [], tableRows = [];

function time(seconds, precise = false) {
  if (!Number.isFinite(seconds)) seconds = 0;
  const minutes = Math.floor(seconds / 60);
  const rest = seconds - minutes * 60;
  return `${String(minutes).padStart(2, "0")}:${precise && rest % 1 ? rest.toFixed(1).padStart(4, "0") : String(Math.floor(rest)).padStart(2, "0")}`;
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
  $("results").hidden = true; $("details").hidden = true; $("empty").hidden = false;
  $("active-sounds").replaceChildren(element("span", "Your detected sounds will appear here.", "muted"));
}
function setBusy(value) {
  busy = value;
  $("analyze").disabled = value || !selectedFile || !config?.token_configured || !config?.ffmpeg_available;
  $("clear").disabled = value; $("file").disabled = value; $("threshold").disabled = value;
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
    const response = await fetch(`/api/analyze/stream?threshold=${Number($("threshold").value) / 100}`, { method: "POST", body: form, signal: controller.signal });
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
        } else $("progress-text").textContent = "Decoding your audio…";
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

function renderResults() {
  $("empty").hidden = true; $("results").hidden = false; $("details").hidden = false;
  $("resolution").textContent = `${result.chunk_duration} SECOND RESOLUTION`;
  $("result-summary").textContent = `${Object.keys(result.instruments).length} sounds · ${time(result.duration, true)}`;
  $("player-hint").textContent = `Analyzed at ${Math.round(result.threshold * 100)}% confidence. Play or seek to explore.`;
  const axis = $("axis"); axis.replaceChildren();
  for (let i = 0; i <= 5; i++) {
    const label = element("span", time(result.duration * i / 5, result.duration < 5));
    label.style.left = `${i * 20}%`; axis.append(label);
  }
  $("tracks").replaceChildren(); rowElements = [];
  Object.entries(result.instruments).sort(([a], [b]) => a.localeCompare(b)).forEach(([name, segments], index) => {
    const row = element("div", undefined, "track-row"); row.style.setProperty("--track-color", colors[index % colors.length]);
    const label = element("div", undefined, "track-name"); label.append(element("span", undefined, "dot"), document.createTextNode(name));
    const lane = element("div", undefined, "track-lane");
    for (const segment of segments) {
      const bar = element("button", undefined, "segment");
      const description = `${name}, ${time(segment.start, true)} to ${time(segment.end, true)}, ${Math.round(segment.average_confidence * 100)}% confidence`;
      bar.title = description; bar.setAttribute("aria-label", description);
      bar.style.left = `${segment.start / result.duration * 100}%`;
      bar.style.width = `${(segment.end - segment.start) / result.duration * 100}%`;
      bar.addEventListener("click", () => { audio.currentTime = segment.start; updatePlayback(); });
      lane.append(bar);
    }
    row.append(label, lane); $("tracks").append(row); rowElements.push({ name, row });
  });
  if (!rowElements.length) $("tracks").append(element("p", result.failed_chunks === result.windows.length ? "All chunks failed. See the errors below." : "No supported sounds exceeded your threshold.", "muted"));
  $("warnings").replaceChildren(...result.warnings.map((message) => element("p", message)));
  const failures = [...new Set(result.windows.filter((w) => w.error).map((w) => w.error))];
  for (const message of failures) $("warnings").append(element("p", message));
  $("table-body").replaceChildren(); tableRows = [];
  for (const entry of result.timeline) {
    const row = element("tr"), start = element("td"), button = element("button", time(entry.start, true), "seek-button");
    button.addEventListener("click", () => { audio.currentTime = entry.start; updatePlayback(); }); start.append(button);
    row.append(start, element("td", time(entry.end, true)), element("td", entry.status === "failed" ? "Analysis failed" : entry.events.join(" + ") || "No confident detection"),
      element("td", entry.events.map((name) => `${name} ${Math.round(entry.confidences[name] * 100)}%`).join(" · ") || "—"));
    $("table-body").append(row); tableRows.push({ entry, row });
  }
  lastActiveKey = ""; updatePlayback();
}

function updatePlayback() {
  const current = audio.currentTime || 0;
  const duration = result?.duration || (Number.isFinite(audio.duration) ? audio.duration : 0);
  $("clock").textContent = `${time(current)} / ${time(duration, true)}`;
  if (!result) return;
  const fraction = Math.min(1, Math.max(0, current / result.duration));
  $("playhead").style.left = `calc(var(--label-width) + (100% - var(--label-width)) * ${fraction})`;
  // Raw chunk scores determine current events; merged rows only summarize them.
  const window = result.windows.find((w) => current >= w.start && current < w.end);
  const key = window ? `${window.start}:${window.status}` : "ended";
  if (key !== lastActiveKey) {
    lastActiveKey = key;
    const events = window?.events || [];
    $("active-sounds").replaceChildren(...events.map((e) => element("span", `${e.name} · ${Math.round(e.confidence * 100)}%`, "sound-chip")));
    if (!events.length) $("active-sounds").append(element("span", !window ? "End of audio." : window.status === "failed" ? "This interval could not be analyzed." : "No confident detection in this interval.", "muted"));
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
  const link = element("a"); link.href = url; link.download = "sound-atlas-analysis.json"; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
(async () => {
  try {
    const response = await fetch("/health"); if (!response.ok) throw new Error("Health check failed");
    config = await response.json();
    $("connection").textContent = config.status === "ready" ? "● API configured" : "○ Setup needed";
    $("connection").classList.toggle("ready", config.status === "ready");
    $("setup").hidden = config.token_configured;
    $("max-size").textContent = config.max_upload_mb;
    $("resolution").textContent = `${config.chunk_duration} SECOND RESOLUTION`;
    $("threshold").value = Math.round(config.confidence_threshold * 100);
    $("threshold-value").textContent = `${$("threshold").value}%`;
    if (!config.ffmpeg_available) error("FFmpeg is unavailable. Install it or set FFMPEG_PATH, then restart.");
    setBusy(false);
  } catch { error("Cannot reach the server. Start FastAPI and reload this page."); $("connection").textContent = "○ Offline"; }
})();
