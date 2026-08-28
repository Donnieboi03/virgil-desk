/**
 * Consecutive failed act counter — stops click spirals.
 */

export function stallKey(runId, tabId) {
  return `${runId || ""}:${tabId || ""}`;
}

export function isFailedAct(result) {
  if (!result) return true;
  if (result.ok === false) return true;
  const err = String(result.error || "");
  if (err.includes("stale_observe") || err.includes("stall_detected")) return true;
  const used = result.act_resolved?.used;
  if (used === "none") return true;
  return false;
}

export function isSuccessfulAct(result) {
  if (!result || result.ok === false) return false;
  const used = result.act_resolved?.used;
  if (used && used !== "none") return true;
  // observe / scrape success without act_resolved
  if (!result.act_resolved && result.ok !== false) return false;
  return false;
}

/**
 * @returns {{ count: number, stalled: boolean, next: Map<string, number> }}
 */
export function updateActStall(map, runId, tabId, result, maxStall = 3) {
  const next = new Map(map);
  const key = stallKey(runId, tabId);
  if (isSuccessfulAct(result)) {
    next.set(key, 0);
    return { count: 0, stalled: false, next };
  }
  if (!isFailedAct(result)) {
    return { count: next.get(key) || 0, stalled: false, next };
  }
  const count = (next.get(key) || 0) + 1;
  next.set(key, count);
  return { count, stalled: maxStall > 0 && count >= maxStall, next };
}
