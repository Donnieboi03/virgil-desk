import { describe, expect, it } from "vitest";
import {
  authGateParksFromOps,
  planAgentTabPromotion,
  resolveParkAgentTabId,
  shouldRevealAgentTab,
} from "./tabCustody.js";

describe("planAgentTabPromotion", () => {
  it("spawns previous primary when openTab creates a new tab", () => {
    expect(planAgentTabPromotion(10, 20)).toEqual({
      agentTabId: 20,
      spawnPrev: 10,
    });
  });

  it("does not spawn when first tab or same id", () => {
    expect(planAgentTabPromotion(null, 5)).toEqual({
      agentTabId: 5,
      spawnPrev: null,
    });
    expect(planAgentTabPromotion(5, 5)).toEqual({
      agentTabId: 5,
      spawnPrev: null,
    });
  });
});

describe("shouldRevealAgentTab", () => {
  it("true for auth_gate with agent_tab_id", () => {
    expect(
      shouldRevealAgentTab({ park_kind: "auth_gate", agent_tab_id: 9 }),
    ).toBe(true);
  });

  it("false for human_remainder", () => {
    expect(
      shouldRevealAgentTab({
        park_kind: "human_remainder",
        agent_tab_id: 9,
        source: { url: "https://x" },
      }),
    ).toBe(false);
  });

  it("false without tab id", () => {
    expect(shouldRevealAgentTab({ park_kind: "auth_gate" })).toBe(false);
  });
});

describe("resolveParkAgentTabId", () => {
  it("uses You agent_tab_id first", () => {
    expect(
      resolveParkAgentTabId(
        { agent_tab_id: 5, parent_id: "p" },
        [{ id: "p", agent_tab_id: 7 }],
      ),
    ).toBe(5);
  });

  it("falls back to parent", () => {
    expect(
      resolveParkAgentTabId(
        { parent_id: "p", park_kind: "auth_gate" },
        [{ id: "p", column: "agent", agent_tab_id: 7 }],
      ),
    ).toBe(7);
  });

  it("returns null when neither has a tab", () => {
    expect(resolveParkAgentTabId({ parent_id: "p" }, [{ id: "p" }])).toBeNull();
    expect(resolveParkAgentTabId({}, [])).toBeNull();
  });
});

describe("authGateParksFromOps", () => {
  it("finds auth_gate You adds", () => {
    const parks = authGateParksFromOps(
      [
        {
          op: "add",
          item: {
            id: "y1",
            column: "you",
            park_kind: "auth_gate",
            agent_tab_id: 42,
            run_id: "r1",
          },
        },
        {
          op: "update",
          item: { id: "a1", status: "awaiting_human" },
        },
      ],
      "r1",
    );
    expect(parks).toHaveLength(1);
    expect(parks[0].agentTabId).toBe(42);
    expect(parks[0].youItem.id).toBe("y1");
  });

  it("ignores human_remainder and non-add ops", () => {
    expect(
      authGateParksFromOps(
        [
          {
            op: "add",
            item: {
              id: "y2",
              column: "you",
              park_kind: "human_remainder",
              agent_tab_id: 1,
            },
          },
          {
            op: "update",
            item: {
              id: "y3",
              column: "you",
              park_kind: "auth_gate",
              agent_tab_id: 2,
            },
          },
        ],
        "r",
      ),
    ).toEqual([]);
  });

  it("resolves tab from parent update in same patch", () => {
    const parks = authGateParksFromOps(
      [
        {
          op: "add",
          item: {
            id: "y1",
            column: "you",
            park_kind: "auth_gate",
            parent_id: "a1",
          },
        },
        {
          op: "update",
          item: { id: "a1", column: "agent", agent_tab_id: 88, status: "awaiting_human" },
        },
      ],
      "r2",
    );
    expect(parks).toHaveLength(1);
    expect(parks[0].agentTabId).toBe(88);
  });
});
