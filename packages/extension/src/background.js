const BOARD_KEY = "virgil_desk_board_v1";
const PAIRS_KEY = "virgil_desk_tab_pairs";
const AGENT_GROUP_TITLE = "Virgil · Agent";
const DEFAULT_HOST = "http://127.0.0.1:8787";

import { applyBoardPatch, chooseNavigationOp, policyBlock as tabPolicyBlock } from "./tabPolicy.js";

const HANDOFF_URLS_KEY = "virgil_desk_handoff_urls";

let ws = null;
let hostUrl = DEFAULT_HOST;
let deskConfig = {
  browser: {
    scrape_text_max_chars: 8000,
    scrape_links_max: 50,
    scrape_excerpt_max_chars: 4000,
    handoff_excerpt_max_chars: 2000,
    screenshot_mode: "captureVisibleTab",
    default_wait_ms: 500,
  },
};
let wsConnected = false;
let pendingHandoffResolve = null;

const META_KEY = "virgil_desk_panel_meta";

chrome.runtime.onInstalled.addListener(() => {
  chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true });
});

chrome.storage.sync.get(["hostUrl"], (data) => {
  if (data.hostUrl) hostUrl = data.hostUrl;
  connectWs();
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
    loadBoard().then((board) => sendResponse({ board }));
    return true;
  }
  if (msg.type === "handoffTab") {
    handoffActiveTab(msg.intent).then(sendResponse);
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
});

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
    if (msg.type === "browser_command") {
      const command = await normalizeCommand(msg.command);
      const result = await runBrowserCommand(command);
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
  const board = await loadBoard();
  await saveBoard(applyBoardPatch(board, ops));
  chrome.runtime.sendMessage({ type: "boardUpdated" }).catch(() => {});
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
  const pairs = (await chrome.storage.session.get(PAIS_KEY))[PAIRS_KEY] || {};
  const runId = command.run_id;
  if (pairs[runId]?.agentTabId) {
    return { tabId: pairs[runId].agentTabId, tabMode: "reuse" };
  }
  if (command.op === "duplicateTab") {
    const dup = await chrome.tabs.duplicate(command.human_tab_id);
    await chrome.tabs.update(dup.id, { active: false });
    const tab = await chrome.tabs.get(dup.id);
    const groupId = await ensureAgentGroup(dup.id, tab.windowId);
    pairs[runId] = {
      humanTabId: command.human_tab_id,
      agentTabId: dup.id,
      groupId,
    };
    await chrome.storage.session.set({ [PAIRS_KEY]: pairs });
    return { tabId: dup.id, tabMode: "duplicate" };
  }
  if (command.op === "openTab" || (command.op === "openTab" && command.url)) {
    const human = command.human_tab_id
      ? await chrome.tabs.get(command.human_tab_id)
      : null;
    const windowId = human?.windowId;
    const tab = await chrome.tabs.create({
      url: command.url || "about:blank",
      active: false,
      windowId,
    });
    const groupId = await ensureAgentGroup(tab.id, tab.windowId);
    pairs[runId] = {
      humanTabId: command.human_tab_id,
      agentTabId: tab.id,
      groupId,
    };
    await chrome.storage.session.set({ [PAIRS_KEY]: pairs });
    return { tabId: tab.id, tabMode: "create" };
  }
  return { tabId: command.tab_id, tabMode: "reuse" };
}

function policyBlock(command, tabId) {
  return tabPolicyBlock(command, tabId);
}

async function scrapeTab(tabId) {
  const maxText = deskConfig.browser?.scrape_text_max_chars ?? 8000;
  const maxLinks = deskConfig.browser?.scrape_links_max ?? 50;
  const [{ result }] = await chrome.scripting.executeScript({
    target: { tabId },
    func: (textMax, linkMax) => {
      const links = [...document.querySelectorAll("a[href]")]
        .map((a) => a.href)
        .filter((h) => h.startsWith("http"))
        .slice(0, linkMax);
      const text = (document.body?.innerText || "").slice(0, textMax);
      return { text, links, url: location.href, title: document.title };
    },
    args: [maxText, maxLinks],
  });
  return result;
}

async function screenshotTab(tabId) {
  const mode = deskConfig.browser?.screenshot_mode || "captureVisibleTab";
  if (mode !== "captureVisibleTab") {
    return screenshotTabCanvas(tabId);
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
    return { mime: "image/png", base64, width: 0, height: 0 };
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
      const snap = await scrapeTab(command.human_tab_id);
      return {
        ...base,
        url: snap.url,
        title: snap.title,
        scrape_excerpt: snap.text?.slice(0, 2000),
        duration_ms: Date.now() - started,
      };
    }

    let tabId = command.tab_id;
    if (command.op === "duplicateTab") {
      const resolved = await resolveAgentTab(command);
      tabId = resolved.tabId;
    } else if (command.op === "openTab") {
      const resolved = await resolveAgentTab({ ...command, op: "openTab" });
      tabId = resolved.tabId;
    }

    const block = policyBlock(command, tabId);
    if (block) {
      return { ...base, ok: false, error: block, duration_ms: Date.now() - started };
    }

    if (command.op === "scroll") {
      const dir = command.params?.direction === "up" ? -1 : 1;
      await chrome.scripting.executeScript({
        target: { tabId },
        func: (d) => window.scrollBy(0, d * window.innerHeight * 0.85),
        args: [dir],
      });
    } else if (command.op === "click") {
      const sel = command.params?.selector;
      await chrome.scripting.executeScript({
        target: { tabId },
        func: (s) => {
          const el = document.querySelector(s);
          if (el) el.click();
        },
        args: [sel],
      });
    } else if (command.op === "fill") {
      const sel = command.params?.selector;
      const val = command.params?.value || "";
      await chrome.scripting.executeScript({
        target: { tabId },
        func: (s, v) => {
          const el = document.querySelector(s);
          if (el) {
            el.value = v;
            el.dispatchEvent(new Event("input", { bubbles: true }));
          }
        },
        args: [sel, val],
      });
    } else if (command.op === "wait") {
      await new Promise((r) => setTimeout(r, command.params?.ms || 500));
    }

    if (["click", "fill", "scroll", "scrape", "screenshot", "openTab", "duplicateTab"].includes(command.op)) {
      const excerptMax = deskConfig.browser?.scrape_excerpt_max_chars ?? 4000;
      const snap = await scrapeTab(tabId);
      const shot = await screenshotTab(tabId);
      const out = {
        ...base,
        tab_id: tabId,
        url: snap.url,
        title: snap.title,
        scrape_excerpt: snap.text?.slice(0, excerptMax),
        screenshot: shot,
        duration_ms: Date.now() - started,
      };
      if (command.op === "click" || command.op === "fill") {
        // auto-verify already included
      }
      if (command.op === "scrape" || command.op === "screenshot") return out;
      if (command.op === "click" || command.op === "fill") return out;
      return out;
    }

    if (command.op === "closeTab" && tabId) {
      await chrome.tabs.remove(tabId);
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

async function handoffActiveTab(intent) {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id) return { ok: false, error: "no active tab" };
  const handoffMax = deskConfig.browser?.handoff_excerpt_max_chars ?? 2000;
  const snap = await scrapeTab(tab.id);
  const handoff = {
    url: tab.url || "",
    title: tab.title || "",
    human_tab_id: tab.id,
    window_id: tab.windowId,
    intent: intent || "",
    snapshot: { excerpt: snap.text?.slice(0, handoffMax), links: snap.links },
  };
  if (ws?.readyState === WebSocket.OPEN) {
    const resultPromise = new Promise((resolve) => {
      pendingHandoffResolve = resolve;
      setTimeout(() => {
        if (pendingHandoffResolve === resolve) {
          pendingHandoffResolve = null;
          resolve({ ok: false, error: "handoff timeout" });
        }
      }, 120000);
    });
    ws.send(JSON.stringify({ type: "handoff_started", handoff }));
    const result = await resultPromise;
    if (result.run_id) {
      await rememberHandoffUrl(result.run_id, handoff.url);
    }
    return result;
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
    await applyPatch(data.items.map((item) => ({ op: "add", item })), data.run_id);
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
  return res.json();
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
  return res.json();
}
