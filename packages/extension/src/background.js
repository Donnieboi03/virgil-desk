const BOARD_KEY = "virgil_desk_board_v1";
const PAIRS_KEY = "virgil_desk_tab_pairs";
const AGENT_GROUP_TITLE = "Virgil · Agent";
const DEFAULT_HOST = "http://127.0.0.1:8787";

import { applyBoardPatch, chooseNavigationOp, policyBlock as tabPolicyBlock, openTabPlacement } from "./tabPolicy.js";
import { withProvisionLock, planAgentTabForItem } from "./agentTabs.js";
import {
  storeTargetMap,
  getTargetMap,
  clearTargetMap,
  clearMapsForTab,
} from "./targetMap.js";
import {
  MEMORY_KEY,
  emptyMemory,
  applyMemoryPatch,
} from "./deskMemory.js";
import { tabsToCloseForItem } from "./tabCleanup.js";
import { shouldCloseSpawnedTab } from "./popupPolicy.js";
import { updateActStall } from "./actStall.js";
import { normalizeScrapeResult } from "./scrapeResult.js";
import {
  decideExcerpt,
  getLastFullTextUrl,
  setLastFullTextUrl,
  clearExcerptBaselinesForRun,
  clearExcerptBaselinesForTab,
} from "./observeExcerpt.js";

const BUNDLE_FILE = "interactObserve.bundle.js";

const HANDOFF_URLS_KEY = "virgil_desk_handoff_urls";

let ws = null;
let hostUrl = DEFAULT_HOST;
let deskConfig = {
  browser: {
    scrape_text_max_chars: 16000,
    scrape_links_max: 200,
    scrape_excerpt_max_chars: 4000,
    handoff_excerpt_max_chars: 12000,
    handoff_scroll_loops: 2,
    handoff_scroll_viewport_ratio: 0.85,
    screenshot_mode: "captureVisibleTab",
    default_wait_ms: 500,
    interact_targets_max: 40,
    observe_annotate_default: true,
    act_stall_max: 3,
    observe_followup_excerpt_max_chars: 2000,
    observe_skip_screenshot_default: true,
    observe_all_frames: true,
    page_tree_max_chars: 2000,
    page_tree_max_nodes: 400,
  },
  memory: {
    recent_max: 3,
    notepad_max_bullets: 20,
    notepad_max_chars: 4000,
  },
};
let wsConnected = false;
let pendingHandoffResolve = null;
/** @type {{ runId: string, itemId: string, agentTabId: number, humanTabId: number, handoffUrl: string } | null} */
let activeExecute = null;
/** @type {Map<string, number>} */
let actStallMap = new Map();
/** Last URL that received a full/followup text excerpt (run_id:tab_id → url) */
let excerptBaselineMap = new Map();
/** Pending spawn tabs awaiting URL (tabId → itemId) */
const pendingSpawnTabs = new Map();

const META_KEY = "virgil_desk_panel_meta";

chrome.runtime.onInstalled.addListener(() => {
  chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true });
  chrome.alarms.create("desk-ws-keepalive", { periodInMinutes: 1 });
});

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name !== "desk-ws-keepalive") return;
  if (ws?.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: "ping" }));
  } else {
    connectWs();
  }
});

chrome.storage.sync.get(["hostUrl"], (data) => {
  if (data.hostUrl) hostUrl = data.hostUrl;
  connectWs();
});

chrome.storage.onChanged.addListener((changes, area) => {
  if (area !== "sync" || !changes.hostUrl) return;
  const next = changes.hostUrl.newValue;
  if (typeof next === "string" && next) {
    hostUrl = next;
    connectWs();
  }
});

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.type === "getPanelMeta") {
    chrome.storage.local.get(META_KEY).then((data) => sendResponse(data[META_KEY] || {}));
    return true;
  }
  if (msg.type === "getHealth") {
    fetch(`${hostUrl}/v1/health`)
      .then((r) => r.json())
      .then((health) => sendResponse({ ok: true, health, wsConnected }))
      .catch((err) => sendResponse({ ok: false, error: String(err), wsConnected }));
    return true;
  }
  if (msg.type === "getBoard") {
    loadBoard().then((board) => sendResponse({ board }));
    return true;
  }
  if (msg.type === "reconnectWs") {
    connectWs();
    sendResponse({ ok: true, wsConnected: ws?.readyState === WebSocket.OPEN });
    return true;
  }
  if (msg.type === "handoffTab") {
    handoffActiveTab(msg.intent, msg.tabId).then(sendResponse);
    return true;
  }
  if (msg.type === "acceptProposal") {
    acceptProposal(msg).then(sendResponse);
    return true;
  }
  if (msg.type === "denyProposal") {
    denyProposal(msg).then(sendResponse);
    return true;
  }
  if (msg.type === "runAgentItem") {
    runAgentItem(msg).then(sendResponse);
    return true;
  }
  if (msg.type === "completeItem") {
    completeItem(msg).then(sendResponse);
    return true;
  }
});

async function loadDeskMemory() {
  const data = await chrome.storage.local.get(MEMORY_KEY);
  return data[MEMORY_KEY] || emptyMemory();
}

async function saveDeskMemory(memory) {
  await chrome.storage.local.set({ [MEMORY_KEY]: memory });
}

function memoryLimits() {
  const m = deskConfig.memory || {};
  return {
    recentMax: m.recent_max ?? 3,
    maxBullets: m.notepad_max_bullets ?? 20,
    maxChars: m.notepad_max_chars ?? 4000,
  };
}

async function handleMemoryGet(msg) {
  const memory = await loadDeskMemory();
  if (ws?.readyState === WebSocket.OPEN) {
    ws.send(
      JSON.stringify({
        type: "memory_snapshot",
        request_id: msg.request_id,
        run_id: msg.run_id,
        memory,
      }),
    );
  }
}

async function handleMemoryPatch(msg) {
  const limits = memoryLimits();
  const current = await loadDeskMemory();
  const next = applyMemoryPatch(current, msg.ops || [], limits);
  await saveDeskMemory(next);
}

async function handleExecuteSession(msg) {
  if (msg.active === false) {
    activeExecute = null;
    return;
  }
  activeExecute = {
    runId: msg.run_id,
    itemId: msg.item_id,
    agentTabId: Number(msg.agent_tab_id),
    humanTabId: Number(msg.human_tab_id),
    handoffUrl: msg.handoff_url || (await handoffUrlForRun(msg.run_id)) || "",
  };
  actStallMap = new Map();
  excerptBaselineMap = clearExcerptBaselinesForRun(
    excerptBaselineMap,
    msg.run_id,
  );
}

async function trackSpawnedTab(runId, itemId, tabId) {
  const data = await chrome.storage.session.get(PAIRS_KEY);
  const pairs = data[PAIRS_KEY] || {};
  if (!pairs[runId]) pairs[runId] = { items: {}, spawnedByItem: {} };
  if (!pairs[runId].spawnedByItem) pairs[runId].spawnedByItem = {};
  const list = pairs[runId].spawnedByItem[itemId] || [];
  if (!list.includes(tabId)) list.push(tabId);
  pairs[runId].spawnedByItem[itemId] = list;
  await chrome.storage.session.set({ [PAIRS_KEY]: pairs });
}

/** Park human remainder tabs outside agent cleanup (not closed on execute_cleanup). */
async function trackHumanParkedTab(runId, itemId, tabId) {
  const data = await chrome.storage.session.get(PAIRS_KEY);
  const pairs = data[PAIRS_KEY] || {};
  if (!pairs[runId]) pairs[runId] = { items: {}, humanParkedByItem: {} };
  if (!pairs[runId].humanParkedByItem) pairs[runId].humanParkedByItem = {};
  const list = pairs[runId].humanParkedByItem[itemId] || [];
  if (!list.includes(tabId)) list.push(tabId);
  pairs[runId].humanParkedByItem[itemId] = list;
  await chrome.storage.session.set({ [PAIRS_KEY]: pairs });
}

async function maybeQuarantineSpawn(tabId, url) {
  if (!activeExecute) return;
  const openerPending = pendingSpawnTabs.get(tabId);
  if (openerPending == null && !pendingSpawnTabs.has(tabId)) {
    // Only tabs we marked as spawned from agent
    return;
  }
  if (!shouldCloseSpawnedTab(activeExecute.handoffUrl, url)) return;
  try {
    await chrome.tabs.remove(tabId);
  } catch {
    /* already closed */
  }
  pendingSpawnTabs.delete(tabId);
  if (ws?.readyState === WebSocket.OPEN) {
    ws.send(
      JSON.stringify({
        type: "browser_popup_closed",
        run_id: activeExecute.runId,
        item_id: activeExecute.itemId,
        tab_id: tabId,
        url,
      }),
    );
  }
}

chrome.tabs.onCreated.addListener((tab) => {
  if (!activeExecute || !tab?.id) return;
  const opener = tab.openerTabId;
  if (opener != null && opener === activeExecute.agentTabId) {
    pendingSpawnTabs.set(tab.id, activeExecute.itemId);
    trackSpawnedTab(activeExecute.runId, activeExecute.itemId, tab.id);
    if (tab.url) maybeQuarantineSpawn(tab.id, tab.url);
  }
});

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (!activeExecute) return;
  if (!pendingSpawnTabs.has(tabId)) return;
  const url = changeInfo.url || tab?.url;
  if (url) maybeQuarantineSpawn(tabId, url);
});

async function handleExecuteCleanup(msg) {
  const runId = msg.run_id;
  const itemId = msg.item_id;
  const humanTabId = msg.human_tab_id ?? activeExecute?.humanTabId;
  const agentTabId = msg.agent_tab_id;
  const data = await chrome.storage.session.get(PAIRS_KEY);
  const pairs = data[PAIRS_KEY] || {};
  const runPair = pairs[runId] || {};
  const toClose = tabsToCloseForItem(runPair, itemId, humanTabId, agentTabId);
  for (const tabId of toClose) {
    try {
      await chrome.tabs.remove(tabId);
    } catch {
      /* tab may already be gone */
    }
    clearMapsForTab(tabId);
    excerptBaselineMap = clearExcerptBaselinesForTab(excerptBaselineMap, tabId);
  }
  excerptBaselineMap = clearExcerptBaselinesForRun(excerptBaselineMap, runId);
  if (pairs[runId]?.items) {
    delete pairs[runId].items[itemId];
  }
  if (pairs[runId]?.spawnedByItem) {
    delete pairs[runId].spawnedByItem[itemId];
  }
  await chrome.storage.session.set({ [PAIRS_KEY]: pairs });
  for (const [tid, iid] of [...pendingSpawnTabs.entries()]) {
    if (iid === itemId) pendingSpawnTabs.delete(tid);
  }
  if (activeExecute?.itemId === itemId) {
    activeExecute = null;
  }
  actStallMap = new Map();
  if (ws?.readyState === WebSocket.OPEN) {
    ws.send(
      JSON.stringify({
        type: "execute_cleanup_done",
        run_id: runId,
        item_id: itemId,
        closed_tab_ids: toClose,
      }),
    );
  }
}

async function loadBoard() {
  const data = await chrome.storage.local.get(BOARD_KEY);
  return data[BOARD_KEY] || { you: [], agent: [], waiting: [] };
}

async function saveBoard(board) {
  await chrome.storage.local.set({ [BOARD_KEY]: board });
}

function wsUrl() {
  return hostUrl.replace(/^http/, "ws") + "/v1/extension";
}

async function fetchDeskConfig() {
  try {
    const res = await fetch(`${hostUrl}/v1/config`);
    if (res.ok) {
      const data = await res.json();
      if (data.browser) {
        deskConfig = { ...deskConfig, ...data };
      }
    }
  } catch {
    /* host may be down until WS connects */
  }
}

function applyRegisteredConfig(msg) {
  if (msg.config) {
    deskConfig = { ...deskConfig, ...msg.config };
  }
}

async function savePanelMeta(partial) {
  const data = await chrome.storage.local.get(META_KEY);
  const meta = { ...(data[META_KEY] || {}), ...partial };
  await chrome.storage.local.set({ [META_KEY]: meta });
  chrome.runtime.sendMessage({ type: "panelMetaUpdated", meta }).catch(() => {});
}

function connectWs() {
  try {
    ws = new WebSocket(wsUrl());
  } catch {
    wsConnected = false;
    return;
  }
  ws.onopen = () => {
    wsConnected = true;
    fetchDeskConfig();
    ws.send(JSON.stringify({ type: "register", extension_version: "0.1.0" }));
  };
  ws.onmessage = async (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.type === "registered") {
      applyRegisteredConfig(msg);
      chrome.runtime.sendMessage({ type: "connectionUpdated", wsConnected: true }).catch(() => {});
    }
    if (msg.type === "pong") {
      return;
    }
    if (msg.type === "handoff_result") {
      const { ok = true, run_id: runId, decomposition, error } = msg;
      if (runId) {
        await savePanelMeta({
          lastRunId: runId,
          lastDecomposition: decomposition || "",
          lastHandoffError: error || "",
        });
      }
      if (pendingHandoffResolve) {
        const resolve = pendingHandoffResolve;
        pendingHandoffResolve = null;
        resolve({ ok, run_id: runId, decomposition, error, ...msg });
      }
    }
    if (msg.type === "board_patch") {
      await applyPatch(msg.ops, msg.run_id);
    }
    if (msg.type === "memory_get") {
      await handleMemoryGet(msg);
    }
    if (msg.type === "memory_patch") {
      await handleMemoryPatch(msg);
    }
    if (msg.type === "execute_session") {
      await handleExecuteSession(msg);
    }
    if (msg.type === "execute_cleanup") {
      await handleExecuteCleanup(msg);
    }
    if (msg.type === "browser_command") {
      const command = await normalizeCommand(msg.command);
      const actOps = new Set(["click", "fill", "key", "scroll"]);
      const maxStall = deskConfig.browser?.act_stall_max ?? 3;
      const tabForStall = command.tab_id;
      if (actOps.has(command.op) && tabForStall != null) {
        const prior = actStallMap.get(`${command.run_id}:${tabForStall}`) || 0;
        if (maxStall > 0 && prior >= maxStall) {
          ws.send(
            JSON.stringify({
              type: "command_result",
              run_id: command.run_id,
              result: {
                command_id: command.command_id,
                ok: false,
                error: "stall_detected: re-observe or stop",
                duration_ms: 0,
              },
            }),
          );
          return;
        }
      }
      let result = await runBrowserCommand(command);
      if (actOps.has(command.op) && (result.tab_id != null || tabForStall != null)) {
        const tid = result.tab_id ?? tabForStall;
        const updated = updateActStall(
          actStallMap,
          command.run_id,
          tid,
          result,
          maxStall,
        );
        actStallMap = updated.next;
        if (updated.stalled) {
          result = {
            ...result,
            ok: false,
            error: "stall_detected: re-observe or stop",
          };
        }
      }
      if (command.op === "observe" && result.ok !== false) {
        const tid = result.tab_id ?? command.tab_id;
        if (tid != null) {
          actStallMap.set(`${command.run_id}:${tid}`, 0);
        }
      }
      ws.send(
        JSON.stringify({
          type: "command_result",
          run_id: msg.command.run_id,
          result,
        }),
      );
    }
  };
  ws.onclose = () => {
    wsConnected = false;
    chrome.runtime.sendMessage({ type: "connectionUpdated", wsConnected: false }).catch(() => {});
    setTimeout(connectWs, 3000);
  };
}

async function rememberHandoffUrl(runId, url) {
  const data = await chrome.storage.session.get(HANDOFF_URLS_KEY);
  const map = data[HANDOFF_URLS_KEY] || {};
  map[runId] = url;
  await chrome.storage.session.set({ [HANDOFF_URLS_KEY]: map });
}

async function handoffUrlForRun(runId) {
  const data = await chrome.storage.session.get(HANDOFF_URLS_KEY);
  return data[HANDOFF_URLS_KEY]?.[runId] || "";
}

async function normalizeCommand(command) {
  const url = command.url;
  if (!url) return command;
  if (command.op === "navigate" || command.op === "openTab" || command.op === "duplicateTab") {
    const handoffUrl =
      command.handoff_url || (await handoffUrlForRun(command.run_id));
    const op = chooseNavigationOp(handoffUrl, url);
    return { ...command, op, handoff_url: handoffUrl };
  }
  return command;
}

async function applyPatch(ops, runId) {
  if (runId) {
    const handoffPatch = ops.find((p) => p.op === "add" && p.item?.source?.url);
    if (handoffPatch) {
      await rememberHandoffUrl(runId, handoffPatch.item.source.url);
    }
  }
  // Agent tabs are provisioned only on Run agent — not on board_patch adds.
  const board = await loadBoard();
  await saveBoard(applyBoardPatch(board, ops));
  chrome.runtime.sendMessage({ type: "boardUpdated" }).catch(() => {});
}

async function duplicateUngroupedSnapshot(humanTabId, runId) {
  /** Handoff scrape only — do NOT create Virgil · Agent (group on Run agent). */
  const dup = await chrome.tabs.duplicate(humanTabId);
  await chrome.tabs.update(dup.id, { active: false });
  const data = await chrome.storage.session.get(PAIRS_KEY);
  const pairs = data[PAIRS_KEY] || {};
  pairs[runId] = {
    humanTabId,
    items: pairs[runId]?.items || {},
    spawnedByItem: pairs[runId]?.spawnedByItem || {},
    humanParkedByItem: pairs[runId]?.humanParkedByItem || {},
  };
  await chrome.storage.session.set({ [PAIRS_KEY]: pairs });
  return dup.id;
}

async function duplicateAgentTabForItem(humanTabId, runId, itemId) {
  const dup = await chrome.tabs.duplicate(humanTabId);
  await chrome.tabs.update(dup.id, { active: false });
  const tab = await chrome.tabs.get(dup.id);
  await ensureAgentGroup(dup.id, tab.windowId);
  const data = await chrome.storage.session.get(PAIRS_KEY);
  const pairs = data[PAIRS_KEY] || {};
  if (!pairs[runId]) {
    pairs[runId] = { humanTabId, items: {} };
  }
  if (!pairs[runId].items) pairs[runId].items = {};
  pairs[runId].items[itemId] = dup.id;
  pairs[runId].humanTabId = humanTabId;
  pairs[runId].agentTabId = dup.id;
  await chrome.storage.session.set({ [PAIRS_KEY]: pairs });
  return dup.id;
}

async function syncItemAgentTab(itemId, runId, agentTabId) {
  const res = await fetch(`${hostUrl}/v1/items/${itemId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ run_id: runId, agent_tab_id: agentTabId }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || res.statusText || "failed to sync agent_tab_id");
  }
}

async function loadRunPair(runId) {
  const data = await chrome.storage.session.get(PAIRS_KEY);
  return data[PAIRS_KEY]?.[runId];
}

async function findBoardItem(itemId) {
  const board = await loadBoard();
  for (const col of ["you", "agent", "waiting"]) {
    const found = (board[col] || []).find((i) => i.id === itemId);
    if (found) return { item: found, column: col, board };
  }
  return null;
}

async function clearHandoffSnapshotTab(runId, snapshotTabId) {
  try {
    await chrome.tabs.remove(snapshotTabId);
  } catch {
    /* already closed */
  }
  const data = await chrome.storage.session.get(PAIRS_KEY);
  const pairs = data[PAIRS_KEY] || {};
  if (pairs[runId]) {
    delete pairs[runId].agentTabId;
    await chrome.storage.session.set({ [PAIRS_KEY]: pairs });
  }
}

/**
 * Provision one agent tab for this item at Run agent time (not handoff/board_patch).
 */
async function provisionAgentTabBeforeExecute(itemId, runId) {
  return withProvisionLock(runId, async () => {
    const located = await findBoardItem(itemId);
    if (!located?.item) {
      return { ok: false, error: "work item not found on board" };
    }
    const { item, board } = located;
    if (item.column !== "agent") {
      return { ok: false, error: "execute only for agent column" };
    }
    const runPair = await loadRunPair(runId);
    const humanTabId = item.human_tab_id || runPair?.humanTabId;
    if (!humanTabId) {
      return { ok: false, error: "missing human_tab_id — hand off again before Run agent" };
    }

    if (item.agent_tab_id) {
      try {
        await chrome.tabs.get(item.agent_tab_id);
        const data = await chrome.storage.session.get(PAIRS_KEY);
        const pairs = data[PAIRS_KEY] || {};
        if (!pairs[runId]) pairs[runId] = { humanTabId, items: {} };
        if (!pairs[runId].items) pairs[runId].items = {};
        pairs[runId].items[itemId] = item.agent_tab_id;
        pairs[runId].agentTabId = item.agent_tab_id;
        pairs[runId].humanTabId = humanTabId;
        await chrome.storage.session.set({ [PAIRS_KEY]: pairs });
        return { ok: true, agentTabId: item.agent_tab_id, humanTabId };
      } catch {
        /* tab gone — provision fresh */
      }
    }

    const plan = planAgentTabForItem(itemId, 0, await loadRunPair(runId));
    let tabId = plan.tabId;
    if (plan.source === "duplicate" || !tabId) {
      tabId = await duplicateAgentTabForItem(humanTabId, runId, itemId);
    }
    if (!tabId) {
      return { ok: false, error: "failed to provision agent tab" };
    }

    const data = await chrome.storage.session.get(PAIRS_KEY);
    const pairs = data[PAIRS_KEY] || {};
    if (!pairs[runId]) pairs[runId] = { humanTabId, items: {} };
    pairs[runId].humanTabId = humanTabId;
    pairs[runId].agentTabId = tabId;
    if (!pairs[runId].items) pairs[runId].items = {};
    pairs[runId].items[itemId] = tabId;
    await chrome.storage.session.set({ [PAIRS_KEY]: pairs });

    item.agent_tab_id = tabId;
    item.human_tab_id = humanTabId;
    await saveBoard(board);
    try {
      await syncItemAgentTab(itemId, runId, tabId);
    } catch (err) {
      return { ok: false, error: String(err.message || err) };
    }
    chrome.runtime.sendMessage({ type: "boardUpdated" }).catch(() => {});
    return { ok: true, agentTabId: tabId, humanTabId };
  });
}

async function ensureAgentGroup(tabId, windowId) {
  const groups = await chrome.tabGroups.query({ windowId, title: AGENT_GROUP_TITLE });
  if (groups.length) {
    await chrome.tabs.group({ tabIds: tabId, groupId: groups[0].id });
    await chrome.tabGroups.update(groups[0].id, { collapsed: true });
    return groups[0].id;
  }
  const groupId = await chrome.tabs.group({
    tabIds: tabId,
    createProperties: { windowId },
  });
  await chrome.tabGroups.update(groupId, {
    title: AGENT_GROUP_TITLE,
    color: "grey",
    collapsed: true,
  });
  return groupId;
}

async function resolveAgentTab(command) {
  const pairs = (await chrome.storage.session.get(PAIRS_KEY))[PAIRS_KEY] || {};
  const runId = command.run_id;
  const placement = openTabPlacement(command);

  // Human remainder tabs stay outside Virgil · Agent and are not the agent collage.
  if (command.op === "openTab" && placement === "human") {
    const human = command.human_tab_id
      ? await chrome.tabs.get(command.human_tab_id)
      : null;
    const windowId = human?.windowId;
    const tab = await chrome.tabs.create({
      url: command.url || "about:blank",
      active: false,
      windowId,
    });
    if (activeExecute?.itemId && runId) {
      await trackHumanParkedTab(runId, activeExecute.itemId, tab.id);
    }
    return { tabId: tab.id, tabMode: "create", placement: "human" };
  }

  // openTab always creates (or navigates a new tab) — never reuse collage without loading url.
  if (command.op !== "openTab" && pairs[runId]?.agentTabId) {
    return { tabId: pairs[runId].agentTabId, tabMode: "reuse" };
  }
  if (command.op === "duplicateTab") {
    const dup = await chrome.tabs.duplicate(command.human_tab_id);
    await chrome.tabs.update(dup.id, { active: false });
    const tab = await chrome.tabs.get(dup.id);
    await ensureAgentGroup(dup.id, tab.windowId);
    pairs[runId] = {
      humanTabId: command.human_tab_id,
      agentTabId: dup.id,
      items: pairs[runId]?.items || {},
      spawnedByItem: pairs[runId]?.spawnedByItem || {},
      humanParkedByItem: pairs[runId]?.humanParkedByItem || {},
    };
    await chrome.storage.session.set({ [PAIRS_KEY]: pairs });
    return { tabId: dup.id, tabMode: "duplicate", placement: "agent" };
  }
  if (command.op === "openTab") {
    const human = command.human_tab_id
      ? await chrome.tabs.get(command.human_tab_id)
      : null;
    const windowId = human?.windowId;
    const tab = await chrome.tabs.create({
      url: command.url || "about:blank",
      active: false,
      windowId,
    });
    await ensureAgentGroup(tab.id, tab.windowId);
    if (!pairs[runId]) {
      pairs[runId] = {
        humanTabId: command.human_tab_id,
        items: {},
        spawnedByItem: {},
        humanParkedByItem: {},
      };
    }
    if (!pairs[runId].agentTabId) {
      pairs[runId].agentTabId = tab.id;
      if (activeExecute?.itemId) {
        if (!pairs[runId].items) pairs[runId].items = {};
        pairs[runId].items[activeExecute.itemId] = tab.id;
      }
    } else if (activeExecute?.itemId) {
      await trackSpawnedTab(runId, activeExecute.itemId, tab.id);
    }
    pairs[runId].humanTabId = pairs[runId].humanTabId || command.human_tab_id;
    await chrome.storage.session.set({ [PAIRS_KEY]: pairs });
    return { tabId: tab.id, tabMode: "create", placement: "agent" };
  }
  return { tabId: command.tab_id, tabMode: "reuse" };
}

function policyBlock(command, tabId) {
  return tabPolicyBlock(command, tabId);
}

async function scrapeTab(tabId) {
  const maxText = deskConfig.browser?.scrape_text_max_chars ?? 8000;
  const maxLinks = deskConfig.browser?.scrape_links_max ?? 50;
  try {
    const injected = await chrome.scripting.executeScript({
      target: { tabId },
      func: (textMax, linkMax) => {
        const allLinks = [...document.querySelectorAll("a[href]")]
          .map((a) => a.href)
          .filter((h) => h.startsWith("http"));
        const fullText = document.body?.innerText || "";
        return {
          text: fullText.slice(0, textMax),
          links: allLinks.slice(0, linkMax),
          url: location.href,
          title: document.title,
          metrics: {
            full_text_chars: fullText.length,
            full_link_count: allLinks.length,
          },
        };
      },
      args: [maxText, maxLinks],
    });
    const result = injected?.[0]?.result;
    return normalizeScrapeResult(result);
  } catch {
    return normalizeScrapeResult(null);
  }
}

async function settleTabAfterOpen() {
  const ms = deskConfig.browser?.default_wait_ms ?? 500;
  await new Promise((r) => setTimeout(r, ms));
}

function scrollViewportRatio() {
  return deskConfig.browser?.handoff_scroll_viewport_ratio ?? 0.85;
}

function observeAllFrames() {
  return deskConfig.browser?.observe_all_frames !== false;
}

function slimTargetForEyes(t) {
  if (!t) return t;
  const out = {
    id: t.id,
    ref: t.ref,
    kind: t.kind,
    label: t.label,
  };
  if (t.frame_id != null) out.frame_id = t.frame_id;
  return out;
}

/** Prefer conversation rows when merging multi-frame Eyes under the cap. */
function targetSortKey(t) {
  const tag = (t?.tag || "").toLowerCase();
  const role = (t?.role || "").toLowerCase();
  if (tag === "tr" || role === "row") return 0;
  if (tag === "input" || tag === "textarea") return 1;
  if (tag === "a" || tag === "button") return 2;
  return 3;
}

/** Bare Gmail/list row CSS hits the first match — force target_id instead. */
function isBareAmbiguousRowSelector(selector) {
  const s = String(selector || "").trim();
  if (!s) return false;
  return (
    /^tr\.z[AE]$/i.test(s) ||
    /^tr\.z[AE]\s*$/i.test(s) ||
    /^\[role=["']?row["']?\]$/i.test(s)
  );
}

async function injectInteractBundle(tabId, { allFrames = false } = {}) {
  await chrome.scripting.executeScript({
    target: allFrames ? { tabId, allFrames: true } : { tabId },
    files: [BUNDLE_FILE],
    world: "MAIN",
  });
}

async function readViewportMeta(tabId) {
  const [{ result }] = await chrome.scripting.executeScript({
    target: { tabId },
    func: () => ({
      w: window.innerWidth,
      h: window.innerHeight,
      device_pixel_ratio: window.devicePixelRatio || 1,
    }),
  });
  return result;
}

async function runPageObserve(tabId, opts) {
  const allFrames = observeAllFrames();
  await injectInteractBundle(tabId, { allFrames });
  const results = await chrome.scripting.executeScript({
    target: allFrames ? { tabId, allFrames: true } : { tabId },
    world: "MAIN",
    func: (o) => globalThis.deskObserve(o),
    args: [opts],
  });
  const maxTargets = opts.maxTargets ?? 40;
  const collected = [];
  const scroll_containers = [];
  let primary = results?.[0]?.result || {};
  for (const entry of results || []) {
    const frameId = entry.frameId ?? 0;
    const r = entry.result;
    if (!r) continue;
    if (frameId === 0 || !primary.url) primary = r;
    for (const t of r.interact_targets || []) {
      collected.push({
        ...t,
        frame_id: frameId,
      });
    }
    for (const s of r.scroll_containers || []) {
      if (scroll_containers.length >= 20) break;
      scroll_containers.push({
        ...s,
        frame_id: frameId,
        id: scroll_containers.length + 1,
        ref: `s${scroll_containers.length + 1}`,
      });
    }
  }
  collected.sort((a, b) => targetSortKey(a) - targetSortKey(b));
  const interact_targets = collected.slice(0, maxTargets).map((t, idx) => ({
    ...t,
    id: idx + 1,
    ref: `t${idx + 1}`,
  }));
  return {
    ...primary,
    interact_targets,
    scroll_containers,
  };
}

async function runPageTree(tabId, { includeTree }) {
  if (!includeTree) return null;
  const allFrames = observeAllFrames();
  await injectInteractBundle(tabId, { allFrames });
  const maxChars = deskConfig.browser?.page_tree_max_chars ?? 2000;
  const maxNodes = deskConfig.browser?.page_tree_max_nodes ?? 400;
  const results = await chrome.scripting.executeScript({
    target: allFrames ? { tabId, allFrames: true } : { tabId },
    world: "MAIN",
    func: (o) => globalThis.deskPageTree(o),
    args: [{ maxChars, maxNodes }],
  });
  const chunks = [];
  let used = 0;
  for (const entry of results || []) {
    const tree = entry.result?.page_tree;
    if (!tree) continue;
    const header =
      (entry.frameId ?? 0) === 0 ? "" : `\n--- frame ${entry.frameId} ---\n`;
    const piece = `${header}${tree}`;
    if (used + piece.length > maxChars) {
      chunks.push(piece.slice(0, Math.max(0, maxChars - used)));
      break;
    }
    chunks.push(piece);
    used += piece.length;
  }
  return chunks.length ? chunks.join("\n") : null;
}

async function runPageUnmark(tabId) {
  try {
    const allFrames = observeAllFrames();
    await injectInteractBundle(tabId, { allFrames });
    await chrome.scripting.executeScript({
      target: allFrames ? { tabId, allFrames: true } : { tabId },
      world: "MAIN",
      func: () => globalThis.deskUnmark(),
    });
  } catch {
    /* tab may be gone */
  }
}

async function runPageAct(tabId, op, params, targets, urlBefore) {
  const frameId = Number(
    params?.frame_id ??
      targets?.find((t) => t.id === Number(params?.target_id))?.frame_id ??
      0,
  );
  const allFrames = observeAllFrames();
  await injectInteractBundle(tabId, { allFrames });
  const target =
    Number.isFinite(frameId) && frameId > 0
      ? { tabId, frameIds: [frameId] }
      : { tabId };
  const [{ result }] = await chrome.scripting.executeScript({
    target,
    world: "MAIN",
    func: (operation, p, t, before) => globalThis.deskAct(operation, p, t, before),
    args: [op, params, targets, urlBefore],
  });
  return result;
}

async function runPageProbe(tabId, kind) {
  const allFrames = observeAllFrames();
  await injectInteractBundle(tabId, { allFrames });
  const results = await chrome.scripting.executeScript({
    target: allFrames ? { tabId, allFrames: true } : { tabId },
    world: "MAIN",
    func: (k) => {
      if (k === "probe_form") return globalThis.deskProbeForm();
      if (k === "probe_links") return globalThis.deskProbeLinks();
      if (k === "probe_table") return globalThis.deskProbeTable();
      return { error: "unknown probe" };
    },
    args: [kind],
  });
  if (kind === "probe_form") {
    const form_fields = [];
    for (const entry of results || []) {
      for (const f of entry.result?.form_fields || []) {
        if (form_fields.length >= 40) break;
        form_fields.push({ ...f, frame_id: entry.frameId ?? 0 });
      }
    }
    return { form_fields, url: results?.[0]?.result?.url };
  }
  if (kind === "probe_links") {
    const links = [];
    for (const entry of results || []) {
      for (const l of entry.result?.links || []) {
        if (links.length >= 80) break;
        links.push({ ...l, frame_id: entry.frameId ?? 0 });
      }
    }
    return { links, url: results?.[0]?.result?.url };
  }
  // probe_table: prefer first frame with rows
  for (const entry of results || []) {
    if (entry.result?.found && entry.result?.rows?.length) {
      return { ...entry.result, frame_id: entry.frameId ?? 0 };
    }
  }
  return results?.[0]?.result || { rows: [], found: false };
}

async function screenshotTab(tabId) {
  const mode = deskConfig.browser?.screenshot_mode || "captureVisibleTab";
  const vp = await readViewportMeta(tabId).catch(() => ({
    w: 0,
    h: 0,
    device_pixel_ratio: 1,
  }));
  if (mode !== "captureVisibleTab") {
    const shot = await screenshotTabCanvas(tabId);
    return {
      ...shot,
      width: shot.width || vp.w,
      height: shot.height || vp.h,
      device_pixel_ratio: vp.device_pixel_ratio,
    };
  }
  const tab = await chrome.tabs.get(tabId);
  const windowId = tab.windowId;
  const [activeTab] = await chrome.tabs.query({ active: true, windowId });
  const priorTabId = activeTab?.id;
  const waitMs = deskConfig.browser?.default_wait_ms ?? 500;
  try {
    await chrome.tabs.update(tabId, { active: true });
    await new Promise((r) => setTimeout(r, waitMs));
    const dataUrl = await chrome.tabs.captureVisibleTab(windowId, { format: "png" });
    const base64 = dataUrl.split(",")[1] || "";
    const dpr = vp.device_pixel_ratio || 1;
    return {
      mime: "image/png",
      base64,
      width: Math.round(vp.w * dpr),
      height: Math.round(vp.h * dpr),
      css_width: vp.w,
      css_height: vp.h,
      device_pixel_ratio: dpr,
    };
  } finally {
    if (priorTabId && priorTabId !== tabId) {
      await chrome.tabs.update(priorTabId, { active: true }).catch(() => {});
    }
  }
}

async function screenshotTabCanvas(tabId) {
  const [{ result }] = await chrome.scripting.executeScript({
    target: { tabId },
    func: async () => {
      const w = Math.min(document.documentElement.scrollWidth, 1280);
      const h = Math.min(window.innerHeight, 1600);
      const canvas = document.createElement("canvas");
      canvas.width = w;
      canvas.height = h;
      const ctx = canvas.getContext("2d");
      ctx.fillStyle = "#ffffff";
      ctx.fillRect(0, 0, w, h);
      const text = (document.body?.innerText || "").slice(0, 500);
      ctx.fillStyle = "#111";
      ctx.font = "14px sans-serif";
      text.split("\n").slice(0, 40).forEach((line, i) => {
        ctx.fillText(line.slice(0, 120), 8, 20 + i * 18);
      });
      const dataUrl = canvas.toDataURL("image/png");
      const base64 = dataUrl.split(",")[1] || "";
      return { mime: "image/png", base64, width: w, height: h };
    },
  });
  return result;
}

async function ensureTargetMapFresh(stored, runId, tabId, urlBeforeAct) {
  if (!stored) {
    return { ok: false, error: "stale_observe: run observe first" };
  }
  const liveUrl =
    urlBeforeAct || (await scrapeTab(tabId).catch(() => ({}))).url || "";
  if (stored.url && liveUrl && stored.url !== liveUrl) {
    clearTargetMap(runId, tabId);
    return {
      ok: false,
      error: "stale_observe: page navigated since observe — run observe again",
    };
  }
  return { ok: true, liveUrl: liveUrl || stored.url };
}

function applyExcerptPolicy(runId, tabId, url, rawText) {
  const fullMax = deskConfig.browser?.scrape_excerpt_max_chars ?? 4000;
  const followupMax =
    deskConfig.browser?.observe_followup_excerpt_max_chars ?? 2000;
  const decided = decideExcerpt({
    url: url || "",
    text: rawText || "",
    lastFullTextUrl: getLastFullTextUrl(excerptBaselineMap, runId, tabId),
    fullMax,
    followupMax,
  });
  if (decided.nextBaseline) {
    excerptBaselineMap = setLastFullTextUrl(
      excerptBaselineMap,
      runId,
      tabId,
      decided.nextBaseline,
    );
  }
  return decided;
}

async function runBrowserCommand(command) {
  command = await normalizeCommand(command);
  const started = Date.now();
  const base = {
    command_id: command.command_id,
    ok: true,
    duration_ms: 0,
  };
  try {
    if (command.op === "captureHandoffSnapshot") {
      const handoffMax = deskConfig.browser?.handoff_excerpt_max_chars ?? 8000;
      const snap = await scrapeTab(command.human_tab_id);
      return {
        ...base,
        url: snap.url,
        title: snap.title,
        scrape_excerpt: snap.text?.slice(0, handoffMax),
        duration_ms: Date.now() - started,
      };
    }

    let tabId = command.tab_id;
    if (command.op === "duplicateTab") {
      const resolved = await resolveAgentTab(command);
      tabId = resolved.tabId;
      await settleTabAfterOpen();
    } else if (command.op === "openTab") {
      const resolved = await resolveAgentTab({ ...command, op: "openTab" });
      tabId = resolved.tabId;
      await settleTabAfterOpen();
    }

    const block = policyBlock(command, tabId);
    if (block) {
      return { ...base, ok: false, error: block, duration_ms: Date.now() - started };
    }

    if (command.op === "observe") {
      const maxTargets = deskConfig.browser?.interact_targets_max ?? 40;
      const annotate =
        command.params?.annotate ??
        deskConfig.browser?.observe_annotate_default ??
        true;
      const snap = await scrapeTab(tabId);
      const pageObserve = await runPageObserve(tabId, { maxTargets, annotate });
      const skipShot =
        command.skip_screenshot ??
        deskConfig.browser?.observe_skip_screenshot_default ??
        true;
      const shot = skipShot ? null : await screenshotTab(tabId);
      await runPageUnmark(tabId);
      const interact_targets_full = (pageObserve?.interact_targets || []).map(
        ({ mark_label, ...rest }) => rest,
      );
      const pageUrl = pageObserve?.url || snap.url;
      storeTargetMap(command.run_id, tabId, {
        interact_targets: interact_targets_full,
        scroll_containers: pageObserve?.scroll_containers || [],
        url: pageUrl,
      });
      const excerpt = applyExcerptPolicy(
        command.run_id,
        tabId,
        pageUrl,
        snap.text || "",
      );
      const includeTree = !excerpt.text_omitted;
      const page_tree = await runPageTree(tabId, { includeTree }).catch(() => null);
      const interact_targets = interact_targets_full.map(slimTargetForEyes);
      const observe = {
        url: pageUrl,
        title: pageObserve?.title || snap.title,
        viewport: pageObserve?.viewport || { w: 0, h: 0 },
        device_pixel_ratio: pageObserve?.device_pixel_ratio ?? 1,
        text_excerpt: excerpt.text,
        text_omitted: excerpt.text_omitted,
        interact_targets,
        scroll_containers: (pageObserve?.scroll_containers || []).map((s) => ({
          id: s.id,
          ref: s.ref,
          label: s.label,
          scrollHeight: s.scrollHeight,
          clientHeight: s.clientHeight,
          frame_id: s.frame_id,
        })),
      };
      if (excerpt.note) observe.excerpt_note = excerpt.note;
      if (page_tree) observe.page_tree = page_tree;
      return {
        ...base,
        tab_id: tabId,
        url: observe.url,
        title: observe.title,
        scrape_excerpt: observe.text_excerpt,
        text_omitted: excerpt.text_omitted,
        excerpt_note: excerpt.note,
        observe,
        interact_targets,
        scroll_containers: observe.scroll_containers,
        viewport: observe.viewport,
        device_pixel_ratio: observe.device_pixel_ratio,
        page_tree: page_tree || undefined,
        screenshot: shot,
        duration_ms: Date.now() - started,
      };
    }

    if (
      command.op === "probe_form" ||
      command.op === "probe_links" ||
      command.op === "probe_table"
    ) {
      const probe = await runPageProbe(tabId, command.op);
      return {
        ...base,
        tab_id: tabId,
        ok: true,
        url: probe.url,
        ...probe,
        duration_ms: Date.now() - started,
      };
    }

    let actResolved = undefined;
    const urlBeforeAct = (await scrapeTab(tabId).catch(() => ({}))).url;

    if (command.op === "scroll") {
      const stored = getTargetMap(command.run_id, tabId);
      const scrollParams = { ...command.params, ratio: scrollViewportRatio() };
      const wantsContainer =
        scrollParams.target_id != null ||
        (scrollParams.ref && String(scrollParams.ref).startsWith("s"));
      if (wantsContainer) {
        const fresh = await ensureTargetMapFresh(
          stored,
          command.run_id,
          tabId,
          urlBeforeAct,
        );
        if (!fresh.ok) {
          return {
            ...base,
            ok: false,
            error: fresh.error,
            duration_ms: Date.now() - started,
          };
        }
        const scrollTargets = (stored?.scroll_containers || []).map((s) => ({
          ...s,
          kind: "scroll_container",
        }));
        if (!scrollTargets.length) {
          return {
            ...base,
            ok: false,
            error: "stale_observe: no scroll containers from observe",
            duration_ms: Date.now() - started,
          };
        }
        const act = await runPageAct(
          tabId,
          "scroll",
          scrollParams,
          scrollTargets,
          urlBeforeAct || fresh.liveUrl,
        );
        if (!act?.ok) {
          return { ...base, ok: false, error: act.error, act_resolved: act.act_resolved, duration_ms: Date.now() - started };
        }
        actResolved = act.act_resolved;
      } else {
        const dir = command.params?.direction === "up" ? -1 : 1;
        const ratio = scrollViewportRatio();
        await chrome.scripting.executeScript({
          target: { tabId },
          func: (d, r) => window.scrollBy(0, d * window.innerHeight * r),
          args: [dir, ratio],
        });
        actResolved = {
          op: "scroll",
          requested: command.params || {},
          used: "viewport",
          url_before: urlBeforeAct,
          url_after: (await scrapeTab(tabId).catch(() => ({}))).url,
        };
      }
    } else if (command.op === "focusTab") {
      await chrome.tabs.update(tabId, { active: true });
      return { ...base, tab_id: tabId, duration_ms: Date.now() - started };
    } else if (command.op === "click") {
      const params = command.params || {};
      const stored = getTargetMap(command.run_id, tabId);
      const hasCoords = params.x != null && params.y != null;
      const needsMap =
        params.target_id != null ||
        params.ref ||
        params.text ||
        params.contains;
      if (hasCoords && !needsMap) {
        const act = await runPageAct(tabId, "click", params, [], urlBeforeAct);
        if (!act?.ok) {
          return {
            ...base,
            ok: false,
            error: act.error,
            act_resolved: act.act_resolved,
            duration_ms: Date.now() - started,
          };
        }
        actResolved = act.act_resolved;
      } else if (needsMap) {
        const fresh = await ensureTargetMapFresh(
          stored,
          command.run_id,
          tabId,
          urlBeforeAct,
        );
        if (!fresh.ok) {
          return {
            ...base,
            ok: false,
            error: fresh.error,
            duration_ms: Date.now() - started,
          };
        }
        if (!stored?.interact_targets?.length) {
          return {
            ...base,
            ok: false,
            error: "stale_observe: run observe first",
            duration_ms: Date.now() - started,
          };
        }
        const act = await runPageAct(
          tabId,
          "click",
          params,
          stored.interact_targets,
          urlBeforeAct || fresh.liveUrl,
        );
        if (!act?.ok) {
          return {
            ...base,
            ok: false,
            error: act.error,
            act_resolved: act.act_resolved,
            duration_ms: Date.now() - started,
          };
        }
        actResolved = act.act_resolved;
      } else if (params.selector) {
        if (isBareAmbiguousRowSelector(params.selector)) {
          return {
            ...base,
            ok: false,
            error:
              "ambiguous_row_selector: use target_id from observe (bare tr.zA / [role=row] rejected)",
            duration_ms: Date.now() - started,
          };
        }
        const [{ result: clicked }] = await chrome.scripting.executeScript({
          target: { tabId },
          func: (s) => {
            const el = document.querySelector(s);
            if (!el) return false;
            el.click();
            return true;
          },
          args: [params.selector],
        });
        if (!clicked) {
          return {
            ...base,
            ok: false,
            error: `selector not found: ${params.selector}`,
            duration_ms: Date.now() - started,
          };
        }
        actResolved = {
          op: "click",
          requested: params,
          used: "selector",
          url_before: urlBeforeAct,
          url_after: (await scrapeTab(tabId).catch(() => ({}))).url,
        };
      } else {
        return {
          ...base,
          ok: false,
          error: "click requires target_id, text, coordinates, or selector",
          duration_ms: Date.now() - started,
        };
      }
    } else if (command.op === "fill") {
      const params = command.params || {};
      const stored = getTargetMap(command.run_id, tabId);
      if (params.target_id != null || params.ref || params.text) {
        const fresh = await ensureTargetMapFresh(
          stored,
          command.run_id,
          tabId,
          urlBeforeAct,
        );
        if (!fresh.ok) {
          return {
            ...base,
            ok: false,
            error: fresh.error,
            duration_ms: Date.now() - started,
          };
        }
        if (!stored?.interact_targets?.length) {
          return {
            ...base,
            ok: false,
            error: "stale_observe: run observe first",
            duration_ms: Date.now() - started,
          };
        }
        const act = await runPageAct(
          tabId,
          "fill",
          params,
          stored.interact_targets,
          urlBeforeAct || fresh.liveUrl,
        );
        if (!act?.ok) {
          return {
            ...base,
            ok: false,
            error: act.error,
            act_resolved: act.act_resolved,
            duration_ms: Date.now() - started,
          };
        }
        actResolved = act.act_resolved;
      } else if (params.selector) {
        const sel = params.selector;
        const val = params.value || "";
        const [{ result: filled }] = await chrome.scripting.executeScript({
          target: { tabId },
          func: (s, v) => {
            const el = document.querySelector(s);
            if (!el) return false;
            el.value = v;
            el.dispatchEvent(new Event("input", { bubbles: true }));
            return true;
          },
          args: [sel, val],
        });
        if (!filled) {
          return {
            ...base,
            ok: false,
            error: `selector not found: ${sel}`,
            duration_ms: Date.now() - started,
          };
        }
        actResolved = {
          op: "fill",
          requested: params,
          used: "selector",
          url_before: urlBeforeAct,
          url_after: (await scrapeTab(tabId).catch(() => ({}))).url,
        };
      } else {
        return {
          ...base,
          ok: false,
          error: "fill requires target_id or selector",
          duration_ms: Date.now() - started,
        };
      }
    } else if (command.op === "key") {
      const params = command.params || {};
      const stored = getTargetMap(command.run_id, tabId);
      const targets = stored?.interact_targets || [];
      if (params.target_id != null || params.ref) {
        const fresh = await ensureTargetMapFresh(
          stored,
          command.run_id,
          tabId,
          urlBeforeAct,
        );
        if (!fresh.ok) {
          return {
            ...base,
            ok: false,
            error: fresh.error,
            duration_ms: Date.now() - started,
          };
        }
      }
      const act = await runPageAct(
        tabId,
        "key",
        params,
        targets,
        urlBeforeAct || stored?.url,
      );
      if (!act?.ok) {
        return {
          ...base,
          ok: false,
          error: act.error,
          act_resolved: act.act_resolved,
          duration_ms: Date.now() - started,
        };
      }
      actResolved = act.act_resolved;
    } else if (command.op === "wait") {
      await new Promise((r) => setTimeout(r, command.params?.ms || 500));
    }

    if (["click", "fill", "scroll", "key", "scrape", "screenshot", "openTab", "duplicateTab"].includes(command.op)) {
      const snap = await scrapeTab(tabId);
      let shot = null;
      const skipShot =
        command.skip_screenshot ??
        (command.op !== "screenshot" &&
          deskConfig.browser?.observe_skip_screenshot_default);
      if (!skipShot) {
        shot = await screenshotTab(tabId);
      }
      const excerpt = applyExcerptPolicy(
        command.run_id,
        tabId,
        snap.url,
        snap.text || "",
      );
      const out = {
        ...base,
        tab_id: tabId,
        url: snap.url,
        title: snap.title,
        scrape_excerpt: excerpt.text,
        text_omitted: excerpt.text_omitted,
        excerpt_note: excerpt.note,
        screenshot: shot,
        act_resolved: actResolved,
        duration_ms: Date.now() - started,
      };
      if (command.op === "scrape" || command.op === "screenshot") return out;
      return out;
    }

    if (command.op === "closeTab") {
      if (tabId == null || tabId === "") {
        return {
          ...base,
          ok: false,
          error: "closeTab requires tab_id",
          duration_ms: Date.now() - started,
        };
      }
      const block = policyBlock(command, tabId);
      if (block) {
        return { ...base, ok: false, error: block, duration_ms: Date.now() - started };
      }
      await chrome.tabs.remove(tabId);
      const runId = command.run_id;
      if (runId) {
        const data = await chrome.storage.session.get(PAIRS_KEY);
        const pairs = data[PAIRS_KEY] || {};
        const pair = pairs[runId];
        if (pair) {
          if (pair.agentTabId === tabId) delete pair.agentTabId;
          if (pair.items) {
            for (const [iid, tid] of Object.entries(pair.items)) {
              if (Number(tid) === Number(tabId)) delete pair.items[iid];
            }
          }
          if (pair.spawnedByItem) {
            for (const [iid, list] of Object.entries(pair.spawnedByItem)) {
              pair.spawnedByItem[iid] = (list || []).filter(
                (id) => Number(id) !== Number(tabId),
              );
            }
          }
          await chrome.storage.session.set({ [PAIRS_KEY]: pairs });
        }
      }
      clearMapsForTab(tabId);
      return { ...base, tab_id: tabId, duration_ms: Date.now() - started };
    }

    return { ...base, duration_ms: Date.now() - started };
  } catch (err) {
    return {
      ...base,
      ok: false,
      error: String(err),
      duration_ms: Date.now() - started,
    };
  }
}

function mintRunId() {
  return `desk_${crypto.randomUUID().replace(/-/g, "").slice(0, 16)}`;
}

async function scrollAgentTab(tabId, loops) {
  const waitMs = deskConfig.browser?.default_wait_ms ?? 500;
  const ratio = scrollViewportRatio();
  for (let i = 0; i < loops; i++) {
    await chrome.scripting.executeScript({
      target: { tabId },
      func: (r) => window.scrollBy(0, window.innerHeight * r),
      args: [ratio],
    });
    await new Promise((r) => setTimeout(r, waitMs));
  }
}

async function buildHandoffPayload(tab, intent) {
  const runId = mintRunId();
  const handoffMax = deskConfig.browser?.handoff_excerpt_max_chars ?? 8000;
  const scrapeTextMax = deskConfig.browser?.scrape_text_max_chars ?? 16000;
  const scrapeLinksMax = deskConfig.browser?.scrape_links_max ?? 200;
  const scrollLoops = deskConfig.browser?.handoff_scroll_loops ?? 0;
  const scrollRatio = scrollViewportRatio();
  // Ungrouped temp tab — Virgil · Agent is created only on Run agent.
  const snapshotTabId = await duplicateUngroupedSnapshot(tab.id, runId);
  const scrollLoopsExecuted = scrollLoops > 0 ? scrollLoops : 0;
  if (scrollLoops > 0) {
    await scrollAgentTab(snapshotTabId, scrollLoops);
  }
  const snap = await scrapeTab(snapshotTabId);
  const shot = await screenshotTab(snapshotTabId);
  // Defer agent collage until Run agent — close scrape tab after snapshot.
  await clearHandoffSnapshotTab(runId, snapshotTabId);
  const scrapeTextLen = snap.text?.length ?? 0;
  const metrics = snap.metrics || {};
  const fullTextChars = metrics.full_text_chars ?? scrapeTextLen;
  const fullLinkCount = metrics.full_link_count ?? (snap.links?.length ?? 0);
  const excerpt = snap.text?.slice(0, handoffMax) ?? "";
  return {
    run_id: runId,
    url: tab.url || "",
    title: tab.title || "",
    human_tab_id: tab.id,
    window_id: tab.windowId,
    intent: intent || "",
    snapshot: {
      excerpt,
      links: snap.links,
      screenshot: shot,
      capture: {
        scroll_loops_executed: scrollLoopsExecuted,
        scroll_loops_configured: scrollLoops,
        scroll_viewport_ratio: scrollRatio,
        scrape_text_max_chars: scrapeTextMax,
        handoff_excerpt_max_chars: handoffMax,
        scrape_links_max: scrapeLinksMax,
        scrape_text_chars: scrapeTextLen,
        excerpt_chars: excerpt.length,
        link_count: snap.links?.length ?? 0,
        full_text_chars: fullTextChars,
        full_link_count: fullLinkCount,
        scrape_text_capped: fullTextChars > scrapeTextMax,
        handoff_excerpt_capped: scrapeTextLen > handoffMax,
        links_capped: fullLinkCount > scrapeLinksMax,
      },
    },
  };
}

async function handoffActiveTab(intent, explicitTabId) {
  let tab;
  if (explicitTabId) {
    try {
      tab = await chrome.tabs.get(explicitTabId);
    } catch {
      tab = undefined;
    }
  }
  if (!tab?.id) {
    [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  }
  if (!tab?.id) {
    return { ok: false, error: "no active tab — focus the page to hand off, then try again" };
  }
  if (tab.url?.startsWith("chrome://") || tab.url?.startsWith("chrome-extension://")) {
    return { ok: false, error: "cannot hand off Chrome system or extension pages" };
  }
  if (!wsConnected || ws?.readyState !== WebSocket.OPEN) {
    return { ok: false, error: "extension not connected to host — reload panel when WS connected" };
  }
  let handoff;
  try {
    handoff = await buildHandoffPayload(tab, intent);
  } catch (err) {
    return { ok: false, error: String(err) };
  }
  if (ws?.readyState === WebSocket.OPEN) {
    const resultPromise = new Promise((resolve) => {
      pendingHandoffResolve = resolve;
      setTimeout(() => {
        if (pendingHandoffResolve === resolve) {
          pendingHandoffResolve = null;
          resolve({ ok: false, error: "handoff timeout (Hermes decompose >120s)" });
        }
      }, 120000);
    });
    try {
      ws.send(JSON.stringify({ type: "handoff_started", handoff }));
    } catch (err) {
      pendingHandoffResolve = null;
      return { ok: false, error: `WebSocket send failed: ${err}` };
    }
    const result = await resultPromise;
    if (result.run_id) {
      await rememberHandoffUrl(result.run_id, handoff.url);
    }
    if (result.error) {
      await savePanelMeta({
        lastHandoffError: result.error,
        lastRunId: result.run_id || "",
      });
      return { ok: false, ...result };
    }
    if (result.items?.length) {
      await applyPatch(
        [{ op: "clear" }, ...result.items.map((item) => ({ op: "add", item }))],
        result.run_id,
      );
    }
    if (result.run_id) {
      await savePanelMeta({
        lastRunId: result.run_id,
        lastDecomposition: result.decomposition || "",
        lastHandoffError: "",
      });
    }
    return { ok: result.ok !== false, ...result };
  }
  const res = await fetch(`${hostUrl}/v1/handoff`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(handoff),
  });
  const data = await res.json();
  if (data.run_id) {
    await rememberHandoffUrl(data.run_id, handoff.url);
    await savePanelMeta({
      lastRunId: data.run_id,
      lastDecomposition: data.decomposition || "",
      lastHandoffError: "",
    });
  }
  if (data.items) {
    await applyPatch(
      [{ op: "clear" }, ...data.items.map((item) => ({ op: "add", item }))],
      data.run_id,
    );
  }
  return { ok: true, ...data };
}

async function acceptProposal({ itemId, proposalId, runId }) {
  // Waiting Accept: commit proposal only — no agent tab provisioning until NEXTSTEPS ships.
  const res = await fetch(`${hostUrl}/v1/items/${itemId}/accept`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      run_id: runId,
      proposal_id: proposalId,
      work_item_id: itemId,
    }),
  });
  const data = await res.json();
  chrome.runtime.sendMessage({ type: "boardUpdated" }).catch(() => {});
  return data;
}

async function denyProposal({ itemId, proposalId, runId, reason }) {
  const res = await fetch(`${hostUrl}/v1/items/${itemId}/deny`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      run_id: runId,
      proposal_id: proposalId,
      reason,
    }),
  });
  const data = await res.json();
  chrome.runtime.sendMessage({ type: "boardUpdated" }).catch(() => {});
  return data;
}

async function ensureWsReady() {
  if (wsConnected && ws?.readyState === WebSocket.OPEN) {
    return null;
  }
  connectWs();
  for (let i = 0; i < 24; i++) {
    await new Promise((r) => setTimeout(r, 250));
    if (wsConnected && ws?.readyState === WebSocket.OPEN) {
      return null;
    }
  }
  return "WS disconnected — reload extension or wait for reconnect";
}

async function runAgentItem({ itemId, runId }) {
  const wsErr = await ensureWsReady();
  if (wsErr) {
    return { ok: false, error: wsErr };
  }
  const provisioned = await provisionAgentTabBeforeExecute(itemId, runId);
  if (!provisioned.ok) {
    return provisioned;
  }
  const res = await fetch(`${hostUrl}/v1/items/${itemId}/execute`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ run_id: runId }),
  });
  const data = await res.json();
  if (!res.ok) {
    return { ok: false, error: data.detail || res.statusText, ...data };
  }
  chrome.runtime.sendMessage({ type: "boardUpdated" }).catch(() => {});
  return data;
}

async function completeItem({ itemId, runId }) {
  const wsErr = await ensureWsReady();
  if (wsErr) {
    return { ok: false, error: wsErr };
  }
  const res = await fetch(`${hostUrl}/v1/items/${itemId}/complete`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ run_id: runId }),
  });
  const data = await res.json();
  if (!res.ok) {
    return { ok: false, error: data.detail || res.statusText, ...data };
  }
  chrome.runtime.sendMessage({ type: "boardUpdated" }).catch(() => {});
  return data;
}
