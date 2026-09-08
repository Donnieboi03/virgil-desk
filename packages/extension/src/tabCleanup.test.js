import { describe, it, expect } from "vitest";
import { tabsToCloseForItem } from "./tabCleanup.js";

describe("tabsToCloseForItem", () => {
  it("closes agent + spawned, never human", () => {
    const pair = {
      humanTabId: 1,
      items: { agent_0: 10 },
      spawnedByItem: { agent_0: [20, 21] },
    };
    expect(tabsToCloseForItem(pair, "agent_0", 1, 10).sort()).toEqual([10, 20, 21]);
  });

  it("uses fallback agent tab id", () => {
    expect(tabsToCloseForItem({}, "x", 5, 99)).toEqual([99]);
  });

  it("dedupes and skips human if listed as agent", () => {
    const pair = { humanTabId: 7, items: { a: 7 } };
    expect(tabsToCloseForItem(pair, "a", 7, 7)).toEqual([]);
  });

  it("does not close humanParkedByItem tabs", () => {
    const pair = {
      humanTabId: 1,
      items: { agent_0: 10 },
      spawnedByItem: { agent_0: [20] },
      humanParkedByItem: { agent_0: [30] },
    };
    expect(tabsToCloseForItem(pair, "agent_0", 1, 10).sort()).toEqual([10, 20]);
  });

  it("excludes parked ids even when listed in spawned", () => {
    const pair = {
      humanTabId: 1,
      items: { agent_0: 10 },
      spawnedByItem: { agent_0: [20, 30] },
      humanParkedByItem: { agent_0: [30] },
    };
    expect(tabsToCloseForItem(pair, "agent_0", 1, 10).sort()).toEqual([10, 20]);
  });

  it("excludes parked tabs from sibling items", () => {
    const pair = {
      humanTabId: 1,
      items: { agent_0: 10 },
      spawnedByItem: { agent_0: [20] },
      humanParkedByItem: { agent_1: [20] },
    };
    expect(tabsToCloseForItem(pair, "agent_0", 1, 10)).toEqual([10]);
  });
});
