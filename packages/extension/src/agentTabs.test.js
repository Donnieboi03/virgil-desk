import { describe, expect, it } from "vitest";
import { planAgentTabAssignments, planAgentTabForItem } from "./agentTabs.js";

describe("planAgentTabForItem", () => {
  const runPair = {
    humanTabId: 100,
    agentTabId: 200,
    items: { desk_run_agent_0: 200 },
  };

  it("reuses existing item tab mapping", () => {
    expect(planAgentTabForItem("desk_run_agent_0", 0, runPair)).toEqual({
      tabId: 200,
      source: "existing",
    });
  });

  it("assigns snapshot tab to first agent item when unmapped", () => {
    expect(planAgentTabForItem("desk_run_agent_0", 0, { agentTabId: 200 })).toEqual({
      tabId: 200,
      source: "snapshot",
    });
  });

  it("requires duplicate for second agent item", () => {
    expect(planAgentTabForItem("desk_run_agent_1", 1, { agentTabId: 200 })).toEqual({
      tabId: null,
      source: "duplicate",
    });
  });
});

describe("planAgentTabAssignments", () => {
  it("plans snapshot then duplicate for two agent items", () => {
    const adds = [
      { item: { id: "a0", column: "agent" } },
      { item: { id: "a1", column: "agent" } },
    ];
    const plans = planAgentTabAssignments(adds, { agentTabId: 42 });
    expect(plans[0]).toEqual({ itemId: "a0", tabId: 42, source: "snapshot" });
    expect(plans[1]).toEqual({ itemId: "a1", tabId: null, source: "duplicate" });
  });
});
