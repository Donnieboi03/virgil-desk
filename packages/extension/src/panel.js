function truncateUrl(url) {
  if (!url) return "";
  try {
    const u = new URL(url);
    const path = u.pathname.length > 24 ? `${u.pathname.slice(0, 24)}…` : u.pathname;
    return `${u.hostname}${path}`;
  } catch {
    return url.slice(0, 40);
  }
}

let panelWsConnected = false;

function appendItemError(li, message) {
  const errEl = li.querySelector(".item-error");
  if (errEl) errEl.remove();
  if (!message) return;
  const err = document.createElement("div");
  err.className = "item-error";
  err.textContent = message;
  li.appendChild(err);
}

function appendEvidence(li, item) {
  const summary = item.evidence?.summary;
  if (!summary) return;
  const el = document.createElement("div");
  el.className = "item-evidence";
  el.textContent = summary.length > 120 ? `${summary.slice(0, 120)}…` : summary;
  el.title = summary;
  li.appendChild(el);
}

async function runAgentAction(item, li, runBtn) {
  runBtn.disabled = true;
  appendItemError(li, "");
  try {
    const result = await chrome.runtime.sendMessage({
      type: "runAgentItem",
      itemId: item.id,
      runId: item.run_id || "",
    });
    if (result.error || result.detail) {
      appendItemError(li, result.error || result.detail);
    }
  } catch (err) {
    appendItemError(li, String(err));
  } finally {
    runBtn.disabled = !panelWsConnected;
    refresh();
  }
}

function renderColumn(el, items, column) {
  el.innerHTML = "";
  for (const item of items) {
    const li = document.createElement("li");
    li.dataset.itemId = item.id || "";
    const badge = document.createElement("span");
    badge.className = `badge ${item.status || "proposed"}`;
    badge.textContent = item.status || "proposed";
    const title = document.createElement("div");
    title.className = "item-title";
    title.appendChild(badge);
    title.appendChild(document.createTextNode(item.title || "(untitled)"));
    li.appendChild(title);
    const url = item.source?.url;
    if (url) {
      const meta = document.createElement("div");
      meta.className = "item-meta";
      meta.textContent = truncateUrl(url);
      meta.title = url;
      li.appendChild(meta);
    }
    appendEvidence(li, item);
    if (item.last_error) {
      appendItemError(li, item.last_error);
    }
    const proposals = item.proposals || [];
    if (column === "agent") {
      const canRun =
        item.status === "running" ||
        item.status === "proposed" ||
        item.status === "failed";
      if (canRun) {
        const actions = document.createElement("div");
        actions.className = "item-actions";
        const runBtn = document.createElement("button");
        runBtn.textContent = item.status === "failed" ? "Retry agent" : "Run agent";
        runBtn.disabled = !panelWsConnected;
        runBtn.title = panelWsConnected ? "" : "Connect extension WS first";
        runBtn.onclick = () => runAgentAction(item, li, runBtn);
        actions.appendChild(runBtn);
        li.appendChild(actions);
      }
    } else if (
      column === "you" &&
      item.status !== "done" &&
      item.status !== "denied"
    ) {
      const actions = document.createElement("div");
      actions.className = "item-actions";
      const doneBtn = document.createElement("button");
      doneBtn.textContent = "Mark done";
      doneBtn.disabled = !panelWsConnected;
      doneBtn.title = panelWsConnected ? "" : "Connect extension WS first";
      doneBtn.onclick = async () => {
        doneBtn.disabled = true;
        appendItemError(li, "");
        try {
          const result = await chrome.runtime.sendMessage({
            type: "completeItem",
            itemId: item.id,
            runId: item.run_id || "",
          });
          if (result.error || result.detail) {
            appendItemError(li, result.error || result.detail);
          }
        } catch (err) {
          appendItemError(li, String(err));
        } finally {
          doneBtn.disabled = !panelWsConnected;
          refresh();
        }
      };
      actions.appendChild(doneBtn);
      li.appendChild(actions);
    } else if (column === "waiting" && (proposals.length || item.status === "proposed")) {
      const actions = document.createElement("div");
      actions.className = "item-actions";
      if (item.status !== "done" && item.status !== "denied") {
        const accept = document.createElement("button");
        accept.textContent = "Accept";
        accept.disabled = !panelWsConnected;
        accept.onclick = async () => {
          await chrome.runtime.sendMessage({
            type: "acceptProposal",
            itemId: item.id,
            proposalId: proposals[0]?.id || "",
            runId: item.run_id || "",
          });
          refresh();
        };
        const deny = document.createElement("button");
        deny.textContent = "Deny";
        deny.disabled = !panelWsConnected;
        deny.onclick = async () => {
          await chrome.runtime.sendMessage({
            type: "denyProposal",
            itemId: item.id,
            proposalId: proposals[0]?.id || "",
            runId: item.run_id || "",
            reason: "operator denied",
          });
          refresh();
        };
        actions.appendChild(accept);
        actions.appendChild(deny);
      }
      li.appendChild(actions);
    } else if (proposals.length) {
      for (const p of proposals) {
        const accept = document.createElement("button");
        accept.textContent = "Accept";
        accept.disabled = !panelWsConnected;
        accept.onclick = () =>
          chrome.runtime.sendMessage({
            type: "acceptProposal",
            itemId: item.id,
            proposalId: p.id,
            runId: item.run_id || "",
          });
        li.appendChild(accept);
      }
    }
    el.appendChild(li);
  }
}

function setText(id, text, cls) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = text;
  el.className = cls || "";
}

function showDecomposition(text) {
  const el = document.getElementById("decomposition");
  if (!text) {
    el.classList.add("hidden");
    return;
  }
  el.textContent = text;
  el.classList.remove("hidden");
}

function showRunId(runId) {
  const wrap = document.getElementById("last-handoff");
  const code = document.getElementById("run-id");
  if (!runId) {
    wrap.classList.add("hidden");
    return;
  }
  code.textContent = runId;
  wrap.classList.remove("hidden");
}

function showHandoffError(msg) {
  const el = document.getElementById("handoff-error");
  if (!msg) {
    el.classList.add("hidden");
    return;
  }
  el.textContent = msg;
  el.classList.remove("hidden");
}

function updateActionButtons() {
  const handoffBtn = document.getElementById("handoff");
  if (handoffBtn) {
    handoffBtn.disabled = !panelWsConnected;
    handoffBtn.title = panelWsConnected ? "" : "WS disconnected — wait for connection";
  }
}

async function refreshStatus() {
  const health = await chrome.runtime.sendMessage({ type: "getHealth" });
  const hostEl = document.getElementById("host-status");
  const wsEl = document.getElementById("ws-status");
  const backendEl = document.getElementById("backend-status");
  panelWsConnected = Boolean(health.wsConnected);
  if (health.ok) {
    hostEl.textContent = "Host OK";
    hostEl.className = "ok";
    backendEl.textContent = `backend: ${health.health?.agent_backend || "?"}`;
  } else {
    hostEl.textContent = "Host down";
    hostEl.className = "bad";
    backendEl.textContent = "";
  }
  wsEl.textContent = health.wsConnected ? "WS connected" : "WS disconnected";
  wsEl.className = health.wsConnected ? "ok" : "bad";
  updateActionButtons();
}

async function refreshMeta() {
  const meta = await chrome.runtime.sendMessage({ type: "getPanelMeta" });
  showDecomposition(meta.lastDecomposition);
  showRunId(meta.lastRunId);
  showHandoffError(meta.lastHandoffError);
}

async function refresh() {
  const { board } = await chrome.runtime.sendMessage({ type: "getBoard" });
  renderColumn(document.getElementById("col-you"), board.you || [], "you");
  renderColumn(document.getElementById("col-agent"), board.agent || [], "agent");
  renderColumn(
    document.getElementById("col-waiting"),
    board.waiting || [],
    "waiting",
  );
  await refreshStatus();
  await refreshMeta();
}

const handoffBtn = document.getElementById("handoff");
handoffBtn.addEventListener("click", async () => {
  if (!panelWsConnected) {
    showHandoffError("WS disconnected — cannot hand off");
    return;
  }
  handoffBtn.disabled = true;
  showHandoffError("");
  try {
    const result = await chrome.runtime.sendMessage({ type: "handoffTab" });
    if (result.error) {
      showHandoffError(result.error);
    }
    if (result.decomposition) {
      showDecomposition(result.decomposition);
    }
    if (result.run_id) {
      showRunId(result.run_id);
    }
  } catch (err) {
    showHandoffError(String(err));
  } finally {
    handoffBtn.disabled = !panelWsConnected;
    await refresh();
  }
});

document.getElementById("copy-run-id")?.addEventListener("click", async () => {
  const meta = await chrome.runtime.sendMessage({ type: "getPanelMeta" });
  if (meta.lastRunId) {
    await navigator.clipboard.writeText(meta.lastRunId);
  }
});

chrome.runtime.onMessage.addListener((msg) => {
  if (msg.type === "boardUpdated" || msg.type === "panelMetaUpdated") {
    refresh();
  }
  if (msg.type === "connectionUpdated") {
    panelWsConnected = msg.wsConnected;
    refreshStatus().then(() => refresh());
  }
});

refresh();
