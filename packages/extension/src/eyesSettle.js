/**
 * Fast early-exit Eyes settle: poll until ready or budget expires.
 * No focus / screenshot — extension inject only.
 */

/**
 * @param {{
 *   scrape: () => Promise<any>,
 *   isReady: (result: any) => boolean,
 *   budgetMs?: number,
 *   pollMs?: number,
 *   sleep?: (ms: number) => Promise<void>,
 *   now?: () => number,
 * }} opts
 * @returns {Promise<{ result: any, attempts: number, elapsedMs: number, ready: boolean }>}
 */
export async function settleEyes({
  scrape,
  isReady,
  budgetMs = 2000,
  pollMs = 250,
  sleep = (ms) => new Promise((r) => setTimeout(r, ms)),
  now = () => Date.now(),
}) {
  const budget = Math.max(0, Number(budgetMs) || 0);
  const poll = Math.max(1, Number(pollMs) || 250);
  const start = now();
  let attempts = 0;
  let last = null;

  while (true) {
    attempts += 1;
    last = await scrape();
    if (isReady(last)) {
      return {
        result: last,
        attempts,
        elapsedMs: Math.max(0, now() - start),
        ready: true,
      };
    }
    const elapsed = Math.max(0, now() - start);
    if (elapsed >= budget) {
      return {
        result: last,
        attempts,
        elapsedMs: elapsed,
        ready: false,
      };
    }
    await sleep(Math.min(poll, budget - elapsed));
  }
}

/**
 * @param {string | null | undefined} text
 * @param {number} minChars
 */
export function textReady(text, minChars = 40) {
  return (text || "").trim().length >= Math.max(0, Number(minChars) || 0);
}

/**
 * Scrape snapshot ready: enough text or any http links.
 * @param {{ text?: string, links?: string[] } | null | undefined} snap
 * @param {number} minChars
 */
export function scrapeEyesReady(snap, minChars = 40) {
  if (!snap) return false;
  if (textReady(snap.text, minChars)) return true;
  return Array.isArray(snap.links) && snap.links.length > 0;
}

/**
 * Observe ready: text or interact targets.
 * @param {{ text?: string, targetCount?: number } | null | undefined} state
 * @param {number} minChars
 */
export function observeEyesReady(state, minChars = 40) {
  if (!state) return false;
  if (textReady(state.text, minChars)) return true;
  return (state.targetCount || 0) > 0;
}
