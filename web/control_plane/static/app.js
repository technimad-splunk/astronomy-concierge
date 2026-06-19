const logPane = document.getElementById("live-log");
const scenarioList = document.getElementById("scenario-list");
const registryErrors = document.getElementById("registry-errors");
const playlistOutput = document.getElementById("playlist-output");

let activeStream = null;

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

function renderScenario(s) {
  const card = document.createElement("article");
  card.className = "scenario-card";

  const prompt = s.trigger.params.drive_prompt || "";
  card.innerHTML = `
    <h3>${s.id}</h3>
    <p><strong>${s.title}</strong></p>
    <p>Message: ${s.message} | Duration: ${s.duration_min} min</p>
    <p>Trigger: ${s.trigger.type} (ref=${s.trigger.ref})</p>
    <label>Prompt override</label>
    <input type="text" class="prompt-input" placeholder="${prompt}" />
    <div class="actions">
      <button type="button" class="play-btn">Play (SSE)</button>
      <button type="button" class="reset-btn">Reset</button>
      <button type="button" class="verify-btn">Verify (SSE)</button>
    </div>
  `;

  card.querySelector(".play-btn").addEventListener("click", () => {
    const promptInput = card.querySelector(".prompt-input").value.trim();
    const params = new URLSearchParams({
      id: s.id,
      ...(promptInput ? { prompt: promptInput } : {}),
      ...Object.fromEntries(new URLSearchParams(csrfQuery())),
    });
    appendLog(`Starting play stream for ${s.id}`);
    openStream(`/api/play/stream?${params.toString()}`);
  });

  card.querySelector(".reset-btn").addEventListener("click", async () => {
    appendLog(`Resetting ${s.id}`);
    try {
      const out = await apiPost("/api/reset", { id: s.id });
      appendLog(`Reset exit code ${out.exit_code}`);
      (out.output || []).forEach((line) => appendLog(line));
    } catch (err) {
      appendLog(`ERROR: ${err.message}`);
    }
  });

  card.querySelector(".verify-btn").addEventListener("click", () => {
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
    const res = await fetch("/api/list");
    const data = await res.json();
    scenarioList.innerHTML = "";
    registryErrors.innerHTML = "";

    (data.scenarios || []).forEach((scenario) => {
      scenarioList.appendChild(renderScenario(scenario));
    });
    if ((data.errors || []).length) {
      registryErrors.textContent = data.errors
        .map((e) => `${e.folder}: ${e.error}`)
        .join("\n");
    }
    appendLog(`Loaded ${data.scenarios.length} scenario(s).`);
  } catch (err) {
    appendLog(`ERROR refreshing scenarios: ${err.message}`);
  }
}

document.getElementById("refresh-btn").addEventListener("click", refreshScenarios);

document.getElementById("clear-log-btn").addEventListener("click", () => {
  logPane.textContent = "";
});

document.getElementById("playlist-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const messageRaw = document.getElementById("playlist-messages").value.trim();
  const budgetRaw = document.getElementById("playlist-budget").value.trim();
  const message = messageRaw
    ? messageRaw.split(",").map((item) => item.trim()).filter(Boolean)
    : null;
  const budget = budgetRaw ? parseInt(budgetRaw, 10) : null;

  try {
    const out = await apiPost("/api/playlist", { message, budget });
    playlistOutput.textContent = JSON.stringify(out, null, 2);
    appendLog(`Composed playlist with ${out.count} scenario(s).`);
  } catch (err) {
    appendLog(`ERROR composing playlist: ${err.message}`);
  }
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
