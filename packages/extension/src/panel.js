import {
  childChecklist,
  itemsForColumn,
  groupsForFollowColumn,
  followGroupShouldOpen,
} from "./panelBoard.js";

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

function statusLabel(status) {
  if (status === "awaiting_human") return "awaiting you";
  return status || "proposed";
}

/** Clickable destination URL for You parks (URL-first handoff). */
function appendSourceUrl(container, url) {
  if (!url) return;
  const meta = document.createElement("div");
  meta.className = "item-meta";
  const link = document.createElement("a");
  link.href = url;
  link.className = "item-url";
  link.textContent = truncateUrl(url);
  link.title = url;
  link.addEventListener("click", async (ev) => {
    ev.preventDefault();
    try {
      await chrome.tabs.create({ url, active: true });
    } catch {
      window.open(url, "_blank", "noopener,noreferrer");
    }
  });
  meta.appendChild(link);
  const openBtn = document.createElement("button");
  openBtn.type = "button";
  openBtn.className = "item-open-url";
  openBtn.textContent = "Open";
  openBtn.title = "Open in Chrome";
  openBtn.addEventListener("click", async () => {
    try {
      await chrome.tabs.create({ url, active: true });
    } catch (err) {
      console.warn(err);
    }
  });
  meta.appendChild(document.createTextNode(" "));
  meta.appendChild(openBtn);
  container.appendChild(meta);
}

let panelWsConnected = false;
let handoffTargetTabId = null;

async function resolveHandoffTabId() {
  const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  handoffTargetTabId = tab?.id && !tab.url?.startsWith("chrome-extension://") ? tab.id : null;
  return handoffTargetTabId;
}

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

async function findBoardItem(itemId) {
  const { board } = await chrome.runtime.sendMessage({ type: "getBoard" });
  for (const col of ["you", "agent", "waiting"]) {
    const hit = (board[col] || []).find((i) => i.id === itemId);
    if (hit) return hit;
  }
  return null;
}

async function runAgentAction(item, li, runBtn) {
  runBtn.disabled = true;
  runBtn.textContent = "Running…";
  appendItemError(li, "");
  try {
    const result = await chrome.runtime.sendMessage({
      type: "runAgentItem",
      itemId: item.id,
      runId: item.run_id || "",
    });
    if (result?.error || result?.detail) {
      appendItemError(li, result.error || result.detail);
    }
  } catch (err) {
    appendItemError(li, String(err));
  } finally {
    await refreshStatus();
    await refreshBoard();
    const updated = await findBoardItem(item.id);
    const status = updated?.status || item.status;
    if (updated?.last_error) {
      appendItemError(li, updated.last_error);
    }
    if (status === "failed") runBtn.textContent = "Retry agent";
    else if (status === "proposed" && updated?.resume_ready) runBtn.textContent = "Resume agent";
    else runBtn.textContent = "Run agent";
    runBtn.disabled = !panelWsConnected || status === "done" || status === "awaiting_human";
  }
}

function appendChildRow(ul, child) {
  const cli = document.createElement("li");
  const cb = document.createElement("span");
  cb.className = `badge ${child.status || "proposed"}`;
  cb.textContent = statusLabel(child.status);
  cli.appendChild(cb);
  cli.appendChild(document.createTextNode(` ${child.title || "(untitled)"}`));
  appendSourceUrl(cli, child.source?.url);
  if (child.last_error) {
    const err = document.createElement("div");
    err.className = "item-error";
    err.textContent = child.last_error;
    cli.appendChild(err);
  }
  ul.appendChild(cli);
}

function appendItemActions(li, item, column) {
  if (column === "agent") {
    const canRun =
      !item.parent_id &&
      (item.status === "running" ||
        item.status === "proposed" ||
        item.status === "failed");
    if (item.status === "awaiting_human") {
      const note = document.createElement("div");
      note.className = "item-meta item-awaiting";
      note.textContent = "Waiting on you — open You card URL, then Mark done to Resume";
      li.appendChild(note);
      return;
    }
    if (canRun) {
      const actions = document.createElement("div");
      actions.className = "item-actions";
      const runBtn = document.createElement("button");
      if (item.status === "failed") runBtn.textContent = "Retry agent";
      else if (item.status === "proposed" && item.resume_ready) runBtn.textContent = "Resume agent";
      else runBtn.textContent = "Run agent";
      runBtn.disabled = !panelWsConnected;
      runBtn.title = panelWsConnected ? "" : "Connect extension WS first";
      runBtn.onclick = () => runAgentAction(item, li, runBtn);
      actions.appendChild(runBtn);
      li.appendChild(actions);
    }
    return;
  }
  if (column === "you" && item.status !== "done" && item.status !== "denied") {
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
    return;
  }
  if (column === "waiting" && ((item.proposals || []).length || item.status === "proposed")) {
    const proposals = item.proposals || [];
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
    return;
  }
  if ((item.proposals || []).length) {
    for (const p of item.proposals) {
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
}

function renderItemCard(item, column, columnItems, { showFrom = false, byId = {} } = {}) {
  const li = document.createElement("li");
  li.dataset.itemId = item.id || "";
  if (column === "agent") {
    li.classList.add("item-parent");
  }
  const badge = document.createElement("span");
  badge.className = `badge ${item.status || "proposed"}`;
  badge.textContent = statusLabel(item.status);
  const title = document.createElement("div");
  title.className = "item-title";
  title.appendChild(badge);
  title.appendChild(document.createTextNode(item.title || "(untitled)"));
  li.appendChild(title);
  appendSourceUrl(li, item.source?.url);
  if (showFrom && item.parent_id && byId[item.parent_id]) {
    const from = document.createElement("div");
    from.className = "item-meta item-from";
    from.textContent = `from: ${byId[item.parent_id].title || item.parent_id}`;
    li.appendChild(from);
  }
  appendEvidence(li, item);
  if (item.last_error) {
    appendItemError(li, item.last_error);
  }
  if (column === "agent") {
    const kids = childChecklist(columnItems, item.id);
    if (kids.length) {
      const details = document.createElement("details");
      details.className = "item-accordion";
      details.open = kids.some((k) => k.status === "proposed" || k.status === "running");
      const summary = document.createElement("summary");
      summary.textContent = `Subtasks (${kids.length})`;
      details.appendChild(summary);
      const ul = document.createElement("ul");
      ul.className = "item-children";
      for (const child of kids) {
        appendChildRow(ul, child);
      }
      details.appendChild(ul);
      li.appendChild(details);
    }
  }
  appendItemActions(li, item, column);
  return li;
}

function renderColumn(el, items, column, allItems) {
  el.innerHTML = "";
  const columnItems = items || [];
  const byId = Object.fromEntries((allItems || columnItems).map((i) => [i.id, i]));

  if (column === "you" || column === "waiting") {
    const { roots, groups } = groupsForFollowColumn(columnItems, allItems || columnItems);
    for (const item of roots) {
      el.appendChild(renderItemCard(item, column, columnItems, { showFrom: false, byId }));
    }
    for (const group of groups) {
      const wrap = document.createElement("li");
      wrap.className = "item-follow-wrap";
      const details = document.createElement("details");
      details.className = "item-follow";
      details.open = followGroupShouldOpen(group.children);
      const summary = document.createElement("summary");
      summary.textContent = `From: ${group.parentTitle} (${group.children.length})`;
      details.appendChild(summary);
      const ul = document.createElement("ul");
      ul.className = "item-follow-children";
      for (const child of group.children) {
        const childLi = renderItemCard(child, column, columnItems, {
          showFrom: false,
          byId,
        });
        ul.appendChild(childLi);
      }
      details.appendChild(ul);
      wrap.appendChild(details);
      el.appendChild(wrap);
    }
    return;
  }

  const visible = itemsForColumn(column, columnItems);
  for (const item of visible) {
    el.appendChild(
      renderItemCard(item, column, columnItems, { showFrom: true, byId }),
    );
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
  // Wake SW + wait for WS before reading health flags.
  const reconnect = await chrome.runtime.sendMessage({ type: "reconnectWs" }).catch(() => null);
  const health = await chrome.runtime.sendMessage({ type: "getHealth" });
  const hostEl = document.getElementById("host-status");
  const wsEl = document.getElementById("ws-status");
  const backendEl = document.getElementById("backend-status");
  panelWsConnected = Boolean(
    health?.wsConnected || reconnect?.wsConnected,
  );
  if (health?.ok) {
    hostEl.textContent = "Host OK";
    hostEl.className = "ok";
    backendEl.textContent = `backend: ${health.health?.agent_backend || "?"}`;
  } else {
    hostEl.textContent = "Host down";
    hostEl.className = "bad";
    backendEl.textContent = "";
  }
  wsEl.textContent = panelWsConnected ? "WS connected" : "WS disconnected";
  wsEl.className = panelWsConnected ? "ok" : "bad";
  updateActionButtons();
}

async function refreshMeta() {
  const meta = await chrome.runtime.sendMessage({ type: "getPanelMeta" });
  showDecomposition(meta.lastDecomposition);
  showRunId(meta.lastRunId);
  showHandoffError(meta.lastHandoffError);
}

async function refreshBoard() {
  const { board } = await chrome.runtime.sendMessage({ type: "getBoard" });
  const all = [
    ...(board.you || []),
    ...(board.agent || []),
    ...(board.waiting || []),
  ];
  renderColumn(document.getElementById("col-you"), board.you || [], "you", all);
  renderColumn(document.getElementById("col-agent"), board.agent || [], "agent", all);
  renderColumn(
    document.getElementById("col-waiting"),
    board.waiting || [],
    "waiting",
    all,
  );
}

async function refresh() {
  await refreshBoard();
  await refreshStatus();
  await refreshMeta();
}

const handoffBtn = document.getElementById("handoff");
handoffBtn.addEventListener("click", async () => {
  if (!panelWsConnected) {
    await refreshStatus();
  }
  if (!panelWsConnected) {
    showHandoffError("WS disconnected — cannot hand off");
    return;
  }
  handoffBtn.disabled = true;
  handoffBtn.textContent = "Handing off…";
  showHandoffError("");
  try {
    const tabId = handoffTargetTabId || (await resolveHandoffTabId());
    const result = await chrome.runtime.sendMessage({ type: "handoffTab", tabId });
    if (!result) {
      showHandoffError("Handoff failed — background did not respond (reload extension)");
    } else if (result.error || result.ok === false) {
      showHandoffError(result.error || "Handoff failed");
    }
    if (result?.decomposition) {
      showDecomposition(result.decomposition);
    }
    if (result?.run_id) {
      showRunId(result.run_id);
    }
    if (result?.run_id || result?.items?.length) {
      await refreshBoard();
      await refreshMeta();
    }
  } catch (err) {
    showHandoffError(String(err));
  } finally {
    handoffBtn.textContent = "Hand off this tab";
    handoffBtn.disabled = !panelWsConnected;
    await refreshStatus();
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
    refreshBoard().then(() => refreshMeta());
  }
  if (msg.type === "connectionUpdated") {
    panelWsConnected = msg.wsConnected;
    refreshStatus().then(() => refreshBoard()).then(() => refreshMeta());
  }
});

// Keep the MV3 service worker alive while the side panel is open, and
// reconnect WS as soon as the panel mounts.
try {
  chrome.runtime.connect({ name: "virgil-desk-panel" });
} catch {
  /* ignore */
}

resolveHandoffTabId();
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") {
    resolveHandoffTabId();
    refreshStatus();
  }
});

refresh();

// While disconnected, retry more often than the 1‑minute alarm.
setInterval(() => {
  if (!panelWsConnected) {
    refreshStatus();
  }
}, 3000);
