/** Decide whether to omit or cap page text on follow-up observe/act scrapes. */

const OMIT_NOTE =
  "text_omitted: url unchanged since last full excerpt — use interact_targets; re-observe after navigation";

/**
 * Cheap content fingerprint so Gmail-style SPAs (same URL, new body) still get text.
 * @param {string} text
 * @returns {string}
 */
export function contentFingerprint(text) {
  const t = text || "";
  const n = t.length;
  if (!n) return "0";
  const mid = Math.floor(n / 2);
  return `${n}:${t.slice(0, 48)}:${t.slice(Math.max(0, mid - 24), mid + 24)}:${t.slice(-48)}`;
}

/**
 * Baseline stored as `url@@fingerprint` (url-only baselines still supported).
 * @param {string | null | undefined} baseline
 * @returns {{ url: string | null, fp: string | null }}
 */
export function parseExcerptBaseline(baseline) {
  if (!baseline) return { url: null, fp: null };
  const i = baseline.indexOf("@@");
  if (i < 0) return { url: baseline, fp: null };
  return { url: baseline.slice(0, i), fp: baseline.slice(i + 2) };
}

/**
 * @param {string} url
 * @param {string} text
 * @returns {string}
 */
export function makeExcerptBaseline(url, text) {
  const pageUrl = url || "";
  return `${pageUrl}@@${contentFingerprint(text)}`;
}

/**
 * @param {{
 *   url: string,
 *   text: string,
 *   lastFullTextUrl: string | null | undefined,
 *   fullMax: number,
 *   followupMax: number,
 * }} args
 * @returns {{
 *   text: string,
 *   text_omitted: boolean,
 *   note: string | undefined,
 *   nextBaseline: string,
 * }}
 */
export function decideExcerpt({
  url,
  text,
  lastFullTextUrl,
  fullMax,
  followupMax,
}) {
  const pageUrl = url || "";
  const raw = text || "";
  // Empty scrapes must not lock an omit baseline (SPA race / settle retries).
  if (!raw.trim()) {
    return {
      text: "",
      text_omitted: false,
      note: undefined,
      nextBaseline: lastFullTextUrl || null,
    };
  }
  const fp = contentFingerprint(raw);
  const prev = parseExcerptBaseline(lastFullTextUrl);
  const sameUrl = Boolean(prev.url && pageUrl && pageUrl === prev.url);
  const sameContent = sameUrl && prev.fp != null && prev.fp === fp;
  // Legacy url-only baseline: treat as omit when URL matches (prior behavior).
  const legacySameUrl = sameUrl && prev.fp == null;

  if (sameContent || legacySameUrl) {
    return {
      text: "",
      text_omitted: true,
      note: OMIT_NOTE,
      nextBaseline: lastFullTextUrl || makeExcerptBaseline(pageUrl, raw),
    };
  }

  const urlChanged = Boolean(prev.url && pageUrl && pageUrl !== prev.url);
  const contentChangedSameUrl = sameUrl && prev.fp != null && prev.fp !== fp;
  const cap =
    urlChanged || contentChangedSameUrl ? followupMax : fullMax;
  const max = Math.max(0, Number(cap) || 0);
  return {
    text: raw.slice(0, max),
    text_omitted: false,
    note: undefined,
    nextBaseline: makeExcerptBaseline(pageUrl, raw),
  };
}

export function excerptMapKey(runId, tabId) {
  return `${runId}:${tabId}`;
}

export function getLastFullTextUrl(map, runId, tabId) {
  return map.get(excerptMapKey(runId, tabId)) || null;
}

export function setLastFullTextUrl(map, runId, tabId, url) {
  const next = new Map(map);
  const key = excerptMapKey(runId, tabId);
  if (!url) {
    next.delete(key);
  } else {
    next.set(key, url);
  }
  return next;
}

export function clearExcerptBaselinesForRun(map, runId) {
  const next = new Map(map);
  const prefix = `${runId}:`;
  for (const key of [...next.keys()]) {
    if (key.startsWith(prefix)) next.delete(key);
  }
  return next;
}

export function clearExcerptBaselinesForTab(map, tabId) {
  const next = new Map(map);
  const suffix = `:${tabId}`;
  for (const key of [...next.keys()]) {
    if (key.endsWith(suffix)) next.delete(key);
  }
  return next;
}
