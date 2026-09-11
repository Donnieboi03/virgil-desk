const BOARD_KEY = "virgil_desk_board_v1";
const PAIRS_KEY = "virgil_desk_tab_pairs";
const AGENT_GROUP_TITLE = "Virgil · Agent";
const DEFAULT_HOST = "http://127.0.0.1:8787";

import { applyBoardPatch, chooseNavigationOp, policyBlock as tabPolicyBlock } from "./tabPolicy.js";
import { withProvisionLock, planAgentTabForItem } from "./agentTabs.js";
import {
  authGateParksFromOps,
  planAgentTabPromotion,
  resolveParkAgentTabId,
} from "./tabCustody.js";
import {
  storeTargetMap,
  getTargetMap,
  clearTargetMap,
  clearMapsForTab,
} from "./targetMap.js";
import {
  MEMORY_KEY,
  SEMANTIC_KEY,
  emptyMemory,
  emptySemantic,
  applyMemoryPatch,
  applySemanticPatch,
  partitionMemoryOps,
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
import {
  settleEyes,
  scrapeEyesReady,
  observeEyesReady,
} from "./eyesSettle.js";
import { promoteEyesExcerpt, urlPathHint } from "./eyesEscalate.js";
import { humanAttentionSummary, shouldNotifyAttention } from "./boardNotify.js";
import { loadVault, addVaultFile, getVaultFile } from "./deskVault.js";

const BUNDLE_FILE = "interactObserve.bundle.js";

const HANDOFF_URLS_KEY = "virgil_desk_handoff_urls";
const CONTEXT_HANDOFF_ID = "virgil_desk_handoff_page";
const CONTEXT_HANDOFF_SELECTION_ID = "virgil_desk_handoff_selection";

/** @type {ReturnType<typeof humanAttentionSummary> | null} */
let lastAttention = null;
/** @type {Set<string>} */
const autoRunStarted = new Set();

let ws = null;
let wsReconnectTimer = null;
/** Host URL the current socket was opened against (detect Options / e2e retarget). */
let wsBoundHost = null;
let hostUrl = DEFAULT_HOST;
let deskConfig = {
  browser: {
    scrape_text_max_chars: 16000,
    scrape_links_max: 200,
    scrape_excerpt_max_chars: 4000,
    handoff_excerpt_max_chars: 12000,
    handoff_scroll_loops: 0,
    handoff_scroll_viewport_ratio: 0.85,
    screenshot_mode: "captureVisibleTab",
    default_wait_ms: 500,
    eyes_settle_budget_ms: 2000,
    eyes_settle_poll_ms: 250,
    eyes_settle_min_text_chars: 40,
    eyes_challenge_extra_ms: 8000,
    eyes_deep_text_max_chars: 4000,
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
    semantic_max_facts: 20,
    semantic_packet_max_facts: 10,
    semantic_max_value_chars: 200,
    semantic_max_key_chars: 64,
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
const WS_KEEPALIVE_ALARM = "desk-ws-keepalive";
/** Chrome min alarm period is ~30s (Chrome 120+); keep SW + WS warm. */
const WS_KEEPALIVE_PERIOD_MIN = 0.5;
const PANEL_PORT = "virgil-desk-panel";

/** @type {Set<chrome.runtime.Port>} */
const panelPorts = new Set();

function resolveHostUrl(raw) {
  if (typeof raw === "string" && raw.trim()) return raw.trim().replace(/\/$/, "");
  return DEFAULT_HOST;
}

function ensureWsKeepaliveAlarm() {
  chrome.alarms.create(WS_KEEPALIVE_ALARM, { periodInMinutes: WS_KEEPALIVE_PERIOD_MIN });
}

function bootExtension() {
  chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }).catch(() => {});
  ensureWsKeepaliveAlarm();
  connectWs();
  try {
    ensureContextMenus();
  } catch {
    /* contextMenus optional in some Chromium builds */
  }
}

function ensureContextMenus() {
  if (!chrome.contextMenus?.create) return;
  try {
    chrome.contextMenus.removeAll(() => {
      try {
        chrome.contextMenus.create({
          id: CONTEXT_HANDOFF_ID,
          title: "Hand off to Virgil Desk",
          contexts: ["page", "frame"],
        });
        chrome.contextMenus.create({
          id: CONTEXT_HANDOFF_SELECTION_ID,
          title: "Hand off selection to Virgil Desk",
          contexts: ["selection"],
        });
      } catch {
        /* ignore create races */
      }
    });
  } catch {
    /* ignore */
  }
}

chrome.runtime.onInstalled.addListener(() => {
  bootExtension();
});

chrome.runtime.onStartup.addListener(() => {
  bootExtension();
});

if (chrome.contextMenus?.onClicked) {
  chrome.contextMenus.onClicked.addListener((info, tab) => {
    if (info.menuItemId === CONTEXT_HANDOFF_ID) {
      handoffActiveTab("all visible", tab?.id).catch(() => {});
      return;
    }
    if (info.menuItemId === CONTEXT_HANDOFF_SELECTION_ID) {
      const sel = String(info.selectionText || "").trim().slice(0, 500);
      const intent = sel ? `this item: ${sel}` : "this item";
      handoffActiveTab(intent, tab?.id).catch(() => {});
    }
  });
}

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name !== WS_KEEPALIVE_ALARM) return;
  if (ws?.readyState === WebSocket.OPEN) {
    try {
      ws.send(JSON.stringify({ type: "ping" }));
    } catch {
      connectWs();
    }
  } else {
    connectWs();
  }
});

chrome.runtime.onConnect.addListener((port) => {
  if (port.name !== PANEL_PORT) return;
  panelPorts.add(port);
  connectWs();
  port.onDisconnect.addListener(() => {
    panelPorts.delete(port);
  });
});

chrome.storage.sync.get(["hostUrl"], (data) => {
  hostUrl = resolveHostUrl(data.hostUrl);
  ensureWsKeepaliveAlarm();
  connectWs();
});

chrome.storage.onChanged.addListener((changes, area) => {
  if (area !== "sync" || !changes.hostUrl) return;
  hostUrl = resolveHostUrl(changes.hostUrl.newValue);
  closeWs({ reconnect: false });
  connectWs();
});

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.type === "getPanelMeta") {
    chrome.storage.local.get(META_KEY).then((data) => sendResponse(data[META_KEY] || {}));
    return true;
  }
  if (msg.type === "getHealth") {
    const url = hostUrl || DEFAULT_HOST;
    fetch(`${url}/v1/health`)
      .then((r) => r.json())
      .then((health) =>
        sendResponse({
          ok: true,
          health,
          wsConnected: Boolean(wsConnected && ws?.readyState === WebSocket.OPEN),
          hostUrl: url,
        }),
      )
      .catch((err) =>
        sendResponse({
          ok: false,
          error: String(err),
          wsConnected: Boolean(wsConnected && ws?.readyState === WebSocket.OPEN),
          hostUrl: url,
        }),
      );
    return true;
  }
  if (msg.type === "getBoard") {
    loadBoard().then((board) => sendResponse({ board }));
    return true;
  }
  if (msg.type === "reconnectWs") {
    ensureWsReady()
      .then((err) =>
        sendResponse({
          ok: !err,
          wsConnected: Boolean(wsConnected && ws?.readyState === WebSocket.OPEN),
          error: err || undefined,
          hostUrl,
        }),
      )
      .catch((err) => sendResponse({ ok: false, wsConnected: false, error: String(err) }));
    return true;
  }
  if (msg.type === "handoffTab") {
    handoffActiveTab(msg.intent, msg.tabId).then(sendResponse);
    return true;
  }
  if (msg.type === "listVault") {
    loadVault()
      .then((vault) =>
        sendResponse({
          ok: true,
          files: (vault.files || []).map(({ id, name, mime, added_at }) => ({
            id,
            name,
            mime,
            added_at,
          })),
        }),
      )
      .catch((err) => sendResponse({ ok: false, error: String(err) }));
    return true;
  }
  if (msg.type === "addVaultFile") {
    addVaultFile({ name: msg.name, mime: msg.mime, base64: msg.base64 })
      .then((entry) =>
        sendResponse({
          ok: true,
          file: { id: entry.id, name: entry.name, mime: entry.mime, added_at: entry.added_at },
        }),
      )
      .catch((err) => sendResponse({ ok: false, error: String(err) }));
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
  if (msg.type === "runAgentTab") {
    runAgentTab(msg).then(sendResponse);
    return true;
  }
  if (msg.type === "cancelAgentTab") {
    cancelAgentTab(msg).then(sendResponse);
    return true;
  }
  if (msg.type === "completeItem") {
    completeItem(msg).then(sendResponse);
    return true;
  }
  if (msg.type === "revealAgentTab") {
    revealAgentTab(msg.tabId, {
      itemId: msg.itemId,
      runId: msg.runId,
    }).then(sendResponse);
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

async function loadDeskSemantic() {
  const data = await chrome.storage.local.get(SEMANTIC_KEY);
  return data[SEMANTIC_KEY] || emptySemantic();
}

async function saveDeskSemantic(semantic) {
  await chrome.storage.local.set({ [SEMANTIC_KEY]: semantic });
}

function memoryLimits() {
  const m = deskConfig.memory || {};
  return {
    recentMax: m.recent_max ?? 3,
    maxBullets: m.notepad_max_bullets ?? 20,
    maxChars: m.notepad_max_chars ?? 4000,
  };
}

function semanticLimits() {
  const m = deskConfig.memory || {};
  return {
    maxFacts: m.semantic_max_facts ?? 20,
    maxKeyChars: m.semantic_max_key_chars ?? 64,
    maxValueChars: m.semantic_max_value_chars ?? 200,
  };
}

async function handleMemoryGet(msg) {
  const [memory, semantic, vault] = await Promise.all([
    loadDeskMemory(),
    loadDeskSemantic(),
    loadVault(),
  ]);
  if (ws?.readyState === WebSocket.OPEN) {
    ws.send(
      JSON.stringify({
        type: "memory_snapshot",
        request_id: msg.request_id,
        run_id: msg.run_id,
        memory,
        semantic,
        vault: {
          files: (vault.files || []).map(({ id, name, mime, added_at }) => ({
            id,
            name,
            mime,
            added_at,
          })),
        },
      }),
    );
  }
}

async function handleMemoryPatch(msg) {
  const { memoryOps, semanticOps } = partitionMemoryOps(msg.ops || []);
  if (memoryOps.length) {
    const limits = memoryLimits();
    const current = await loadDeskMemory();
    const next = applyMemoryPatch(current, memoryOps, limits);
    await saveDeskMemory(next);
  }
  if (semanticOps.length) {
    const limits = semanticLimits();
    const current = await loadDeskSemantic();
    const next = applySemanticPatch(current, semanticOps, limits);
    await saveDeskSemantic(next);
  }
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

function closeWs({ reconnect = false } = {}) {
  if (wsReconnectTimer) {
    clearTimeout(wsReconnectTimer);
    wsReconnectTimer = null;
  }
  if (ws) {
    try {
      ws.onclose = null;
      ws.onerror = null;
      ws.onmessage = null;
      ws.onopen = null;
      ws.close();
    } catch {
      /* ignore */
    }
    ws = null;
  }
  wsConnected = false;
  wsBoundHost = null;
  if (reconnect && hostUrl) {
    wsReconnectTimer = setTimeout(connectWs, 1000);
  }
}

function connectWs() {
  if (wsReconnectTimer) {
    clearTimeout(wsReconnectTimer);
    wsReconnectTimer = null;
  }
  hostUrl = resolveHostUrl(hostUrl);
  if (!hostUrl) {
    closeWs({ reconnect: false });
    return;
  }
  // Already live on this host — do not tear down.
  if (
    (ws?.readyState === WebSocket.OPEN || ws?.readyState === WebSocket.CONNECTING) &&
    wsBoundHost === hostUrl
  ) {
    return;
  }
  // Host retarget (e2e / Options) while a socket is mid-handshake.
  if (ws) {
    try {
      ws.onclose = null;
      ws.onerror = null;
      ws.close();
    } catch {
      /* ignore */
    }
    ws = null;
  }
  wsBoundHost = hostUrl;
  try {
    ws = new WebSocket(wsUrl());
  } catch {
    wsConnected = false;
    wsBoundHost = null;
    wsReconnectTimer = setTimeout(connectWs, 1000);
    return;
  }
  ws.onopen = () => {
    wsConnected = true;
    ensureWsKeepaliveAlarm();
    fetchDeskConfig();
    try {
      ws.send(JSON.stringify({ type: "register", extension_version: "0.1.0" }));
    } catch {
      /* ignore */
    }
    chrome.runtime.sendMessage({ type: "connectionUpdated", wsConnected: true }).catch(() => {});
  };
  ws.onerror = () => {
    // onclose will follow; schedule reconnect there.
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
      const cleared = (msg.ops || []).some((p) => p.op === "clear");
      if (cleared && msg.run_id) {
        const board = await loadBoard();
        await maybeAutoRunTabAfterHandoff(msg.run_id, board);
      }
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
      const actOps = new Set(["click", "fill", "upload", "set_files", "key", "scroll"]);
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
    ws = null;
    chrome.runtime.sendMessage({ type: "connectionUpdated", wsConnected: false }).catch(() => {});
    if (!hostUrl) return;
    wsReconnectTimer = setTimeout(connectWs, 1000);
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
  const next = applyBoardPatch(board, ops);
  await saveBoard(next);
  chrome.runtime.sendMessage({ type: "boardUpdated" }).catch(() => {});
  await maybeNotifyHumanAttention(next);

  const parks = authGateParksFromOps(ops, runId);
  const allItems = [...(next.you || []), ...(next.agent || []), ...(next.waiting || [])];
  for (const park of parks) {
    let tabId = park.agentTabId;
    if (tabId == null) {
      tabId = resolveParkAgentTabId(park.youItem, allItems);
    }
    if (tabId == null) continue;
    try {
      await releaseAgentTabToHuman(tabId);
      const shot = await captureIfActive(tabId);
      await postTabCustody({
        itemId: park.youItem.id,
        runId: park.runId || runId,
        action: "park",
        agentTabId: tabId,
        viewportShot: shot,
        flags: shot
          ? { shot_skipped_inactive: false }
          : { shot_skipped_inactive: true },
      });
    } catch {
      /* tab closed / host down — board still updated */
    }
  }
}

async function notifyEnabled() {
  if (deskConfig.execute?.notify_human_attention) return true;
  const data = await chrome.storage.sync.get(["notifyHumanAttention"]);
  return data.notifyHumanAttention === true;
}

async function maybeNotifyHumanAttention(board) {
  const next = humanAttentionSummary(board);
  const prev = lastAttention;
  lastAttention = next;
  const enabled = await notifyEnabled();
  const text = next.total > 0 ? String(next.total) : "";
  try {
    await chrome.action.setBadgeText({ text });
    await chrome.action.setBadgeBackgroundColor({ color: "#b45309" });
  } catch {
    /* older chrome */
  }
  if (!enabled || !shouldNotifyAttention(prev, next)) return;
  const title =
    next.youNeeds && next.waitingNeeds
      ? "Desk needs you"
      : next.youNeeds
        ? "You column needs you"
        : "Waiting needs Accept";
  const message =
    next.titles.slice(0, 2).join(" · ") ||
    `${next.total} item${next.total === 1 ? "" : "s"} need attention`;
  try {
    chrome.notifications.create(`desk-attn-${Date.now()}`, {
      type: "basic",
      iconUrl: "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
      title,
      message,
      priority: 1,
    });
  } catch {
    /* notifications permission */
  }
}

async function maybeAutoRunTabAfterHandoff(runId, board) {
  const auto = deskConfig.execute?.auto_run_tab === true;
  const hostLoop = deskConfig.execute?.runtime === "host_loop";
  if (!auto || !hostLoop || !runId) return;
  if (autoRunStarted.has(runId)) return;
  const itemIds = (board?.agent || [])
    .filter((i) => i && (i.status === "proposed" || i.status === "running"))
    .map((i) => i.id)
    .filter(Boolean);
  if (!itemIds.length) return;
  autoRunStarted.add(runId);
  try {
    const result = await runAgentTab({ runId, itemIds });
    if (!result || result.ok === false) {
      autoRunStarted.delete(runId);
      const detail = result?.error || result?.detail || "auto Run tab failed";
      await savePanelMeta({
        lastRunId: runId,
        lastHandoffError: String(detail).slice(0, 500),
      });
      chrome.runtime.sendMessage({ type: "boardUpdated" }).catch(() => {});
    }
  } catch (err) {
    autoRunStarted.delete(runId);
    await savePanelMeta({
      lastRunId: runId,
      lastHandoffError: String(err?.message || err).slice(0, 500),
    });
    chrome.runtime.sendMessage({ type: "boardUpdated" }).catch(() => {});
  }
}

/** Ungroup agent tab for human; do not activate. */
async function releaseAgentTabToHuman(tabId) {
  try {
    const tab = await chrome.tabs.get(tabId);
    if (tab.groupId != null && tab.groupId !== -1) {
      await chrome.tabs.ungroup(tabId);
    }
  } catch {
    /* already closed or not grouped */
  }
}

/** Screenshot only if tabId is already the active tab in its window. */
async function captureIfActive(tabId) {
  try {
    const tab = await chrome.tabs.get(tabId);
    const [active] = await chrome.tabs.query({ active: true, windowId: tab.windowId });
    if (active?.id !== tabId) return null;
    const dataUrl = await chrome.tabs.captureVisibleTab(tab.windowId, { format: "png" });
    const base64 = dataUrl.split(",")[1] || "";
    return {
      mime: "image/png",
      base64,
      width: 0,
      height: 0,
    };
  } catch {
    return null;
  }
}

async function postTabCustody({ itemId, runId, action, agentTabId, viewportShot, flags }) {
  if (!itemId || !runId || !hostUrl) return;
  try {
    await fetch(`${hostUrl}/v1/items/${itemId}/tab_custody`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        run_id: runId,
        action,
        agent_tab_id: agentTabId,
        viewport_shot: viewportShot || undefined,
        flags: flags || undefined,
      }),
    });
  } catch {
    /* observability best-effort */
  }
}

/**
 * Activate existing agent tab for human (no create). Used by panel + reveal.html.
 */
async function revealAgentTab(tabId, { itemId, runId } = {}) {
  const id = Number(tabId);
  if (!id) return { ok: false, error: "missing tabId" };
  try {
    await releaseAgentTabToHuman(id);
    const tab = await chrome.tabs.get(id);
    await chrome.tabs.update(id, { active: true });
    if (tab.windowId != null) {
      await chrome.windows.update(tab.windowId, { focused: true }).catch(() => {});
    }
    await new Promise((r) => setTimeout(r, deskConfig.browser?.default_wait_ms ?? 200));
    const shot = await captureIfActive(id);
    if (itemId && runId) {
      await postTabCustody({
        itemId,
        runId,
        action: "reveal",
        agentTabId: id,
        viewportShot: shot,
        flags: { shot_skipped_inactive: !shot },
      });
    }
    return { ok: true, tabId: id, has_shot: !!shot };
  } catch (err) {
    return { ok: false, error: String(err?.message || err) };
  }
}

/**
 * Background tab via create({ active: false }) — does not activate (unlike tabs.duplicate).
 */
async function createBackgroundTab(url, windowId) {
  const targetUrl = (url || "").trim();
  if (!targetUrl || targetUrl === "about:blank" || !/^https?:\/\//i.test(targetUrl)) {
    throw new Error("createBackgroundTab requires http(s) url");
  }
  const opts = { url: targetUrl, active: false };
  if (windowId != null) opts.windowId = windowId;
  return chrome.tabs.create(opts);
}

async function createUngroupedSnapshot(humanTabId, runId) {
  /** Handoff scrape only — do NOT create Virgil · Agent (group on Run agent). */
  const human = await chrome.tabs.get(humanTabId);
  const tab = await createBackgroundTab(human.url, human.windowId);
  const data = await chrome.storage.session.get(PAIRS_KEY);
  const pairs = data[PAIRS_KEY] || {};
  pairs[runId] = {
    humanTabId,
    items: pairs[runId]?.items || {},
    spawnedByItem: pairs[runId]?.spawnedByItem || {},
  };
  await chrome.storage.session.set({ [PAIRS_KEY]: pairs });
  return tab.id;
}

async function createAgentTabForItem(humanTabId, runId, itemId) {
  let url = "";
  let windowId;
  try {
    const human = await chrome.tabs.get(humanTabId);
    url = human?.url || "";
    windowId = human?.windowId;
  } catch {
    /* human tab closed — fall back to stored handoff URL */
  }
  if (!url || !/^https?:\/\//i.test(url)) {
    url = await handoffUrlForRun(runId);
  }
  const tab = await createBackgroundTab(url, windowId);
  await ensureAgentGroup(tab.id, tab.windowId);
  await settleTabAfterOpen(tab.id, { requireHttp: true });
  const data = await chrome.storage.session.get(PAIRS_KEY);
  const pairs = data[PAIRS_KEY] || {};
  if (!pairs[runId]) {
    pairs[runId] = { humanTabId, items: {} };
  }
  if (!pairs[runId].items) pairs[runId].items = {};
  pairs[runId].items[itemId] = tab.id;
  pairs[runId].humanTabId = humanTabId;
  pairs[runId].agentTabId = tab.id;
  await chrome.storage.session.set({ [PAIRS_KEY]: pairs });
  return tab.id;
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

/**
 * Point run/item primary agent tab at tabId (openTab destinations for Show-tab custody).
 * Previous primary is retained in spawnedByItem for later cleanup.
 */
async function promoteAgentTab(runId, itemId, tabId, pairs) {
  if (!pairs[runId]) {
    pairs[runId] = { items: {}, spawnedByItem: {} };
  }
  const prev = pairs[runId].agentTabId;
  const plan = planAgentTabPromotion(prev, tabId);
  if (plan.spawnPrev != null && itemId) {
    await trackSpawnedTab(runId, itemId, plan.spawnPrev);
  }
  pairs[runId].agentTabId = plan.agentTabId;
  if (itemId) {
    if (!pairs[runId].items) pairs[runId].items = {};
    pairs[runId].items[itemId] = tabId;
  }
  await chrome.storage.session.set({ [PAIRS_KEY]: pairs });
  if (activeExecute && activeExecute.runId === runId) {
    activeExecute.agentTabId = Number(tabId);
  }
  if (!itemId || !hostUrl) return;
  try {
    await syncItemAgentTab(itemId, runId, tabId);
    const located = await findBoardItem(itemId);
    if (located?.item) {
      located.item.agent_tab_id = tabId;
      await saveBoard(located.board);
      chrome.runtime.sendMessage({ type: "boardUpdated" }).catch(() => {});
    }
  } catch {
    /* mid-flight sync best-effort */
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
        const tab = await chrome.tabs.get(item.agent_tab_id);
        const handoff = await handoffUrlForRun(runId);
        if (
          handoff &&
          (!tab.url || !/^https?:\/\//i.test(tab.url) || tab.url === "about:blank")
        ) {
          await loadUrlInTab(item.agent_tab_id, handoff);
        }
        await ensureAgentGroup(item.agent_tab_id, tab.windowId);
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
    if (plan.source === "create" || !tabId) {
      tabId = await createAgentTabForItem(humanTabId, runId, itemId);
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

  // openTab always creates (or navigates a new tab) — never reuse collage without loading url.
  if (command.op !== "openTab" && pairs[runId]?.agentTabId) {
    return { tabId: pairs[runId].agentTabId, tabMode: "reuse" };
  }
  // duplicateTab is legacy alias — same as openTab (create background; never tabs.duplicate).
  if (command.op === "duplicateTab" || command.op === "openTab") {
    let human = null;
    if (command.human_tab_id) {
      try {
        human = await chrome.tabs.get(command.human_tab_id);
      } catch {
        // Human tab may be closed — still allow openTab when command.url is valid https.
        human = null;
      }
    }
    const targetUrl = (command.url || human?.url || command.handoff_url || "").trim();
    if (!targetUrl || targetUrl === "about:blank" || !/^https?:\/\//i.test(targetUrl)) {
      return {
        tabId: null,
        tabMode: "error",
        placement: "agent",
        error: "openTab requires http(s) url",
      };
    }

    // Prefer loading into the existing agent tab (Run-tab rescue) instead of spawning another.
    const existingId = command.tab_id ?? pairs[runId]?.agentTabId;
    if (existingId != null) {
      try {
        await chrome.tabs.get(existingId);
        await loadUrlInTab(existingId, targetUrl);
        await ensureAgentGroup(
          existingId,
          (await chrome.tabs.get(existingId)).windowId,
        );
        if (!pairs[runId]) {
          pairs[runId] = {
            humanTabId: command.human_tab_id,
            items: {},
            spawnedByItem: {},
          };
        }
        pairs[runId].humanTabId = pairs[runId].humanTabId || command.human_tab_id;
        await promoteAgentTab(runId, activeExecute?.itemId, existingId, pairs);
        return { tabId: existingId, tabMode: "navigate", placement: "agent" };
      } catch (err) {
        const msg = String(err?.message || err);
        // Fall through to create only if the existing tab is gone.
        if (!/No tab with id/i.test(msg)) {
          return {
            tabId: null,
            tabMode: "error",
            placement: "agent",
            error: msg,
          };
        }
      }
    }

    const windowId = human?.windowId;
    const tab = await createBackgroundTab(targetUrl, windowId);
    await ensureAgentGroup(tab.id, tab.windowId);
    await settleTabAfterOpen(tab.id, { requireHttp: true });
    if (!pairs[runId]) {
      pairs[runId] = {
        humanTabId: command.human_tab_id,
        items: {},
        spawnedByItem: {},
      };
    }
    pairs[runId].humanTabId = pairs[runId].humanTabId || command.human_tab_id;
    // Always promote: Show-tab / auth_gate mint must target the tab the agent just opened.
    await promoteAgentTab(runId, activeExecute?.itemId, tab.id, pairs);
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
  let metaUrl = "";
  let metaTitle = "";
  try {
    const tab = await chrome.tabs.get(tabId);
    metaUrl = tab?.url || "";
    metaTitle = tab?.title || "";
  } catch (err) {
    const msg = String(err?.message || err);
    if (/No tab with id/i.test(msg)) {
      return {
        ...normalizeScrapeResult(null),
        tab_missing: true,
        error: msg,
      };
    }
  }
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
    const normalized = normalizeScrapeResult(result);
    if (!normalized.url && metaUrl) normalized.url = metaUrl;
    if (!normalized.title && metaTitle) normalized.title = metaTitle;
    return normalized;
  } catch (err) {
    const msg = String(err?.message || err);
    if (/No tab with id/i.test(msg)) {
      return {
        ...normalizeScrapeResult(null),
        tab_missing: true,
        error: msg,
      };
    }
    const fallback = normalizeScrapeResult(null);
    if (metaUrl) fallback.url = metaUrl;
    if (metaTitle) fallback.title = metaTitle;
    return fallback;
  }
}

async function assertTabAlive(tabId) {
  if (tabId == null) return "missing tab_id";
  try {
    await chrome.tabs.get(tabId);
    return null;
  } catch (err) {
    return String(err?.message || err);
  }
}

async function settleScrapeEyes(tabId) {
  const budgetMs = deskConfig.browser?.eyes_settle_budget_ms ?? 2000;
  const pollMs = deskConfig.browser?.eyes_settle_poll_ms ?? 250;
  const minChars = deskConfig.browser?.eyes_settle_min_text_chars ?? 40;
  const challengeExtraMs = deskConfig.browser?.eyes_challenge_extra_ms ?? 8000;
  return settleEyes({
    scrape: () => scrapeTab(tabId),
    isReady: (snap) =>
      Boolean(snap?.tab_missing) || scrapeEyesReady(snap, minChars),
    budgetMs,
    pollMs,
    challengeExtraMs,
  });
}

function eyesMetaFromSettle(settled, { targetCount = 0, minChars = 40 } = {}) {
  const snap = settled?.result || {};
  const text = snap.text || "";
  const empty =
    !observeEyesReady({ text, targetCount }, minChars) &&
    !scrapeEyesReady(snap, minChars);
  const meta = {
    eyes_settle_ms: settled?.elapsedMs ?? 0,
    eyes_settle_attempts: settled?.attempts ?? 0,
    eyes_empty: Boolean(empty),
  };
  if (settled?.challenge_extended != null) {
    meta.challenge_extended = Boolean(settled.challenge_extended);
  }
  return meta;
}

async function runDeepText(tabId) {
  const allFrames = observeAllFrames();
  const { inject_ms } = await injectInteractBundle(tabId, { allFrames });
  const maxChars = deskConfig.browser?.eyes_deep_text_max_chars ?? 4000;
  try {
    const results = await chrome.scripting.executeScript({
      target: allFrames ? { tabId, allFrames: true } : { tabId },
      world: "MAIN",
      func: (o) => globalThis.deskDeepText(o),
      args: [{ maxChars }],
    });
    const chunks = [];
    let used = 0;
    let title = "";
    let url = "";
    for (const entry of results || []) {
      const text = entry.result?.text;
      if (!text) continue;
      if (!title && entry.result?.title) title = entry.result.title;
      if (!url && entry.result?.url) url = entry.result.url;
      const header =
        (entry.frameId ?? 0) === 0 ? "" : `\n--- frame ${entry.frameId} ---\n`;
      const piece = `${header}${text}`;
      if (used + piece.length > maxChars) {
        chunks.push(piece.slice(0, Math.max(0, maxChars - used)));
        break;
      }
      chunks.push(piece);
      used += piece.length;
    }
    return {
      text: chunks.length ? chunks.join("\n") : "",
      title,
      url,
      inject_ms,
      frame_count: (results || []).length,
    };
  } catch {
    return { text: "", title: "", url: "", inject_ms, frame_count: 0 };
  }
}

/**
 * Fail-only Eyes ladder after T0 settle. Returns mode + possibly promoted excerpt.
 * @returns {Promise<{
 *   eyes_mode: 0|1|2,
 *   eyes_empty: boolean,
 *   scrape_excerpt: string,
 *   text_omitted: boolean,
 *   excerpt_note?: string,
 *   page_tree: string|null|undefined,
 *   eyes_hints?: { url_path_hint: string },
 * }>}
 */
async function applyEyesEscalation({
  tabId,
  runId,
  url,
  title,
  eyesMeta,
  excerpt,
  includeTreeAlready,
  pageTreeAlready,
}) {
  const minChars = deskConfig.browser?.eyes_settle_min_text_chars ?? 40;
  const maxExcerpt = deskConfig.browser?.scrape_excerpt_max_chars ?? 4000;

  if (!eyesMeta?.eyes_empty) {
    return {
      eyes_mode: 0,
      eyes_empty: false,
      scrape_excerpt: excerpt?.text || "",
      text_omitted: Boolean(excerpt?.text_omitted),
      excerpt_note: excerpt?.note,
      page_tree: pageTreeAlready,
    };
  }

  // T1: one deep text + forced tree; promote into excerpt (replace, don't stack).
  const phase = {};
  const deep = await runDeepText(tabId).catch(() => ({ text: "" }));
  mergeActPhase(phase, deep);
  let page_tree = pageTreeAlready;
  if (!includeTreeAlready || !page_tree) {
    const treeResult = await runPageTree(tabId, { includeTree: true }).catch(
      () => null,
    );
    if (treeResult && typeof treeResult === "object") {
      page_tree = treeResult.page_tree ?? null;
      mergeActPhase(phase, treeResult);
    } else {
      page_tree = treeResult;
    }
  }
  const promoted = promoteEyesExcerpt(deep.text, page_tree, {
    minChars,
    maxChars: maxExcerpt,
  });

  if (promoted) {
    // Force non-omitted so same-URL omit does not swallow the first useful excerpt.
    excerptBaselineMap = setLastFullTextUrl(
      excerptBaselineMap,
      runId,
      tabId,
      url || "",
    );
    return {
      eyes_mode: 1,
      eyes_empty: false,
      scrape_excerpt: promoted,
      text_omitted: false,
      excerpt_note: "eyes_mode_1_promoted",
      page_tree: page_tree || undefined,
      ...phase,
    };
  }

  // T2: soft URL/title hints only.
  const hint = urlPathHint(url, title || deep.title);
  const eyes_hints = hint ? { url_path_hint: hint } : undefined;
  return {
    eyes_mode: 2,
    eyes_empty: true,
    scrape_excerpt: excerpt?.text || "",
    text_omitted: Boolean(excerpt?.text_omitted),
    excerpt_note: excerpt?.note,
    page_tree: page_tree || undefined,
    eyes_hints,
    ...phase,
  };
}

async function settleTabAfterOpen(tabId, { requireHttp = false } = {}) {
  const ms = deskConfig.browser?.default_wait_ms ?? 500;
  if (tabId == null) {
    await new Promise((r) => setTimeout(r, ms));
    return;
  }
  const timeoutMs = Math.max(ms, requireHttp ? 8000 : 2000);
  const deadline = Date.now() + timeoutMs;

  function urlOk(url) {
    if (!requireHttp) return true;
    const u = (url || "").trim();
    return /^https?:\/\//i.test(u);
  }

  while (Date.now() < deadline) {
    try {
      const tab = await chrome.tabs.get(tabId);
      if (tab?.status === "complete" && urlOk(tab.url)) {
        await new Promise((r) => setTimeout(r, Math.min(ms, 200)));
        return;
      }
    } catch {
      return;
    }
    await new Promise((r) => setTimeout(r, 200));
  }
}

/** Navigate an existing agent tab (prefer over creating another when rescuing empty Eyes). */
async function loadUrlInTab(tabId, url) {
  const targetUrl = (url || "").trim();
  if (!targetUrl || !/^https?:\/\//i.test(targetUrl)) {
    throw new Error("loadUrlInTab requires http(s) url");
  }
  await chrome.tabs.update(tabId, { url: targetUrl });
  await settleTabAfterOpen(tabId, { requireHttp: true });
  return tabId;
}

/** Safe first-frame result from chrome.scripting.executeScript (may be empty). */
function scriptInjectionResult(injected, fallback = null) {
  return injected?.[0]?.result ?? fallback;
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
  const t0 = Date.now();
  await chrome.scripting.executeScript({
    target: allFrames ? { tabId, allFrames: true } : { tabId },
    files: [BUNDLE_FILE],
    world: "MAIN",
  });
  return { inject_ms: Math.max(0, Date.now() - t0) };
}

async function readViewportMeta(tabId) {
  try {
    const injected = await chrome.scripting.executeScript({
      target: { tabId },
      func: () => ({
        w: window.innerWidth,
        h: window.innerHeight,
        device_pixel_ratio: window.devicePixelRatio || 1,
      }),
    });
    return (
      scriptInjectionResult(injected) || {
        w: 0,
        h: 0,
        device_pixel_ratio: 1,
      }
    );
  } catch {
    return { w: 0, h: 0, device_pixel_ratio: 1 };
  }
}


function mergeActPhase(actPhase, act) {
  if (!act || typeof act !== "object") return actPhase;
  if (act.inject_ms != null) {
    actPhase.inject_ms =
      (actPhase.inject_ms || 0) + (Number(act.inject_ms) || 0);
  }
  if (act.frame_count != null) {
    const prev = actPhase.frame_count;
    const next = Number(act.frame_count) || 0;
    actPhase.frame_count =
      prev == null ? next : Math.max(Number(prev) || 0, next);
  }
  return actPhase;
}

function actFailResult(base, act, started, actPhase) {
  mergeActPhase(actPhase, act);
  return {
    ...base,
    ok: false,
    error: act?.error,
    act_resolved: act?.act_resolved,
    ...actPhase,
    duration_ms: Date.now() - started,
  };
}

async function runPageObserve(tabId, opts) {
  const allFrames = observeAllFrames();
  const { inject_ms } = await injectInteractBundle(tabId, { allFrames });
  const results = await chrome.scripting.executeScript({
    target: allFrames ? { tabId, allFrames: true } : { tabId },
    world: "MAIN",
    func: (o) => globalThis.deskObserve(o),
    args: [opts],
  });
  const frame_count = (results || []).length;
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
    inject_ms,
    frame_count,
  };
}

async function runPageTree(tabId, { includeTree }) {
  if (!includeTree) return null;
  const allFrames = observeAllFrames();
  const { inject_ms } = await injectInteractBundle(tabId, { allFrames });
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
  return {
    page_tree: chunks.length ? chunks.join("\n") : null,
    inject_ms,
    frame_count: (results || []).length,
  };
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
  const { inject_ms } = await injectInteractBundle(tabId, { allFrames });
  const target =
    Number.isFinite(frameId) && frameId > 0
      ? { tabId, frameIds: [frameId] }
      : { tabId };
  const injected = await chrome.scripting.executeScript({
    target,
    world: "MAIN",
    func: (operation, p, t, before) => globalThis.deskAct(operation, p, t, before),
    args: [op, params, targets, urlBefore],
  });
  const act =
    scriptInjectionResult(injected) || {
      ok: false,
      error: "act inject returned null",
    };
  return {
    ...act,
    inject_ms,
    frame_count: (injected || []).length,
  };
}

async function runPageProbe(tabId, kind) {
  const allFrames = observeAllFrames();
  const { inject_ms } = await injectInteractBundle(tabId, { allFrames });
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
  const frame_count = (results || []).length;
  const phase = { inject_ms, frame_count };
  if (kind === "probe_form") {
    const form_fields = [];
    for (const entry of results || []) {
      for (const f of entry.result?.form_fields || []) {
        if (form_fields.length >= 40) break;
        form_fields.push({ ...f, frame_id: entry.frameId ?? 0 });
      }
    }
    return { form_fields, url: results?.[0]?.result?.url, ...phase };
  }
  if (kind === "probe_links") {
    const links = [];
    for (const entry of results || []) {
      for (const l of entry.result?.links || []) {
        if (links.length >= 80) break;
        links.push({ ...l, frame_id: entry.frameId ?? 0 });
      }
    }
    return { links, url: results?.[0]?.result?.url, ...phase };
  }
  // probe_table: prefer first frame with rows
  for (const entry of results || []) {
    if (entry.result?.found && entry.result?.rows?.length) {
      return { ...entry.result, frame_id: entry.frameId ?? 0, ...phase };
    }
  }
  return {
    ...(results?.[0]?.result || { rows: [], found: false }),
    ...phase,
  };
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
  try {
    const injected = await chrome.scripting.executeScript({
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
    return scriptInjectionResult(injected);
  } catch {
    return null;
  }
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
      if (snap?.tab_missing || snap?.error) {
        return {
          ...base,
          ok: false,
          error: snap.error || "handoff tab missing",
          duration_ms: Date.now() - started,
        };
      }
      return {
        ...base,
        url: snap.url,
        title: snap.title,
        scrape_excerpt: snap.text?.slice(0, handoffMax),
        duration_ms: Date.now() - started,
      };
    }

    let tabId = command.tab_id;
    if (command.op === "duplicateTab" || command.op === "openTab") {
      const resolved = await resolveAgentTab(command);
      if (resolved.error || !resolved.tabId) {
        return {
          ...base,
          ok: false,
          error: resolved.error || "openTab requires http(s) url",
          duration_ms: Date.now() - started,
        };
      }
      tabId = resolved.tabId;
      await settleTabAfterOpen(tabId);
    }

    const block = policyBlock(command, tabId);
    if (block) {
      return { ...base, ok: false, error: block, duration_ms: Date.now() - started };
    }

    // Fail fast on dead tab ids — do not mask as empty Eyes (scrape used to).
    if (
      command.op !== "openTab" &&
      command.op !== "duplicateTab" &&
      command.op !== "captureHandoffSnapshot"
    ) {
      const missing = await assertTabAlive(tabId);
      if (missing) {
        return {
          ...base,
          ok: false,
          error: missing,
          tab_id: tabId,
          duration_ms: Date.now() - started,
        };
      }
    }

    if (command.op === "observe") {
      const maxTargets = deskConfig.browser?.interact_targets_max ?? 40;
      const annotate =
        command.params?.annotate ??
        deskConfig.browser?.observe_annotate_default ??
        true;
      const minChars = deskConfig.browser?.eyes_settle_min_text_chars ?? 40;

      const settled = await settleScrapeEyes(tabId);
      let snap = settled.result || (await scrapeTab(tabId));
      if (snap?.tab_missing || (snap?.error && /No tab with id/i.test(String(snap.error)))) {
        return {
          ...base,
          ok: false,
          error: snap.error || "No tab with id",
          tab_id: tabId,
          duration_ms: Date.now() - started,
        };
      }
      let pageObserve = null;
      if (!scrapeEyesReady(snap, minChars)) {
        pageObserve = await runPageObserve(tabId, { maxTargets, annotate });
        if (
          observeEyesReady(
            {
              text: snap.text,
              targetCount: (pageObserve?.interact_targets || []).length,
            },
            minChars,
          )
        ) {
          // targets alone count as ready
        } else {
          // one more scrape after interact in case paint raced
          snap = await scrapeTab(tabId);
        }
      }
      if (!pageObserve) {
        pageObserve = await runPageObserve(tabId, { maxTargets, annotate });
      }
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
      const eyesMeta = eyesMetaFromSettle(
        {
          ...settled,
          // include post-interact scrape/targets in empty check
          result: snap,
        },
        {
          targetCount: interact_targets_full.length,
          minChars,
        },
      );
      // Force AX tree when Eyes still empty or URL change (no screenshot / no focus).
      const includeTree = !excerpt.text_omitted || eyesMeta.eyes_empty;
      const injectPhase = {};
      mergeActPhase(injectPhase, pageObserve);
      const treeResult = await runPageTree(tabId, { includeTree }).catch(
        () => null,
      );
      let page_tree =
        treeResult && typeof treeResult === "object"
          ? treeResult.page_tree
          : treeResult;
      mergeActPhase(injectPhase, treeResult);
      const escalated = await applyEyesEscalation({
        tabId,
        runId: command.run_id,
        url: pageUrl,
        title: pageObserve?.title || snap.title,
        eyesMeta,
        excerpt,
        includeTreeAlready: includeTree,
        pageTreeAlready: page_tree,
      });
      page_tree = escalated.page_tree ?? page_tree;
      mergeActPhase(injectPhase, escalated);
      const interact_targets = interact_targets_full.map(slimTargetForEyes);
      const observe = {
        url: pageUrl,
        title: pageObserve?.title || snap.title,
        viewport: pageObserve?.viewport || { w: 0, h: 0 },
        device_pixel_ratio: pageObserve?.device_pixel_ratio ?? 1,
        text_excerpt: escalated.scrape_excerpt,
        text_omitted: escalated.text_omitted,
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
      if (escalated.excerpt_note) observe.excerpt_note = escalated.excerpt_note;
      if (page_tree) observe.page_tree = page_tree;
      const out = {
        ...base,
        tab_id: tabId,
        url: observe.url,
        title: observe.title,
        scrape_excerpt: observe.text_excerpt,
        text_omitted: escalated.text_omitted,
        excerpt_note: escalated.excerpt_note,
        observe,
        interact_targets,
        scroll_containers: observe.scroll_containers,
        viewport: observe.viewport,
        device_pixel_ratio: observe.device_pixel_ratio,
        page_tree: page_tree || undefined,
        screenshot: shot,
        eyes_settle_ms: eyesMeta.eyes_settle_ms,
        eyes_settle_attempts: eyesMeta.eyes_settle_attempts,
        eyes_empty: escalated.eyes_empty,
        eyes_mode: escalated.eyes_mode,
        duration_ms: Date.now() - started,
      };
      if (eyesMeta.challenge_extended != null) {
        out.challenge_extended = eyesMeta.challenge_extended;
      }
      if (injectPhase.inject_ms != null) out.inject_ms = injectPhase.inject_ms;
      if (injectPhase.frame_count != null) {
        out.frame_count = injectPhase.frame_count;
      }
      if (escalated.eyes_hints) out.eyes_hints = escalated.eyes_hints;
      return out;
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
    let actPhase = {};
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
          return actFailResult(base, act, started, actPhase);
        }
        actResolved = act.act_resolved;
        mergeActPhase(actPhase, act);
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
          return actFailResult(base, act, started, actPhase);
        }
        actResolved = act.act_resolved;
        mergeActPhase(actPhase, act);
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
          return actFailResult(base, act, started, actPhase);
        }
        actResolved = act.act_resolved;
        mergeActPhase(actPhase, act);
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
        const injected = await chrome.scripting.executeScript({
          target: { tabId },
          func: (s) => {
            const el = document.querySelector(s);
            if (!el) return false;
            el.click();
            return true;
          },
          args: [params.selector],
        });
        const clicked = scriptInjectionResult(injected, false);
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
          return actFailResult(base, act, started, actPhase);
        }
        actResolved = act.act_resolved;
        mergeActPhase(actPhase, act);
      } else if (params.selector) {
        const sel = params.selector;
        const val = params.value || "";
        const injected = await chrome.scripting.executeScript({
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
        const filled = scriptInjectionResult(injected, false);
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
    } else if (command.op === "upload" || command.op === "set_files") {
      const params = command.params || {};
      const vaultId = params.vault_id || params.vaultId;
      if (!vaultId) {
        return {
          ...base,
          ok: false,
          error: "upload requires vault_id (add a file in Desk options vault)",
          duration_ms: Date.now() - started,
        };
      }
      const entry = await getVaultFile(String(vaultId));
      if (!entry) {
        return {
          ...base,
          ok: false,
          error: `vault file not found: ${vaultId}`,
          duration_ms: Date.now() - started,
        };
      }
      const stored = getTargetMap(command.run_id, tabId);
      let selector = params.selector || "";
      let targetMeta = null;
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
        const targets = stored?.interact_targets || [];
        targetMeta =
          targets.find((t) => t.id === params.target_id) ||
          targets.find((t) => t.ref === params.ref) ||
          null;
        if (!targetMeta) {
          return {
            ...base,
            ok: false,
            error: "upload target_id not in observe map — re-observe",
            duration_ms: Date.now() - started,
          };
        }
        if (targetMeta.kind && targetMeta.kind !== "file") {
          return {
            ...base,
            ok: false,
            error: `upload target kind is ${targetMeta.kind}, expected file`,
            duration_ms: Date.now() - started,
          };
        }
        selector = targetMeta.selector_hint || targetMeta.selector || selector;
      }
      const injected = await chrome.scripting.executeScript({
        target: { tabId },
        func: (sel, targetId, name, mime, b64) => {
          let el = null;
          if (sel) el = document.querySelector(sel);
          if (!el && targetId != null) {
            el = document.querySelector(`[data-virgil-target-id="${targetId}"]`);
          }
          if (!el) {
            const files = Array.from(document.querySelectorAll('input[type="file"]'));
            el = files.find((f) => f.offsetParent !== null) || files[0] || null;
          }
          if (!el || el.tagName !== "INPUT" || (el.type || "").toLowerCase() !== "file") {
            return { ok: false, error: "file input not found" };
          }
          try {
            const bin = atob(b64);
            const bytes = new Uint8Array(bin.length);
            for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
            const file = new File([bytes], name, { type: mime || "application/octet-stream" });
            const dt = new DataTransfer();
            dt.items.add(file);
            el.files = dt.files;
            el.dispatchEvent(new Event("input", { bubbles: true }));
            el.dispatchEvent(new Event("change", { bubbles: true }));
            return { ok: true, files: el.files?.length || 0 };
          } catch (err) {
            return { ok: false, error: String(err) };
          }
        },
        args: [
          selector || "",
          params.target_id ?? null,
          entry.name,
          entry.mime,
          entry.base64,
        ],
      });
      const up = scriptInjectionResult(injected, { ok: false, error: "inject failed" });
      if (!up?.ok) {
        return {
          ...base,
          ok: false,
          error: up?.error || "upload failed",
          duration_ms: Date.now() - started,
        };
      }
      return {
        ...base,
        ok: true,
        tab_id: tabId,
        act_resolved: {
          op: "upload",
          requested: { vault_id: vaultId, target_id: params.target_id },
          used: selector ? "selector" : "file_input",
          url_before: urlBeforeAct,
          url_after: (await scrapeTab(tabId).catch(() => ({}))).url,
        },
        duration_ms: Date.now() - started,
      };
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
        return actFailResult(base, act, started, actPhase);
      }
      actResolved = act.act_resolved;
      mergeActPhase(actPhase, act);
    } else if (command.op === "wait") {
      await new Promise((r) => setTimeout(r, command.params?.ms || 500));
    }

    if (["click", "fill", "scroll", "key", "scrape", "screenshot", "openTab", "duplicateTab"].includes(command.op)) {
      const minChars = deskConfig.browser?.eyes_settle_min_text_chars ?? 40;
      const useSettle =
        command.op === "openTab" ||
        command.op === "duplicateTab" ||
        command.op === "scrape";
      let snap;
      let settled = null;
      if (useSettle) {
        settled = await settleScrapeEyes(tabId);
        snap = settled.result || (await scrapeTab(tabId));
      } else {
        snap = await scrapeTab(tabId);
      }
      if (snap?.tab_missing || (snap?.error && /No tab with id/i.test(String(snap.error)))) {
        return {
          ...base,
          ok: false,
          error: snap.error || "No tab with id",
          tab_id: tabId,
          duration_ms: Date.now() - started,
        };
      }
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
      const eyesMeta = settled
        ? eyesMetaFromSettle(settled, { minChars })
        : {};
      let out = {
        ...base,
        tab_id: tabId,
        url: snap.url,
        title: snap.title,
        scrape_excerpt: excerpt.text,
        text_omitted: excerpt.text_omitted,
        excerpt_note: excerpt.note,
        screenshot: shot,
        act_resolved: actResolved,
        ...eyesMeta,
        ...actPhase,
        duration_ms: Date.now() - started,
      };
      if (settled && eyesMeta.eyes_empty) {
        const escalated = await applyEyesEscalation({
          tabId,
          runId: command.run_id,
          url: snap.url,
          title: snap.title,
          eyesMeta,
          excerpt,
          includeTreeAlready: false,
          pageTreeAlready: null,
        });
        out = {
          ...out,
          scrape_excerpt: escalated.scrape_excerpt,
          text_omitted: escalated.text_omitted,
          excerpt_note: escalated.excerpt_note,
          eyes_empty: escalated.eyes_empty,
          eyes_mode: escalated.eyes_mode,
          page_tree: escalated.page_tree || undefined,
          duration_ms: Date.now() - started,
        };
        mergeActPhase(actPhase, escalated);
        if (actPhase.inject_ms != null) out.inject_ms = actPhase.inject_ms;
        if (actPhase.frame_count != null) out.frame_count = actPhase.frame_count;
        if (escalated.eyes_hints) out.eyes_hints = escalated.eyes_hints;
      } else if (settled) {
        out.eyes_mode = 0;
      }
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
  // Default (scroll=0): scrape + shot the human tab — no extra tab (avoids empty SPA shells).
  // Scroll >0 uses a short-lived background create so we don't move the human viewport.
  let snapshotTabId = tab.id;
  let usedScrapeTab = false;
  if (scrollLoops > 0) {
    snapshotTabId = await createUngroupedSnapshot(tab.id, runId);
    usedScrapeTab = true;
    await scrollAgentTab(snapshotTabId, scrollLoops);
  }
  const scrollLoopsExecuted = scrollLoops > 0 ? scrollLoops : 0;
  const settled = await settleScrapeEyes(snapshotTabId);
  const snap = settled.result || (await scrapeTab(snapshotTabId));
  const shot = await screenshotTab(snapshotTabId);
  if (usedScrapeTab) {
    await clearHandoffSnapshotTab(runId, snapshotTabId);
  }
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
        used_scrape_tab: usedScrapeTab,
        used_duplicate_tab: usedScrapeTab,
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
      const board = await loadBoard();
      await maybeAutoRunTabAfterHandoff(result.run_id, board);
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
    const board = await loadBoard();
    await maybeAutoRunTabAfterHandoff(data.run_id, board);
  }
  return { ok: true, ...data };
}

async function acceptProposal({ itemId, proposalId, runId }) {
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
  if (data.needs_agent_tab) {
    // Wait for host board_patch (Waiting → Agent) before provision so we don't
    // race applyPatch and drop agent_tab_id on a stale waiting-column snapshot.
    await waitForBoardItemColumn(itemId, "agent", 2500);
    const provisioned = await provisionAgentTabForWaitingItem(itemId, runId).catch(
      (err) => ({ ok: false, error: String(err?.message || err) }),
    );
    if (provisioned && provisioned.ok === false) {
      data.provision_error = provisioned.error;
    } else if (provisioned?.agentTabId != null) {
      data.agent_tab_id = provisioned.agentTabId;
    }
  }
  chrome.runtime.sendMessage({ type: "boardUpdated" }).catch(() => {});
  return data;
}

/** Poll until item is on the expected column (host board_patch applied). */
async function waitForBoardItemColumn(itemId, column, timeoutMs = 2000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const located = await findBoardItem(itemId);
    if (located?.item && (located.column === column || located.item.column === column)) {
      return located;
    }
    await new Promise((r) => setTimeout(r, 50));
  }
  return findBoardItem(itemId);
}

/**
 * Waiting Accept that needs UI: duplicate from handoff human tab (same as Agent provision).
 */
async function provisionAgentTabForWaitingItem(itemId, runId) {
  return withProvisionLock(runId, async () => {
    // Always re-load inside the lock — Accept's board_patch may have just landed.
    let located = await findBoardItem(itemId);
    if (!located?.item) {
      return { ok: false, error: "work item not found on board" };
    }
    let { item, board } = located;
    const runPair = await loadRunPair(runId);
    const humanTabId = item.human_tab_id || runPair?.humanTabId;
    if (!humanTabId) {
      return { ok: false, error: "missing human_tab_id" };
    }
    if (item.agent_tab_id) {
      try {
        await chrome.tabs.get(item.agent_tab_id);
        return { ok: true, agentTabId: item.agent_tab_id, humanTabId };
      } catch {
        /* reprovision */
      }
    }
    const tabId = await createAgentTabForItem(humanTabId, runId, itemId);
    if (!tabId) {
      return { ok: false, error: "failed to provision agent tab" };
    }
    // Re-load board before save so a concurrent board_patch cannot wipe this stamp.
    located = await findBoardItem(itemId);
    board = located?.board || (await loadBoard());
    item = located?.item || item;
    const col = item.column || located?.column || "agent";
    const list = board[col] || [];
    const idx = list.findIndex((i) => i.id === itemId);
    const stamped = {
      ...(idx >= 0 ? list[idx] : item),
      id: itemId,
      column: col,
      agent_tab_id: tabId,
      human_tab_id: humanTabId,
    };
    if (idx >= 0) list[idx] = stamped;
    else {
      if (!board.agent) board.agent = [];
      board.agent.push({ ...stamped, column: "agent" });
    }
    board[col] = list;
    await saveBoard(board);
    try {
      await syncItemAgentTab(itemId, runId, tabId);
    } catch (err) {
      return { ok: false, error: String(err.message || err) };
    }
    const data = await chrome.storage.session.get(PAIRS_KEY);
    const pairs = data[PAIRS_KEY] || {};
    if (!pairs[runId]) pairs[runId] = { humanTabId, items: {} };
    pairs[runId].humanTabId = humanTabId;
    pairs[runId].agentTabId = tabId;
    if (!pairs[runId].items) pairs[runId].items = {};
    pairs[runId].items[itemId] = tabId;
    await chrome.storage.session.set({ [PAIRS_KEY]: pairs });
    chrome.runtime.sendMessage({ type: "boardUpdated" }).catch(() => {});
    return { ok: true, agentTabId: tabId, humanTabId };
  });
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
  for (let i = 0; i < 40; i++) {
    await new Promise((r) => setTimeout(r, 250));
    if (wsConnected && ws?.readyState === WebSocket.OPEN) {
      return null;
    }
    // If handshake died mid-wait, kick again.
    if (!ws || ws.readyState === WebSocket.CLOSED || ws.readyState === WebSocket.CLOSING) {
      connectWs();
    }
  }
  return "WS disconnected — open Virgil Desk side panel and wait, or reload extension";
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

/**
 * Provision one shared agent tab for the run, stamp all eligible Agent roots,
 * then POST /v1/runs/{run_id}/execute (Run tab).
 */
async function provisionAgentTabForRun(runId, itemIds) {
  if (!itemIds?.length) {
    return { ok: false, error: "no agent items to run" };
  }
  const firstId = itemIds[0];
  const provisioned = await provisionAgentTabBeforeExecute(firstId, runId);
  if (!provisioned.ok) return provisioned;
  const { agentTabId, humanTabId } = provisioned;
  const board = await loadBoard();
  for (const col of ["you", "agent", "waiting"]) {
    for (const item of board[col] || []) {
      if (itemIds.includes(item.id)) {
        item.agent_tab_id = agentTabId;
        item.human_tab_id = humanTabId;
        try {
          await syncItemAgentTab(item.id, runId, agentTabId);
        } catch {
          /* host may already get tab from execute_run body */
        }
      }
    }
  }
  await saveBoard(board);
  const data = await chrome.storage.session.get(PAIRS_KEY);
  const pairs = data[PAIRS_KEY] || {};
  if (!pairs[runId]) pairs[runId] = { humanTabId, items: {} };
  pairs[runId].agentTabId = agentTabId;
  pairs[runId].humanTabId = humanTabId;
  if (!pairs[runId].items) pairs[runId].items = {};
  for (const id of itemIds) pairs[runId].items[id] = agentTabId;
  await chrome.storage.session.set({ [PAIRS_KEY]: pairs });
  chrome.runtime.sendMessage({ type: "boardUpdated" }).catch(() => {});
  return { ok: true, agentTabId, humanTabId };
}

async function runAgentTab({ runId, itemIds }) {
  const wsErr = await ensureWsReady();
  if (wsErr) {
    return { ok: false, error: wsErr };
  }
  const ids = itemIds || [];
  const provisioned = await provisionAgentTabForRun(runId, ids);
  if (!provisioned.ok) return provisioned;
  const res = await fetch(`${hostUrl}/v1/runs/${encodeURIComponent(runId)}/execute`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      agent_tab_id: provisioned.agentTabId,
      human_tab_id: provisioned.humanTabId,
    }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    return { ok: false, error: data.detail || res.statusText, ...data };
  }
  chrome.runtime.sendMessage({ type: "boardUpdated" }).catch(() => {});
  return data;
}

async function cancelAgentTab({ runId }) {
  const res = await fetch(
    `${hostUrl}/v1/runs/${encodeURIComponent(runId)}/execute/cancel`,
    { method: "POST" },
  );
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    return { ok: false, error: data.detail || res.statusText, ...data };
  }
  return data;
}

async function completeItem({ itemId, runId }) {
  const wsErr = await ensureWsReady();
  if (wsErr) {
    return { ok: false, error: wsErr };
  }
  const boardBefore = await loadBoard();
  const allBefore = [
    ...(boardBefore.you || []),
    ...(boardBefore.agent || []),
    ...(boardBefore.waiting || []),
  ];
  const youItem = allBefore.find((i) => i.id === itemId);
  const agentTabId = youItem ? resolveParkAgentTabId(youItem, allBefore) : null;
  let viewportShot = null;
  let shotOnAgentTab = false;
  if (agentTabId != null) {
    viewportShot = await captureIfActive(agentTabId);
    shotOnAgentTab = !!viewportShot;
  }
  const res = await fetch(`${hostUrl}/v1/items/${itemId}/complete`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      run_id: runId,
      viewport_shot: viewportShot || undefined,
      shot_on_agent_tab: shotOnAgentTab,
    }),
  });
  const data = await res.json();
  if (!res.ok) {
    return { ok: false, error: data.detail || res.statusText, ...data };
  }
  // Re-load after POST so required board_patch (cleared_gates, etc.) is not clobbered.
  const board = await loadBoard();
  let changed = false;
  for (const col of ["you", "agent", "waiting"]) {
    const list = board[col] || [];
    const idx = list.findIndex((i) => i.id === itemId);
    if (idx >= 0 && list[idx].status !== "done") {
      list[idx] = { ...list[idx], status: "done" };
      board[col] = list;
      changed = true;
      break;
    }
  }
  const resumeParentId = data.resume_parent_id;
  if (resumeParentId) {
    for (const col of ["you", "agent", "waiting"]) {
      const list = board[col] || [];
      const idx = list.findIndex((i) => i.id === resumeParentId);
      if (idx >= 0) {
        const prev = list[idx];
        list[idx] = {
          ...prev,
          status: "proposed",
          resume_ready: true,
          cleared_gates: prev.cleared_gates,
        };
        delete list[idx].last_error;
        board[col] = list;
        changed = true;
        break;
      }
    }
  }
  if (changed) {
    await saveBoard(board);
  }
  chrome.runtime.sendMessage({ type: "boardUpdated" }).catch(() => {});
  return data;
}
