import {
  childChecklist,
  itemsForColumn,
  groupsForFollowColumn,
  followGroupShouldOpen,
  openYouParkUnder,
  agentRunButtonLabel,
  shouldRevealAgentTab,
  resolveParkAgentTabId,
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

/** Clickable destination: Show agent tab for auth_gate, else open page URL. */
function appendSourceUrl(container, item, allItems = []) {
  const url = item?.source?.url;
  const tabId = resolveParkAgentTabId(item, allItems);
  const reveal = shouldRevealAgentTab(item) || (item?.park_kind === "auth_gate" && tabId != null);

  if (reveal && tabId != null) {
    const meta = document.createElement("div");
    meta.className = "item-meta";
    const link = document.createElement("a");
    const revealUrl = chrome.runtime.getURL(
      `reveal.html?tab=${encodeURIComponent(String(tabId))}&item=${encodeURIComponent(item.id || "")}&run=${encodeURIComponent(item.run_id || "")}`,
    );
    link.href = revealUrl;
    link.className = "item-url";
    link.textContent = "Show tab";
    link.title = "Open the existing agent tab (no duplicate)";
    link.addEventListener("click", async (ev) => {
      ev.preventDefault();
      const result = await chrome.runtime.sendMessage({
        type: "revealAgentTab",
        tabId,
        itemId: item.id,
        runId: item.run_id || "",
      });
      if (!result?.ok && url) {
        try {
          await chrome.tabs.create({ url, active: true });
        } catch {
          window.open(url, "_blank", "noopener,noreferrer");
        }
      }
    });
    meta.appendChild(link);
    if (url) {
      const sep = document.createElement("span");
      sep.textContent = " · ";
      meta.appendChild(sep);
      const page = document.createElement("a");
      page.href = url;
      page.className = "item-url";
      page.textContent = truncateUrl(url);
      page.title = url;
      page.addEventListener("click", async (ev) => {
        ev.preventDefault();
        try {
          await chrome.tabs.create({ url, active: true });
        } catch {
          window.open(url, "_blank", "noopener,noreferrer");
        }
      });
      meta.appendChild(page);
    }
    container.appendChild(meta);
    return;
  }

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
  container.appendChild(meta);
}

let panelWsConnected = false;
let handoffTargetTabId = null;
/** Agent item ids with an in-flight Run — survives boardUpdated re-renders. */
const runningAgentItemIds = new Set();

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

async function runAgentAction(item, li, runBtn) {
  if (runBtn.disabled) return;
  runningAgentItemIds.add(item.id);
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
    runningAgentItemIds.delete(item.id);
    await refreshStatus();
    await refreshBoard();
    // refreshBoard rebuilds the DOM — do not touch runBtn after this.
  }
}

function appendChildRow(ul, child, allItems = []) {
  const cli = document.createElement("li");
  const cb = document.createElement("span");
  cb.className = `badge ${child.status || "proposed"}`;
  cb.textContent = statusLabel(child.status);
  cli.appendChild(cb);
  cli.appendChild(document.createTextNode(` ${child.title || "(untitled)"}`));
  appendSourceUrl(cli, child, allItems);
  if (child.last_error) {
    const err = document.createElement("div");
    err.className = "item-error";
    err.textContent = child.last_error;
    cli.appendChild(err);
  }
  ul.appendChild(cli);
}

function appendItemActions(li, item, column, allItems = []) {
  if (column === "agent") {
    const canRun =
      !item.parent_id &&
      (item.status === "running" ||
        item.status === "proposed" ||
        item.status === "failed");
    if (item.status === "awaiting_human") {
      const note = document.createElement("div");
      note.className = "item-meta item-awaiting";
      note.textContent = "Waiting on you — Show tab on the You card, then Mark done to Resume";
      li.appendChild(note);
      return;
    }
    if (canRun) {
      const actions = document.createElement("div");
      actions.className = "item-actions";
      const runBtn = document.createElement("button");
      const inFlight = runningAgentItemIds.has(item.id);
      const hasPark = !!openYouParkUnder(item.id, allItems);
      if (inFlight) {
        runBtn.textContent = "Running…";
        runBtn.disabled = true;
      } else {
        runBtn.textContent = agentRunButtonLabel(item, hasPark);
        runBtn.disabled = !panelWsConnected;
      }
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
      if (doneBtn.disabled) return;
      doneBtn.disabled = true;
      doneBtn.textContent = "Saving…";
      appendItemError(li, "");
      try {
        const result = await chrome.runtime.sendMessage({
          type: "completeItem",
          itemId: item.id,
          runId: item.run_id || "",
        });
        if (!result || result.error || result.detail || result.ok === false) {
          appendItemError(li, result?.error || result?.detail || "Mark done failed");
          doneBtn.textContent = "Mark done";
          doneBtn.disabled = !panelWsConnected;
          return;
        }
        const badge = li.querySelector(".badge");
        if (badge) {
          badge.className = "badge done";
          badge.textContent = statusLabel("done");
        }
        doneBtn.remove();
        await refresh();
      } catch (err) {
        appendItemError(li, String(err));
        doneBtn.textContent = "Mark done";
        doneBtn.disabled = !panelWsConnected;
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
        if (accept.disabled) return;
        accept.disabled = true;
        deny.disabled = true;
        accept.textContent = "Saving…";
        try {
          await chrome.runtime.sendMessage({
            type: "acceptProposal",
            itemId: item.id,
            proposalId: proposals[0]?.id || "",
            runId: item.run_id || "",
          });
          await refresh();
        } catch {
          accept.textContent = "Accept";
          accept.disabled = !panelWsConnected;
          deny.disabled = !panelWsConnected;
        }
      };
      const deny = document.createElement("button");
      deny.textContent = "Deny";
      deny.disabled = !panelWsConnected;
      deny.onclick = async () => {
        if (deny.disabled) return;
        accept.disabled = true;
        deny.disabled = true;
        deny.textContent = "Saving…";
        try {
          await chrome.runtime.sendMessage({
            type: "denyProposal",
            itemId: item.id,
            proposalId: proposals[0]?.id || "",
            runId: item.run_id || "",
            reason: "operator denied",
          });
          await refresh();
        } catch {
          deny.textContent = "Deny";
          accept.disabled = !panelWsConnected;
          deny.disabled = !panelWsConnected;
        }
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

function renderItemCard(item, column, columnItems, { showFrom = false, byId = {}, allItems = [] } = {}) {
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
  appendSourceUrl(li, item, allItems);
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
        appendChildRow(ul, child, allItems);
      }
      details.appendChild(ul);
      li.appendChild(details);
    }
  }
  appendItemActions(li, item, column, allItems);
  return li;
}

function renderColumn(el, items, column, allItems) {
  el.innerHTML = "";
  const columnItems = items || [];
  const boardAll = allItems || columnItems;
  const byId = Object.fromEntries(boardAll.map((i) => [i.id, i]));

  if (column === "you" || column === "waiting") {
    const { roots, groups } = groupsForFollowColumn(columnItems, boardAll);
    for (const item of roots) {
      el.appendChild(
        renderItemCard(item, column, columnItems, {
          showFrom: false,
          byId,
          allItems: boardAll,
        }),
      );
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
          allItems: boardAll,
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
      renderItemCard(item, column, columnItems, {
        showFrom: true,
        byId,
        allItems: boardAll,
      }),
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
let selectedIntentChip = "all visible";

function readHandoffIntent() {
  const extra = (document.getElementById("intent-extra")?.value || "").trim();
  const chip = selectedIntentChip || "all visible";
  if (extra) return `${chip}: ${extra}`;
  return chip;
}

document.querySelectorAll(".intent-chip").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".intent-chip").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    selectedIntentChip = btn.dataset.intent || "all visible";
  });
});

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
    const intent = readHandoffIntent();
    const result = await chrome.runtime.sendMessage({
      type: "handoffTab",
      tabId,
      intent,
    });
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
