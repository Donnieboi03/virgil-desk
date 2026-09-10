import { describe, expect, it } from "vitest";
import {
  childChecklist,
  itemsForColumn,
  groupsForFollowColumn,
  followGroupShouldOpen,
  openYouParkUnder,
  agentRunButtonLabel,
  shouldRevealAgentTab,
} from "./panelBoard.js";

describe("itemsForColumn", () => {
  const items = [
    { id: "p1", title: "Parent" },
    { id: "c1", title: "Child", parent_id: "p1" },
    { id: "p2", title: "Other" },
  ];

  it("agent column shows roots only", () => {
    expect(itemsForColumn("agent", items).map((i) => i.id)).toEqual(["p1", "p2"]);
  });

  it("you/waiting show all including children", () => {
    expect(itemsForColumn("you", items).map((i) => i.id)).toEqual(["p1", "c1", "p2"]);
  });
});

describe("childChecklist", () => {
  it("lists children under parent", () => {
    const items = [
      { id: "p1" },
      { id: "c1", parent_id: "p1", status: "proposed" },
      { id: "c2", parent_id: "p1", status: "done" },
      { id: "x", parent_id: "other" },
    ];
    expect(childChecklist(items, "p1").map((i) => i.id)).toEqual(["c1", "c2"]);
  });
});

describe("groupsForFollowColumn", () => {
  it("nests you children under agent parent title", () => {
    const all = [
      { id: "agent1", title: "Western Digital questions", column: "agent" },
      {
        id: "you1",
        title: "Complete questionnaire",
        parent_id: "agent1",
        column: "you",
        status: "proposed",
      },
      { id: "you_root", title: "Standalone review", column: "you" },
    ];
    const you = all.filter((i) => i.column === "you");
    const { roots, groups } = groupsForFollowColumn(you, all);
    expect(roots.map((r) => r.id)).toEqual(["you_root"]);
    expect(groups).toHaveLength(1);
    expect(groups[0].parentTitle).toBe("Western Digital questions");
    expect(groups[0].children.map((c) => c.id)).toEqual(["you1"]);
    expect(followGroupShouldOpen(groups[0].children)).toBe(true);
  });

  it("closes group when all children done", () => {
    expect(
      followGroupShouldOpen([{ status: "done" }, { status: "denied" }]),
    ).toBe(false);
  });
});

describe("openYouParkUnder + agentRunButtonLabel", () => {
  it("finds open auth_gate You under parent", () => {
    const items = [
      {
        id: "y1",
        parent_id: "a1",
        column: "you",
        park_kind: "auth_gate",
        status: "proposed",
      },
      {
        id: "y2",
        parent_id: "a1",
        column: "you",
        park_kind: "auth_gate",
        status: "done",
      },
    ];
    expect(openYouParkUnder("a1", items)?.id).toBe("y1");
    expect(openYouParkUnder("other", items)).toBeNull();
  });

  it("labels Resume when resume_ready or open You park", () => {
    expect(agentRunButtonLabel({ status: "proposed", resume_ready: true })).toBe(
      "Resume agent",
    );
    expect(
      agentRunButtonLabel({ status: "failed" }, true),
    ).toBe("Resume agent");
    expect(agentRunButtonLabel({ status: "failed" }, false)).toBe("Retry agent");
    expect(agentRunButtonLabel({ status: "proposed" }, false)).toBe("Run agent");
  });
});

describe("shouldRevealAgentTab", () => {
  it("re-exports auth_gate tab reveal", () => {
    expect(shouldRevealAgentTab({ park_kind: "auth_gate", agent_tab_id: 3 })).toBe(
      true,
    );
  });
});
