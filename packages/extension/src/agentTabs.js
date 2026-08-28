/**
 * Agent tab assignment for decomposed board items.
 * First agent item reuses the handoff snapshot tab; further items duplicate from human.
 */

/** @typedef {{ humanTabId?: number, agentTabId?: number, items?: Record<string, number> }} RunPair */

/**
 * Pure plan for one agent item (testable).
 * @returns {{ tabId: number | null, source: 'existing' | 'snapshot' | 'duplicate' }}
 */
export function planAgentTabForItem(itemId, agentIndex, runPair) {
  const existing = runPair?.items?.[itemId];
  if (existing) {
    return { tabId: existing, source: "existing" };
  }
  if (agentIndex === 0 && runPair?.agentTabId) {
    return { tabId: runPair.agentTabId, source: "snapshot" };
  }
  return { tabId: null, source: "duplicate" };
}

/**
 * @param {Array<{ item: { id: string, column?: string } }>} agentAdds
 * @param {RunPair | undefined} runPair
 * @returns {Array<{ itemId: string, source: string, tabId: number | null }>}
 */
export function planAgentTabAssignments(agentAdds, runPair) {
  return agentAdds.map((patch, index) => {
    const itemId = patch.item.id;
    const plan = planAgentTabForItem(itemId, index, runPair);
    return { itemId, ...plan };
  });
}

const provisionLocks = new Map();

export async function withProvisionLock(runId, fn) {
  while (provisionLocks.has(runId)) {
    await provisionLocks.get(runId);
  }
  const work = fn();
  provisionLocks.set(runId, work);
  try {
    return await work;
  } finally {
    provisionLocks.delete(runId);
  }
}
