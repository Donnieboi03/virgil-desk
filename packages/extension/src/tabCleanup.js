/**
 * Pure helpers: which tabs to close when an agent item finishes execute.
 */

/**
 * @param {{ humanTabId?: number, agentTabId?: number, items?: Record<string, number>, spawnedByItem?: Record<string, number[]> }} runPair
 * @param {string} itemId
 * @param {number|null|undefined} humanTabId
 * @param {number|null|undefined} agentTabIdFallback
 * @returns {number[]}
 */
export function tabsToCloseForItem(runPair, itemId, humanTabId, agentTabIdFallback) {
  const ids = new Set();
  const mapped = runPair?.items?.[itemId];
  if (mapped != null) ids.add(Number(mapped));
  if (agentTabIdFallback != null) ids.add(Number(agentTabIdFallback));
  const spawned = runPair?.spawnedByItem?.[itemId] || [];
  for (const id of spawned) {
    if (id != null) ids.add(Number(id));
  }
  const human = humanTabId != null ? Number(humanTabId) : runPair?.humanTabId;
  if (human != null) ids.delete(Number(human));
  return [...ids].filter((id) => Number.isFinite(id) && id > 0);
}
