const logPane = document.getElementById("live-log");
const scenarioList = document.getElementById("scenario-list");
const registryErrors = document.getElementById("registry-errors");
const fixtureToggle = document.getElementById("show-fixtures");
const runbookButton = document.getElementById("runbook-btn");
const modal = document.getElementById("doc-modal");
const modalTitle = document.getElementById("doc-title");
const modalMeta = document.getElementById("doc-meta");
const modalContent = document.getElementById("doc-content");
const modalCloseButton = document.getElementById("doc-close-btn");

let activeStream = null;
let visibleScenarios = [];

function appendLog(line) {
  const ts = new Date().toISOString();
  logPane.textContent += `[${ts}] ${line}\n`;
  logPane.scrollTop = logPane.scrollHeight;
}

function readCookie(name) {
  const cookie = document.cookie
    .split(";")
    .map((item) => item.trim())
    .find((item) => item.startsWith(`${name}=`));
  return cookie ? decodeURIComponent(cookie.split("=")[1]) : "";
}

function csrfHeader() {
  return { "X-CSRF-Token": readCookie("control_plane_csrf") };
}

function csrfQuery() {
  const token = encodeURIComponent(readCookie("control_plane_csrf"));
  return `csrf_token=${token}`;
}

async function apiPost(path, body) {
  const res = await fetch(path, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...csrfHeader(),
    },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.detail || `Request failed (${res.status})`);
  }
  return data;
}

async function apiGet(path) {
  const res = await fetch(path);
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.detail || `Request failed (${res.status})`);
  }
  return data;
}

function openStream(url) {
  if (activeStream) {
    activeStream.close();
    activeStream = null;
  }
  activeStream = new EventSource(url);
  activeStream.addEventListener("log", (event) => appendLog(event.data));
  activeStream.addEventListener("error", (event) => {
    appendLog(`ERROR: ${event.data || "stream failure"}`);
    activeStream.close();
    activeStream = null;
  });
  activeStream.addEventListener("done", (event) => {
    appendLog(`DONE: ${event.data}`);
    activeStream.close();
    activeStream = null;
  });
}

function closeDocumentModal() {
  modal.classList.add("hidden");
  modalContent.innerHTML = "";
  modalMeta.textContent = "";
}

function openDocumentModal({ title, meta, html, emptyMessage }) {
  modalTitle.textContent = title;
  modalMeta.textContent = meta || "";
  if (html && html.trim()) {
    modalContent.innerHTML = html;
  } else {
    const empty = document.createElement("p");
    empty.className = "doc-empty";
    empty.textContent = emptyMessage || "No content available.";
    modalContent.replaceChildren(empty);
  }
  modal.classList.remove("hidden");
}

function renderScenario(s) {
  const card = document.createElement("article");
  card.className = "scenario-card";
  const drivePrompt = s.drive_prompt || s.trigger?.params?.drive_prompt || "";

  const heading = document.createElement("h3");
  heading.textContent = s.id;
  card.appendChild(heading);

  const title = document.createElement("p");
  const strong = document.createElement("strong");
  strong.textContent = s.title;
  title.appendChild(strong);
  card.appendChild(title);

  const summary = document.createElement("p");
  summary.textContent = `Message: ${s.message} | Duration: ${s.duration_min} min`;
  card.appendChild(summary);

  const trigger = document.createElement("p");
  trigger.textContent = `Trigger: ${s.trigger.type} (ref=${s.trigger.ref})`;
  card.appendChild(trigger);

  const promptLabel = document.createElement("label");
  promptLabel.textContent = "Drive prompt";
  card.appendChild(promptLabel);

  const promptBlock = document.createElement("pre");
  promptBlock.className = "prompt-block";
  promptBlock.textContent = drivePrompt || "(No drive prompt configured.)";
  card.appendChild(promptBlock);

  const copyRow = document.createElement("div");
  copyRow.className = "copy-row";
  const copyButton = document.createElement("button");
  copyButton.type = "button";
  copyButton.className = "copy-btn";
  copyButton.textContent = "Copy prompt";
  copyButton.disabled = !drivePrompt;
  const copyStatus = document.createElement("span");
  copyStatus.className = "copy-status";
  copyRow.appendChild(copyButton);
  copyRow.appendChild(copyStatus);
  card.appendChild(copyRow);

  copyButton.addEventListener("click", async () => {
    if (!drivePrompt) {
      return;
    }
    try {
      await navigator.clipboard.writeText(drivePrompt);
      copyStatus.textContent = "Copied!";
      window.setTimeout(() => {
        copyStatus.textContent = "";
      }, 2000);
    } catch (err) {
      appendLog(`ERROR copying prompt for ${s.id}: ${err.message}`);
      copyStatus.textContent = "Copy failed";
    }
  });

  const scriptButton = document.createElement("button");
  scriptButton.type = "button";
  scriptButton.className = "script-btn";
  scriptButton.textContent = "View Demo Script";
  card.appendChild(scriptButton);
  scriptButton.addEventListener("click", () => {
    const scriptUrl = `/scenarios/${encodeURIComponent(s.id)}/script.html`;
    const opened = window.open(scriptUrl, "_blank", "noopener");
    if (!opened) {
      appendLog(`ERROR opening script for ${s.id}: popup blocked by browser.`);
    }
  });

  const actions = document.createElement("div");
  actions.className = "actions";
  const playButton = document.createElement("button");
  playButton.type = "button";
  playButton.className = "play-btn";
  playButton.textContent = "Play (SSE)";
  const resetButton = document.createElement("button");
  resetButton.type = "button";
  resetButton.className = "reset-btn";
  resetButton.textContent = "Reset";
  const verifyButton = document.createElement("button");
  verifyButton.type = "button";
  verifyButton.className = "verify-btn";
  verifyButton.textContent = "Verify (SSE)";
  actions.appendChild(playButton);
  actions.appendChild(resetButton);
  actions.appendChild(verifyButton);
  card.appendChild(actions);

  playButton.addEventListener("click", () => {
    const params = new URLSearchParams({
      id: s.id,
      no_drive: "true",
      ...Object.fromEntries(new URLSearchParams(csrfQuery())),
    });
    appendLog(`Starting setup-only play stream for ${s.id}`);
    openStream(`/api/play/stream?${params.toString()}`);
  });

  resetButton.addEventListener("click", async () => {
    appendLog(`Resetting ${s.id}`);
    try {
      const out = await apiPost("/api/reset", { id: s.id });
      appendLog(`Reset exit code ${out.exit_code}`);
      (out.output || []).forEach((line) => appendLog(line));
    } catch (err) {
      appendLog(`ERROR: ${err.message}`);
    }
  });

  verifyButton.addEventListener("click", () => {
    const params = new URLSearchParams({
      id: s.id,
      ...Object.fromEntries(new URLSearchParams(csrfQuery())),
    });
    appendLog(`Starting verify stream for ${s.id}`);
    openStream(`/api/verify/stream?${params.toString()}`);
  });

  return card;
}

async function refreshScenarios() {
  try {
    const params = new URLSearchParams({
      include_fixtures: fixtureToggle.checked ? "true" : "false",
    });
    const res = await fetch(`/api/list?${params.toString()}`);
    const data = await res.json();
    scenarioList.innerHTML = "";
    registryErrors.innerHTML = "";
    visibleScenarios = data.scenarios || [];

    visibleScenarios.forEach((scenario) => {
      scenarioList.appendChild(renderScenario(scenario));
    });
    if ((data.errors || []).length) {
      registryErrors.textContent = data.errors
        .map((e) => `${e.folder}: ${e.error}`)
        .join("\n");
    }
    appendLog(
      `Loaded ${data.scenarios.length} scenario(s). fixtures=${fixtureToggle.checked ? "on" : "off"}`,
    );
  } catch (err) {
    appendLog(`ERROR refreshing scenarios: ${err.message}`);
  }
}

document.getElementById("refresh-btn").addEventListener("click", refreshScenarios);
fixtureToggle.addEventListener("change", refreshScenarios);
runbookButton.addEventListener("click", async () => {
  runbookButton.disabled = true;
  runbookButton.textContent = "Loading Runbook...";
  try {
    const data = await apiGet("/api/runbook");
    openDocumentModal({
      title: data.title || "Runbook",
      meta: `Source: ${data.source_path}`,
      html: data.available ? data.html : "",
      emptyMessage: data.detail || "Runbook not available yet.",
    });
  } catch (err) {
    appendLog(`ERROR loading runbook: ${err.message}`);
  } finally {
    runbookButton.disabled = false;
    runbookButton.textContent = "Open Runbook";
  }
});
modalCloseButton.addEventListener("click", closeDocumentModal);
modal.addEventListener("click", (event) => {
  if (event.target === modal) {
    closeDocumentModal();
  }
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !modal.classList.contains("hidden")) {
    closeDocumentModal();
  }
});

document.getElementById("clear-log-btn").addEventListener("click", () => {
  logPane.textContent = "";
});

document.getElementById("verify-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const id = document.getElementById("verify-scenario").value.trim();
  const timeout = document.getElementById("verify-timeout").value.trim();
  const interval = document.getElementById("verify-interval").value.trim();
  const params = new URLSearchParams({
    id,
    timeout,
    interval,
    ...Object.fromEntries(new URLSearchParams(csrfQuery())),
  });
  appendLog(`Starting verify stream for ${id}`);
  openStream(`/api/verify/stream?${params.toString()}`);
});

refreshScenarios();
