import { describe, it, expect, vi } from "vitest";
import {
  settleEyes,
  textReady,
  scrapeEyesReady,
  observeEyesReady,
} from "./eyesSettle.js";

describe("textReady / scrapeEyesReady / observeEyesReady", () => {
  it("requires min text chars", () => {
    expect(textReady("short", 40)).toBe(false);
    expect(textReady("x".repeat(40), 40)).toBe(true);
  });

  it("scrape ready via links", () => {
    expect(scrapeEyesReady({ text: "", links: ["https://a"] }, 40)).toBe(true);
    expect(scrapeEyesReady({ text: "", links: [] }, 40)).toBe(false);
  });

  it("observe ready via targets", () => {
    expect(observeEyesReady({ text: "", targetCount: 2 }, 40)).toBe(true);
    expect(observeEyesReady({ text: "", targetCount: 0 }, 40)).toBe(false);
  });
});

describe("settleEyes", () => {
  it("exits immediately when first scrape is ready", async () => {
    const scrape = vi.fn(async () => ({ text: "y".repeat(50), links: [] }));
    const r = await settleEyes({
      scrape,
      isReady: (s) => scrapeEyesReady(s, 40),
      budgetMs: 2000,
      pollMs: 250,
    });
    expect(r.ready).toBe(true);
    expect(r.attempts).toBe(1);
    expect(scrape).toHaveBeenCalledTimes(1);
  });

  it("polls until ready within budget", async () => {
    let n = 0;
    const scrape = vi.fn(async () => {
      n += 1;
      return { text: n >= 3 ? "z".repeat(50) : "", links: [] };
    });
    let t = 0;
    const r = await settleEyes({
      scrape,
      isReady: (s) => scrapeEyesReady(s, 40),
      budgetMs: 2000,
      pollMs: 100,
      sleep: async (ms) => {
        t += ms;
      },
      now: () => t,
    });
    expect(r.ready).toBe(true);
    expect(r.attempts).toBe(3);
  });

  it("stops when budget exhausted", async () => {
    const scrape = vi.fn(async () => ({ text: "", links: [] }));
    let t = 0;
    const r = await settleEyes({
      scrape,
      isReady: (s) => scrapeEyesReady(s, 40),
      budgetMs: 300,
      pollMs: 100,
      sleep: async (ms) => {
        t += ms;
      },
      now: () => t,
    });
    expect(r.ready).toBe(false);
    expect(r.attempts).toBeGreaterThanOrEqual(2);
  });
});
