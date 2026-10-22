// Global context: execute the production dashboard against an inert DOM and
// manually completed fetches; no browser, app server, or network is started.
// Node's built-in runner and VM need no package installation:
// https://nodejs.org/api/test.html and https://nodejs.org/api/vm.html
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

// Read the real script once so assertions exercise shipped rendering behavior.
const source = fs.readFileSync(
  path.join(__dirname, "../deepwork/webui/static/dashboard.js"), "utf8",
);

class Element {
  // Local context: model only DOM operations the dashboard actually uses.
  constructor() {
    this.textContent = "";
    this.dataset = {};
    this.attributes = {};
    this.children = [];
    this.listeners = {};
    this.checked = false;
    this.classList = { toggle() {} };
  }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; }
  setAttribute(name, value) { this.attributes[name] = value; }
  addEventListener(name, listener) { this.listeners[name] = listener; }
  querySelectorAll() { return []; }
  reset() {}
}

function dashboard() {
  // Local context: controllable timers/fetches make render and polling races
  // reproducible without waiting for real three-second intervals.
  const nodes = new Map();
  const timers = new Map();
  const requests = [];
  const errors = [];
  const documentListeners = {};
  const windowListeners = {};
  let timerId = 0;
  const get = (id) => {
    if (!nodes.has(id)) nodes.set(id, new Element());
    return nodes.get(id);
  };
  get("goal-access-duration-mode").value = "timed";
  const document = {
    hidden: false,
    getElementById: get,
    createElement: () => new Element(),
    createDocumentFragment: () => new Element(),
    addEventListener: (name, listener) => { documentListeners[name] = listener; },
  };
  const window = {
    location: { search: "", href: "http://127.0.0.1/" },
    history: { replaceState() {} },
    addEventListener: (name, listener) => { windowListeners[name] = listener; },
    setInterval() {},
    clearTimeout: (id) => timers.delete(id),
    setTimeout: (callback, delay) => {
      timers.set(++timerId, { callback, delay });
      return timerId;
    },
  };
  const context = vm.createContext({
    window, document, URL, URLSearchParams,
    console: { error: (...args) => errors.push(args.map(String).join(" ")) },
    fetch: () => new Promise((resolve) => requests.push(resolve)),
  });
  vm.runInContext(source, context, { timeout: 1000 });
  return {
    get, timers, requests, document, documentListeners, windowListeners,
    async respond(payload) {
      // Resolve one pending request and drain its asynchronous render work.
      assert.ok(requests.length, "dashboard must have a pending status request");
      requests.shift()({ ok: true, json: async () => payload });
      await new Promise(setImmediate);
      assert.deepEqual(errors, [], "status rendering must not log an exception");
    },
    poll() {
      // Run exactly the recursive timeout the production script scheduled.
      assert.equal(timers.size, 1);
      const [id, timer] = timers.entries().next().value;
      timers.delete(id);
      timer.callback();
    },
  };
}

function status(overrides = {}) {
  // Local context: fields match /status; individual cases change only the
  // policy or monitoring facts relevant to the claim being verified.
  return {
    mode: "on", agentic_mode: false, agent_busy: false,
    monitoring_active: true, social_minutes_cap: 120,
    social_minutes_remaining: 120, evaluation_history: [],
    work_access: {}, enforcement: {}, runtime: { running: true, loops: {} },
    ...overrides,
  };
}

test("zero allowance remains zero in visible and accessible text", async () => {
  const ui = dashboard();
  await ui.respond(status({ social_minutes_cap: 0, social_minutes_remaining: 0 }));
  assert.equal(ui.get("social-remaining").textContent, "0 of 0 min");
  assert.equal(ui.get("social-progress").attributes["aria-label"],
    "0 of 0 social allowance minutes remaining");
  assert.equal(ui.get("social-progress").max, 1);
  assert.equal(ui.get("social-progress").value, 0);
});

test("positive allowance retains its actual cap", async () => {
  const ui = dashboard();
  await ui.respond(status({ social_minutes_remaining: 35 }));
  assert.equal(ui.get("social-remaining").textContent, "35 of 120 min");
  assert.equal(ui.get("social-progress").max, 120);
  assert.equal(ui.get("social-progress").value, 35);
});

for (const mode of ["off", "break"]) {
  for (const busy of [false, true]) {
    test(`${mode} does not present a retained agent verdict as active policy (${busy})`, async () => {
      const ui = dashboard();
      await ui.respond(status({ mode, agentic_mode: true, agent_busy: busy,
        monitoring_active: false }));
      assert.equal(ui.get("agent-state").textContent, "Watcher paused");
      assert.equal(ui.get("agent-detail").textContent, mode === "break"
        ? "Agent watching is paused during the break."
        : "Agent watching is inactive while enforcement is off.");
    });
  }
}

test("agent-busy task access describes the monitoring pause", async () => {
  const ui = dashboard();
  await ui.respond(status({ agentic_mode: true, agent_busy: true,
    monitoring_active: false, work_access: { allowed_group_labels: ["Discord"] } }));
  assert.match(ui.get("project-detail").textContent, /monitoring is paused/);
  assert.match(ui.get("agent-detail").textContent, /Website policy allows/);
  assert.doesNotMatch(ui.get("agent-detail").textContent, /restrictions are temporarily open/);
});

test("normal task access describes enabled monitoring", async () => {
  const ui = dashboard();
  await ui.respond(status({ work_access: { allowed_group_labels: ["Discord"] } }));
  assert.match(ui.get("project-detail").textContent, /monitoring is enabled/);
});

test("watcher checkbox follows server changes without replacing an unsaved edit", async () => {
  const ui = dashboard();
  const checkbox = ui.get("agentic-enabled");
  await ui.respond(status({ agentic_mode: true }));
  assert.equal(checkbox.checked, true);
  checkbox.checked = false;
  checkbox.listeners.change();
  ui.poll();
  await ui.respond(status({ agentic_mode: true }));
  assert.equal(checkbox.checked, false);
  ui.poll();
  await ui.respond(status({ agentic_mode: false }));
  ui.poll();
  await ui.respond(status({ agentic_mode: true }));
  assert.equal(checkbox.checked, true);
});

test("a checkbox edit before the first response is preserved", async () => {
  const ui = dashboard();
  const checkbox = ui.get("agentic-enabled");
  checkbox.checked = true;
  checkbox.listeners.change();
  await ui.respond(status({ agentic_mode: false }));
  assert.equal(checkbox.checked, true);
});

function textTree(node) {
  // Local context: collect nested runtime-row text without pretending that
  // this lightweight test DOM implements a browser's layout engine.
  return [node.textContent, ...node.children.map(textTree)].join(" ");
}

test("enforcer reports termination requests and fixed delays without asserting exits", async () => {
  const ui = dashboard();
  const runtime = { running: true, loops: { enforcer: {
    enabled: true, interval_s: 3, phase: "waiting",
    last_result: { status: "active", killed_processes: [] },
  } } };
  await ui.respond(status({ runtime }));
  let text = textTree(ui.get("runtime-loops"));
  assert.match(text, /No process termination requests succeeded/);
  assert.match(text, /3s after each run/);
  runtime.loops.enforcer.last_result.killed_processes = ["discord.exe"];
  ui.poll();
  await ui.respond(status({ runtime }));
  text = textTree(ui.get("runtime-loops"));
  assert.match(text, /Termination requested: discord.exe/);
  assert.doesNotMatch(text, /Stopped:|No target apps found/);
});

test("polling waits for completion, avoids overlap, and skips hidden tabs", async () => {
  const ui = dashboard();
  assert.equal(ui.requests.length, 1);
  assert.equal(ui.timers.size, 0);
  ui.windowListeners.online();
  assert.equal(ui.requests.length, 1);
  await ui.respond(status());
  assert.equal(ui.timers.size, 1);
  assert.equal([...ui.timers.values()][0].delay, 3000);
  ui.document.hidden = true;
  ui.poll();
  assert.equal(ui.requests.length, 0);
  ui.document.hidden = false;
  ui.documentListeners.visibilitychange();
  assert.equal(ui.requests.length, 1);
  await ui.respond(status());
});
