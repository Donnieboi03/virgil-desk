import { describe, expect, it } from "vitest";
import {
  childChecklist,
  itemsForColumn,
  groupsForFollowColumn,
  followGroupShouldOpen,
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
