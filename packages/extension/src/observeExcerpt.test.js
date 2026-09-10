import { describe, it, expect } from "vitest";
import {
  decideExcerpt,
  contentFingerprint,
  makeExcerptBaseline,
  setLastFullTextUrl,
  getLastFullTextUrl,
  clearExcerptBaselinesForRun,
  clearExcerptBaselinesForTab,
} from "./observeExcerpt.js";

describe("decideExcerpt", () => {
  it("sends full excerpt on first visit", () => {
    const text = "x".repeat(500);
    const url = "https://mail.example/inbox";
    const r = decideExcerpt({
      url,
      text,
      lastFullTextUrl: null,
      fullMax: 100,
      followupMax: 40,
    });
    expect(r.text_omitted).toBe(false);
    expect(r.text).toHaveLength(100);
    expect(r.nextBaseline).toBe(makeExcerptBaseline(url, text));
  });

  it("omits text when URL unchanged (legacy url-only baseline)", () => {
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

  it("omits text when url+fingerprint unchanged", () => {
    const url = "https://mail.example/inbox";
    const text = "same body";
    const r = decideExcerpt({
      url,
      text,
      lastFullTextUrl: makeExcerptBaseline(url, text),
      fullMax: 1000,
      followupMax: 40,
    });
    expect(r.text_omitted).toBe(true);
    expect(r.text).toBe("");
  });

  it("sends followup excerpt when same URL but content changes", () => {
    const url = "https://mail.example/inbox";
    const r = decideExcerpt({
      url,
      text: "opened thread body ".repeat(20),
      lastFullTextUrl: makeExcerptBaseline(url, "list preview only"),
      fullMax: 1000,
      followupMax: 40,
    });
    expect(r.text_omitted).toBe(false);
    expect(r.text).toHaveLength(40);
    expect(r.nextBaseline).toContain("@@");
    expect(contentFingerprint("opened thread body ".repeat(20))).toBeTruthy();
  });

  it("caps followup excerpt when URL changes", () => {
    const text = "y".repeat(200);
    const r = decideExcerpt({
      url: "https://mail.example/thread/1",
      text,
      lastFullTextUrl: "https://mail.example/inbox",
      fullMax: 1000,
      followupMax: 40,
    });
    expect(r.text_omitted).toBe(false);
    expect(r.text).toHaveLength(40);
    expect(r.nextBaseline).toBe(
      makeExcerptBaseline("https://mail.example/thread/1", text),
    );
  });

  it("does not lock omit baseline on empty scrape", () => {
    const url = "https://spa.example/expired";
    const r = decideExcerpt({
      url,
      text: "",
      lastFullTextUrl: null,
      fullMax: 1000,
      followupMax: 40,
    });
    expect(r.text_omitted).toBe(false);
    expect(r.text).toBe("");
    expect(r.nextBaseline).toBe(null);

    const again = decideExcerpt({
      url,
      text: "",
      lastFullTextUrl: null,
      fullMax: 1000,
      followupMax: 40,
    });
    expect(again.text_omitted).toBe(false);

    const later = decideExcerpt({
      url,
      text: "You can't access the questions. ".repeat(3),
      lastFullTextUrl: null,
      fullMax: 1000,
      followupMax: 40,
    });
    expect(later.text_omitted).toBe(false);
    expect(later.text.length).toBeGreaterThan(0);
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
