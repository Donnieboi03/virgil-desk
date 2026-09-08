import { describe, expect, it } from "vitest";
import { childChecklist, itemsForColumn } from "./panelBoard.js";

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
