import { describe, expect, it } from "vitest";
import { planAgentTabAssignments, planAgentTabForItem } from "./agentTabs.js";

describe("planAgentTabForItem", () => {
  const runPair = {
    humanTabId: 100,
    items: { desk_run_agent_0: 200 },
  };

  it("reuses existing item tab mapping", () => {
    expect(planAgentTabForItem("desk_run_agent_0", 0, runPair)).toEqual({
      tabId: 200,
      source: "existing",
    });
  });

  it("requires create when unmapped (no snapshot reuse)", () => {
    expect(planAgentTabForItem("desk_run_agent_0", 0, { agentTabId: 200 })).toEqual({
      tabId: null,
      source: "create",
    });
  });

  it("requires create for second agent item", () => {
    expect(planAgentTabForItem("desk_run_agent_1", 1, { agentTabId: 200 })).toEqual({
      tabId: null,
      source: "create",
    });
  });
});

describe("planAgentTabAssignments", () => {
  it("plans create for each unmapped agent item", () => {
    const adds = [
      { item: { id: "a0", column: "agent" } },
      { item: { id: "a1", column: "agent" } },
    ];
    const plans = planAgentTabAssignments(adds, { agentTabId: 42 });
    expect(plans[0]).toEqual({ itemId: "a0", tabId: null, source: "create" });
    expect(plans[1]).toEqual({ itemId: "a1", tabId: null, source: "create" });
  });
});
