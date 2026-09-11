/**
 * Pure helpers: detect when the board needs human attention (You lane).
 */

/**
 * You cards that need a ping: parked gates / remainders, or proposals needing Accept.
 * Routine homework `proposed` without park/proposals does not ping.
 * @param {any} item
 */
export function youNeedsHuman(item) {
  if (!item) return false;
  if (item.status === "done" || item.status === "denied") return false;
  if (item.status === "awaiting_human") return true;
  if (item.park_kind === "auth_gate" || item.park_kind === "human_remainder") return true;
  if (Array.isArray(item.proposals) && item.proposals.length > 0) {
    return item.status === "proposed" || item.status === "waiting";
  }
  return false;
}

/**
 * @deprecated Use youNeedsHuman; Waiting folded into You.
 * @param {any} item
 */
export function waitingNeedsHuman(item) {
  return youNeedsHuman(item);
}

/**
 * @param {{ you?: any[], waiting?: any[], agent?: any[] } | null | undefined} board
 * @returns {{ youNeeds: number, waitingNeeds: number, total: number, titles: string[] }}
 */
export function humanAttentionSummary(board) {
  const you = board?.you || [];
  // Soft-compat: count leftover waiting[] until migrate-on-read clears it.
  const waiting = board?.waiting || [];
  const youNeeds = [...you, ...waiting].filter(youNeedsHuman);
  const titles = youNeeds
    .map((i) => String(i.title || i.id || "").slice(0, 80))
    .filter(Boolean)
    .slice(0, 5);
  return {
    youNeeds: youNeeds.length,
    waitingNeeds: 0,
    total: youNeeds.length,
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
