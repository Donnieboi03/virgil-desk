const BOARD_KEY = "virgil_desk_board_v1";
const PAIRS_KEY = "virgil_desk_tab_pairs";
const AGENT_GROUP_TITLE = "Virgil · Agent";
const DEFAULT_HOST = "http://127.0.0.1:8787";

import { applyBoardPatch, chooseNavigationOp, policyBlock as tabPolicyBlock } from "./tabPolicy.js";
import { withProvisionLock, planAgentTabForItem } from "./agentTabs.js";
import {
  storeTargetMap,
  getTargetMap,
  clearTargetMap,
  clearMapsForTab,
} from "./targetMap.js";

const BUNDLE_FILE = "interactObserve.bundle.js";

const HANDOFF_URLS_KEY = "virgil_desk_handoff_urls";

let ws = null;
let hostUrl = DEFAULT_HOST;
let deskConfig = {
  browser: {
    scrape_text_max_chars: 16000,
    scrape_links_max: 200,
    scrape_excerpt_max_chars: 8000,
    handoff_excerpt_max_chars: 8000,
    handoff_scroll_loops: 2,
    handoff_scroll_viewport_ratio: 0.85,
    screenshot_mode: "captureVisibleTab",
    default_wait_ms: 500,
    interact_targets_max: 80,
    observe_annotate_default: true,
  },
};
let wsConnected = false;
let pendingHandoffResolve = null;

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
  ops = await provisionAgentItemTabs(runId, ops);
  const board = await loadBoard();
  await saveBoard(applyBoardPatch(board, ops));
  chrome.runtime.sendMessage({ type: "boardUpdated" }).catch(() => {});
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
  await chrome.storage.session.set({ [PAIRS_KEY]: pairs });
  return dup.id;
}

async function syncItemAgentTab(itemId, runId, agentTabId) {
  try {
    await fetch(`${hostUrl}/v1/items/${itemId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ run_id: runId, agent_tab_id: agentTabId }),
    });
  } catch {
    /* host may be unreachable; board still updated locally */
  }
}

async function assignSnapshotTabToItem(runId, itemId, tabId, humanTabId) {
  const data = await chrome.storage.session.get(PAIRS_KEY);
  const pairs = data[PAIRS_KEY] || {};
  if (!pairs[runId]) {
    pairs[runId] = { humanTabId, items: {} };
  }
  if (!pairs[runId].items) pairs[runId].items = {};
  pairs[runId].items[itemId] = tabId;
  await chrome.storage.session.set({ [PAIRS_KEY]: pairs });
}

async function loadRunPair(runId) {
  const data = await chrome.storage.session.get(PAIRS_KEY);
  return data[PAIRS_KEY]?.[runId];
}

async function provisionAgentItemTabs(runId, ops) {
  if (!runId) return ops;
  const agentAdds = ops.filter((p) => p.op === "add" && p.item?.column === "agent");
  if (!agentAdds.length) return ops;

  return withProvisionLock(runId, async () => {
    const runPair = await loadRunPair(runId);
    const humanTabId = runPair?.humanTabId;
    if (!humanTabId) return ops;

    for (let index = 0; index < agentAdds.length; index++) {
      const item = agentAdds[index].item;
      const freshPair = (await loadRunPair(runId)) || runPair;
      const plan = planAgentTabForItem(item.id, index, freshPair);
      let tabId = plan.tabId;
      if (plan.source === "duplicate") {
        tabId = await duplicateAgentTabForItem(humanTabId, runId, item.id);
      } else if (plan.source === "snapshot" && tabId) {
        await assignSnapshotTabToItem(runId, item.id, tabId, humanTabId);
      }
      if (!tabId) continue;
      item.agent_tab_id = tabId;
      item.human_tab_id = item.human_tab_id || humanTabId;
      await syncItemAgentTab(item.id, runId, tabId);
    }
    return ops;
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
      items: pairs[runId]?.items || {},
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
      items: pairs[runId]?.items || {},
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
  return result;
}

function scrollViewportRatio() {
  return deskConfig.browser?.handoff_scroll_viewport_ratio ?? 0.85;
}

async function injectInteractBundle(tabId) {
  await chrome.scripting.executeScript({
    target: { tabId },
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
  await injectInteractBundle(tabId);
  const [{ result }] = await chrome.scripting.executeScript({
    target: { tabId },
    world: "MAIN",
    func: (o) => globalThis.deskObserve(o),
    args: [opts],
  });
  return result;
}

async function runPageUnmark(tabId) {
  try {
    await injectInteractBundle(tabId);
    await chrome.scripting.executeScript({
      target: { tabId },
      world: "MAIN",
      func: () => globalThis.deskUnmark(),
    });
  } catch {
    /* tab may be gone */
  }
}

async function runPageAct(tabId, op, params, targets, urlBefore) {
  await injectInteractBundle(tabId);
  const [{ result }] = await chrome.scripting.executeScript({
    target: { tabId },
    world: "MAIN",
    func: (operation, p, t, before) => globalThis.deskAct(operation, p, t, before),
    args: [op, params, targets, urlBefore],
  });
  return result;
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
    } else if (command.op === "openTab") {
      const resolved = await resolveAgentTab({ ...command, op: "openTab" });
      tabId = resolved.tabId;
    }

    const block = policyBlock(command, tabId);
    if (block) {
      return { ...base, ok: false, error: block, duration_ms: Date.now() - started };
    }

    if (command.op === "observe") {
      const maxTargets = deskConfig.browser?.interact_targets_max ?? 80;
      const annotate =
        command.params?.annotate ??
        deskConfig.browser?.observe_annotate_default ??
        true;
      const excerptMax = deskConfig.browser?.scrape_excerpt_max_chars ?? 8000;
      const snap = await scrapeTab(tabId);
      const pageObserve = await runPageObserve(tabId, { maxTargets, annotate });
      const shot = command.skip_screenshot ? null : await screenshotTab(tabId);
      await runPageUnmark(tabId);
      const interact_targets = (pageObserve?.interact_targets || []).map(
        ({ mark_label, ...rest }) => rest,
      );
      storeTargetMap(command.run_id, tabId, {
        interact_targets,
        scroll_containers: pageObserve?.scroll_containers || [],
        url: pageObserve?.url || snap.url,
      });
      const observe = {
        url: pageObserve?.url || snap.url,
        title: pageObserve?.title || snap.title,
        viewport: pageObserve?.viewport || { w: 0, h: 0 },
        device_pixel_ratio: pageObserve?.device_pixel_ratio ?? 1,
        text_excerpt: snap.text?.slice(0, excerptMax) ?? "",
        interact_targets,
        scroll_containers: pageObserve?.scroll_containers || [],
      };
      return {
        ...base,
        tab_id: tabId,
        url: observe.url,
        title: observe.title,
        scrape_excerpt: observe.text_excerpt,
        observe,
        interact_targets,
        scroll_containers: observe.scroll_containers,
        viewport: observe.viewport,
        device_pixel_ratio: observe.device_pixel_ratio,
        screenshot: shot,
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
      const excerptMax = deskConfig.browser?.scrape_excerpt_max_chars ?? 4000;
      const snap = await scrapeTab(tabId);
      let shot = null;
      if (!command.skip_screenshot) {
        shot = await screenshotTab(tabId);
      }
      const out = {
        ...base,
        tab_id: tabId,
        url: snap.url,
        title: snap.title,
        scrape_excerpt: snap.text?.slice(0, excerptMax),
        screenshot: shot,
        act_resolved: actResolved,
        duration_ms: Date.now() - started,
      };
      if (command.op === "scrape" || command.op === "screenshot") return out;
      return out;
    }

    if (command.op === "closeTab" && tabId) {
      const block = policyBlock(command, tabId);
      if (block) {
        return { ...base, ok: false, error: block, duration_ms: Date.now() - started };
      }
      await chrome.tabs.remove(tabId);
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
  const resolved = await resolveAgentTab({
    op: "duplicateTab",
    run_id: runId,
    human_tab_id: tab.id,
    url: tab.url || "",
  });
  const agentTabId = resolved.tabId;
  const scrollLoopsExecuted = scrollLoops > 0 ? scrollLoops : 0;
  if (scrollLoops > 0) {
    await scrollAgentTab(agentTabId, scrollLoops);
  }
  const snap = await scrapeTab(agentTabId);
  const shot = await screenshotTab(agentTabId);
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
    agent_tab_id: agentTabId,
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
