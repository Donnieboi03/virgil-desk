/**
 * Normalize chrome.scripting.executeScript scrape payloads.
 * Inject can return undefined/null on hostile pages (e.g. LinkedIn).
 */

const EMPTY = Object.freeze({
  text: "",
  links: [],
  url: "",
  title: "",
  metrics: { full_text_chars: 0, full_link_count: 0 },
});

/**
 * @param {unknown} raw
 * @returns {{ text: string, links: string[], url: string, title: string, metrics: { full_text_chars: number, full_link_count: number } }}
 */
export function normalizeScrapeResult(raw) {
  if (!raw || typeof raw !== "object") {
    return { ...EMPTY, metrics: { ...EMPTY.metrics } };
  }
  const o = /** @type {Record<string, unknown>} */ (raw);
  const metricsIn =
    o.metrics && typeof o.metrics === "object"
      ? /** @type {Record<string, unknown>} */ (o.metrics)
      : {};
  const links = Array.isArray(o.links)
    ? o.links.filter((h) => typeof h === "string")
    : [];
  return {
    text: typeof o.text === "string" ? o.text : "",
    links,
    url: typeof o.url === "string" ? o.url : "",
    title: typeof o.title === "string" ? o.title : "",
    metrics: {
      full_text_chars:
        typeof metricsIn.full_text_chars === "number"
          ? metricsIn.full_text_chars
          : 0,
      full_link_count:
        typeof metricsIn.full_link_count === "number"
          ? metricsIn.full_link_count
          : links.length,
    },
  };
}
