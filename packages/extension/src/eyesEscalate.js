/**
 * Fail-only Eyes escalation helpers (pure — no Chrome APIs).
 * Mode 0 = default innerText/targets; 1 = deep text / tree promote; 2 = soft hints.
 */

/**
 * Compress deep text and/or page_tree into a single excerpt for Hermes.
 * Prefers deep text; falls back to quoted labels / plain lines from the tree.
 *
 * @param {string | null | undefined} deepText
 * @param {string | null | undefined} pageTree
 * @param {{ minChars?: number, maxChars?: number }} [opts]
 * @returns {string | null} promoted excerpt, or null if still too thin
 */
export function promoteEyesExcerpt(deepText, pageTree, opts = {}) {
  const minChars = Math.max(0, Number(opts.minChars) || 40);
  const maxChars = Math.max(minChars, Number(opts.maxChars) || 4000);

  const deep = (deepText || "").trim();
  if (deep.length >= minChars) {
    return deep.slice(0, maxChars);
  }

  const fromTree = excerptFromPageTree(pageTree, maxChars);
  if (fromTree && fromTree.length >= minChars) {
    return fromTree;
  }

  // Combine thin deep + thin tree if together they clear the bar.
  const combined = [deep, fromTree].filter(Boolean).join("\n").trim();
  if (combined.length >= minChars) {
    return combined.slice(0, maxChars);
  }
  return null;
}

/**
 * @param {string | null | undefined} pageTree
 * @param {number} maxChars
 */
export function excerptFromPageTree(pageTree, maxChars = 4000) {
  if (!pageTree) return null;
  const lines = String(pageTree).split("\n");
  const out = [];
  let used = 0;
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    if (/^Page:/i.test(trimmed) || /^URL:/i.test(trimmed)) continue;
    if (/^--- frame/i.test(trimmed)) continue;
    if (trimmed === "... (truncated)") continue;

    let piece = trimmed;
    const quoted = trimmed.match(/"([^"]{2,})"/);
    if (quoted) {
      piece = quoted[1];
    } else if (trimmed.startsWith("[")) {
      // Skip bare role lines with no quoted label / text value.
      if (!/"/.test(trimmed) && !/value=/.test(trimmed)) continue;
      const val = trimmed.match(/value="([^"]*)"/);
      piece = val ? val[1] : trimmed.replace(/^\[|\]$/g, "").slice(0, 120);
    }

    piece = piece.replace(/\s+/g, " ").trim();
    if (!piece || piece.length < 2) continue;
    if (used + piece.length + 1 > maxChars) break;
    out.push(piece);
    used += piece.length + 1;
  }
  const text = out.join("\n").trim();
  return text || null;
}

/**
 * Soft pathname / title hints when Eyes remain empty (mode 2).
 * Allowlist only — no LLM classify.
 *
 * @param {string | null | undefined} url
 * @param {string | null | undefined} title
 * @returns {string | null}
 */
export function urlPathHint(url, title) {
  const hay = `${safePath(url)} ${title || ""}`.toLowerCase();
  if (!hay.trim()) return null;

  const rules = [
    { re: /expired|expir(e|ation)|verify.?expired|link.?expired/, hint: "expired_or_stale" },
    { re: /not[_-]?found|404|does.?not.?exist|no.?longer.?available|removed/, hint: "not_found" },
    { re: /login|sign[_-]?in|auth|sso|oauth|account\/login/, hint: "login_or_auth" },
    { re: /captcha|challenge|verify.?you.?are.?human/, hint: "captcha_or_challenge" },
    { re: /forbidden|access.?denied|unauthorized|403/, hint: "forbidden" },
    { re: /unsubscribe|opt[_-]?out/, hint: "unsubscribe" },
  ];
  for (const { re, hint } of rules) {
    if (re.test(hay)) return hint;
  }
  return null;
}

/**
 * @param {string | null | undefined} url
 */
function safePath(url) {
  if (!url) return "";
  try {
    const u = new URL(url);
    return `${u.pathname} ${u.search} ${u.hash}`;
  } catch {
    return String(url);
  }
}
