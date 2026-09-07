const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const html = fs.readFileSync(path.join(root, 'app/static/index.html'), 'utf8');
const source = fs.readFileSync(path.join(root, 'app/static/app.js'), 'utf8');

// A small DOM double exercises the shipped script without browser or network dependencies.
class Element {
  constructor() {
    this.children = []; this.handlers = {}; this.value = ''; this.checked = false;
    this.style = { setProperty() {} };
    this.classList = { toggle() {}, add() {}, remove() {} };
  }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; this.textContent = ''; }
  addEventListener(name, handler) { this.handlers[name] = handler; }
  setAttribute() {}
  removeAttribute() {}
  pause() {}
  click() {}
}
function text(element) {
  return [element.textContent || '', ...element.children.map(text)].join(' ');
}
async function setup(confidence = .2) {
  const nodes = new Map([...html.matchAll(/id="([^"]+)"/g)].map((m) => [m[1], new Element()]));
  const requests = [];
  const window = new Element();
  const context = vm.createContext({
    document: {
      getElementById(id) { assert.ok(nodes.has(id), `Missing HTML element: ${id}`); return nodes.get(id); },
      createElement() { return new Element(); },
      createTextNode(value) { const el = new Element(); el.textContent = value; return el; },
    },
    window, URL: { createObjectURL() { return 'blob:test'; }, revokeObjectURL() {} },
    FormData: class { append() {} }, AbortController, TextDecoder,
    cancelAnimationFrame() {}, requestAnimationFrame() {}, setTimeout,
    fetch: async (url) => {
      if (url === '/health') return { ok: true, json: async () => ({ status: 'ready', provider: 'yamnet',
        token_configured: true, ffmpeg_available: true, supported_instruments: ['Piano'],
        confidence_threshold: confidence, max_upload_mb: 100, chunk_duration: 5 }) };
      requests.push(url);
      return { ok: true, body: { getReader() { return { read: async () => ({ done: true }) }; } } };
    },
  });
  await vm.runInContext(source, context);
  return { nodes, requests, context };
}

test('slider is bounded, initializes at 20%, and submits decimal threshold with fallback', async () => {
  assert.match(html, /id="threshold" type="range" min="5" max="80" value="20"/);
  const { nodes, requests, context } = await setup();
  assert.equal(Number(nodes.get('threshold').value), 20);
  assert.equal(nodes.get('threshold-value').textContent, '20%');
  vm.runInContext('selectFile({ size: 100, name: "music.wav" })', context);
  nodes.get('fallback').checked = true;
  await nodes.get('analyze').handlers.click();
  assert.equal(requests[0], '/api/analyze/stream?threshold=0.2&fallback=true');
});

test('stale 100% configuration cannot submit threshold=1', async () => {
  const { nodes, requests, context } = await setup(1);
  assert.equal(Number(nodes.get('threshold').value), 80);
  vm.runInContext('selectFile({ size: 100, name: "music.wav" })', context);
  await nodes.get('analyze').handlers.click();
  assert.equal(requests[0], '/api/analyze/stream?threshold=0.8&fallback=false');
});

test('raw diagnostics stay separate from instrument tracks and current instruments', async () => {
  const { nodes, context } = await setup();
  const data = { provider: 'yamnet', chunk_duration: 5, duration: 5, threshold: .2, failed_chunks: 0, warnings: [],
    windows: [{ start: 0, end: 5, status: 'ok', instruments: [{ name: 'Piano', confidence: .17 }],
      raw_predictions: [{ label: 'Music', score: .91 }, { label: 'Speech', score: .8 }, { label: 'Piano', score: .17 }],
      fallback_used: true, effective_threshold: .15 }],
    instrument_tracks: { Piano: [{ start: 0, end: 5, average_confidence: .17 }] } };
  data.timeline = data.windows;
  vm.runInContext(`result = ${JSON.stringify(data)}; renderResults();`, context);
  assert.equal(nodes.get('raw-details').hidden, false);
  assert.match(text(nodes.get('raw-windows')), /Speech — 80.00%/);
  assert.match(text(nodes.get('tracks')), /Piano/);
  assert.doesNotMatch(text(nodes.get('tracks')), /Music|Speech/);
  assert.match(text(nodes.get('active-instruments')), /Piano · 17%/);
  assert.match(text(nodes.get('active-instruments')), /15% fallback/);
  assert.doesNotMatch(text(nodes.get('active-instruments')), /Music|Speech/);
  const message = 'YAMNet detected music, but no specific instrument reached the 20% threshold in its top five predictions.';
  data.instrument_tracks = {};
  data.windows[0] = { ...data.windows[0], instruments: [], fallback_used: false, effective_threshold: .2, message };
  data.timeline = data.windows;
  vm.runInContext(`result = ${JSON.stringify(data)}; renderResults();`, context);
  for (const id of ['tracks', 'table-body', 'active-instruments', 'summary-grid']) assert.ok(text(nodes.get(id)).includes(message));
  vm.runInContext('resetResults()', context);
  assert.equal(nodes.get('raw-details').hidden, true);
  assert.equal(nodes.get('raw-windows').children.length, 0);
});
