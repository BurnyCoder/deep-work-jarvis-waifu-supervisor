/*
 * Realtime dashboard renderer.
 * Global context: Flask owns state transitions; this browser code only reads
 * /status, renders with textContent, and keeps countdowns smooth between polls.
 * Fetch docs: https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API
 */

(() => {
  "use strict";

  const POLL_INTERVAL_MS = 3000;
  const CLOCK_INTERVAL_MS = 1000;
  const LOOP_LABELS = {
    monitor: "Productivity monitor",
    enforcer: "App and break enforcer",
    agent_watch: "AI agent watcher",
  };

  let latestStatus = null;
  let fetchedAtMs = 0;
  let pollTimer = null;
  let requestInFlight = false;
  let renderedHistorySignature = "";
  let latestAnnouncedVerdictTs = null;
  let hadActiveGoalAccess = false;

  const byId = (id) => document.getElementById(id);

  function setText(id, value) {
    const element = byId(id);
    if (element) {
      // textContent treats all LLM output as text, never executable markup:
      // https://developer.mozilla.org/en-US/docs/Web/API/Node/textContent
      element.textContent = value;
    }
  }

  function elapsedSinceFetch() {
    return fetchedAtMs ? Math.max(0, Math.floor((Date.now() - fetchedAtMs) / 1000)) : 0;
  }

  function formatElapsed(totalSeconds) {
    const seconds = Math.max(0, Number(totalSeconds) || 0);
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    return hours ? `${hours}h ${String(minutes).padStart(2, "0")}m` : `${minutes}m`;
  }

  function formatCountdown(totalSeconds) {
    const seconds = Math.max(0, Number(totalSeconds) || 0);
    const minutes = Math.floor(seconds / 60);
    const remainder = Math.floor(seconds % 60);
    return minutes ? `${minutes}m ${String(remainder).padStart(2, "0")}s` : `${remainder}s`;
  }

  function formatCadence(totalSeconds) {
    const seconds = Number(totalSeconds) || 0;
    if (seconds >= 60 && seconds % 60 === 0) {
      const minutes = seconds / 60;
      return `every ${minutes} min`;
    }
    return `every ${seconds}s`;
  }

  function formatClock(isoTimestamp) {
    if (!isoTimestamp) {
      return "never";
    }
    const parsed = new Date(isoTimestamp);
    if (Number.isNaN(parsed.getTime())) {
      return "unknown";
    }
    return parsed.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }

  function titleCase(value) {
    return String(value || "")
      .replaceAll("_", " ")
      .replace(/\b\w/g, (letter) => letter.toUpperCase());
  }

  function accessLabels(access) {
    // Prefer canonical group labels and keys. The split site/app fields keep
    // older status payloads readable during a rolling local upgrade.
    const canonicalLabels = Array.isArray(access?.allowed_group_labels)
      ? access.allowed_group_labels
      : [];
    const canonicalGroups = Array.isArray(access?.allowed_groups)
      ? access.allowed_groups.map(titleCase)
      : [];
    const legacySiteLabels = Array.isArray(access?.allowed_site_labels)
      ? access.allowed_site_labels
      : Array.isArray(access?.allowed_sites)
        ? access.allowed_sites.map(titleCase)
        : [];
    const legacyAppLabels = Array.isArray(access?.allowed_app_labels)
      ? access.allowed_app_labels
      : Array.isArray(access?.allowed_apps)
        ? access.allowed_apps.map(titleCase)
        : [];
    const candidates = canonicalLabels.length
      ? canonicalLabels
      : canonicalGroups.length
        ? canonicalGroups
        : [...legacySiteLabels, ...legacyAppLabels];
    // Set preserves insertion order while preventing a dual Web + App group
    // such as Discord from appearing twice in a legacy split payload:
    // https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Set
    return [...new Set(candidates.map(String).filter(Boolean))];
  }

  function setConnection(state, label) {
    const badge = byId("connection-status");
    if (badge) {
      badge.dataset.state = state;
    }
    setText("connection-label", label);
  }

  function renderHeader(status) {
    const mode = status.mode || "off";
    const pill = byId("mode-pill");
    const dashboard = byId("live-dashboard");
    if (pill) {
      pill.dataset.mode = mode;
      pill.textContent = mode.toUpperCase();
    }
    if (dashboard) {
      dashboard.dataset.mode = mode;
    }
    setText("current-topic", status.topic || "No active topic");
  }

  function renderMetrics(status) {
    const history = status.evaluation_history || [];
    const productiveCount = history.filter((item) => item.productive).length;
    const total = history.length;
    const rate = total ? Math.round((productiveCount / total) * 100) : 0;
    const remaining = Number(status.social_minutes_remaining) || 0;
    const cap = Math.max(1, Number(status.social_minutes_cap) || 1);
    const progress = byId("social-progress");

    setText("productive-streak", `${status.productive_streak_min || 0} min`);
    setText("social-remaining", `${remaining} of ${cap} min`);
    setText("evaluation-count", String(total));
    setText(
      "evaluation-summary",
      total
        ? `${productiveCount} productive · ${rate}% of checks`
        : "Waiting for the first evaluation.",
    );
    setText("history-total", `${total} ${total === 1 ? "check" : "checks"}`);

    if (progress) {
      progress.max = cap;
      progress.value = Math.min(cap, remaining);
      progress.setAttribute(
        "aria-label",
        `${remaining} of ${cap} social allowance minutes remaining`,
      );
    }
  }

  function renderConditions(status) {
    const br = status.break;
    const stopBreakForm = byId("stop-break-form");
    if (stopBreakForm) {
      // The server renders the initial state; polling also hides the control
      // when the watchdog expires a break without a page navigation.
      stopBreakForm.classList.toggle("is-hidden", !br);
    }
    if (br) {
      setText("break-state", br.purpose || "Active break");
    } else {
      setText("break-state", "None");
      setText("break-detail", "No active break.");
    }

    if (!status.agentic_mode) {
      setText("agent-state", "Off");
      setText("agent-detail", "Standard focus monitoring.");
    } else if (status.agent_busy) {
      setText("agent-state", "Agent working");
      setText("agent-detail", "Website restrictions are temporarily open.");
    } else {
      setText("agent-state", "Agent idle");
      setText("agent-detail", "Focus monitoring and blocking are active.");
    }

    const workAccess = status.work_access || {};
    const workGroupLabels = accessLabels(workAccess);
    setText(
      "project-state",
      workGroupLabels.length ? workGroupLabels.join(", ") : "None",
    );
    const presetDetail = workAccess.project
      ? `Preset: ${workAccess.project}. `
      : "";
    let accessDetail = "No work-required access groups allowed.";
    if (workGroupLabels.length && status.mode === "off") {
      accessDetail = `${presetDetail}Last session task access; enforcement is off.`;
    } else if (workGroupLabels.length && status.mode === "break") {
      accessDetail = `${presetDetail}Task access groups remain available; monitoring is paused for the break.`;
    } else if (workGroupLabels.length) {
      accessDetail = `${presetDetail}Work-required access groups remain available; monitoring stays active.`;
    }
    setText(
      "project-detail",
      accessDetail,
    );
    const enforcement = status.enforcement || {};
    setText(
      "blocked-domains",
      enforcement.reconciliation_pending
        ? "Pending"
        : enforcement.hosts_active
          ? String(enforcement.blocked_domain_count || 0)
          : "Off",
    );
    setText(
      "watched-processes",
      enforcement.app_killer_active ? String(enforcement.target_process_count || 0) : "Off",
    );
  }

  function syncGoalAccessDuration() {
    const mode = byId("goal-access-duration-mode");
    const minutes = byId("goal-access-minutes");
    const field = byId("goal-access-minutes-field");
    if (!mode || !minutes || !field) {
      return;
    }
    const isTimed = mode.value === "timed";
    // Disabled controls are omitted from form submission, matching the server's
    // `None` representation for access that lasts until the session ends:
    // https://developer.mozilla.org/en-US/docs/Web/HTML/Attributes/disabled
    minutes.disabled = !isTimed;
    minutes.required = isTimed;
    field.dataset.durationDisabled = String(!isTimed);
  }

  function renderGoalAccess(status) {
    const access = status.goal_access;
    const form = byId("goal-access-form");
    const activePanel = byId("goal-access-active");
    const submit = byId("goal-access-submit");
    const stateBadge = byId("goal-access-state");
    const reconciliationPending = Boolean(
      status.enforcement?.reconciliation_pending,
    );

    if (form) {
      form.classList.toggle("is-hidden", Boolean(access));
    }
    if (activePanel) {
      activePanel.classList.toggle("is-hidden", !access);
    }
    if (submit) {
      submit.disabled = status.mode !== "on" || Boolean(access);
    }

    if (!access) {
      if (hadActiveGoalAccess && form) {
        // Automatic expiry happens without navigation. Resetting only on the
        // active-to-idle transition makes the same card ready for another grant.
        form.reset();
        syncGoalAccessDuration();
      }
      hadActiveGoalAccess = false;
      if (stateBadge) {
        stateBadge.dataset.state = reconciliationPending ? "pending" : "idle";
      }
      setText(
        "goal-access-state",
        reconciliationPending ? "Policy update pending" : "Ready",
      );
      setText(
        "goal-access-form-state",
        reconciliationPending
          ? "Access enforcement is retrying the latest policy automatically."
          : status.mode === "on"
          ? "Ready for a goal-based access grant."
          : status.mode === "break"
            ? "Finish the current break before starting another grant."
            : "Start a focused session before requesting temporary access.",
      );
      return;
    }

    hadActiveGoalAccess = true;
    const labels = accessLabels(access);
    if (stateBadge) {
      stateBadge.dataset.state = reconciliationPending
        ? "pending"
        : access.suspended
          ? "suspended"
          : "active";
    }
    setText(
      "goal-access-state",
      reconciliationPending
        ? "Policy update pending"
        : access.suspended
          ? "Suspended for break"
          : "Active",
    );
    setText("goal-access-current-goal", access.goal || "Temporary access goal");
    setText("goal-access-groups", labels.length ? labels.join(", ") : "None");
  }

  function createVerdictItem(item, index, openEvidence) {
    const listItem = document.createElement("li");
    const article = document.createElement("article");
    const header = document.createElement("div");
    const meta = document.createElement("div");
    const badge = document.createElement("span");
    const time = document.createElement("time");
    const reason = document.createElement("p");
    const productive = Boolean(item.productive);

    listItem.className = "timeline-item";
    listItem.dataset.productive = String(productive);
    article.className = "verdict-card";
    article.dataset.latest = String(index === 0);
    header.className = "verdict-header";
    meta.className = "verdict-meta";
    badge.className = "verdict-badge";
    badge.dataset.productive = String(productive);
    badge.textContent = productive ? "Productive" : "Off track";
    time.className = "verdict-time";
    time.dateTime = item.ts || "";
    time.textContent = formatClock(item.ts);
    reason.className = "verdict-reason";
    reason.textContent = item.reason || "No reason was returned.";

    meta.append(badge, time);
    header.append(meta);
    if (index === 0) {
      const latest = document.createElement("span");
      latest.className = "latest-label";
      latest.textContent = "Latest";
      header.append(latest);
      article.setAttribute("aria-current", "true");
    }
    article.append(header, reason);

    if (item.observed) {
      // Native details/summary provides an accessible disclosure without a
      // custom widget: https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/details
      const details = document.createElement("details");
      const summary = document.createElement("summary");
      const observed = document.createElement("p");
      details.dataset.ts = item.ts || "";
      details.open = openEvidence.has(details.dataset.ts);
      summary.textContent = "What the monitor saw";
      observed.className = "verdict-observed";
      observed.textContent = item.observed;
      details.append(summary, observed);
      article.append(details);
    }

    listItem.append(article);
    return listItem;
  }

  function renderHistory(history) {
    const items = history || [];
    const signature = JSON.stringify(
      items.map((item) => [item.ts, item.productive, item.reason, item.observed]),
    );
    if (signature === renderedHistorySignature) {
      return;
    }

    const list = byId("evaluation-history");
    const empty = byId("history-empty");
    if (!list || !empty) {
      return;
    }

    const openEvidence = new Set(
      Array.from(list.querySelectorAll("details[open]"), (details) => details.dataset.ts),
    );
    const fragment = document.createDocumentFragment();
    items.forEach((item, index) => {
      fragment.append(createVerdictItem(item, index, openEvidence));
    });
    list.replaceChildren(fragment);
    list.classList.toggle("is-hidden", items.length === 0);
    empty.classList.toggle("is-hidden", items.length > 0);
    renderedHistorySignature = signature;

    const newest = items[0];
    if (newest && latestAnnouncedVerdictTs && newest.ts !== latestAnnouncedVerdictTs) {
      setText(
        "dashboard-announcement",
        `New productivity evaluation: ${newest.productive ? "productive" : "off track"}. ${newest.reason}`,
      );
    }
    latestAnnouncedVerdictTs = newest ? newest.ts : null;
  }

  function summarizeLoopResult(name, result) {
    if (!result) {
      return "No completed run yet.";
    }
    if (name === "enforcer") {
      const killed = result.killed_processes || [];
      if (killed.length) {
        return `Stopped: ${killed.join(", ")}`;
      }
      return result.status === "off" ? "Enforcement is off." : "No target apps found.";
    }
    if (name === "monitor") {
      return `Last result: ${titleCase(result.status)}`;
    }
    if (name === "agent_watch") {
      return `Last result: ${titleCase(result.status)}`;
    }
    return `Last result: ${titleCase(result.status)}`;
  }

  function createRuntimeRow(name, loop) {
    const row = document.createElement("article");
    const header = document.createElement("div");
    const title = document.createElement("p");
    const phase = document.createElement("span");
    const detail = document.createElement("p");
    const result = document.createElement("p");

    row.className = "runtime-row";
    header.className = "runtime-row-header";
    title.className = "runtime-name";
    title.textContent = LOOP_LABELS[name] || titleCase(name);
    phase.className = "loop-phase";
    phase.dataset.phase = loop.phase || "stopped";
    phase.textContent = titleCase(loop.phase || "stopped");
    detail.className = "runtime-detail";
    detail.textContent = `${formatCadence(loop.interval_s)} · last ${formatClock(loop.last_finished_at)}`;
    result.className = "runtime-result";
    result.textContent = summarizeLoopResult(name, loop.last_result);

    header.append(title, phase);
    row.append(header, detail, result);

    const next = document.createElement("p");
    next.className = "runtime-detail";
    next.id = `loop-next-${name}`;
    row.append(next);

    if (loop.last_error) {
      const error = document.createElement("p");
      error.className = "runtime-error";
      error.textContent = `Error: ${loop.last_error}`;
      row.append(error);
    }
    return row;
  }

  function renderOperations(runtime) {
    const container = byId("runtime-loops");
    if (!container) {
      return;
    }
    const snapshot = runtime || { running: false, loops: {} };
    const fragment = document.createDocumentFragment();
    Object.entries(snapshot.loops || {}).forEach(([name, loop]) => {
      fragment.append(createRuntimeRow(name, loop));
    });
    container.replaceChildren(fragment);
    setText("scheduler-state", snapshot.running ? "Running" : "Stopped");
  }

  function renderStatus(status) {
    renderHeader(status);
    renderMetrics(status);
    renderConditions(status);
    renderGoalAccess(status);
    renderHistory(status.evaluation_history);
    renderOperations(status.runtime);
    updateLiveClocks();
  }

  function loopCountdownText(loop, delta) {
    if (!loop || !loop.enabled) {
      return "Disabled";
    }
    if (loop.phase === "running") {
      return "Running now";
    }
    if (loop.next_due_in_s === null || loop.next_due_in_s === undefined) {
      return loop.phase === "stopped" ? "Stopped" : "Waiting";
    }
    return `Next in ${formatCountdown(Math.max(0, loop.next_due_in_s - delta))}`;
  }

  function updateLiveClocks() {
    if (!latestStatus) {
      return;
    }
    const delta = elapsedSinceFetch();
    const sessionElapsed = Number(latestStatus.session_elapsed_s) || 0;
    const sessionStillRunning = latestStatus.mode !== "off";
    setText(
      "session-elapsed",
      formatElapsed(sessionElapsed + (sessionStillRunning ? delta : 0)),
    );

    const monitor = latestStatus.runtime?.loops?.monitor;
    if (!latestStatus.monitoring_active) {
      setText("monitoring-status", latestStatus.monitoring_pause_reason || "Paused");
      setText("next-evaluation", "Paused");
    } else if (monitor?.phase === "running") {
      setText("monitoring-status", "Evaluating now");
      setText("next-evaluation", "In progress");
    } else {
      setText("monitoring-status", "Active");
      setText(
        "next-evaluation",
        monitor?.next_due_in_s === null || monitor?.next_due_in_s === undefined
          ? "Waiting"
          : `in ${formatCountdown(Math.max(0, monitor.next_due_in_s - delta))}`,
      );
    }

    if (latestStatus.break) {
      const remaining = Math.max(0, Number(latestStatus.break.remaining_s) - delta);
      const allowanceLabels = accessLabels(latestStatus.break);
      const allowanceText = allowanceLabels.length
        ? ` · Allowed: ${allowanceLabels.join(", ")}`
        : "";
      setText(
        "break-detail",
        `${titleCase(latestStatus.break.kind)} · ${formatCountdown(remaining)} remaining${allowanceText}`,
      );
    }

    const goalAccess = latestStatus.goal_access;
    if (goalAccess) {
      const suspension = goalAccess.suspended
        ? " · grant permissions suspended during break; timer continues; another access scope may still keep an option available"
        : "";
      const timing = goalAccess.until_session_end
        ? `Until this focused session ends${suspension}`
        : `${formatCountdown(
            Math.max(0, Number(goalAccess.remaining_s) - delta),
          )} remaining${suspension}`;
      setText("goal-access-timing", timing);
    }

    Object.entries(latestStatus.runtime?.loops || {}).forEach(([name, loop]) => {
      setText(`loop-next-${name}`, loopCountdownText(loop, delta));
    });
    setText(
      "last-updated",
      fetchedAtMs
        ? new Date(fetchedAtMs).toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
          })
        : "—",
    );
  }

  function schedulePoll() {
    window.clearTimeout(pollTimer);
    pollTimer = window.setTimeout(fetchStatus, POLL_INTERVAL_MS);
  }

  async function fetchStatus() {
    if (requestInFlight || document.hidden) {
      schedulePoll();
      return;
    }

    requestInFlight = true;
    try {
      const response = await fetch("/status", {
        cache: "no-store",
        headers: { Accept: "application/json" },
      });
      if (!response.ok) {
        throw new Error(`Status request failed with HTTP ${response.status}`);
      }
      latestStatus = await response.json();
      fetchedAtMs = Date.now();
      renderStatus(latestStatus);
      setConnection("live", "Live");
    } catch (error) {
      // Preserve the last successful dashboard instead of replacing it with a
      // blank screen; the next recursive poll retries automatically.
      setConnection("reconnecting", "Reconnecting");
      console.error("dashboard status refresh failed", error);
    } finally {
      requestInFlight = false;
      schedulePoll();
    }
  }

  // Hidden tabs do not need network polling; refresh immediately on return:
  // https://developer.mozilla.org/en-US/docs/Web/API/Page_Visibility_API
  document.addEventListener("visibilitychange", () => {
    window.clearTimeout(pollTimer);
    if (document.hidden) {
      setConnection("loading", "Paused");
    } else {
      fetchStatus();
    }
  });
  window.addEventListener("online", fetchStatus);
  window.addEventListener("offline", () => {
    setConnection("reconnecting", "Offline");
  });

  const goalAccessDurationMode = byId("goal-access-duration-mode");
  if (goalAccessDurationMode) {
    goalAccessDurationMode.addEventListener("change", syncGoalAccessDuration);
  }
  syncGoalAccessDuration();
  window.setInterval(updateLiveClocks, CLOCK_INTERVAL_MS);
  fetchStatus();
})();
