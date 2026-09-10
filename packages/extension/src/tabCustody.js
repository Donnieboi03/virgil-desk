/**
 * Auth-gate tab custody helpers (pure + patch detection).
 * Extension lends agent_tab_id to human on park; Show/reveal activates; Resume regroups.
 */

/**
 * Prefer You.agent_tab_id; else parent agent item's agent_tab_id.
 * @param {{ agent_tab_id?: number, parent_id?: string, park_kind?: string }} youItem
 * @param {Array<{ id?: string, column?: string, agent_tab_id?: number }>} allItems
 */
export function resolveParkAgentTabId(youItem, allItems = []) {
  if (youItem?.agent_tab_id != null && youItem.agent_tab_id !== "") {
    return Number(youItem.agent_tab_id);
  }
  const parentId = youItem?.parent_id;
  if (!parentId) return null;
  const parent = (allItems || []).find((i) => i.id === parentId);
  if (parent?.agent_tab_id != null && parent.agent_tab_id !== "") {
    return Number(parent.agent_tab_id);
  }
  return null;
}

/** Panel: Show existing agent tab instead of tabs.create for auth_gate. */
export function shouldRevealAgentTab(item) {
  if (!item) return false;
  if (item.park_kind === "auth_gate" && item.agent_tab_id != null && item.agent_tab_id !== "") {
    return true;
  }
  return false;
}

/**
 * Pure plan: when openTab creates tabId, whether to spawn-track the previous primary.
 * @returns {{ agentTabId: number, spawnPrev: number | null }}
 */
export function planAgentTabPromotion(prevAgentTabId, newTabId) {
  const next = Number(newTabId);
  const prev =
    prevAgentTabId != null && prevAgentTabId !== ""
      ? Number(prevAgentTabId)
      : null;
  return {
    agentTabId: next,
    spawnPrev: prev != null && prev !== next ? prev : null,
  };
}

/**
 * From board_patch ops, find auth_gate You adds that need custody release.
 * @returns {Array<{ youItem: object, agentTabId: number | null, runId: string | null }>}
 */
export function authGateParksFromOps(ops, runId) {
  const list = [];
  const itemsById = new Map();
  for (const op of ops || []) {
    const item = op?.item;
    if (item?.id) itemsById.set(item.id, item);
  }
  for (const op of ops || []) {
    if (op?.op !== "add") continue;
    const item = op.item;
    if (!item || item.column !== "you" || item.park_kind !== "auth_gate") continue;
    const all = [...itemsById.values()];
    list.push({
      youItem: item,
      agentTabId: resolveParkAgentTabId(item, all),
      runId: runId || item.run_id || null,
    });
  }
  return list;
}
