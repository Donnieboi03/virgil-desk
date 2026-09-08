import { describe, it, expect } from "vitest";
import { normalizeScrapeResult } from "./scrapeResult.js";

describe("normalizeScrapeResult", () => {
  it("returns empty defaults for null/undefined", () => {
    expect(normalizeScrapeResult(null).url).toBe("");
    expect(normalizeScrapeResult(undefined).title).toBe("");
    expect(normalizeScrapeResult(null).text).toBe("");
    expect(normalizeScrapeResult(null).links).toEqual([]);
  });

  it("does not throw when reading url on empty", () => {
    const snap = normalizeScrapeResult(null);
    expect(() => snap.url).not.toThrow();
    expect(snap.url).toBe("");
  });

  it("preserves valid scrape payload", () => {
    const snap = normalizeScrapeResult({
      text: "hello",
      links: ["https://a.test"],
      url: "https://a.test/x",
      title: "T",
      metrics: { full_text_chars: 5, full_link_count: 1 },
    });
    expect(snap).toEqual({
      text: "hello",
      links: ["https://a.test"],
      url: "https://a.test/x",
      title: "T",
      metrics: { full_text_chars: 5, full_link_count: 1 },
    });
  });

  it("coerces partial / garbage fields", () => {
    const snap = normalizeScrapeResult({
      text: 1,
      links: ["ok", 2],
      url: null,
      title: undefined,
    });
    expect(snap.text).toBe("");
    expect(snap.links).toEqual(["ok"]);
    expect(snap.url).toBe("");
    expect(snap.title).toBe("");
  });
});
