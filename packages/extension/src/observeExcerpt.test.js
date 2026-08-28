import { describe, it, expect } from "vitest";
import {
  decideExcerpt,
  setLastFullTextUrl,
  getLastFullTextUrl,
  clearExcerptBaselinesForRun,
  clearExcerptBaselinesForTab,
} from "./observeExcerpt.js";

describe("decideExcerpt", () => {
  it("sends full excerpt on first visit", () => {
    const r = decideExcerpt({
      url: "https://mail.example/inbox",
      text: "x".repeat(500),
      lastFullTextUrl: null,
      fullMax: 100,
      followupMax: 40,
    });
    expect(r.text_omitted).toBe(false);
    expect(r.text).toHaveLength(100);
    expect(r.nextBaseline).toBe("https://mail.example/inbox");
  });

  it("omits text when URL unchanged", () => {
    const url = "https://mail.example/inbox";
    const r = decideExcerpt({
      url,
      text: "inbox body",
      lastFullTextUrl: url,
      fullMax: 1000,
      followupMax: 40,
    });
    expect(r.text_omitted).toBe(true);
    expect(r.text).toBe("");
    expect(r.note).toMatch(/text_omitted/);
    expect(r.nextBaseline).toBe(url);
  });

  it("caps followup excerpt when URL changes", () => {
    const r = decideExcerpt({
      url: "https://mail.example/thread/1",
      text: "y".repeat(200),
      lastFullTextUrl: "https://mail.example/inbox",
      fullMax: 1000,
      followupMax: 40,
    });
    expect(r.text_omitted).toBe(false);
    expect(r.text).toHaveLength(40);
    expect(r.nextBaseline).toBe("https://mail.example/thread/1");
  });
});

describe("excerpt baseline map", () => {
  it("tracks and clears by run/tab", () => {
    let map = new Map();
    map = setLastFullTextUrl(map, "run1", 2, "https://a");
    map = setLastFullTextUrl(map, "run1", 3, "https://b");
    map = setLastFullTextUrl(map, "run2", 2, "https://c");
    expect(getLastFullTextUrl(map, "run1", 2)).toBe("https://a");
    map = clearExcerptBaselinesForTab(map, 2);
    expect(getLastFullTextUrl(map, "run1", 2)).toBe(null);
    expect(getLastFullTextUrl(map, "run2", 2)).toBe(null);
    expect(getLastFullTextUrl(map, "run1", 3)).toBe("https://b");
    map = clearExcerptBaselinesForRun(map, "run1");
    expect(getLastFullTextUrl(map, "run1", 3)).toBe(null);
  });
});
