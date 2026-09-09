/**
 * Fast early-exit Eyes settle: poll until ready or budget expires.
 * No focus / screenshot — extension inject only.
 */

const CHALLENGE_RE =
  /cloudflare|just a moment|checking your browser|challenge-platform|cf-browser-verification|attention required|enable javascript and cookies/i;

/**
 * Detect bot/challenge interstitial from scrape url/title/text.
 * @param {{ text?: string, title?: string, url?: string } | null | undefined} snap
 */
export function looksLikeChallenge(snap) {
  if (!snap || typeof snap !== "object") return false;
  const hay = `${snap.url || ""} ${snap.title || ""} ${snap.text || ""}`;
  return CHALLENGE_RE.test(hay);
}

/**
 * @param {{
 *   scrape: () => Promise<any>,
 *   isReady: (result: any) => boolean,
 *   budgetMs?: number,
 *   pollMs?: number,
 *   challengeExtraMs?: number,
 *   isChallenge?: (result: any) => boolean,
 *   sleep?: (ms: number) => Promise<void>,
 *   now?: () => number,
 * }} opts
 * @returns {Promise<{ result: any, attempts: number, elapsedMs: number, ready: boolean, challenge_extended?: boolean }>}
 */
export async function settleEyes({
  scrape,
  isReady,
  budgetMs = 2000,
  pollMs = 250,
  challengeExtraMs = 0,
  isChallenge = looksLikeChallenge,
  sleep = (ms) => new Promise((r) => setTimeout(r, ms)),
  now = () => Date.now(),
}) {
  let budget = Math.max(0, Number(budgetMs) || 0);
  const extra = Math.max(0, Number(challengeExtraMs) || 0);
  const poll = Math.max(1, Number(pollMs) || 250);
  const start = now();
  let attempts = 0;
  let last = null;
  let challengeExtended = false;

  while (true) {
    attempts += 1;
    last = await scrape();
    if (isReady(last)) {
      return {
        result: last,
        attempts,
        elapsedMs: Math.max(0, now() - start),
        ready: true,
        challenge_extended: challengeExtended,
      };
    }
    const elapsed = Math.max(0, now() - start);
    if (elapsed >= budget) {
      if (!challengeExtended && extra > 0 && isChallenge(last)) {
        challengeExtended = true;
        budget += extra;
        await sleep(Math.min(poll, budget - elapsed));
        continue;
      }
      return {
        result: last,
        attempts,
        elapsedMs: elapsed,
        ready: false,
        challenge_extended: challengeExtended,
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
