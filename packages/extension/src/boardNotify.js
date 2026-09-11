/**
 * Pure helpers: detect when the board needs human attention (You/Waiting).
 */

/**
 * You cards that need a ping: parked gates / remainders, not routine homework `proposed`.
 * @param {any} item
 */
export function youNeedsHuman(item) {
  if (!item) return false;
  if (item.status === "awaiting_human") return true;
  if (item.park_kind === "auth_gate" || item.park_kind === "human_remainder") return true;
  return false;
}

/**
 * Waiting cards that need Accept (or similar).
 * @param {any} item
 */
export function waitingNeedsHuman(item) {
  if (!item) return false;
  return item.status === "proposed" || item.status === "waiting";
}

/**
 * @param {{ you?: any[], waiting?: any[] } | null | undefined} board
 * @returns {{ youNeeds: number, waitingNeeds: number, total: number, titles: string[] }}
 */
export function humanAttentionSummary(board) {
  const you = board?.you || [];
  const waiting = board?.waiting || [];
  const youNeeds = you.filter(youNeedsHuman);
  const waitingNeeds = waiting.filter(waitingNeedsHuman);
  const titles = [...youNeeds, ...waitingNeeds]
    .map((i) => String(i.title || i.id || "").slice(0, 80))
    .filter(Boolean)
    .slice(0, 5);
  return {
    youNeeds: youNeeds.length,
    waitingNeeds: waitingNeeds.length,
    total: youNeeds.length + waitingNeeds.length,
    titles,
  };
}

/**
 * True when attention count increased vs previous board snapshot.
 * @param {ReturnType<typeof humanAttentionSummary>} prev
 * @param {ReturnType<typeof humanAttentionSummary>} next
 */
export function shouldNotifyAttention(prev, next) {
  if (!next || next.total <= 0) return false;
  if (!prev) return next.total > 0;
  return next.total > (prev.total || 0);
}
