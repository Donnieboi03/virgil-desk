/** Decide whether to omit or cap page text on follow-up observe/act scrapes. */

const OMIT_NOTE =
  "text_omitted: url unchanged since last full excerpt — use interact_targets; re-observe after navigation";

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
  if (lastFullTextUrl && pageUrl && pageUrl === lastFullTextUrl) {
    return {
      text: "",
      text_omitted: true,
      note: OMIT_NOTE,
      nextBaseline: lastFullTextUrl,
    };
  }
  const cap =
    lastFullTextUrl && pageUrl && pageUrl !== lastFullTextUrl
      ? followupMax
      : fullMax;
  const max = Math.max(0, Number(cap) || 0);
  return {
    text: raw.slice(0, max),
    text_omitted: false,
    note: undefined,
    nextBaseline: pageUrl || lastFullTextUrl || "",
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
